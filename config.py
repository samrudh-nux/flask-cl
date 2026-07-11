import os
from dataclasses import dataclass, field


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    claude_model: str = field(default_factory=lambda: os.getenv("CLAUDE_MODEL", "claude-sonnet-5"))

    # Agent behaviour
    max_agent_iterations: int = field(default_factory=lambda: int(os.getenv("MAX_AGENT_ITERATIONS", "6")))
    agent_temperature: float = field(default_factory=lambda: float(os.getenv("AGENT_TEMPERATURE", "0.2")))

    # Image constraints
    max_upload_mb: int = field(default_factory=lambda: int(os.getenv("MAX_UPLOAD_MB", "10")))
    max_image_dimension: int = field(default_factory=lambda: int(os.getenv("MAX_IMAGE_DIMENSION", "1568")))
    allowed_extensions: frozenset = frozenset({"png", "jpg", "jpeg", "gif", "webp"})

    # Ops
    enable_cache: bool = field(default_factory=lambda: _bool("ENABLE_CACHE", True))
    cache_ttl_seconds: int = field(default_factory=lambda: int(os.getenv("CACHE_TTL_SECONDS", "3600")))
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "20")))
    log_level: str = field(default_factory=lambda: os.getenv("LOG_LEVEL", "INFO"))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "5000")))


settings = Settings()
