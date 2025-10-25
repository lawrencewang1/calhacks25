from flask import Flask, send_from_directory, abort
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
app = Flask(__name__, static_folder="static", static_url_path="/static")
app.url_map.strict_slashes = False

# PRODUCTION TODO: Restrict CORS to specific origins instead of allowing all
# Example: CORS(app, supports_credentials=True, origins=["https://yourdomain.com"])
CORS(app, supports_credentials=True)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chatbot.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# PRODUCTION TODO: Set a strong JWT_SECRET_KEY in your .env file
# Never use the default "hithere" in production - generate a secure random key
# Example: openssl rand -hex 32
app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET_KEY", "hithere")

db.init_app(app)
jwt = JWTManager(app)
app.register_blueprint(auth_bp, url_prefix="/api/auth")

# PRODUCTION TODO: Restrict CORS origins for WebSocket connections
# Example: socketio = SocketIO(app, cors_allowed_origins=["https://yourdomain.com"])
socketio = SocketIO(app, cors_allowed_origins="*", manage_session=False)
register_socketio(socketio, app)
for rule in app.url_map.iter_rules():
    print(f"{rule.rule:35s}  {','.join(sorted(rule.methods))}  -> {rule.endpoint}")

@app.route("/")
def index():
    # return send_from_directory(app.static_folder, "testWithLogin.html")
    return send_from_directory(app.static_folder, 'login.html')

@app.route("/<path:path>", methods=["GET"], endpoint="spa_fallback")
def spa_fallback(path):
    if path.startswith("api/"):
        abort(404)   # never return HTML for API paths
    full = os.path.join(app.static_folder, path)
    if os.path.isfile(full):
        return send_from_directory(app.static_folder, path)
    return send_from_directory(app.static_folder, "testWithLogin.html")

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    # PRODUCTION TODO: Set debug=False and remove allow_unsafe_werkzeug=True
    # Use a production WSGI server like gunicorn with eventlet/gevent
    # Example: gunicorn --worker-class eventlet -w 1 app:app
    socketio.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 5000)), debug=True,
                 allow_unsafe_werkzeug=True)
