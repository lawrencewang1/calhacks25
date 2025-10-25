"""
Pytest configuration and fixtures.
"""

import pytest
from backend import create_app
from backend.extensions import db as _db


@pytest.fixture(scope="session")
def app():
    """
    Create application for testing.
    """
    app = create_app("testing")
    return app


@pytest.fixture(scope="session")
def db(app):
    """
    Create database for testing.
    """
    with app.app_context():
        _db.create_all()
        yield _db
        _db.drop_all()


@pytest.fixture(scope="function")
def session(db):
    """
    Create a new database session for a test.
    """
    connection = db.engine.connect()
    transaction = connection.begin()

    session = db.create_scoped_session(
        options={"bind": connection, "binds": {}}
    )
    db.session = session

    yield session

    transaction.rollback()
    connection.close()
    session.remove()


@pytest.fixture
def client(app):
    """
    Create a test client.
    """
    return app.test_client()
