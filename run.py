import os

from app import create_app
from flask_login import LoginManager

app = create_app()

# Setup Flask-Login
login_manager = LoginManager()
login_manager.login_view = "bp.login"
login_manager.init_app(app)

@login_manager.user_loader
def load_user(user_id):
    from app.routes import USERS, User
    if user_id in USERS:
        return User(user_id)
    return None

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port, debug=True)
