from flask import Flask
from database import db
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from routes.auth import auth_bp

from dotenv import load_dotenv
import os
load_dotenv()

app = Flask(__name__)
CORS(app, supports_credentials=True)

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///chatbot.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["JWT_SECRET_KEY"] = os.getenv('JWT_SECRET_KEY', 'hithere')

db.init_app(app)

jwt = JWTManager(app)
app.register_blueprint(auth_bp, url_prefix="/api/auth")

with app.app_context():
    db.create_all()

if __name__ == "__main__":
    app.run(debug=True)