#!/usr/bin/env python
"""
Database initialization script.

This script recreates the database with the new multi-room schema
and creates a default room.

Usage:
    python init_db.py
"""

import os
import secrets
import logging
from backend import create_app
from backend.extensions import db
from backend.models.user import User
from backend.models.room import Room
from backend.models.room_ban import RoomBan

logger = logging.getLogger(__name__)

def init_database():
    """Initialize the database with fresh schema and default data."""
    app = create_app()

    with app.app_context():
        logger.info("Dropping all tables...")
        db.drop_all()

        logger.info("Creating all tables...")
        db.create_all()

        # Create a default user for room creation
        logger.info("Creating default system user...")

        # Generate a secure random password for the system user
        system_password = secrets.token_urlsafe(32)

        default_user = User(
            name="system",
            email="system@chat.local"
        )
        default_user.set_password(system_password)
        db.session.add(default_user)
        db.session.commit()

        # Create official global rooms
        logger.info("Creating official 'General' room...")
        general_room = Room(
            name="General",
            created_by=default_user.id,
            is_official=True,
            is_public=True
        )
        db.session.add(general_room)

        logger.info("Creating official 'Random' room...")
        random_room = Room(
            name="Random",
            created_by=default_user.id,
            is_official=True,
            is_public=True
        )
        db.session.add(random_room)

        logger.info("Creating official 'Tech Talk' room...")
        tech_room = Room(
            name="Tech Talk",
            created_by=default_user.id,
            is_official=True,
            is_public=True
        )
        db.session.add(tech_room)

        db.session.commit()

        # Use print for important user-facing information
        print(f"\nDatabase initialized successfully!")
        print(f"  - System user created: system (email: system@chat.local)")
        print(f"  - System password: {system_password}")
        print(f"  - IMPORTANT: Save this password if you need to log in as the system user!")
        print(f"  - Default rooms: General, Random, Tech Talk")
        print(f"\nYou can now start the application with: python run.py")

if __name__ == "__main__":
    init_database()
