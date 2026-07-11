"""Validation and preprocessing for uploaded images."""
from __future__ import annotations

from PIL import Image, UnidentifiedImageError
import io

from config import settings


class InvalidImageError(ValueError):
    pass


def validate_and_load(data: bytes, filename: str = "") -> Image.Image:
    if filename:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in settings.allowed_extensions:
            raise InvalidImageError(
                f"Unsupported extension '.{ext}'. Allowed: {sorted(settings.allowed_extensions)}"
            )

    size_mb = len(data) / (1024 * 1024)
    if size_mb > settings.max_upload_mb:
        raise InvalidImageError(f"File is {size_mb:.1f}MB, exceeds limit of {settings.max_upload_mb}MB")

    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except UnidentifiedImageError as exc:
        raise InvalidImageError("File is not a valid/readable image") from exc

    return img.convert("RGB")
