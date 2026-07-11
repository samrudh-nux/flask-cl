from __future__ import annotations

import logging
import time

from PIL import Image

from config import settings
from services.claude_client import ClaudeClient
from .prompts import SYSTEM_PROMPT, build_user_prompt
from .schemas import AltTextResult, TraceStep
from .tools import TOOL_SCHEMAS, ImageContext, dispatch_tool

logger = logging.getLogger(__name__)

SUBMIT_TOOL_SCHEMA = {
    "name": "submit_alt_text",
    "description": "Submit the final, WCAG-lint-clean alt text. Call exactly once, as the last action.",
    "input_schema": {
        "type": "object",
        "properties": {
            "alt_text": {"type": "string"},
            "long_description": {"type": ["string", "null"]},
            "detected_text": {"type": ["string", "null"]},
            "image_category": {
                "type": "string",
                "enum": ["photo", "illustration", "screenshot", "chart_or_graph",
                         "diagram", "document_or_text", "meme", "icon_or_logo", "other"],
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "wcag_notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["alt_text", "image_category", "confidence"],
    },
}


class AgentTimeoutError(RuntimeError):
    pass


class AltTextAgent:
    def __init__(self, client: ClaudeClient | None = None):
        self.client = client or ClaudeClient()

    def run(self, image: Image.Image, context_hint: str | None = None, tone: str = "neutral") -> AltTextResult:
        ctx = ImageContext(image=image)
        trace: list[TraceStep] = []

        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/jpeg",
                            "data": ctx.to_base64(max_dim=settings.max_image_dimension),
                        },
                    },
                    {"type": "text", "text": build_user_prompt(context_hint, tone)},
                ],
            }
        ]

        tools = TOOL_SCHEMAS + [SUBMIT_TOOL_SCHEMA]
        start = time.monotonic()

        for iteration in range(1, settings.max_agent_iterations + 1):
            response = self.client.create_message(
                system=SYSTEM_PROMPT,
                max_tokens=1536,
                temperature=settings.agent_temperature,
                tools=tools,
                messages=messages,
            )

            tool_uses = [block for block in response.content if block.type == "tool_use"]
            text_blocks = [block.text for block in response.content if block.type == "text"]
            if text_blocks:
                trace.append(TraceStep(step=iteration, action="reasoning", detail=" ".join(text_blocks)[:400]))

            submit_block = next((b for b in tool_uses if b.name == "submit_alt_text"), None)
            if submit_block:
                trace.append(TraceStep(step=iteration, action="submit", detail="final answer submitted"))
                result = AltTextResult(**submit_block.input, trace=trace)
                logger.info("Agent finished in %.2fs, %d iterations", time.monotonic() - start, iteration)
                return result

            if not tool_uses:
                # Model stopped without submitting — nudge it once rather
                # than silently returning nothing useful.
                messages.append({"role": "assistant", "content": response.content})
                messages.append({
                    "role": "user",
                    "content": "Please call submit_alt_text now with your best final answer.",
                })
                continue

            # Execute every requested tool and feed results back.
            messages.append({"role": "assistant", "content": response.content})
            tool_results = []
            for block in tool_uses:
                trace.append(TraceStep(step=iteration, action=f"tool:{block.name}", detail=str(block.input)[:200]))
                output = dispatch_tool(ctx, block.name, block.input)
                content = self._tool_result_content(block.name, output)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": content,
                })
            messages.append({"role": "user", "content": tool_results})

        # Safety valve: max iterations hit without a submission.
        logger.warning("Agent hit max_agent_iterations (%d) without submitting", settings.max_agent_iterations)
        trace.append(TraceStep(step=settings.max_agent_iterations, action="fallback",
                                detail="max iterations reached without submit_alt_text"))
        return AltTextResult(
            alt_text="Unable to confidently generate alt text for this image.",
            image_category="other",
            confidence=0.0,
            wcag_notes=["Agent exceeded max iterations without a final submission."],
            trace=trace,
        )

    @staticmethod
    def _tool_result_content(tool_name: str, output: dict) -> list[dict]:
        """crop_and_zoom returns an image; feed it back as an image block
        so the agent can actually see the zoomed region. Other tools
        return plain JSON-as-text."""
        if tool_name == "crop_and_zoom" and "image_base64" in output:
            return [
                {"type": "text", "text": f"Cropped region {output.get('region')}"},
                {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                              "data": output["image_base64"]}},
            ]
        return [{"type": "text", "text": str(output)}]
