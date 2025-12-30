import json
import os
import tempfile
import threading
import traceback
import uuid
import zipfile

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, login_user, logout_user, current_user, UserMixin

import utils
from constants.Constants import COUNTRY_CODES_AND_CAMPAIGNS
from main import main, logger
from utils import CommonUtils
from utils.CommonUtils import common_utils
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
            with open(local_config_path, "r", encoding="utf-8") as f:
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


import uuid

# -----------------------------
# RUN BOT THREAD
# -----------------------------
def run_bot_thread(start_date=None, end_date=None, markets=None, run_id=None):
    """
    Thread function that runs the bot for selected markets.
    run_id is unique for this run to avoid conflicts with previous runs.
    """
    global bot_status

    with bot_status_lock:
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
            "zip_blob_name": None,
            "zip_path": None,
            "run_id": run_id,
            "last_run_markets": markets or []
        })

    try:
        bot = main()
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

        not_processed_all = []

        for campaign_id in campaign_ids:
            market = COUNTRY_CODES_AND_CAMPAIGNS.get(campaign_id, f"Unknown-{campaign_id}")

            with bot_status_lock:
                bot_status["current_market"] = market
                bot_status["message"] = f"Processing market: {market}..."
                bot_status["status"] = "running"

            try:
                # Process one market
                result = bot.process_single_market(campaign_id, market, start_date, end_date)
                stats = result["stats"]
                not_processed = result["not_processed"]
                actions_by_state = result.get("actions_by_state", {})

                # Create CSVs
                processed_csv_path = CommonUtils.common_utils.create_market_csv(
                    market, actions_by_state, {"OTHER", "ORDER_UPDATE", "ITEM_RETURNED"}, "processed"
                )
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

        # After all markets, generate ZIP
        csv_paths = bot_status.get("csv_paths", {})
        if csv_paths:
            zip_fd, zip_path = tempfile.mkstemp(suffix=".zip")
            os.close(zip_fd)

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for key, csv_path in csv_paths.items():
                    if csv_path and os.path.exists(csv_path):
                        zipf.write(csv_path, arcname=os.path.basename(csv_path))

            blob_name = utils.CommonUtils.common_utils.upload_zip_to_gcs(zip_path)
            with bot_status_lock:
                bot_status["zip_blob_name"] = blob_name
                bot_status["zip_path"] = None

        # Mark finished
        with bot_status_lock:
            bot_status.update({
                "status": "finished",
                "running": False,
                "current_market": None,
                "message": f"✅ Bot finished. {len(campaign_ids)} market(s) processed."
            })

    except Exception as e:
        logger.exception("Global bot error")
        with bot_status_lock:
            bot_status.update({
                "status": "error",
                "running": False,
                "current_market": None,
                "message": str(e),
                "market_stats": {},
                "not_processed": [],
            })



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
        args=(start_date, end_date, markets, run_id),
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
        return jsonify({
            "status": bot_status.get("status"),
            "message": bot_status.get("message"),
            "current_market": bot_status.get("current_market"),
            "market_stats": bot_status.get("market_stats"),
            "not_processed": bot_status.get("not_processed"),
            "zip_blob_name": bot_status.get("zip_blob_name"),
            "run_id": bot_status.get("run_id")
        })
