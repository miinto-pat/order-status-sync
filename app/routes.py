import threading
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, login_user, logout_user, current_user, UserMixin
from main import main

bp = Blueprint('bp', __name__)  # ONLY once!

# Minimal user store
USERS = {"admin": "password123"}

class User(UserMixin):
    def __init__(self, id):
        self.id = id

# Global bot status
bot_status = {"running": False, "message": "Idle", "status": "idle"}

def run_bot_thread():
    global bot_status
    bot_status["running"] = True
    bot_status["message"] = "Bot started..."
    bot_status["status"] = "started"
    try:
        bot = main()
        bot.main()
        bot_status["message"] = "Bot finished successfully!"
        bot_status["status"] = "finished"
    except Exception as e:
        bot_status["message"] = f"Error: {e}"
        bot_status["status"] = "error"
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
    if not bot_status["running"]:
        thread = threading.Thread(target=run_bot_thread)
        thread.start()
        return jsonify({"message": "Bot started...", "status": "started"})
    else:
        return jsonify({"message": "Bot is already running", "status": "running"})

@bp.route("/bot-status")
@login_required
def bot_status_endpoint():
    return jsonify(bot_status)
