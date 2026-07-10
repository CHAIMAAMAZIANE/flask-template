import json

import pytest
from flask import Flask

from services.auth.app import create_app, db, init_db, User


@pytest.fixture(scope="module")
def auth_app():
    app = create_app(
        {
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "REDIS_URL": "redis://localhost:6379/1",
            "JWT_SECRET": "test-secret",
            "ACCESS_TOKEN_EXPIRES": 10,
        }
    )
    app.config["TESTING"] = True
    from werkzeug.security import generate_password_hash

    with app.app_context():
        db.create_all()
        user = User(
            username="alice",
            password_hash=generate_password_hash("password"),
            role="admin",
        )
        db.session.add(user)
        db.session.commit()
    yield app


@pytest.fixture
def client(auth_app):
    return auth_app.test_client()


def test_login_success(client):
    response = client.post(
        "/auth/login",
        data=json.dumps({"username": "alice", "password": "password"}),
        content_type="application/json",
    )
    assert response.status_code == 200
    assert response.json["access_token"]


def test_login_failure(client):
    response = client.post(
        "/auth/login",
        data=json.dumps({"username": "alice", "password": "wrong"}),
        content_type="application/json",
    )
    assert response.status_code == 401


def test_validate_token(client):
    login = client.post(
        "/auth/login",
        data=json.dumps({"username": "alice", "password": "password"}),
        content_type="application/json",
    )
    token = login.json["access_token"]
    response = client.post(
        "/auth/validate", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json["active"] is True
