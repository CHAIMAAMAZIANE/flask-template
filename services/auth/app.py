import os
import uuid
from datetime import datetime, timedelta, timezone

import jwt
import redis
from flask import Flask, jsonify, request, current_app
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash


db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(32), nullable=False, default="user")

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def as_dict(self):
        return {"id": self.id, "username": self.username, "role": self.role}


def create_app(test_config=None):
    app = Flask(__name__)
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL", "postgresql://postgres:postgres@db:5432/authdb"
    )
    app.config["REDIS_URL"] = os.getenv("REDIS_URL", "redis://cache:6379/0")
    jwt_secret = os.getenv("JWT_SECRET")
    if not jwt_secret:
        raise RuntimeError("JWT_SECRET environment variable must be set")
    app.config["JWT_SECRET"] = jwt_secret
    app.config["JWT_ALGORITHM"] = os.getenv("JWT_ALGORITHM", "HS256")
    app.config["ACCESS_TOKEN_EXPIRES"] = int(os.getenv("ACCESS_TOKEN_EXPIRES", "3600"))

    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    app.redis = redis.Redis.from_url(app.config["REDIS_URL"], decode_responses=True)

    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "service": "auth"}), 200

    @app.route("/auth/login", methods=["POST"])
    def login():
        payload = request.get_json(silent=True) or {}
        username = payload.get("username", "")
        password = payload.get("password", "")

        user = User.query.filter_by(username=username).first()
        if user is None or not user.check_password(password):
            return jsonify({"error": "invalid credentials"}), 401

        token = create_access_token(user)
        return (
            jsonify(
                {
                    "access_token": token,
                    "token_type": "Bearer",
                    "expires_in": app.config["ACCESS_TOKEN_EXPIRES"],
                }
            ),
            200,
        )

    @app.route("/auth/validate", methods=["POST"])
    def validate():
        token = get_bearer_token(request)
        if not token:
            return jsonify({"active": False, "error": "missing token"}), 401

        validation = verify_token(token)
        if not validation["active"]:
            return jsonify(validation), 401

        return jsonify(validation), 200

    @app.route("/auth/logout", methods=["POST"])
    def logout():
        token = get_bearer_token(request)
        if not token:
            return jsonify({"error": "missing token"}), 401

        validation = verify_token(token)
        if not validation["active"]:
            return jsonify(validation), 401

        app.redis.delete(token_key(validation["payload"]["jti"]))
        return jsonify({"message": "logged out"}), 200

    @app.after_request
    def set_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Content-Security-Policy'] = "default-src 'self'"
        response.headers['Permissions-Policy'] = "geolocation=(), microphone=(), camera=()"
        response.headers['Cross-Origin-Resource-Policy'] = "same-origin"
        response.headers.pop('Server', None)
        return response

    return app


def get_bearer_token(request):
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.split(" ", 1)[1].strip()

    body = request.get_json(silent=True) or {}
    return body.get("token")


def token_key(jti):
    return f"auth:token:{jti}"


def create_access_token(user):
    issued_at = datetime.now(timezone.utc)
    expires_at = issued_at + timedelta(seconds=current_app.config["ACCESS_TOKEN_EXPIRES"])
    payload = {
        "sub": user.id,
        "username": user.username,
        "role": user.role,
        "jti": str(uuid.uuid4()),
        "iat": issued_at,
        "exp": expires_at,
    }

    token = jwt.encode(
        payload, current_app.config["JWT_SECRET"], algorithm=current_app.config["JWT_ALGORITHM"]
    )
    if isinstance(token, bytes):
        token = token.decode("utf-8")

    current_app.redis.setex(token_key(payload["jti"]), current_app.config["ACCESS_TOKEN_EXPIRES"], user.id)
    return token


def verify_token(token):
    try:
        payload = jwt.decode(
            token,
            current_app.config["JWT_SECRET"],
            algorithms=[current_app.config["JWT_ALGORITHM"]],
        )
    except jwt.ExpiredSignatureError:
        return {"active": False, "error": "token expired"}
    except jwt.InvalidTokenError as exc:
        return {"active": False, "error": str(exc)}

    if not current_app.redis.exists(token_key(payload["jti"])):
        return {"active": False, "error": "token revoked or unknown"}

    return {"active": True, "payload": payload}


def init_db(app):
    with app.app_context():
        db.create_all()
        if User.query.filter_by(username="alice").first() is None:
            alice = User(
                username="alice",
                password_hash=generate_password_hash("password"),
                role="admin",
            )
            db.session.add(alice)
            db.session.commit()


if __name__ == "__main__":
    app = create_app()
    init_db(app)
    app.run(host="0.0.0.0", port=5001)