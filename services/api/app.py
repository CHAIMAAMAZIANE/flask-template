import os
from functools import wraps

import requests
from flask import Flask, jsonify, request, current_app
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


class Item(db.Model):
    __tablename__ = "items"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(400), nullable=True)
    owner_id = db.Column(db.Integer, nullable=False)

    def as_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "owner_id": self.owner_id,
        }


class AuthClient:
    def __init__(self, auth_url):
        self.auth_url = auth_url.rstrip("/")

    def validate(self, token):
        try:
            response = requests.post(
                f"{self.auth_url}/auth/validate",
                headers={"Authorization": f"Bearer {token}"},
                timeout=3,
            )
            return response.json()
        except requests.RequestException as exc:
            return {"active": False, "error": f"auth service unavailable: {exc}"}


def create_app(test_config=None):
    app = Flask(__name__)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@db:5432/appdb"
    )
    app.config["AUTH_URL"] = os.getenv("AUTH_URL", "http://auth:5001")

    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    app.auth_client = AuthClient(app.config["AUTH_URL"])

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "service": "api"}), 200

    @app.route("/items", methods=["GET"])
    @require_auth
    def read_items(user):
        items = Item.query.all()
        return jsonify([item.as_dict() for item in items]), 200

    @app.route("/items", methods=["POST"])
    @require_auth
    def create_item(user):
        payload = request.get_json(silent=True) or {}
        name = payload.get("name")
        if not name:
            return jsonify({"error": "name is required"}), 400

        item = Item(
            name=name,
            description=payload.get("description", ""),
            owner_id=user["sub"],
        )
        db.session.add(item)
        db.session.commit()
        return jsonify(item.as_dict()), 201

    @app.route("/profile", methods=["GET"])
    @require_auth
    def profile(user):
        return jsonify(user), 200

    return app


def get_bearer_token(request):
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.split(" ", 1)[1].strip()
    body = request.get_json(silent=True) or {}
    return body.get("token")


def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = get_bearer_token(request)
        if not token:
            return jsonify({"error": "missing authorization token"}), 401

        validation = current_app.auth_client.validate(token)
        if not validation.get("active"):
            return jsonify(validation), 401

        return f(validation["payload"], *args, **kwargs)

    return wrapper


def init_db(app):
    with app.app_context():
        db.create_all()


if __name__ == "__main__":
    app = create_app()
    init_db(app)
    app.run(host="0.0.0.0", port=5000)
