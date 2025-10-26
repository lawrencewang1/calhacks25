"""
Backend application package.

This module implements the application factory pattern for creating
Flask application instances with all necessary configuration and extensions.
"""

import os
import logging
from flask import Flask, send_from_directory, abort

from config import get_config
from backend.extensions import db, jwt, cors, socketio, limiter, init_extensions
from backend.routes import auth_bp
from backend.sockets.handlers import register_socketio
from backend.sockets.game_handlers import register_game_handlers
from backend.utils.logging_config import setup_logging

logger = logging.getLogger(__name__)


def create_app(config_name=None):
    """
    Application factory for creating Flask app instances.

    Args:
        config_name: Configuration environment name (development, production, testing)
                    If None, uses FLASK_ENV environment variable

    Returns:
        Flask: Configured Flask application instance
    """
    # Create Flask app
    app = Flask(
        __name__,
        static_folder="../frontend/static",
        template_folder="../frontend/templates"
    )

    # Load configuration
    if config_name is None:
        config_name = os.getenv("FLASK_ENV", "development")

    config_class = get_config()
    app.config.from_object(config_class)

    # Setup logging
    setup_logging(app)

    # Initialize extensions
    init_extensions(app)

    # Register blueprints
    app.register_blueprint(auth_bp, url_prefix="/api/auth")

    # Register Socket.IO handlers
    register_socketio(socketio, app)
    register_game_handlers(socketio, app)

    # Register routes
    register_routes(app)

    # Log registered routes for debugging
    logger.info("Registered routes:")
    for rule in app.url_map.iter_rules():
        methods = ','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
        logger.debug(f"  {rule.rule:40s} {methods:20s} -> {rule.endpoint}")

    return app


def register_routes(app):
    """
    Register additional application routes.

    Args:
        app: Flask application instance
    """

    @app.route("/")
    def index():
        """Serve the login page as the default."""
        return send_from_directory(app.static_folder, 'login.html')

    @app.route("/<path:path>", methods=["GET"], endpoint="spa_fallback")
    def spa_fallback(path):
        """
        SPA fallback handler for serving static files.

        This handles routing for single-page application behavior,
        serving static files when they exist, otherwise falling back
        to the main app HTML.
        """
        # Never return HTML for API paths
        if path.startswith("api/"):
            abort(404)

        # Check if the file exists
        full_path = os.path.join(app.static_folder, path)
        if os.path.isfile(full_path):
            return send_from_directory(app.static_folder, path)

        # Fallback to main chat page
        return send_from_directory(app.static_folder, "chat.html")


# Export commonly used objects
__all__ = ["create_app", "socketio", "db", "limiter"]
