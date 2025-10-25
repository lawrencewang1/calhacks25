"""
Tests for database models.
"""

import pytest
from backend.models.user import User


def test_user_creation(session):
    """Test creating a user."""
    user = User(name="testuser", email="test@example.com")
    user.set_password("password123")

    session.add(user)
    session.commit()

    assert user.id is not None
    assert user.name == "testuser"
    assert user.email == "test@example.com"
    assert user.password_hash is not None


def test_user_password(session):
    """Test user password hashing and checking."""
    user = User(name="testuser", email="test@example.com")
    user.set_password("password123")

    # Password should be hashed
    assert user.password_hash != "password123"

    # Check password should work
    assert user.check_password("password123") is True
    assert user.check_password("wrongpassword") is False


def test_user_unique_email(session):
    """Test that email must be unique."""
    user1 = User(name="user1", email="test@example.com")
    user1.set_password("password123")
    session.add(user1)
    session.commit()

    # Try to create another user with same email
    user2 = User(name="user2", email="test@example.com")
    user2.set_password("password456")
    session.add(user2)

    with pytest.raises(Exception):  # Should raise IntegrityError
        session.commit()
