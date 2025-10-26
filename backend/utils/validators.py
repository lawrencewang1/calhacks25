"""
Validation utilities for input sanitization and validation.
"""

import re
from email_validator import validate_email, EmailNotValidError


def validate_email_format(email: str) -> tuple[bool, str]:
    """
    Validate email format using email-validator library.

    Args:
        email: Email address to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        # Validate and normalize the email
        valid = validate_email(email, check_deliverability=False)
        return True, ""
    except EmailNotValidError as e:
        return False, str(e)


def validate_password_strength(password: str) -> tuple[bool, str]:
    """
    Validate password meets security requirements.

    Requirements:
    - Minimum 12 characters
    - At least one uppercase letter
    - At least one lowercase letter
    - At least one digit
    - At least one special character

    Args:
        password: Password to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if len(password) < 12:
        return False, "Password must be at least 12 characters long"

    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"

    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"

    if not re.search(r'\d', password):
        return False, "Password must contain at least one digit"

    if not re.search(r'[!@#$%^&*(),.?":{}|<>_\-+=\[\]\\;/~`]', password):
        return False, "Password must contain at least one special character"

    return True, ""


def sanitize_text(text: str, max_length: int = None) -> str:
    """
    Sanitize user input text.

    Args:
        text: Text to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized text
    """
    if text is None:
        return ""

    # Strip whitespace
    text = text.strip()

    # Truncate to max length if specified
    if max_length and len(text) > max_length:
        text = text[:max_length]

    return text
