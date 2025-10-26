"""
Authentication routes for user registration and login.
"""

import re
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token, jwt_required, get_jwt_identity
from backend.models.user import User
from backend.extensions import db, limiter
from backend.utils.validators import validate_email_format, validate_password_strength, sanitize_text

auth_bp = Blueprint("auth", __name__)

# PRODUCTION TODO: Consider adding CAPTCHA for registration to prevent bot signups

def _slug_from_email(email: str) -> str:
    base = (email.split("@")[0] if email else "user")
    # keep letters, numbers, underscore; cap length to the model limit (40)
    base = re.sub(r"[^A-Za-z0-9_]", "", base)[:40] or "user"
    return base

@auth_bp.post("/register")
@limiter.limit("5 per hour")  # Strict limit to prevent bot signups
def register():
    data = request.get_json() or {}
    email = sanitize_text(data.get("email"), max_length=120)
    password = data.get("password")
    want_name = sanitize_text(data.get("name"), max_length=40)

    if not email or not password:
        return jsonify({"msg": "email and password required"}), 400

    # Validate email format
    is_valid_email, email_error = validate_email_format(email)
    if not is_valid_email:
        return jsonify({"msg": f"invalid email: {email_error}"}), 400

    # Validate password strength
    is_valid_password, password_error = validate_password_strength(password)
    if not is_valid_password:
        return jsonify({"msg": password_error}), 400

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

    token = create_access_token(identity=str(u.id))
    return jsonify({"access_token": token, "user": {"id": u.id, "email": u.email, "name": u.name}}), 201

@auth_bp.post("/login")
@limiter.limit("10 per minute")  # Prevent brute force attacks
def login():
    data = request.get_json() or {}
    email, password = data.get("email"), data.get("password")
    u = User.query.filter_by(email=email).first()
    if not u or not u.check_password(password):
        # PRODUCTION TODO: Add rate limiting to prevent brute force attacks
        # Consider using Flask-Limiter or similar
        return jsonify({"msg": "invalid credentials"}), 401
    token = create_access_token(identity=str(u.id))
    return jsonify({"access_token": token, "user": {"id": u.id, "email": u.email, "name": u.name}})

@auth_bp.get("/profile")
@jwt_required()
def get_profile():
    """Get current user's profile information."""
    user_id = get_jwt_identity()
    u = User.query.get(int(user_id))

    if not u:
        return jsonify({"msg": "user not found"}), 404

    return jsonify({
        "user": {
            "id": u.id,
            "email": u.email,
            "name": u.name
        }
    })

@auth_bp.put("/profile")
@jwt_required()
def update_profile():
    """Update current user's profile information."""
    user_id = get_jwt_identity()
    u = User.query.get(int(user_id))

    if not u:
        return jsonify({"msg": "user not found"}), 404

    data = request.get_json() or {}
    updated = False

    # Update email
    new_email = sanitize_text(data.get("email"), max_length=120)
    if new_email and new_email != u.email:
        # Validate email format
        is_valid_email, email_error = validate_email_format(new_email)
        if not is_valid_email:
            return jsonify({"msg": f"invalid email: {email_error}"}), 400

        # Check if email is already taken
        if User.query.filter_by(email=new_email).first():
            return jsonify({"msg": "email already in use"}), 400
        u.email = new_email
        updated = True

    # Update name
    new_name = sanitize_text(data.get("name"), max_length=40)
    if new_name and new_name != u.name:
        # Check if name is already taken
        if User.query.filter_by(name=new_name).first():
            return jsonify({"msg": "username already taken"}), 400
        u.name = new_name
        updated = True

    if updated:
        try:
            db.session.commit()
            return jsonify({
                "msg": "profile updated successfully",
                "user": {
                    "id": u.id,
                    "email": u.email,
                    "name": u.name
                }
            })
        except Exception as e:
            db.session.rollback()
            return jsonify({"msg": "failed to update profile"}), 500

    return jsonify({"msg": "no changes made"})

@auth_bp.put("/password")
@jwt_required()
@limiter.limit("5 per hour")  # Prevent password brute forcing
def change_password():
    """Change current user's password."""
    user_id = get_jwt_identity()
    u = User.query.get(int(user_id))

    if not u:
        return jsonify({"msg": "user not found"}), 404

    data = request.get_json() or {}
    current_password = data.get("current_password")
    new_password = data.get("new_password")

    if not current_password or not new_password:
        return jsonify({"msg": "current password and new password required"}), 400

    # Verify current password
    if not u.check_password(current_password):
        return jsonify({"msg": "current password is incorrect"}), 401

    # Validate new password strength
    is_valid_password, password_error = validate_password_strength(new_password)
    if not is_valid_password:
        return jsonify({"msg": password_error}), 400

    # Update password
    u.set_password(new_password)

    try:
        db.session.commit()
        return jsonify({"msg": "password changed successfully"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"msg": "failed to change password"}), 500
