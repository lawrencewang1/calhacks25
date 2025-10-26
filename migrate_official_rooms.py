#!/usr/bin/env python
"""
Migration script to add official rooms without wiping existing data.

This script safely adds official global rooms to an existing database
without destroying any existing users, rooms, or messages.

Usage:
    python migrate_official_rooms.py
"""

import os
import secrets
import logging
from backend import create_app
from backend.extensions import db
from backend.models.user import User
from backend.models.room import Room

logger = logging.getLogger(__name__)

def migrate_official_rooms():
    """Add official rooms to the database without destroying existing data."""
    app = create_app()

    with app.app_context():
        print("\n" + "="*60)
        print("Official Rooms Migration Script")
        print("="*60)

        # Check if official rooms already exist
        existing_official_rooms = Room.query.filter_by(is_official=True).all()
        if existing_official_rooms:
            print(f"\n✓ Found {len(existing_official_rooms)} existing official room(s):")
            for room in existing_official_rooms:
                print(f"  - {room.name}")

            response = input("\nDo you want to add missing official rooms? (y/n): ").strip().lower()
            if response != 'y':
                print("\nMigration cancelled.")
                return

        # Get or create system user
        system_user = User.query.filter_by(email="system@chat.local").first()
        system_password = None

        if not system_user:
            print("\n→ Creating system user...")
            system_password = secrets.token_urlsafe(32)
            system_user = User(
                name="system",
                email="system@chat.local"
            )
            system_user.set_password(system_password)
            db.session.add(system_user)
            db.session.commit()
            print("✓ System user created")
        else:
            print(f"\n✓ System user already exists (ID: {system_user.id})")

        # Define official rooms to create
        official_rooms = [
            {"name": "General", "description": "Main global chat room"},
            {"name": "Random", "description": "For off-topic discussions"},
            {"name": "Tech Talk", "description": "For technical discussions"}
        ]

        created_rooms = []
        skipped_rooms = []

        print("\n→ Checking and creating official rooms...")

        for room_data in official_rooms:
            # Check if room already exists
            existing_room = Room.query.filter_by(
                name=room_data["name"],
                is_official=True
            ).first()

            if existing_room:
                skipped_rooms.append(room_data["name"])
                print(f"  ⊘ '{room_data['name']}' already exists (ID: {existing_room.id})")
            else:
                new_room = Room(
                    name=room_data["name"],
                    created_by=system_user.id,
                    is_official=True,
                    is_public=True
                )
                db.session.add(new_room)
                created_rooms.append(room_data["name"])
                print(f"  ✓ '{room_data['name']}' created")

        if created_rooms:
            db.session.commit()

        # Print summary
        print("\n" + "="*60)
        print("Migration Summary")
        print("="*60)

        if created_rooms:
            print(f"\n✓ Created {len(created_rooms)} official room(s):")
            for room_name in created_rooms:
                print(f"  - {room_name}")

        if skipped_rooms:
            print(f"\n⊘ Skipped {len(skipped_rooms)} existing room(s):")
            for room_name in skipped_rooms:
                print(f"  - {room_name}")

        if system_password:
            print(f"\n⚠ System User Credentials:")
            print(f"  Email: system@chat.local")
            print(f"  Password: {system_password}")
            print(f"  IMPORTANT: Save this password if you need to log in as the system user!")

        # Show current stats
        total_users = User.query.count()
        total_rooms = Room.query.count()
        total_official_rooms = Room.query.filter_by(is_official=True).count()

        print(f"\n📊 Current Database Stats:")
        print(f"  Total Users: {total_users}")
        print(f"  Total Rooms: {total_rooms}")
        print(f"  Official Rooms: {total_official_rooms}")

        print("\n✓ Migration completed successfully!")
        print("="*60 + "\n")

if __name__ == "__main__":
    migrate_official_rooms()
