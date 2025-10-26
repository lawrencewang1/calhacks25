#!/usr/bin/env python
"""
Database initialization script.

This script recreates the database with the new multi-room schema
and creates a default room.

Usage:
    python init_db.py
"""

import os
from backend import create_app
from backend.extensions import db
from backend.models.user import User
from backend.models.room import Room
from backend.models.room_ban import RoomBan

def init_database():
    """Initialize the database with fresh schema and default data."""
    app = create_app()

    with app.app_context():
        print("Dropping all tables...")
        db.drop_all()

        print("Creating all tables...")
        db.create_all()

        # Create a default user for room creation
        print("Creating default user...")
        default_user = User(
            name="system",
            email="system@chat.local"
        )
        default_user.set_password("system123")  # Default password
        db.session.add(default_user)
        db.session.commit()

        # Create official global rooms
        print("Creating official 'General' room...")
        general_room = Room(
            name="General",
            created_by=default_user.id,
            is_official=True,
            is_public=True
        )
        db.session.add(general_room)

        print("Creating official 'Random' room...")
        random_room = Room(
            name="Random",
            created_by=default_user.id,
            is_official=True,
            is_public=True
        )
        db.session.add(random_room)

        print("Creating official 'Tech Talk' room...")
        tech_room = Room(
            name="Tech Talk",
            created_by=default_user.id,
            is_official=True,
            is_public=True
        )
        db.session.add(tech_room)

        db.session.commit()

        print(f"\nDatabase initialized successfully!")
        print(f"  - Default user: system (email: system@chat.local, password: system123)")
        print(f"  - Default rooms: General, Random")
        print(f"\nYou can now start the application with: python run.py")

if __name__ == "__main__":
    init_database()
