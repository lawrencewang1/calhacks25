from flask import Flask, abort, send_from_directory   # <-- import this
from database import db
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from routes.auth import auth_bp
from sockets import register_socketio
from flask_socketio import SocketIO
from dotenv import load_dotenv
import os

load_dotenv()

# Tell Flask where your static files live
app = Flask(__name__, static_folder="static", static_url_path="")
CORS(app, supports_credentials=True)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chatbot.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "hithere")

db.init_app(app)
jwt = JWTManager(app)
app.register_blueprint(auth_bp, url_prefix="/api/auth")

socketio = SocketIO(app, cors_allowed_origins="*")
register_socketio(socketio)

@app.route("/")
def index():
    return send_from_directory(app.static_folder, "testWithLogin.html")

@app.route("/<path:path>", methods=["GET"])
def static_proxy(path):
    # Never serve static for API routes
    if path.startswith("api/"):
        abort(404)

    full = os.path.join(app.static_folder, path)
    if os.path.isfile(full):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, "testWithLogin.html")  # same fallback as "/"

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True,
                 allow_unsafe_werkzeug=True)
