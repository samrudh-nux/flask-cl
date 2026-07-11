from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class TraceStep(BaseModel):
    """One step in the agent's reasoning/tool-use trace, kept for
    transparency and debugging (surfaced via the API as `trace`)."""

    step: int
    action: str
    detail: str


class AltTextResult(BaseModel):
    """Final structured output the agent must produce."""

    alt_text: str = Field(..., description="Concise WCAG-friendly alt text, <= 125 chars ideally")
    long_description: str | None = Field(
        default=None,
        description="Optional extended description for complex images (charts, infographics, screenshots)",
    )
    detected_text: str | None = Field(
        default=None, description="Verbatim text found inside the image, if any (e.g. signage, UI, memes)"
    )
    image_category: Literal[
        "photo", "illustration", "screenshot", "chart_or_graph", "diagram",
        "document_or_text", "meme", "icon_or_logo", "other",
    ] = "other"
    confidence: float = Field(..., ge=0.0, le=1.0)
    wcag_notes: list[str] = Field(default_factory=list, description="Self-critique notes from the verify step")
    trace: list[TraceStep] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class AgentRequest(BaseModel):
    context_hint: str | None = Field(
        default=None,
        description="Optional caller-supplied context, e.g. surrounding page copy or intended use",
    )
    tone: Literal["neutral", "seo", "editorial"] = "neutral"
