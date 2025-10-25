#!/usr/bin/env python
"""
Application entry point for the Multiplayer AI Chat application.

Usage:
    python run.py
"""

import os
from backend import create_app, socketio

# Create the Flask application
app = create_app()

if __name__ == "__main__":
    # Get port from environment or use default
    port = int(os.getenv("PORT", 5000))

    # Get debug mode from environment
    debug = os.getenv("FLASK_ENV", "development") == "development"

    print(f"Starting server on http://0.0.0.0:{port}")
    print(f"Debug mode: {debug}")

    # Run the application with SocketIO
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=debug,
        allow_unsafe_werkzeug=True if debug else False
    )
