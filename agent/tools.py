from __future__ import annotations

import base64
import io
import logging
from dataclasses import dataclass

from PIL import Image, ImageStat

logger = logging.getLogger(__name__)

try:
    import pytesseract
    _OCR_AVAILABLE = True
except ImportError:  # pytesseract / tesseract binary not installed
    _OCR_AVAILABLE = False


@dataclass
class ImageContext:
    """Wraps the working image so tools can share state without
    passing raw bytes through the LLM context on every call."""

    image: Image.Image

    @classmethod
    def from_bytes(cls, data: bytes) -> "ImageContext":
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGB")
        return cls(image=img)

    def to_base64(self, img: Image.Image | None = None, max_dim: int = 1568) -> str:
        target = img or self.image
        target = _resize_if_needed(target, max_dim)
        buf = io.BytesIO()
        target.save(buf, format="JPEG", quality=90)
        return base64.b64encode(buf.getvalue()).decode("utf-8")


def _resize_if_needed(img: Image.Image, max_dim: int) -> Image.Image:
    w, h = img.size
    if max(w, h) <= max_dim:
        return img
    scale = max_dim / max(w, h)
    return img.resize((int(w * scale), int(h * scale)))


# ---------------------------------------------------------------------------
# Tool: crop_and_zoom
# ---------------------------------------------------------------------------

def crop_and_zoom(ctx: ImageContext, x: float, y: float, width: float, height: float) -> dict:
    """Crop a normalized region (0-1 coordinates) of the image and
    return it as base64 so the agent can inspect fine detail — small
    text, faces, logos — that gets lost when the full image is
    downsampled."""
    w, h = ctx.image.size
    box = (
        max(0, int(x * w)),
        max(0, int(y * h)),
        min(w, int((x + width) * w)),
        min(h, int((y + height) * h)),
    )
    if box[2] <= box[0] or box[3] <= box[1]:
        return {"error": "invalid crop region"}
    cropped = ctx.image.crop(box)
    return {"image_base64": ctx.to_base64(cropped), "region": box}


CROP_AND_ZOOM_SCHEMA = {
    "name": "crop_and_zoom",
    "description": (
        "Crop and zoom into a region of the image to inspect fine detail "
        "(small text, faces, distant objects). Coordinates are normalized "
        "0-1 fractions of image width/height."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "x": {"type": "number", "description": "Left edge, 0-1"},
            "y": {"type": "number", "description": "Top edge, 0-1"},
            "width": {"type": "number", "description": "Width, 0-1"},
            "height": {"type": "number", "description": "Height, 0-1"},
        },
        "required": ["x", "y", "width", "height"],
    },
}


# ---------------------------------------------------------------------------
# Tool: extract_text_ocr
# ---------------------------------------------------------------------------

def extract_text_ocr(ctx: ImageContext) -> dict:
    """Run OCR over the full image. Used when the agent suspects the
    image contains meaningful text (screenshots, signage, memes,
    slides) that must be transcribed verbatim for accessibility."""
    if not _OCR_AVAILABLE:
        return {"available": False, "text": "", "note": "pytesseract/tesseract not installed in this environment"}
    try:
        text = pytesseract.image_to_string(ctx.image).strip()
    except Exception as exc:  # tesseract binary missing at runtime, etc.
        logger.warning("OCR failed: %s", exc)
        return {"available": False, "text": "", "note": str(exc)}
    return {"available": True, "text": text}


EXTRACT_TEXT_OCR_SCHEMA = {
    "name": "extract_text_ocr",
    "description": "Run OCR on the full image to extract any embedded text verbatim.",
    "input_schema": {"type": "object", "properties": {}},
}


# ---------------------------------------------------------------------------
# Tool: get_image_metadata
# ---------------------------------------------------------------------------

def get_image_metadata(ctx: ImageContext) -> dict:
    """Return basic technical metadata (dimensions, aspect ratio,
    average brightness) — useful for the agent to decide, e.g., 'this
    is a very wide banner, likely decorative' vs 'this is a tall
    infographic, likely needs a long_description'."""
    w, h = ctx.image.size
    stat = ImageStat.Stat(ctx.image.convert("L"))
    return {
        "width": w,
        "height": h,
        "aspect_ratio": round(w / h, 3) if h else None,
        "avg_brightness_0_255": round(stat.mean[0], 1),
    }


GET_IMAGE_METADATA_SCHEMA = {
    "name": "get_image_metadata",
    "description": "Get width, height, aspect ratio, and average brightness of the image.",
    "input_schema": {"type": "object", "properties": {}},
}


# ---------------------------------------------------------------------------
# Tool: wcag_lint
# ---------------------------------------------------------------------------

_REDUNDANT_PHRASES = (
    "image of", "picture of", "photo of", "graphic of", "icon of", "this is an image",
)


def wcag_lint(alt_text: str) -> dict:
    """Static accessibility lint against WCAG 2.2 / WAI alt-text
    guidance: flags redundant phrasing, excessive length, and missing
    content. The agent is expected to call this on its own draft
    before finalizing, then fix anything flagged."""
    issues = []
    length = len(alt_text)
    if length == 0:
        issues.append("alt_text is empty")
    if length > 150:
        issues.append(f"alt_text is {length} chars; WCAG guidance favors concise text (~125 chars)")
    lowered = alt_text.lower()
    for phrase in _REDUNDANT_PHRASES:
        if lowered.startswith(phrase):
            issues.append(f"starts with redundant phrase '{phrase}' — screen readers already announce 'image'")
    if alt_text.strip().endswith("."):
        issues.append("trailing period is unnecessary for short alt text (screen reader adds a pause)")
    return {"length": length, "issues": issues, "passes": len(issues) == 0}


WCAG_LINT_SCHEMA = {
    "name": "wcag_lint",
    "description": "Lint a draft alt_text string against WCAG accessibility conventions. Call this before finalizing.",
    "input_schema": {
        "type": "object",
        "properties": {"alt_text": {"type": "string"}},
        "required": ["alt_text"],
    },
}


TOOL_SCHEMAS = [
    CROP_AND_ZOOM_SCHEMA,
    EXTRACT_TEXT_OCR_SCHEMA,
    GET_IMAGE_METADATA_SCHEMA,
    WCAG_LINT_SCHEMA,
]


def dispatch_tool(ctx: ImageContext, name: str, tool_input: dict) -> dict:
    """Route a tool_use block from Claude to the matching Python function."""
    if name == "crop_and_zoom":
        return crop_and_zoom(ctx, **tool_input)
    if name == "extract_text_ocr":
        return extract_text_ocr(ctx)
    if name == "get_image_metadata":
        return get_image_metadata(ctx)
    if name == "wcag_lint":
        return wcag_lint(**tool_input)
    return {"error": f"unknown tool '{name}'"}
