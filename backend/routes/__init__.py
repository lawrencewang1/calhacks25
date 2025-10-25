"""
API routes and blueprints for the application.

This package contains all Flask blueprints for API endpoints.
"""

from backend.routes.auth import auth_bp

__all__ = ["auth_bp"]
