import json
import os
import threading
import traceback

from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, login_user, logout_user, current_user, UserMixin
from google.auth.exceptions import DefaultCredentialsError

from constants.Constants import COUNTRY_CODES_AND_CAMPAIGNS
from main import main, logger
from utils.CommonUtils import common_utils
from google.cloud import secretmanager

bp = Blueprint('bp', __name__)
DEFAULT_USER = {
    "username": "AV-Miinto",
    "password": ".)k&J9&4Rf0A"
}

def load_config_from_secret(secret_name: str = "impact_secret_json"):
    project_id = "373688639022"
    secret_path = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    project_id = "373688639022"
    secret_path = f"projects/{project_id}/secrets/{secret_name}/versions/latest"

    try:
        # Try to create a GCP Secret Manager client
        client = secretmanager.SecretManagerServiceClient()
        response = client.access_secret_version(request={"name": secret_path})
        secret_str = response.payload.data.decode("UTF-8")
        logger.info(f"✅ Loaded config from Google Secret Manager: {secret_name}")
        return json.loads(secret_str)

    except (DefaultCredentialsError, Exception) as e:
        # Log a warning but DO NOT crash
        logger.warning(f"⚠️ Cannot load secret '{secret_name}' from Google Secret Manager: {e}")
        logger.warning("➡️ Falling back to default local credentials.")

        # Provide fallback config
        return {
            "USERS": {
                DEFAULT_USER["username"]: DEFAULT_USER["password"]
            }
        }


# ✅ Load once at import time
CONFIG = load_config_from_secret()
USERS = CONFIG.get("USERS", {})


class User(UserMixin):

    def __init__(self, id):
        self.id = id


# Global bot status
bot_status = {"running": False, "message": "Idle", "status": "idle", "market_stats": {}}


def run_bot_thread(start_date=None, end_date=None, markets=None):
    global bot_status

    bot_status.update({
        "running": True,
        "message": "Bot started...",
        "status": "started",
        "market_stats": {},
        "not_processed": [],
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
                    "Not_Modified": 0,
                    "Not_Processed": 0,
                    "error": str(e),
                }

                not_processed_all.append({
                    "market": market,
                    "action_id": "N/A",
                    "error": str(e),
                })
                bot_status["not_processed"] = not_processed_all
                bot_status["message"] = f"⚠️ Failed market: {market}, continuing..."
                continue

        # ✅ If all markets processed (even if some failed)
        bot_status["status"] = "finished"
        bot_status["message"] = f"✅ Bot finished. {len(campaign_ids)} market(s) processed."

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
        # ✅ Always run this even on crash
        if bot_status["status"] not in ("finished", "error"):
            bot_status["status"] = "error"
            bot_status["message"] = "Bot stopped unexpectedly. Partial results available."

        bot_status["running"] = False


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
            logger.warning(f"⚠️ SecretManager unavailable: {e}. Using default user instead.")
            # fallback config structure
            return {
                "USERS": {
                    DEFAULT_USER["username"]: DEFAULT_USER["password"]
                }
            }


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
    return jsonify(bot_status)
