"""
Flask extensions initialization.

This module initializes all Flask extensions used by the application.
Extensions are created here and initialized in the app factory.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_socketio import SocketIO
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Initialize extensions
# These will be initialized in the application factory
db = SQLAlchemy()
jwt = JWTManager()
cors = CORS()
socketio = SocketIO()
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
    storage_uri="memory://"
)


def init_extensions(app):
    """
    Initialize Flask extensions with the application instance.

    Args:
        app: Flask application instance

    Returns:
        None
    """
    # Initialize database
    db.init_app(app)

    # Initialize JWT
    jwt.init_app(app)

    # Initialize CORS
    cors.init_app(app, supports_credentials=True)

    # Initialize rate limiter
    limiter.init_app(app)

    # Initialize SocketIO
    socketio.init_app(
        app,
        cors_allowed_origins=app.config.get("SOCKETIO_CORS_ALLOWED_ORIGINS", "*"),
        manage_session=app.config.get("SOCKETIO_MANAGE_SESSION", False)
    )

    # Create database tables
    with app.app_context():
        db.create_all()
