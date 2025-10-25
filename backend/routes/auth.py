from flask import Blueprint, request, jsonify
from models.user import User
from database import db
from flask_jwt_extended import create_access_token

auth_bp = Blueprint("auth", __name__)

@auth_bp.post("/register")
def register():
    data = request.get_json() or {}
    email, password = data.get("email"), data.get("password")
    if not email or not password:
        return jsonify({"msg": "email and password required"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"msg": "user already exists"}), 400

    u = User(email=email)
    u.set_password(password)
    db.session.add(u); db.session.commit()

    token = create_access_token(identity=u.id)
    return jsonify({"access_token": token, "user": {"id": u.id, "email": u.email}}), 201

@auth_bp.post("/login")
def login():
    data = request.get_json() or {}
    email, password = data.get("email"), data.get("password")
    u = User.query.filter_by(email=email).first()
    if not u or not u.check_password(password):
        return jsonify({"msg": "invalid credentials"}), 401
    token = create_access_token(identity=u.id)
    return jsonify({"access_token": token, "user": {"id": u.id, "email": u.email}})
