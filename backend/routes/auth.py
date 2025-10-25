# routes/auth.py
import re
from flask import Blueprint, request, jsonify
from models.user import User
from database import db
from flask_jwt_extended import create_access_token

auth_bp = Blueprint("auth", __name__)

# PRODUCTION TODO: Add input sanitization to prevent XSS and injection attacks
# PRODUCTION TODO: Consider adding CAPTCHA for registration to prevent bot signups

def _slug_from_email(email: str) -> str:
    base = (email.split("@")[0] if email else "user")
    # keep letters, numbers, underscore; cap length to the model limit (40)
    base = re.sub(r"[^A-Za-z0-9_]", "", base)[:40] or "user"
    return base

@auth_bp.post("/register")
def register():
    data = request.get_json() or {}
    email, password = data.get("email"), data.get("password")
    want_name = (data.get("name") or "").strip()

    if not email or not password:
        return jsonify({"msg": "email and password required"}), 400

    # PRODUCTION TODO: Add email validation (regex or library like email-validator)
    # Example: if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
    #              return jsonify({"msg": "invalid email format"}), 400

    # PRODUCTION TODO: Add password strength requirements
    # Example: minimum length, require special characters, etc.

    if User.query.filter_by(email=email).first():
        return jsonify({"msg": "user already exists"}), 400

    # pick a name (requested or derived), ensure uniqueness
    base = want_name or _slug_from_email(email)
    candidate = base
    i = 1
    while User.query.filter_by(name=candidate).first():
        candidate = f"{base}{i}"
        i += 1

    u = User(name=candidate, email=email)
    u.set_password(password)
    db.session.add(u)

    # PRODUCTION TODO: Add error handling for database commit failures
    # try:
    #     db.session.commit()
    # except Exception as e:
    #     db.session.rollback()
    #     return jsonify({"msg": "registration failed"}), 500
    db.session.commit()

    token = create_access_token(identity=u.id)
    return jsonify({"access_token": token, "user": {"id": u.id, "email": u.email, "name": u.name}}), 201

@auth_bp.post("/login")
def login():
    data = request.get_json() or {}
    email, password = data.get("email"), data.get("password")
    u = User.query.filter_by(email=email).first()
    if not u or not u.check_password(password):
        # PRODUCTION TODO: Add rate limiting to prevent brute force attacks
        # Consider using Flask-Limiter or similar
        return jsonify({"msg": "invalid credentials"}), 401
    token = create_access_token(identity=u.id)
    # PRODUCTION TODO: Consider including user name in login response for consistency with register
    # return jsonify({"access_token": token, "user": {"id": u.id, "email": u.email, "name": u.name}})
    return jsonify({"access_token": token, "user": {"id": u.id, "email": u.email}})
