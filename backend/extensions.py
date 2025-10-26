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

    # Get CORS origins from config
    # Note: When using credentials, origins must be explicit (not "*")
    cors_origins = app.config.get("CORS_ORIGINS", ["*"])

    # Initialize CORS with explicit configuration
    cors.init_app(
        app,
        resources={r"/*": {
            "origins": cors_origins,
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"],
            "supports_credentials": True
        }}
    )

    # Initialize rate limiter
    limiter.init_app(app)

    # Initialize SocketIO
    # Note: When using credentials, cors_allowed_origins must be explicit (not "*")
    socketio_cors_origins = app.config.get("SOCKETIO_CORS_ALLOWED_ORIGINS", cors_origins)

    # Log CORS configuration for debugging
    app.logger.info("=" * 60)
    app.logger.info("Flask CORS Configuration:")
    app.logger.info(f"  Allowed Origins: {cors_origins}")
    app.logger.info(f"  Methods: GET, POST, PUT, DELETE, OPTIONS")
    app.logger.info(f"  Credentials: True")
    app.logger.info("-" * 60)
    app.logger.info("SocketIO CORS Configuration:")
    app.logger.info(f"  Allowed Origins: {socketio_cors_origins}")
    app.logger.info(f"  Credentials: True")
    app.logger.info("=" * 60)

    socketio.init_app(
        app,
        cors_allowed_origins=socketio_cors_origins,
        cors_credentials=True,  # Allow credentials (cookies, auth headers)
        manage_session=app.config.get("SOCKETIO_MANAGE_SESSION", False),
        logger=app.config.get("DEBUG", False),  # Enable socketio logging in debug mode
        engineio_logger=app.config.get("DEBUG", False),  # Enable engineio logging in debug mode
        # Additional options for Cloudflare tunnel compatibility
        async_mode=None,  # Auto-detect (threading, eventlet, or gevent)
        ping_timeout=60,  # Increase ping timeout for tunnels
        ping_interval=25,  # Send pings more frequently
        # Allow both polling and WebSocket transports
        # Polling works better through Cloudflare tunnels
        allow_upgrades=True,  # Allow upgrading from polling to WebSocket
        http_compression=True  # Enable compression
    )

    # Create database tables
    with app.app_context():
        db.create_all()
