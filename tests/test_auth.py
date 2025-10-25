"""
Tests for authentication endpoints.
"""

import pytest
from backend.models.user import User


def test_register(client, session):
    """Test user registration."""
    response = client.post("/api/auth/register", json={
        "name": "testuser",
        "email": "test@example.com",
        "password": "password123"
    })

    assert response.status_code == 201
    data = response.get_json()
    assert "access_token" in data
    assert data["user"]["name"] == "testuser"
    assert data["user"]["email"] == "test@example.com"


def test_register_duplicate_email(client, session):
    """Test registration with duplicate email."""
    # First registration
    client.post("/api/auth/register", json={
        "name": "testuser",
        "email": "test@example.com",
        "password": "password123"
    })

    # Second registration with same email
    response = client.post("/api/auth/register", json={
        "name": "testuser2",
        "email": "test@example.com",
        "password": "password456"
    })

    assert response.status_code == 400
    data = response.get_json()
    assert "already exists" in data["msg"]


def test_login(client, session):
    """Test user login."""
    # Register user first
    client.post("/api/auth/register", json={
        "name": "testuser",
        "email": "test@example.com",
        "password": "password123"
    })

    # Login
    response = client.post("/api/auth/login", json={
        "email": "test@example.com",
        "password": "password123"
    })

    assert response.status_code == 200
    data = response.get_json()
    assert "access_token" in data
    assert data["user"]["email"] == "test@example.com"


def test_login_invalid_credentials(client, session):
    """Test login with invalid credentials."""
    response = client.post("/api/auth/login", json={
        "email": "nonexistent@example.com",
        "password": "wrongpassword"
    })

    assert response.status_code == 401
    data = response.get_json()
    assert "invalid credentials" in data["msg"]
