from __future__ import annotations

import hashlib
import logging
import time
from collections import defaultdict, deque

from flask import Blueprint, jsonify, request

from agent import AltTextAgent
from config import settings
from services.image_utils import InvalidImageError, validate_and_load

logger = logging.getLogger(__name__)
bp = Blueprint("api", __name__)

_agent: AltTextAgent | None = None


def get_agent() -> AltTextAgent:
    """Lazily construct the agent so the app can boot (and health checks
    can pass) even before ANTHROPIC_API_KEY is configured; the key is
    only required once someone actually requests generation."""
    global _agent
    if _agent is None:
        _agent = AltTextAgent()
    return _agent


# --- tiny in-process cache & rate limiter -----------------------------
# Good enough for a single-instance deployment / portfolio project.
# Swap for Redis if you scale this horizontally.
_cache: dict[str, tuple[float, dict]] = {}
_request_log: dict[str, deque] = defaultdict(deque)


def _rate_limited(client_id: str) -> bool:
    now = time.time()
    window = _request_log[client_id]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= settings.rate_limit_per_minute:
        return True
    window.append(now)
    return False


def _cache_get(key: str) -> dict | None:
    if not settings.enable_cache:
        return None
    entry = _cache.get(key)
    if not entry:
        return None
    ts, value = entry
    if time.time() - ts > settings.cache_ttl_seconds:
        _cache.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: dict) -> None:
    if settings.enable_cache:
        _cache[key] = (time.time(), value)


@bp.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@bp.route("/api/alt-text", methods=["POST"])
def generate_alt_text():
    client_id = request.headers.get("X-Client-Id", request.remote_addr or "anonymous")
    if _rate_limited(client_id):
        return jsonify({"error": "rate limit exceeded", "limit_per_minute": settings.rate_limit_per_minute}), 429

    if "image" not in request.files:
        return jsonify({"error": "multipart field 'image' is required"}), 400

    file = request.files["image"]
    data = file.read()
    if not data:
        return jsonify({"error": "empty file"}), 400

    context_hint = request.form.get("context_hint")
    tone = request.form.get("tone", "neutral")

    cache_key = hashlib.sha256(data + tone.encode() + (context_hint or "").encode()).hexdigest()
    cached = _cache_get(cache_key)
    if cached:
        return jsonify({**cached, "cached": True})

    try:
        image = validate_and_load(data, filename=file.filename or "")
    except InvalidImageError as exc:
        return jsonify({"error": str(exc)}), 400

    try:
        result = get_agent().run(image, context_hint=context_hint, tone=tone)
    except RuntimeError as exc:
        logger.exception("Agent run failed")
        return jsonify({"error": "generation failed", "detail": str(exc)}), 502

    payload = result.model_dump()
    _cache_set(cache_key, payload)
    return jsonify({**payload, "cached": False})
