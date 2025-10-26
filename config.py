"""
Configuration settings for the application.

This module provides configuration classes for different environments:
- DevelopmentConfig: For local development
- ProductionConfig: For production deployment
- TestingConfig: For running tests
"""

import os
from datetime import timedelta
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class Config:
    """Base configuration with default settings."""

    # Flask Core Settings
    SECRET_KEY = os.getenv("SECRET_KEY", os.urandom(32))

    # Database Configuration
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "SQLALCHEMY_DATABASE_URI",
        "sqlite:///chatbot.db"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
    }

    # JWT Configuration
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", os.urandom(32))
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=1)
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=30)
    JWT_TOKEN_LOCATION = ["headers"]
    JWT_HEADER_NAME = "Authorization"
    JWT_HEADER_TYPE = "Bearer"

    # CORS Configuration
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")

    # Socket.IO Configuration
    SOCKETIO_CORS_ALLOWED_ORIGINS = os.getenv("CORS_ORIGINS", "*")
    SOCKETIO_MANAGE_SESSION = False

    # LLM API Configuration
    LLM_API_URL = os.getenv(
        "LLM_API_URL",
        "https://janitorai.com/hackathon/completions"
    )
    LLM_AUTH_TOKEN = os.getenv("LLM_AUTH_TOKEN", "calhacks2047")
    MAX_OUT_TOKENS = int(os.getenv("MAX_OUT_TOKENS", "400"))

    # Feature Flags
    ALLOW_GUESTS = os.getenv("ALLOW_GUESTS", "false").lower() == "true"

    # System Prompt for AI
    SYSTEM_PROMPT = os.getenv(
        "SYSTEM_PROMPT",
        """
You are a conversational assistant in a group chat with multiple human users. Your primary goals are:

Be Context-Aware:
Pay attention to who is speaking and what they are referring to.
Reference the correct user when responding.
Use natural conversational cues like "@Alex" or "Good point, Maya — I think…" when needed.

Respond Naturally and at the Right Time:
DO NOT interrupt active human exchanges.
DO NOT RESPOND until a user asks a direct question, mentions you, or leaves a gap in conversation, you will be referred to as "Assistant", "Chatbot", or "AI".
Avoid replying to every message; prioritize helpful or relevant responses.
If no response is needed, reply with exactly "[NO_RESPONSE]".

Be Helpful and Informative:
Give clear, accurate, and actionable answers.
When you're unsure, state your uncertainty politely and suggest how to find the answer.
Keep responses concise unless more depth is explicitly requested.

Maintain Tone and Flow:
Match the chatroom's tone — casual if the group is casual, professional if it's work-related.
Encourage positive and inclusive conversation.
Avoid repeating information that's already been said.

Boundaries:
Never disclose private user data or internal system information.
Focus on maintaining a cooperative, friendly, and respectful environment.

Once again, if you do not need to respond respond exactly with "[NO_RESPONSE]", and only respond if necessary.
        """
    )

    # Message and Chat Settings
    MAX_MESSAGE_LENGTH = 500
    MESSAGE_HISTORY_LIMIT = 200
    CHAT_CONTEXT_MESSAGES = 50

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


class DevelopmentConfig(Config):
    """Development environment configuration."""

    DEBUG = True
    TESTING = False

    # More verbose logging in development
    LOG_LEVEL = "DEBUG"

    # Allow all CORS origins in development
    CORS_ORIGINS = ["*"]
    SOCKETIO_CORS_ALLOWED_ORIGINS = "*"


class ProductionConfig(Config):
    """Production environment configuration."""

    DEBUG = False
    TESTING = False

    # Strict CORS in production
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "").split(",")

    # Require strong JWT secret in production
    if Config.JWT_SECRET_KEY == "hithere":
        raise ValueError(
            "JWT_SECRET_KEY must be set to a strong secret in production! "
            "Generate one with: openssl rand -hex 32"
        )

    # Session security
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"


class TestingConfig(Config):
    """Testing environment configuration."""

    TESTING = True
    DEBUG = True

    # Use in-memory database for tests
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"

    # Disable CSRF for testing
    WTF_CSRF_ENABLED = False

    # Short token expiry for testing
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=5)


# Configuration dictionary
config = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
    "default": DevelopmentConfig,
}


def get_config():
    """Get the configuration object based on FLASK_ENV environment variable."""
    env = os.getenv("FLASK_ENV", "development")
    return config.get(env, config["default"])
