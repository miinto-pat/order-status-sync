import json
import os
import tempfile
import threading
import traceback
import zipfile

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, login_user, logout_user, current_user, UserMixin

from constants.Constants import COUNTRY_CODES_AND_CAMPAIGNS
from main import main, logger
from utils import CommonUtils
from utils.CommonUtils import common_utils
from google.cloud import secretmanager
from flask import current_app

bp = Blueprint('bp', __name__)


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
              "market_stats": {},
              "zip_path": None,
              "csv_paths": {}
              }


@bp.route("/download-csv")
def download_csv():
    csv_path = current_app.config.get("LAST_CSV_PATH")
    if not csv_path or not os.path.exists(csv_path):
        return {"error": "CSV not found"}, 404

    return send_file(
        csv_path,
        as_attachment=True,
        download_name=os.path.basename(csv_path),
        mimetype="text/csv"
    )


@bp.route("/download-zip")
def download_zip():
    zip_path = bot_status.get("zip_path")
    if not zip_path or not os.path.exists(zip_path):
        return {"error": "ZIP not found"}, 404

    return send_file(
        zip_path,
        as_attachment=True,
        download_name="impact_results.zip",
        mimetype="application/zip"
    )


from google.cloud import storage


@bp.route("/get-zip-url")
def get_zip_url():
    zip_path = bot_status.get("zip_path")
    if not zip_path or not os.path.exists(zip_path):
        return jsonify({"error": "ZIP not ready"}), 404

    client = storage.Client()
    bucket_name = "impact-bot-temp-files"
    bucket = client.bucket(bucket_name)
    blob_name = os.path.basename(zip_path)
    blob = bucket.blob(blob_name)

    blob.upload_from_filename(zip_path)

    url = blob.generate_signed_url(expiration=3600)
    return jsonify({"url": url})


def run_bot_thread(start_date=None, end_date=None, markets=None):
    global bot_status

    bot_status.update({
        "running": True,
        "message": "Bot started...",
        "status": "started",
        "market_stats": {},
        "not_processed": [],
        "actions_by_state": {},
    })

    try:
        bot = main()
        data = common_utils.load_config()
        all_campaign_ids = data.get("campaign_ids", [])
        not_processed_all = []

        if markets:
            selected_ids = [int(m) for m in markets]
            campaign_ids = [cid for cid in all_campaign_ids if cid in selected_ids]
        else:
            campaign_ids = all_campaign_ids  # Fallback to all

        for campaign_id in campaign_ids:
            market = COUNTRY_CODES_AND_CAMPAIGNS.get(campaign_id, f"Unknown-{campaign_id}")
            bot_status["message"] = f"Processing market: {market}..."

            try:
                # ✅ Process one market
                result = bot.process_single_market(campaign_id, market, start_date, end_date)
                stats = result["stats"]
                not_processed = result["not_processed"]
                actions_by_state = result.get("actions_by_state", {})
                allowed_states_processed = {"OTHER", "ORDER_UPDATE", "ITEM_RETURNED"}

                processed_csv_path = CommonUtils.common_utils.create_market_csv(market, actions_by_state,
                                                                                allowed_states_processed, "processed")
                allowed_states_not_processed = {"Not_Processed"}
                not_processed_csv_path = CommonUtils.common_utils.create_market_csv(market, actions_by_state,
                                                                                    allowed_states_not_processed,
                                                                                    "not_processed")

                bot_status.setdefault("csv_paths", {})
                bot_status["csv_paths"][f"{market}_processed"] = processed_csv_path
                bot_status["csv_paths"][f"{market}_not_processed"] = not_processed_csv_path

                # ✅ Save results
                bot_status["market_stats"][market] = {
                    k: (v if v is not None else 0) for k, v in stats.items()
                }
                not_processed_all.extend(not_processed)
                bot_status["not_processed"] = not_processed_all
                bot_status["message"] = f"✅ Finished market: {market}"

            except Exception as e:
                # ⚠️ Handle market-level error but continue
                logger.exception(f"Error while processing market {market}: {e}")

                bot_status["market_stats"][market] = {
                    "total_actions": 0,
                    "OTHER": 0,
                    "ITEM_RETURNED": 0,
                    "ORDER_UPDATE": 0,
                    "Not_Processed": 0,
                    "error": str(e),
                }

                not_processed_all.append({
                    "market": market,
                    "action_id": "N/A",
                    "error": str(e),
                })
                bot_status["actions_by_state"][market] = {}

                bot_status["not_processed"] = not_processed_all
                bot_status["message"] = f"⚠️ Failed market: {market}, continuing..."
                continue

        csv_paths = bot_status.get("csv_paths", {})

        if csv_paths:
            # Create temp ZIP file
            zip_fd, zip_path = tempfile.mkstemp(suffix=".zip")
            os.close(zip_fd)

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
                for key, csv_path in csv_paths.items():
                    if csv_path and os.path.exists(csv_path):
                        zipf.write(
                            csv_path,
                            arcname=os.path.basename(csv_path)
                        )

            bot_status["zip_path"] = zip_path
            print(f"zip path: {zip_path}")

        # ✅ If all markets processed (even if some failed)
        bot_status["status"] = "finished"
        bot_status["message"] = f"✅ Bot finished. {len(campaign_ids)} market(s) processed."
        bot_status["running"] = False


    except Exception as e:
        # ❌ Global setup error
        logger.exception("Bot failed during setup or initialization")
        msg = str(e)
        if "400" in msg or "invalid value" in msg:
            msg = "Error while retrieving actions — invalid campaign ID configuration."
        elif "timeout" in msg.lower():
            msg = "Error while retrieving actions — request timed out."
        elif "unauthorized" in msg.lower():
            msg = "Error while retrieving actions — invalid credentials."
        bot_status.update({
            "message": msg,
            "status": "error",
            "market_stats": {},
            "not_processed": [],
        })

    finally:
        pass


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
    try:
        data = request.get_json()
        start_date = data.get("start_date")
        end_date = data.get("end_date")
        markets = data.get("markets", [])

        if not markets:
            return jsonify({"status": "error", "message": "No markets selected"}), 400

        if not bot_status["running"]:
            thread = threading.Thread(target=run_bot_thread, args=(start_date, end_date, markets))
            thread.start()
            return jsonify(
                {"message": f"Running bot for markets: {markets} from {start_date} to {end_date}", "status": "started"})
        else:
            return jsonify({"message": "Bot is already running", "status": "running"})

    except Exception as e:
        tb = traceback.format_exc()
        print(tb)  # print in server console
        return jsonify({"message": f"Error: {e}", "status": "error", "trace": tb})


@bp.route("/bot-status")
@login_required
def bot_status_endpoint():
    # return jsonify(bot_status)
    return jsonify({
        "status": bot_status.get("status"),
        "message": bot_status.get("message"),
        "market_stats": bot_status.get("market_stats"),
        "not_processed": bot_status.get("not_processed"),
        "zip_path": bot_status.get("zip_path")  # add this
    })
