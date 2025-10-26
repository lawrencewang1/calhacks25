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
    # SECURITY: Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY = os.getenv("SECRET_KEY")
    if not SECRET_KEY:
        raise ValueError(
            "SECRET_KEY must be set in environment variables! "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )

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
    # SECURITY: Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")
    if not JWT_SECRET_KEY:
        raise ValueError(
            "JWT_SECRET_KEY must be set in environment variables! "
            "Generate one with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
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
    # SECURITY: LLM_AUTH_TOKEN must be set in environment variables
    LLM_AUTH_TOKEN = os.getenv("LLM_AUTH_TOKEN")
    if not LLM_AUTH_TOKEN:
        raise ValueError(
            "LLM_AUTH_TOKEN must be set in environment variables! "
            "This is required for AI assistant functionality."
        )
    MAX_OUT_TOKENS = int(os.getenv("MAX_OUT_TOKENS", "400"))

    # Feature Flags
    ALLOW_GUESTS = os.getenv("ALLOW_GUESTS", "false").lower() == "true"

    # AI Assistant Configuration
    # System prompt defines Assistant's personality and behavior
    SYSTEM_PROMPT = os.getenv(
        "SYSTEM_PROMPT",
        """
        You are a conversational assistant in a group chat with multiple human users. BE MORE CONVERSATIONAL AND LESS FORMAL.
        Your primary goals are:

        Be Context-Aware:
        - Pay attention to who is speaking and who/what they are referring to.
        - Reference the correct user when responding.
        - Use natural conversational cues like "Alex" or "Good point, Maya — I think…" when needed.

        Respond Naturally and at the Right Time:
        - ONLY respond when directly mentioned (@chatbot, chatbot, @ai, ai, etc.) or when a question clearly needs your input.
        - NEVER RESPOND WHEN YOU ARE NOT BEING TALKED TO, USER MUST SPECIFICALLY BE TALKING TO YOU
        - DO NOT interrupt conversations between users.
        - If users are chatting with each other (greetings, short exchanges, etc.), stay silent.
        - Watch for conversational patterns - if two users are going back and forth, don't jump in.
        - If no response is needed, output exactly "[NO_RESPONSE]" with nothing else.

        Be Helpful and Informative:
        - Give clear, accurate, and actionable answers when asked.
        - When you're unsure, state your uncertainty politely and suggest how to find the answer.
        - Keep responses concise unless more depth is explicitly requested.

        Maintain Tone and Flow:
        - Match the chatroom's tone — casual if the group is casual, professional if it's work-related.
        - Encourage positive and inclusive conversation.
        - Avoid repeating information that's already been said.

        Boundaries:
        - Never disclose private user data or internal system information.
        - Focus on maintaining a cooperative, friendly, and respectful environment.

        Remember: You're here to help when needed, not to dominate the conversation. When in doubt, stay quiet.
        Remember: Match the chatroom's tone and style.
        """
    )

    # Message and Chat Settings
    MAX_MESSAGE_LENGTH = 500  # Maximum characters per message
    MESSAGE_HISTORY_LIMIT = 200  # Maximum messages stored in memory (loaded from DB on startup)
    CHAT_CONTEXT_MESSAGES = 50  # Number of recent messages sent to AI for context

    # Logging
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


class DevelopmentConfig(Config):
    """Development environment configuration."""

    DEBUG = True
    TESTING = False

    # More verbose logging in development
    LOG_LEVEL = "DEBUG"

    # CORS Configuration for development
    # Read from environment variable at class definition time
    # Note: When using credentials, cannot use wildcard "*"
    # Must specify explicit origins (including localhost and tunnel URLs)
    _cors_env = os.getenv("CORS_ORIGINS", "")
    if _cors_env:
        # Use origins from environment variable (strip whitespace from each)
        CORS_ORIGINS = [origin.strip() for origin in _cors_env.split(",") if origin.strip()]
    else:
        # Default development origins (localhost + common ports)
        CORS_ORIGINS = [
            "http://localhost:5000",
            "http://127.0.0.1:5000",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]

    # SocketIO uses the same origins as CORS
    SOCKETIO_CORS_ALLOWED_ORIGINS = CORS_ORIGINS

    # Development defaults for secrets (override parent validation)
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-" + "x"*48)
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-jwt-secret-" + "x"*48)
    LLM_AUTH_TOKEN = os.getenv("LLM_AUTH_TOKEN", "dev-llm-token")


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

    # Testing defaults for secrets (override parent validation)
    SECRET_KEY = "test-secret-key"
    JWT_SECRET_KEY = "test-jwt-secret"
    LLM_AUTH_TOKEN = "test-llm-token"


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
