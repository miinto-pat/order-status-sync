from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, login_user, logout_user, current_user, UserMixin
from main import main

bp = Blueprint('bp', __name__)

# Minimal user store
USERS = {"admin": "password123"}

class User(UserMixin):
    def __init__(self, id):
        self.id = id

# Flask-Login setup happens in app/__init__.py or main Flask file

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
    try:
        bot = main()
        bot.main()
        flash("Bot executed successfully!")
    except Exception as e:
        flash(f"Error: {e}")
    return redirect(url_for("bp.dashboard"))
