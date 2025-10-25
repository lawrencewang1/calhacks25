"""
Flask extensions initialization.

This module initializes all Flask extensions used by the application.
Extensions are created here and initialized in the app factory.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from flask_socketio import SocketIO

# Initialize extensions
# These will be initialized in the application factory
db = SQLAlchemy()
jwt = JWTManager()
cors = CORS()
socketio = SocketIO()


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

    # Initialize SocketIO
    socketio.init_app(
        app,
        cors_allowed_origins=app.config.get("SOCKETIO_CORS_ALLOWED_ORIGINS", "*"),
        manage_session=app.config.get("SOCKETIO_MANAGE_SESSION", False)
    )

    # Create database tables
    with app.app_context():
        db.create_all()
