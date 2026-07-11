from __future__ import annotations

import logging
import time

import anthropic

from config import settings

logger = logging.getLogger(__name__)

_MAX_RETRIES = 4
_BACKOFF_BASE_SECONDS = 1.5


class ClaudeClient:
    def __init__(self, api_key: str | None = None, model: str | None = None):
        self.api_key = api_key or settings.anthropic_api_key
        self.model = model or settings.claude_model
        if not self.api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Copy .env.example to .env and add your key."
            )
        self._client = anthropic.Anthropic(api_key=self.api_key)

    def create_message(self, **kwargs) -> anthropic.types.Message:
        """Call messages.create with retry on transient errors
        (rate limits, overloaded, connection resets)."""
        kwargs.setdefault("model", self.model)
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return self._client.messages.create(**kwargs)
            except (anthropic.RateLimitError, anthropic.APIConnectionError, anthropic.InternalServerError) as exc:
                last_exc = exc
                wait = _BACKOFF_BASE_SECONDS ** attempt
                logger.warning("Claude API transient error (attempt %d/%d): %s. Retrying in %.1fs",
                                attempt, _MAX_RETRIES, exc, wait)
                time.sleep(wait)
            except anthropic.APIStatusError:
                raise
        raise RuntimeError(f"Claude API failed after {_MAX_RETRIES} retries") from last_exc
