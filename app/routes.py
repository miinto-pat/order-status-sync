import json
import os
import tempfile
import threading
import time
import traceback
import uuid
import zipfile

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, login_user, logout_user, current_user, UserMixin

import utils
from constants.Constants import COUNTRY_CODES_AND_CAMPAIGNS
from clients.ImpactClient import ImpactClient
from clients.ImpactSFTPClient import ImpactSFTPClient, config_from_app_config
from main import main, logger
from utils import CommonUtils
from utils.CommonUtils import common_utils
from utils.ImpactBatch import (
    batch_rows_from_actions_by_state,
    create_batch_file_path,
    create_market_batch_zip_file_path,
    write_batch_csv,
    write_market_batch_zip,
)
from utils.ProgressTracker import ProgressTracker
from utils.RunTimer import RunTimer
from google.cloud import secretmanager
from flask import current_app

bp = Blueprint('bp', __name__)
from threading import Lock
bot_status_lock = Lock()


def load_config_from_secret(secret_name: str = "impact_secret_json"):
    """
        Tries to load credentials/config from Google Secret Manager.
        Falls back to DEFAULT_USER if unavailable.
        """
    project_id = "373688639022"
    secret_path = f"projects/{project_id}/secrets/{secret_name}/versions/latest"

    try:
        client = secretmanager.SecretManagerServiceClient()
        response = client.access_secret_version(request={"name": secret_path})
        secret_str = response.payload.data.decode("UTF-8")
        return json.loads(secret_str)
    except Exception as e:
        logger.warning(f"SecretManager unavailable: {e}. Using default user instead.")
        # fallback config structure
        try:
            local_config_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "config.json"
            )
            with open(local_config_path, "r", encoding="utf-8-sig") as f:
                local_config = json.load(f)
                logger.info(f"Loaded fallback config from {local_config_path}")
                return local_config
        except Exception as e2:
            logger.error(f"Failed to load fallback config file: {e2}")
            # Last-resort fallback (hardcoded user)
            return {
                "USERS": {
                    "AV-Miinto": ".)k&J9&4Rf0A"
                }
            }


# ✅ Load once at import time
CONFIG = load_config_from_secret()
USERS = CONFIG.get("USERS", {})


class User(UserMixin):

    def __init__(self, id):
        self.id = id


# Global bot status
bot_status = {"running": False,
              "message": "Idle",
              "status": "idle",
              "current_market": None,
              "market_stats": {},
              "progress": ProgressTracker([]).snapshot(),
              "sftp_batch": {},
              "zip_path": None,
              "csv_paths": {}
              }


from google.cloud import storage


@bp.route("/get-zip-url")
def get_zip_url():
    blob_name = bot_status.get("zip_blob_name")
    if not blob_name:
        return jsonify({"error": "ZIP not ready"}), 404

    CONFIG = load_config_from_secret()
    GCP_SERVICE_ACCOUNT = CONFIG.get("GCP_SERVICE_ACCOUNT", {})

    if not GCP_SERVICE_ACCOUNT:
        raise RuntimeError("GCP_SERVICE_ACCOUNT not found in Secret Manager config")

    client = storage.Client.from_service_account_info(GCP_SERVICE_ACCOUNT)
    # client = storage.Client()
    bucket_name = "impact-bot-temp-files"
    bucket = client.bucket(bucket_name)
    for blob in bucket.list_blobs():
        print(blob.name)
    blob = bucket.blob(blob_name)

    url = blob.generate_signed_url(
        expiration=3600,
        version="v4",
        response_disposition=f'attachment; filename="{blob_name}"'
    )
    return jsonify({"url": url})


@bp.route("/download-sftp-batch")
@login_required
def download_sftp_batch():
    with bot_status_lock:
        batch = bot_status.get("sftp_batch") or {}
        path = batch.get("file_path")
        file_name = batch.get("file_name") or "impact_batch.csv"

    if not path or not os.path.exists(path):
        return jsonify({"error": "SFTP batch file is not ready"}), 404

    return send_file(path, as_attachment=True, download_name=file_name)


@bp.route("/download-sftp-market-batches")
@login_required
def download_sftp_market_batches():
    with bot_status_lock:
        batch = bot_status.get("sftp_batch") or {}
        path = batch.get("market_zip_path")
        file_name = batch.get("market_zip_file_name") or "impact_batch_by_market.zip"

    if not path or not os.path.exists(path):
        return jsonify({"error": "SFTP market batch ZIP is not ready"}), 404

    return send_file(path, as_attachment=True, download_name=file_name)


import uuid


def _new_sftp_batch_status(enabled=False):
    return {
        "enabled": enabled,
        "status": "disabled" if not enabled else "pending",
        "message": "SFTP batch mode is disabled." if not enabled else "SFTP batch pending.",
        "file_available": False,
        "file_name": None,
        "market_zip_available": False,
        "market_zip_file_name": None,
        "market_files": {},
        "row_count": 0,
        "uploaded": False,
        "remote_path": None,
        "submission": None,
        "errors": [],
    }


def _poll_ftp_submission(impact_client, file_name, timeout_seconds=900, interval_seconds=30):
    deadline = time.time() + max(0, int(timeout_seconds))
    interval_seconds = max(1, int(interval_seconds))

    while True:
        submissions = impact_client.list_ftp_submissions()
        matching = [
            item for item in submissions
            if item.get("FileName") == file_name
        ]
        if matching:
            submission = matching[0]
            status = submission.get("Status")
            if status == "Complete":
                errors = []
                errors_uri = submission.get("ErrorsUri")
                if errors_uri and int(submission.get("TotalErrors") or 0) > 0:
                    errors = impact_client.list_ftp_submission_errors(errors_uri)
                return submission, errors

        if time.time() >= deadline:
            return None, []

        time.sleep(interval_seconds)


# -----------------------------
# RUN BOT THREAD
# -----------------------------
def run_bot_thread(start_date=None, end_date=None, markets=None, run_id=None, impact_delivery_mode="rest"):
    """
    Thread function that runs the bot for selected markets.
    run_id is unique for this run to avoid conflicts with previous runs.
    """
    global bot_status
    timer = RunTimer(
        run_id=run_id,
        context={
            "start_date": start_date,
            "end_date": end_date,
            "markets": markets or [],
            "impact_delivery_mode": impact_delivery_mode,
        },
    )
    progress_tracker = ProgressTracker(markets or [])
    sftp_batch_status = _new_sftp_batch_status(impact_delivery_mode == "batch_sftp")

    def publish_progress():
        bot_status["progress"] = progress_tracker.snapshot()

    def handle_market_progress(event):
        market = event.get("market")
        event_name = event.get("event")

        with bot_status_lock:
            if event_name == "actions_loaded":
                progress_tracker.actions_loaded(market, event.get("total_actions", 0))
            elif event_name == "action_completed":
                progress_tracker.action_completed(
                    market,
                    event.get("processed_actions", 0),
                    event.get("stats", {}),
                )
            elif event_name == "market_finished":
                progress_tracker.finish_market(market, event.get("stats", {}))
            publish_progress()

    with bot_status_lock:
        progress_tracker.start_run()
        # Initialize bot_status for this run
        bot_status.update({
            "running": True,
            "status": "running",
            "message": "Bot started...",
            "current_market": None,
            "market_stats": {},
            "not_processed": [],
            "actions_by_state": {},
            "csv_paths": {},
            "sftp_batch": sftp_batch_status,
            "zip_blob_name": None,
            "zip_path": None,
            "run_id": run_id,
            "last_run_markets": markets or []
        })
        publish_progress()

    try:
        bot = main()
        with timer.measure("run.config_load"):
            data = common_utils.load_config()
        all_campaign_ids = data.get("campaign_ids", [])

        # Map frontend market codes to numeric campaign IDs
        if markets:
            campaign_ids = [
                cid for cid, market_code in COUNTRY_CODES_AND_CAMPAIGNS.items()
                if market_code in markets
            ]
        else:
            campaign_ids = all_campaign_ids

        if not markets:
            selected_market_codes = [
                COUNTRY_CODES_AND_CAMPAIGNS.get(cid, f"Unknown-{cid}")
                for cid in campaign_ids
            ]
            progress_tracker = ProgressTracker(selected_market_codes)
            with bot_status_lock:
                progress_tracker.start_run()
                publish_progress()

        not_processed_all = []
        impact_batch_rows = []

        for campaign_id in campaign_ids:
            market = COUNTRY_CODES_AND_CAMPAIGNS.get(campaign_id, f"Unknown-{campaign_id}")

            with bot_status_lock:
                progress_tracker.start_market(market)
                bot_status["current_market"] = market
                bot_status["message"] = f"Processing market: {market}..."
                bot_status["status"] = "running"
                publish_progress()

            try:
                # Process one market
                with timer.measure("market.process_single_market", campaign_id=campaign_id, market=market):
                    result = bot.process_single_market(
                        campaign_id,
                        market,
                        start_date,
                        end_date,
                        timer=timer,
                        progress_callback=handle_market_progress,
                        impact_delivery_mode=impact_delivery_mode,
                    )
                stats = result["stats"]
                not_processed = result["not_processed"]
                actions_by_state = result.get("actions_by_state", {})
                if impact_delivery_mode == "batch_sftp":
                    impact_batch_rows.extend(batch_rows_from_actions_by_state(market, actions_by_state))

                # Create CSVs
                with timer.measure("csv.create_market_csv", campaign_id=campaign_id, market=market, target_state="processed"):
                    processed_csv_path = CommonUtils.common_utils.create_market_csv(
                        market, actions_by_state, {"OTHER", "ORDER_UPDATE", "ITEM_RETURNED"}, "processed"
                    )
                with timer.measure("csv.create_market_csv", campaign_id=campaign_id, market=market, target_state="not_processed"):
                    not_processed_csv_path = CommonUtils.common_utils.create_market_csv(
                        market, actions_by_state, {"Not_Processed"}, "not_processed"
                    )

                with bot_status_lock:
                    bot_status.setdefault("csv_paths", {})
                    bot_status["csv_paths"][f"{market}_processed"] = processed_csv_path
                    bot_status["csv_paths"][f"{market}_not_processed"] = not_processed_csv_path

                    # Save stats
                    bot_status["market_stats"][market] = {k: v or 0 for k, v in stats.items()}
                    not_processed_all.extend(not_processed)
                    bot_status["not_processed"] = not_processed_all
                    progress_tracker.finish_market(market, stats)
                    publish_progress()

            except Exception as e:
                logger.exception(f"Error processing market {market}: {e}")
                with bot_status_lock:
                    bot_status["market_stats"][market] = {
                        "total_actions": 0,
                        "OTHER": 0,
                        "ITEM_RETURNED": 0,
                        "ORDER_UPDATE": 0,
                        "Not_Processed": 0,
                        "error": str(e),
                    }
                    not_processed_all.append({"market": market, "action_id": "N/A", "error": str(e)})
                    bot_status["actions_by_state"][market] = {}
                    bot_status["not_processed"] = not_processed_all
                    progress_tracker.fail_market(market, e)
                    publish_progress()

        if impact_delivery_mode == "batch_sftp":
            with bot_status_lock:
                bot_status["sftp_batch"].update({
                    "status": "creating_file",
                    "message": "Creating Impact batch CSV...",
                    "row_count": len(impact_batch_rows),
                })

            if impact_batch_rows:
                with timer.measure("impact_batch.create_csv", row_count=len(impact_batch_rows)):
                    batch_path = create_batch_file_path(run_id, markets or selected_market_codes)
                    write_batch_csv(batch_path, impact_batch_rows)
                    market_zip_path = create_market_batch_zip_file_path(run_id, markets or selected_market_codes)
                    market_files = write_market_batch_zip(market_zip_path, impact_batch_rows, run_id=run_id)

                batch_file_name = os.path.basename(batch_path)
                market_zip_file_name = os.path.basename(market_zip_path)
                with bot_status_lock:
                    bot_status.setdefault("csv_paths", {})
                    bot_status["csv_paths"]["impact_sftp_batch"] = batch_path
                    bot_status["sftp_batch"].update({
                        "status": "file_ready",
                        "message": "Impact batch CSV is ready.",
                        "file_available": True,
                        "file_path": batch_path,
                        "file_name": batch_file_name,
                        "market_zip_available": True,
                        "market_zip_path": market_zip_path,
                        "market_zip_file_name": market_zip_file_name,
                        "market_files": market_files,
                        "row_count": len(impact_batch_rows),
                    })

                sftp_config = config_from_app_config(data)
                if sftp_config:
                    try:
                        with bot_status_lock:
                            bot_status["sftp_batch"].update({
                                "status": "uploading",
                                "message": "Uploading Impact batch CSV through SFTP...",
                            })

                        with timer.measure("impact_batch.sftp_upload", row_count=len(impact_batch_rows)):
                            remote_path = ImpactSFTPClient(sftp_config).upload_file(batch_path)

                        with bot_status_lock:
                            bot_status["sftp_batch"].update({
                                "status": "uploaded",
                                "message": "Impact batch CSV uploaded. Waiting for Impact confirmation...",
                                "uploaded": True,
                                "remote_path": remote_path,
                            })

                        first_market = (markets or selected_market_codes or [None])[0]
                        if first_market:
                            timeout_seconds = data.get("impact_sftp_poll_timeout_seconds", 900)
                            interval_seconds = data.get("impact_sftp_poll_interval_seconds", 30)
                            with timer.measure("impact_batch.poll_submission", file_name=batch_file_name):
                                submission, errors = _poll_ftp_submission(
                                    ImpactClient(data, market=first_market),
                                    batch_file_name,
                                    timeout_seconds=timeout_seconds,
                                    interval_seconds=interval_seconds,
                                )

                            with bot_status_lock:
                                if submission:
                                    total_errors = int(submission.get("TotalErrors") or 0)
                                    bot_status["sftp_batch"].update({
                                        "status": "complete_with_errors" if total_errors else "complete",
                                        "message": (
                                            f"Impact processed the batch with {total_errors} error(s)."
                                            if total_errors else
                                            "Impact processed the batch successfully."
                                        ),
                                        "submission": submission,
                                        "errors": errors,
                                    })
                                else:
                                    bot_status["sftp_batch"].update({
                                        "status": "uploaded_waiting_confirmation",
                                        "message": "Uploaded to SFTP, but Impact submission was not visible before polling timed out.",
                                    })
                    except Exception as e:
                        logger.exception("Impact SFTP upload or confirmation failed")
                        with bot_status_lock:
                            bot_status["sftp_batch"].update({
                                "status": "upload_error",
                                "message": str(e),
                                "uploaded": False,
                            })
                else:
                    with bot_status_lock:
                        bot_status["sftp_batch"].update({
                            "status": "manual_upload_available",
                            "message": "SFTP credentials are not configured. Download the combined CSV or the per-market ZIP and upload manually.",
                        })
            else:
                with bot_status_lock:
                    bot_status["sftp_batch"].update({
                        "status": "empty",
                        "message": "No Impact changes were prepared for SFTP batch upload.",
                        "file_available": False,
                        "row_count": 0,
                    })

        # After all markets, generate ZIP
        csv_paths = bot_status.get("csv_paths", {})
        if csv_paths:
            with bot_status_lock:
                progress_tracker.start_zip()
                publish_progress()
            with timer.measure("zip.create", file_count=len(csv_paths)):
                zip_fd, zip_path = tempfile.mkstemp(suffix=".zip")
                os.close(zip_fd)

                with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                    for key, csv_path in csv_paths.items():
                        if csv_path and os.path.exists(csv_path):
                            zipf.write(csv_path, arcname=os.path.basename(csv_path))

            with timer.measure("gcs.upload_zip"):
                blob_name = utils.CommonUtils.common_utils.upload_zip_to_gcs(zip_path)
            with bot_status_lock:
                bot_status["zip_blob_name"] = blob_name
                bot_status["zip_path"] = None

        # Mark finished
        with bot_status_lock:
            progress_tracker.finish_run(f"Bot finished. {len(campaign_ids)} market(s) processed.")
            bot_status.update({
                "status": "finished",
                "running": False,
                "current_market": None,
                "message": f"✅ Bot finished. {len(campaign_ids)} market(s) processed."
            })

            publish_progress()

    except Exception as e:
        logger.exception("Global bot error")
        with bot_status_lock:
            progress_tracker.fail_run(str(e))
            bot_status.update({
                "status": "error",
                "running": False,
                "current_market": None,
                "message": str(e),
                "market_stats": {},
                "not_processed": [],
            })
            publish_progress()
    finally:
        timer.log_summary(logger)



# Routes
@bp.route("/login", methods=["GET", "POST"])
def login():
    config = load_config_from_secret("impact_secret_json")
    USERS = config.get("USERS", {})

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if USERS.get(username) == password:
            user = User(username)
            login_user(user)
            return redirect(url_for("bp.dashboard"))

        flash("Invalid credentials", "danger")

    return render_template("login.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("bp.login"))


@bp.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html", markets=COUNTRY_CODES_AND_CAMPAIGNS)

@bp.route("/run-bot", methods=["POST"])
@login_required
def run_bot():
    global bot_status

    data = request.get_json()
    start_date = data.get("start_date")
    end_date = data.get("end_date")
    markets = data.get("markets", [])
    impact_delivery_mode = data.get("impact_delivery_mode", "rest")

    if not markets:
        return jsonify({"status": "error", "message": "No markets selected"}), 400

    with bot_status_lock:
        if bot_status.get("running"):
            return jsonify({"status": "running", "message": "Bot is already running"})

        # Generate a unique run_id for this run
        run_id = str(uuid.uuid4())

    # Start bot thread
    thread = threading.Thread(
        target=run_bot_thread,
        args=(start_date, end_date, markets, run_id, impact_delivery_mode),
        daemon=True
    )
    thread.start()

    return jsonify({
        "status": "started",
        "message": f"Running bot for markets: {markets}",
        "run_id": run_id
    })


@bp.route("/bot-status")
@login_required
def bot_status_endpoint():
    with bot_status_lock:
        sftp_batch = dict(bot_status.get("sftp_batch") or {})
        sftp_batch.pop("file_path", None)
        sftp_batch.pop("market_zip_path", None)
        return jsonify({
            "status": bot_status.get("status"),
            "message": bot_status.get("message"),
            "current_market": bot_status.get("current_market"),
            "market_stats": bot_status.get("market_stats"),
            "not_processed": bot_status.get("not_processed"),
            "progress": bot_status.get("progress"),
            "sftp_batch": sftp_batch,
            "zip_blob_name": bot_status.get("zip_blob_name"),
            "run_id": bot_status.get("run_id")
        })
