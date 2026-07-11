# 🖼️ Alt-Text Agent

**An agentic, tool-using AI service that writes WCAG-grade alt text for images — not a single captioning call, but a Claude-powered agent that plans, inspects, self-critiques, and refines before it commits to an answer.**

[![CI](https://github.com/samrudh-nux/alt-text-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/samrudh-nux/alt-text-agent/actions/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Powered by Claude](https://img.shields.io/badge/powered%20by-Claude-6ea8fe.svg)](https://www.anthropic.com)

---

## Why this exists

Most "alt text generator" projects are a single call to a vision model: `image in → caption out`. That's fine for a demo, but it fails the cases that actually matter for accessibility:

- Screenshots and memes where the **text in the image** is the content
- Charts/infographics where a one-line caption throws away the data
- Small but load-bearing detail (a warning icon, a price tag, a face) that gets lost when the image is downsampled for the model

**Alt-Text Agent** treats this as an agentic problem instead. Given an image, Claude decides for itself — turn by turn, using real tools — whether it needs to zoom into a region, run OCR, check image metadata, or lint its own draft against WCAG conventions, before it's allowed to submit a final answer.

## How the agent works

```mermaid
flowchart TD
    A[Image upload] --> B[Agent loop starts]
    B --> C{Claude reasons:<br/>what does this image need?}
    C -->|small text / detail unclear| D[crop_and_zoom]
    C -->|likely contains text| E[extract_text_ocr]
    C -->|orientation/size matters| F[get_image_metadata]
    D --> C
    E --> C
    F --> C
    C -->|has a draft| G[wcag_lint self-critique]
    G -->|issues found| C
    G -->|clean| H[submit_alt_text]
    H --> I[Structured result:<br/>alt_text, long_description,<br/>detected_text, confidence, trace]
```

The loop is capped at `MAX_AGENT_ITERATIONS` (default 6) as a safety valve, and every tool call is recorded in a `trace` returned alongside the answer — so you can see *why* the agent wrote what it wrote, not just the output.

### Tools available to the agent

| Tool | Purpose |
|---|---|
| `crop_and_zoom` | Inspect a region of the image at full resolution (small text, faces, distant objects) |
| `extract_text_ocr` | Transcribe embedded text verbatim (screenshots, slides, signage, memes) |
| `get_image_metadata` | Dimensions, aspect ratio, brightness — informs categorization |
| `wcag_lint` | Static accessibility lint the agent runs on its **own draft** before submitting |

## Quickstart

```bash
git clone https://github.com/samrudh-nux/alt-text-agent.git
cd alt-text-agent
cp .env.example .env   # add your ANTHROPIC_API_KEY

pip install -r requirements.txt
python app.py
# → http://localhost:5000
```

Or with Docker:

```bash
docker compose up --build
```

## API

### `POST /api/alt-text`

`multipart/form-data`:

| Field | Required | Description |
|---|---|---|
| `image` | yes | Image file (png/jpg/jpeg/gif/webp, ≤ 10MB by default) |
| `context_hint` | no | Free-text context, e.g. `"hero image on pricing page"` |
| `tone` | no | `neutral` \| `seo` \| `editorial` (default `neutral`) |

```bash
curl -X POST http://localhost:5000/api/alt-text \
  -F "image=@examples/chart.png" \
  -F "context_hint=Q3 revenue chart in an investor deck" \
  -F "tone=editorial"
```

```json
{
  "alt_text": "Bar chart showing Q3 revenue up 34% quarter over quarter",
  "long_description": "Bar chart with four quarters on the x-axis and revenue in USD millions on the y-axis. Q1: 2.1M, Q2: 2.8M, Q3: 3.75M, Q4 (projected): 4.2M. Q3 marks the steepest single-quarter increase in the series.",
  "detected_text": "Q1 Q2 Q3 Q4 (proj.) Revenue (USD M)",
  "image_category": "chart_or_graph",
  "confidence": 0.91,
  "wcag_notes": [],
  "trace": [
    {"step": 1, "action": "tool:get_image_metadata", "detail": "{}"},
    {"step": 1, "action": "tool:extract_text_ocr", "detail": "{}"},
    {"step": 2, "action": "tool:wcag_lint", "detail": "{'alt_text': '...'}"},
    {"step": 2, "action": "submit", "detail": "final answer submitted"}
  ],
  "cached": false
}
```

### `GET /health`

Liveness check, returns `{"status": "ok"}`.

## Design decisions worth knowing about

- **Structured output via tool use, not prompt parsing.** The final answer is a `submit_alt_text` tool call validated through Pydantic — no regexing JSON out of free text.
- **The agent lints itself.** `wcag_lint` is exposed as a tool, not a post-processing step, so the model can iterate on its own draft before it ever reaches the API response.
- **Zoom feeds back as an image, not a description.** When the agent calls `crop_and_zoom`, the cropped region is returned as a real image block in the next turn — the model actually *sees* the detail it asked for.
- **Graceful OCR degradation.** If `tesseract` isn't installed in the environment, `extract_text_ocr` reports itself unavailable instead of crashing the loop.
- **Cache + rate limit are in-process by design** (see `api/routes.py`) — enough for a single instance / portfolio deployment; swap in Redis if you need to scale horizontally.

## Project structure

```
alt-text-agent/
├── app.py                  # Flask app factory + entrypoint
├── config.py                # Env-driven settings
├── agent/
│   ├── orchestrator.py      # The agentic loop
│   ├── tools.py              # Tool implementations + JSON schemas
│   ├── prompts.py            # System/user prompts
│   └── schemas.py            # Pydantic contracts (AltTextResult, etc.)
├── services/
│   ├── claude_client.py      # Anthropic SDK wrapper w/ retry
│   └── image_utils.py        # Upload validation
├── api/routes.py             # Flask blueprint (/api/alt-text, /health)
├── static/index.html         # Zero-build demo UI
├── tests/                    # pytest suite (agent + routes)
└── .github/workflows/ci.yml  # Lint + test + docker build on every PR
```

## Testing

```bash
pip install -r requirements-dev.txt
pytest -v
ruff check .
```

The agent tests mock the Claude client entirely (`tests/test_agent.py`), so the suite runs in milliseconds with no API key or network access required — CI included.

## Roadmap

- [ ] Batch endpoint for processing an image directory / sitemap crawl
- [ ] Pluggable model backend (swap Claude for a local VLM via the same tool interface)
- [ ] Browser extension: right-click any image on the web → generate alt text
- [ ] Persistent cache (Redis) + multi-instance rate limiting

## License

MIT — see [LICENSE](LICENSE).
