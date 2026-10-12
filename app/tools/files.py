"""Tools that create downloadable artifacts: documents, spreadsheets, slides, charts and images.

Files are stored as private attachments of the requesting employee and shown in the chat as download cards.
"""
import asyncio
import base64
import logging

import httpx
from openai import AsyncOpenAI

from ..attachments import store_generated
from ..config import Settings, get_llm_profile
from ..db import Database
from ..files.generator import CHART_TYPES, FORMATS, build_chart, build_file, safe_filename
from .base import Tool, ToolContext

log = logging.getLogger(__name__)
MAX_CONTENT_CHARS = 200_000


def _artifact(ctx: ToolContext, stored: dict, kind: str, title: str) -> dict:
    art = {"type": kind, "id": stored["id"], "name": stored["name"], "mime": stored["mime"],
           "size_bytes": stored["size_bytes"], "title": title, "url": f"/api/files/{stored['id']}"}
    ctx.artifacts.append(art)
    return art


class CreateFileTool(Tool):
    def __init__(self, settings: Settings, db: Database):
        super().__init__(
            name="create_file",
            label="Creating file",
            kind="files",
            description=(
                "Create a downloadable file for the user: pdf, docx (Word), pptx (PowerPoint), xlsx (Excel), csv, "
                "txt, md, html or json. Use when the user asks to create, export, download, draft or save something "
                "as a file/document/report/sheet/presentation. Write the COMPLETE final content (never placeholders). "
                "For pdf/docx/txt/md/html pass Markdown in `content` (headings, lists, tables). For pptx use one "
                "`## Slide title` per slide followed by bullet points. For xlsx/csv pass `columns` + `rows` "
                "(or `sheets` for several sheets). After creating, tell the user briefly what the file contains; "
                "the download card is shown automatically, so do not write links."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "format": {"type": "string", "enum": list(FORMATS)},
                    "filename": {"type": "string", "description": "File name without extension, e.g. 'Q3 sales report'."},
                    "title": {"type": "string", "description": "Document title shown at the top."},
                    "content": {"type": "string", "description": "Full Markdown content (documents / slides / text)."},
                    "columns": {"type": "array", "items": {"type": "string"}, "description": "Table header (xlsx/csv/json)."},
                    "rows": {"type": "array", "items": {"type": "array", "items": {"type": "string"}},
                             "description": "Table rows, each an array of cell values aligned with columns."},
                    "sheets": {"type": "array", "description": "xlsx only: several sheets.",
                               "items": {"type": "object", "properties": {
                                   "name": {"type": "string"},
                                   "columns": {"type": "array", "items": {"type": "string"}},
                                   "rows": {"type": "array",
                                            "items": {"type": "array", "items": {"type": "string"}}}}}},
                },
                "required": ["format", "filename"],
            },
        )
        self.s = settings
        self.db = db

    def available_for(self, user) -> bool:
        return self.s.file_generation_enabled

    def status_text(self, args: dict) -> str:
        return f"Creating {str(args.get('format', 'file')).upper()} \u201c{args.get('filename', '')}\u201d"

    async def run(self, args: dict, ctx: ToolContext) -> str:
        fmt = str(args.get("format", "")).lower()
        if fmt not in FORMATS:
            return f"Error: format must be one of {', '.join(FORMATS)}."
        content = str(args.get("content") or "")[:MAX_CONTENT_CHARS]
        columns, rows, sheets = args.get("columns"), args.get("rows"), args.get("sheets")
        if not content and not rows and not sheets:
            return "Error: provide `content` (Markdown) or `columns`/`rows`."
        title = str(args.get("title") or args.get("filename") or "Document")[:200]
        name = safe_filename(str(args.get("filename") or title), fmt)
        try:
            data = await asyncio.to_thread(build_file, fmt, title=title, content=content, columns=columns,
                                           rows=rows, sheets=sheets)
        except ImportError as exc:
            return f"Error: the server is missing a library for {fmt} files ({exc.name}). Tell the user."
        except Exception as exc:
            log.exception("create_file failed")
            return f"Error: could not build the {fmt} file ({type(exc).__name__}: {str(exc)[:200]})."
        stored = await asyncio.to_thread(store_generated, self.s, self.db, user_id=ctx.user.id,
                                         conversation_id=ctx.conversation_id, filename=name, data=data,
                                         mime=FORMATS[fmt], source_text=content or None)
        _artifact(ctx, stored, "file", title)
        return f"File created: {name} ({len(data):,} bytes). The user can preview/download it from the card below your answer."


class CreateChartTool(Tool):
    def __init__(self, settings: Settings, db: Database):
        super().__init__(
            name="create_chart",
            label="Drawing chart",
            kind="files",
            description=(
                "Draw a chart image (PNG) from numeric data: bar, barh, stacked_bar, line, area, pie, donut, scatter. "
                "Use when the user asks for a chart/graph/plot/visualisation, or when data is clearer as a chart. "
                "Only plot numbers that come from the conversation or tool results, never invented data."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "chart_type": {"type": "string", "enum": list(CHART_TYPES)},
                    "title": {"type": "string"},
                    "labels": {"type": "array", "items": {"type": "string"},
                               "description": "Category / x-axis labels."},
                    "series": {"type": "array", "description": "One or more data series aligned with labels.",
                               "items": {"type": "object", "properties": {
                                   "name": {"type": "string"},
                                   "values": {"type": "array", "items": {"type": "number"}}},
                                   "required": ["values"]}},
                    "x_label": {"type": "string"},
                    "y_label": {"type": "string"},
                },
                "required": ["chart_type", "title", "labels", "series"],
            },
        )
        self.s = settings
        self.db = db

    def available_for(self, user) -> bool:
        return self.s.file_generation_enabled

    def status_text(self, args: dict) -> str:
        return f"Drawing chart \u201c{args.get('title', '')}\u201d"

    async def run(self, args: dict, ctx: ToolContext) -> str:
        chart_type = args.get("chart_type") if args.get("chart_type") in CHART_TYPES else "bar"
        labels, series = args.get("labels") or [], args.get("series") or []
        if not labels or not series:
            return "Error: labels and series are required."
        title = str(args.get("title") or "Chart")[:200]
        try:
            png = await asyncio.to_thread(build_chart, chart_type=chart_type, title=title, labels=labels,
                                          series=series, x_label=str(args.get("x_label") or ""),
                                          y_label=str(args.get("y_label") or ""))
        except ImportError:
            return "Error: charting library (matplotlib) is not installed on the server."
        except (TypeError, ValueError) as exc:
            return f"Error: invalid chart data ({exc})."
        stored = await asyncio.to_thread(store_generated, self.s, self.db, user_id=ctx.user.id,
                                         conversation_id=ctx.conversation_id,
                                         filename=safe_filename(title, "png", "chart"), data=png, mime="image/png",
                                         source_text=None)
        _artifact(ctx, stored, "image", title)
        return "Chart created and displayed to the user below your answer. Summarise the key insight in 1-2 sentences."


class GenerateImageTool(Tool):
    """Text-to-image through an OpenAI-compatible images API (OpenAI gpt-image-1 / dall-e-3, or compatible)."""

    def __init__(self, settings: Settings, db: Database, http: httpx.AsyncClient):
        super().__init__(
            name="generate_image",
            label="Generating image",
            kind="files",
            description=(
                "Generate an image (illustration, photo-style picture, logo concept, poster, icon) from a text "
                "description. Write a detailed visual prompt in English. Not for charts of data (use create_chart)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Detailed description of the image."},
                    "size": {"type": "string", "enum": ["1024x1024", "1536x1024", "1024x1536"]},
                },
                "required": ["prompt"],
            },
        )
        self.s = settings
        self.db = db
        self.http = http
        profile = get_llm_profile()
        mode = settings.image_generation.lower()
        key = settings.image_api_key or (settings.llm_api_key if profile.provider == "openai" or mode == "on" else "")
        self.enabled = mode not in ("off", "none") and bool(key or settings.image_base_url)
        base_url = settings.image_base_url or (None if settings.image_api_key else profile.base_url or None)
        self.client = AsyncOpenAI(api_key=key or "local-no-key", base_url=base_url,
                                  timeout=httpx.Timeout(120, connect=5), max_retries=1) if self.enabled else None

    def available_for(self, user) -> bool:
        return self.enabled

    def status_text(self, args: dict) -> str:
        return "Generating image"

    async def run(self, args: dict, ctx: ToolContext) -> str:
        prompt = str(args.get("prompt", "")).strip()[:3000]
        if not prompt:
            return "Error: prompt is required."
        size = args.get("size") if args.get("size") in ("1024x1024", "1536x1024", "1024x1536") else "1024x1024"
        kwargs = {"model": self.s.image_model, "prompt": prompt, "n": 1, "size": size}
        if self.s.image_model.startswith("dall-e"):
            kwargs["response_format"] = "b64_json"
            kwargs["size"] = {"1536x1024": "1792x1024", "1024x1536": "1024x1792"}.get(size, size)
        try:
            resp = await self.client.images.generate(**kwargs)
        except Exception as exc:
            log.warning("Image generation failed: %s", exc)
            return f"Error: image generation failed ({type(exc).__name__}). Tell the user to try a different prompt."
        item = resp.data[0]
        if getattr(item, "b64_json", None):
            data = base64.b64decode(item.b64_json)
        elif getattr(item, "url", None):
            r = await self.http.get(item.url, timeout=30)
            r.raise_for_status()
            data = r.content
        else:
            return "Error: the image service returned no image."
        stored = await asyncio.to_thread(store_generated, self.s, self.db, user_id=ctx.user.id,
                                         conversation_id=ctx.conversation_id,
                                         filename=safe_filename(prompt[:40], "png", "image"), data=data,
                                         mime="image/png", source_text=prompt)
        _artifact(ctx, stored, "image", prompt[:80])
        return "Image generated and displayed to the user. Describe it in one short sentence; do not add links."
