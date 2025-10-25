import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app import app
from database import db
from models.user import User

with app.app_context():
    users = User.query.all()
    for u in users:
        print(f"ID: {u.id}, Email: {u.email}, Password Hash: {u.password_hash}")
