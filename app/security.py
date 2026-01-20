from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any

import jwt
from flask import current_app, g, jsonify, request

from app.extensions import db
from app.models import User, UserRole


def _extract_token() -> str | None:
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header.split(" ", 1)[1].strip() or None


def create_access_token(user: User) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {
        "sub": str(user.id),
        "role": user.role.value,
        "iat": now,
        "exp": now + timedelta(hours=current_app.config["JWT_EXPIRY_HOURS"]),
    }
    return jwt.encode(payload, current_app.config["JWT_SECRET_KEY"], algorithm="HS256")


def decode_access_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        current_app.config["JWT_SECRET_KEY"],
        algorithms=["HS256"],
    )


def token_required(*roles: UserRole):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            token = _extract_token()
            if not token:
                return jsonify({"error": "Missing Bearer token"}), 401

            try:
                payload = decode_access_token(token)
            except jwt.ExpiredSignatureError:
                return jsonify({"error": "Token expired"}), 401
            except jwt.InvalidTokenError:
                return jsonify({"error": "Invalid token"}), 401

            raw_user_id = payload.get("sub")
            try:
                user_id = int(raw_user_id)
            except (TypeError, ValueError):
                return jsonify({"error": "Invalid token subject"}), 401

            user = db.session.get(User, user_id)
            if not user:
                return jsonify({"error": "User not found"}), 401

            if roles:
                allowed_roles = {role.value for role in roles}
                if user.role.value not in allowed_roles:
                    return jsonify({"error": "Forbidden"}), 403

            g.current_user = user
            return func(*args, **kwargs)

        return wrapper

    return decorator
