import threading
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, login_user, logout_user, current_user, UserMixin
from main import main, logger

bp = Blueprint('bp', __name__)  # ONLY once!

# Minimal user store
USERS = {"admin": "password123"}

class User(UserMixin):
    def __init__(self, id):
        self.id = id


# Global bot status
bot_status = {"running": False, "message": "Idle", "status": "idle", "market_stats": {}}


def run_bot_thread(start_date=None, end_date=None):
    global bot_status
    bot_status["running"] = True
    bot_status["message"] = "Bot started..."
    bot_status["status"] = "started"
    bot_status["market_stats"] = {}

    try:
        bot = main()
        raw_stats = bot.main(start_date=start_date, end_date=end_date)

        # ✅ Ensure all stats values are integers, never None
        safe_stats = {}
        for market, stats in raw_stats.items():
            safe_stats[market] = {k: (v if v is not None else 0) for k, v in stats.items()}

        bot_status["market_stats"] = safe_stats
        bot_status["message"] = f"Bot finished with range {start_date} → {end_date}"
        bot_status["status"] = "finished"


    except Exception as e:
        # Keep developer-friendly logs in console
        logger.exception("Bot failed during execution")

        # Set user-friendly message in UI
        user_message = str(e)
        if "400" in user_message or "invalid value" in user_message:
            user_message = "Error while retrieving actions — invalid campaign ID configuration."
        elif "timeout" in user_message.lower():
            user_message = "Error while retrieving actions — request timed out."
        elif "unauthorized" in user_message.lower():
            user_message = "Error while retrieving actions — invalid credentials."

        bot_status["message"] = user_message
        bot_status["status"] = "error"
        bot_status["market_stats"] = {}


    finally:
        bot_status["running"] = False


# Routes
@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        if USERS.get(username) == password:
            user = User(username)
            login_user(user)
            return redirect(url_for("bp.dashboard"))
        flash("Invalid credentials")
    return render_template("login.html")

@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("bp.login"))

@bp.route("/")
@login_required
def dashboard():
    return render_template("dashboard.html")

@bp.route("/run-bot", methods=["POST"])
@login_required
def run_bot():
    global bot_status
    try:
        data = request.get_json()
        start_date = data.get("start_date")
        end_date = data.get("end_date")

        if not bot_status["running"]:
            thread = threading.Thread(target=run_bot_thread, args=(start_date, end_date))
            thread.start()
            return jsonify({"message": f"Bot started from {start_date} to {end_date}", "status": "started"})
        else:
            return jsonify({"message": "Bot is already running", "status": "running"})

    except Exception as e:
        # Return the full error message for debugging
        import traceback
        tb = traceback.format_exc()
        print(tb)  # print in server console
        return jsonify({"message": f"Error: {e}", "status": "error", "trace": tb})

@bp.route("/bot-status")
@login_required
def bot_status_endpoint():
    return jsonify(bot_status)
