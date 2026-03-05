from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from typing import Any

from flask import current_app

from app.extensions import get_redis_client


CACHE_NS_STUDENT_JOBS = "student_jobs"
CACHE_NS_ADMIN_COMPANIES = "admin_companies"
CACHE_NS_ADMIN_STUDENTS = "admin_students"


def _normalize_params(params: Mapping[str, Any] | None) -> dict[str, Any]:
    if not params:
        return {}
    normalized: dict[str, Any] = {}
    for key, value in sorted(params.items()):
        if value is None:
            continue
        if isinstance(value, (list, tuple)):
            serialized = [str(item) for item in value if item not in (None, "")]
            if serialized:
                normalized[key] = serialized
            continue
        text = str(value)
        if text != "":
            normalized[key] = text
    return normalized


def _cache_prefix() -> str:
    return current_app.config.get("CACHE_KEY_PREFIX", "ppa:cache")


def is_cache_enabled() -> bool:
    return bool(current_app.config.get("CACHE_ENABLED", True)) and get_redis_client() is not None


def build_cache_key(
    namespace: str,
    params: Mapping[str, Any] | None = None,
    user_scope: str | None = None,
) -> str:
    key_payload = {
        "scope": user_scope or "global",
        "params": _normalize_params(params),
    }
    digest = hashlib.sha256(
        json.dumps(key_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return f"{_cache_prefix()}:{namespace}:{digest}"


def get_cached_json(cache_key: str) -> Any | None:
    client = get_redis_client()
    if client is None:
        return None
    try:
        payload = client.get(cache_key)
        if payload is None:
            return None
        return json.loads(payload)
    except Exception:
        return None


def set_cached_json(cache_key: str, payload: Any, ttl_seconds: int | None = None) -> None:
    client = get_redis_client()
    if client is None:
        return
    ttl = int(ttl_seconds or current_app.config.get("CACHE_DEFAULT_TTL_SECONDS", 120))
    try:
        client.setex(cache_key, max(ttl, 1), json.dumps(payload, separators=(",", ":")))
    except Exception:
        return


def load_cached_json(
    namespace: str,
    params: Mapping[str, Any] | None,
    ttl_seconds: int,
    loader: Callable[[], Any],
    user_scope: str | None = None,
) -> tuple[Any, bool]:
    if not is_cache_enabled():
        return loader(), False

    cache_key = build_cache_key(namespace=namespace, params=params, user_scope=user_scope)
    cached_payload = get_cached_json(cache_key)
    if cached_payload is not None:
        return cached_payload, True

    payload = loader()
    set_cached_json(cache_key, payload, ttl_seconds=ttl_seconds)
    return payload, False


def invalidate_cache_namespace(namespace: str) -> int:
    client = get_redis_client()
    if client is None:
        return 0
    pattern = f"{_cache_prefix()}:{namespace}:*"
    keys_batch: list[str] = []
    deleted = 0
    try:
        for key in client.scan_iter(match=pattern, count=200):
            keys_batch.append(key)
            if len(keys_batch) >= 200:
                deleted += client.delete(*keys_batch)
                keys_batch.clear()
        if keys_batch:
            deleted += client.delete(*keys_batch)
    except Exception:
        return 0
    return deleted


def invalidate_cache_namespaces(*namespaces: str) -> int:
    return sum(invalidate_cache_namespace(namespace) for namespace in namespaces)
