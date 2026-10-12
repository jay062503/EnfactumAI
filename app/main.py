import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import quote

import httpx
import yaml
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .agent import Agent
from .attachments import ATTACHMENT_EXTENSIONS, save_attachment
from .auth import AuthService, UserContext
from .config import BASE_DIR, csv_list, get_settings
from .db import Database
from .files.generator import FORMATS, build_file, safe_filename
from .llm import LLM, VisionReader
from .rag.embeddings import Embedder
from .rag.extract import Extractor
from .rag.index import DocumentIndex, can_view
from .rag.ingest import Ingestor, kb_extensions
from .rag.parsers import UnsupportedDocument
from .runs import ConversationBusy, RunManager
from .security import RateLimiter, SecurityHeadersMiddleware
from .tools.actions import ActionService, load_action_tools
from .tools.db_query import load_db_tools
from .tools.documents import DocumentSearchTool
from .tools.files import CreateChartTool, CreateFileTool, GenerateImageTool
from .tools.os_api import load_os_tools
from .tools.registry import MODES, ToolRegistry
from .tools.web_search import WebSearchTool

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("enfactum")
settings = get_settings()
STATIC_DIR = BASE_DIR / "static"
DEFAULT_PREFS = {
    "theme": "system",            # system | light | dark
    "default_mode": "auto",       # auto | general | web | company
    "enter_to_send": True,
    "show_context_meter": True,
    "show_timing": True,
    "response_length": "balanced",  # concise | balanced | detailed
    "about_me": "",
    "response_instructions": "",
}
PREF_CHOICES = {"theme": {"system", "light", "dark"}, "default_mode": set(MODES),
                "response_length": {"concise", "balanced", "detailed"}}


@asynccontextmanager
async def lifespan(app: FastAPI):
    http = httpx.AsyncClient(verify=settings.os_verify_ssl, limits=httpx.Limits(max_connections=100))
    db = Database(settings.data_dir / "assistant.db")
    llm = LLM(settings)
    extractor = Extractor(settings, VisionReader(settings, llm))
    embedder = Embedder(settings)
    index = DocumentIndex(db, embedder)
    index.reload()
    ingestor = Ingestor(settings, db, embedder, index, extractor)

    tools = [DocumentSearchTool(settings, index)]
    web = WebSearchTool(settings, http)
    if web.enabled:
        tools.insert(0, web)
    tools.extend(load_os_tools(settings, http))
    tools.extend(load_db_tools(settings))
    actions = load_action_tools(settings, db)
    tools.extend(actions)
    tools.extend([CreateFileTool(settings, db), CreateChartTool(settings, db), GenerateImageTool(settings, db, http)])
    registry = ToolRegistry(tools)

    app.state.db = db
    app.state.index = index
    app.state.ingestor = ingestor
    app.state.extractor = extractor
    app.state.registry = registry
    app.state.llm = llm
    app.state.auth = AuthService(settings, http)
    app.state.agent = Agent(settings, llm, registry, db)
    app.state.actions = ActionService(settings, db, http, actions)
    app.state.runs = RunManager()
    app.state.limiter = RateLimiter(settings.rate_limit_per_minute)

    if settings.seed_sample_docs and db.count_documents() == 0:
        await _seed_samples(ingestor)
    log.info("Ready: auth=%s tools=%s docs_chunks=%d", settings.auth_mode,
             [t.name for t in registry.all() if t.available_for(_SYSTEM)], index.size)
    yield
    await app.state.runs.shutdown()
    await http.aclose()


_SYSTEM = UserContext(id="system", name="system", roles=frozenset({"super_admin"}))

app = FastAPI(title=settings.app_name, version=__version__, lifespan=lifespan,
              docs_url=None if settings.is_production else "/api/docs", redoc_url=None)
app.add_middleware(SecurityHeadersMiddleware, frame_ancestors=" ".join(csv_list(settings.cors_origins)))
if settings.cors_origins:
    app.add_middleware(CORSMiddleware, allow_origins=csv_list(settings.cors_origins), allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
                       allow_headers=["Authorization", "Content-Type", "X-Demo-User"],
                       expose_headers=["Content-Disposition"])
if settings.mock_os_enabled:
    from .mock_os import build_router

    app.include_router(build_router(settings))


async def current_user(request: Request) -> UserContext:
    user = await request.app.state.auth.authenticate(request)
    if not user.allowed_in_app:
        raise HTTPException(403, "employees_only")
    if not user.can(settings.perm_chat or None):
        raise HTTPException(403, "You do not have access to the AI assistant")
    return user


def user_prefs(db: Database, user_id: str) -> dict:
    return {**DEFAULT_PREFS, **db.get_settings(user_id)}


def _disposition(name: str, download: bool) -> str:
    kind = "attachment" if download else "inline"
    ascii_name = name.encode("ascii", "replace").decode().replace('"', "")
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"


# ---------------------------------------------------------------------------------------------------------------
@app.get("/api/health")
async def health(request: Request):
    return {"status": "ok", "version": __version__, "indexed_chunks": request.app.state.index.size}


@app.get("/api/health/llm")
async def health_llm(request: Request, user: UserContext = Depends(current_user)):
    return await request.app.state.llm.check()


@app.get("/api/config")
async def public_config():
    return {"app_name": settings.app_name, "auth_mode": settings.auth_mode, "modes": list(MODES),
            "max_upload_mb": settings.max_upload_mb, "max_attachment_mb": settings.max_attachment_mb,
            "supported_extensions": sorted(kb_extensions()),
            "attachment_extensions": sorted(ATTACHMENT_EXTENSIONS),
            "trusted_origins": csv_list(settings.cors_origins),
            "cookie_auth": settings.auth_mode == "laravel" and settings.os_forward_cookies}


@app.get("/api/app-manifest")
async def app_manifest(request: Request):
    """Descriptor the Enfactum OS app launcher can read to add the assistant as an employee-only application tab."""
    base = str(request.base_url).rstrip("/")
    return {"id": "enfactum-ai-assistant", "name": settings.app_name, "version": __version__,
            "description": "AI assistant for Enfactum employees: answers from company knowledge, live OS data and "
                           "the web; reads files and images; creates documents, charts and confirmed OS actions.",
            "audience": csv_list(settings.allowed_user_types), "required_permission": settings.perm_chat or None,
            "entry_url": f"{base}/?embed=app", "widget_url": f"{base}/?embed=widget",
            "icon_url": f"{base}/static/icon.svg", "auth": settings.auth_mode}


@app.get("/api/me")
async def me(request: Request, user: UserContext = Depends(current_user)):
    tools = request.app.state.registry.for_user(user)
    names = {t.name for t in tools}
    profile = request.app.state.llm.profile
    return {"user": user.public(),
            "settings": user_prefs(request.app.state.db, user.id),
            "model": {"provider": profile.provider, "name": profile.model, "context_window": profile.context_window,
                      "vision": settings.llm_supports_vision, "configured": not profile.key_missing},
            "capabilities": {"web_search": any(t.kind == "web" for t in tools),
                             "documents_manage": user.can(settings.perm_documents_manage or None),
                             "os_tools": [t.label for t in tools if t.kind == "company"],
                             "actions": [t.label for t in tools if t.kind == "action"],
                             "files": "create_file" in names, "charts": "create_chart" in names,
                             "image_generation": "generate_image" in names,
                             "ocr": request.app.state.extractor.engine},
            "version": __version__}


# ---------------------------------------------------------------------------------------------------------------
@app.get("/api/settings")
async def get_user_settings(request: Request, user: UserContext = Depends(current_user)):
    return user_prefs(request.app.state.db, user.id)


@app.put("/api/settings")
async def put_user_settings(body: dict, request: Request, user: UserContext = Depends(current_user)):
    current = user_prefs(request.app.state.db, user.id)
    for key, value in body.items():
        if key not in DEFAULT_PREFS:
            continue
        default = DEFAULT_PREFS[key]
        if isinstance(default, bool):
            current[key] = bool(value)
        elif key in PREF_CHOICES:
            if value not in PREF_CHOICES[key]:
                raise HTTPException(422, f"Invalid value for {key}")
            current[key] = value
        else:
            current[key] = str(value or "")[:1500]
    request.app.state.db.save_settings(user.id, current)
    return current


# ---------------------------------------------------------------------------------------------------------------
class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)
    conversation_id: str | None = None
    mode: str = "auto"
    attachment_ids: list[str] = Field(default_factory=list, max_length=10)
    # Edit / regenerate: delete this user message and everything after it, then answer `message` again.
    replace_from_message_id: str | None = None


@app.post("/api/chat")
async def chat(body: ChatRequest, request: Request, user: UserContext = Depends(current_user)):
    request.app.state.limiter.check(user.id)
    db: Database = request.app.state.db
    runs: RunManager = request.app.state.runs
    mode = body.mode if body.mode in MODES else "auto"
    message = body.message.strip()
    if not message:
        raise HTTPException(422, "Message is empty")
    attachments = []
    for att_id in body.attachment_ids:
        att = db.get_attachment(att_id, user.id)
        if not att or (att["conversation_id"] and att["conversation_id"] != body.conversation_id):
            raise HTTPException(404, "Attachment not found")
        attachments.append(att)

    title = None
    if body.conversation_id:
        if not db.get_conversation(body.conversation_id, user.id):
            raise HTTPException(404, "Conversation not found")
        conv_id = body.conversation_id
        if runs.active_for_conversation(conv_id, user.id):
            raise HTTPException(409, "An answer is still being generated in this chat")
    else:
        title = _title(message)
        conv_id = db.create_conversation(user.id, title)

    if body.replace_from_message_id:
        original = db.get_message(body.replace_from_message_id, user.id)
        if not original or original["conversation_id"] != conv_id or original["role"] != "user":
            raise HTTPException(404, "Message not found")
        known = {a["id"] for a in attachments}
        for ref in (original["meta"] or {}).get("attachments", []):
            att = db.get_attachment(ref["id"], user.id)
            if att and att["id"] not in known:
                attachments.append(att)
        db.delete_messages_from(conv_id, original["id"])
        db.audit(user.id, "message_edit" if original["content"] != message else "message_regenerate",
                 {"conversation": conv_id})

    for att in attachments:
        db.link_attachment(att["id"], user.id, conv_id)
    prefs = user_prefs(db, user.id)
    agent: Agent = request.app.state.agent

    def factory(should_stop):
        return agent.run(user, conv_id, message, mode, attachments, prefs, should_stop=should_stop)

    try:
        run = runs.start(user.id, conv_id, factory,
                         [{"type": "conversation", "id": conv_id, "title": title}])
    except ConversationBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    return _stream(runs, run, 0, run_id_first=True)


def _stream(runs: RunManager, run, start: int, run_id_first: bool = False) -> StreamingResponse:
    async def events():
        if run_id_first:
            yield _sse({"type": "run", "id": run.id, "conversation_id": run.conversation_id})
        async for event in runs.subscribe(run, start):
            yield _sse(event)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ---------------------------------------------------------------------------------------------------------------
@app.get("/api/runs")
async def list_runs(request: Request, user: UserContext = Depends(current_user)):
    return {"runs": [r.public() for r in request.app.state.runs.for_user(user.id)]}


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str, request: Request, start: int = Query(0, alias="from", ge=0),
                     user: UserContext = Depends(current_user)):
    run = request.app.state.runs.get(run_id, user.id)
    if not run:
        raise HTTPException(404, "Run not found")
    return _stream(request.app.state.runs, run, start)


@app.post("/api/runs/{run_id}/cancel")
async def cancel_run(run_id: str, request: Request, user: UserContext = Depends(current_user)):
    if not request.app.state.runs.cancel(run_id, user.id):
        raise HTTPException(404, "No running answer to stop")
    return {"ok": True}


# ---------------------------------------------------------------------------------------------------------------
@app.get("/api/conversations")
async def list_conversations(request: Request, user: UserContext = Depends(current_user)):
    rows = request.app.state.db.list_conversations(user.id)
    return {"conversations": [{**r, "pinned": bool(r["pinned"])} for r in rows]}


@app.get("/api/conversations/{conv_id}")
async def get_conversation(conv_id: str, request: Request, user: UserContext = Depends(current_user)):
    db: Database = request.app.state.db
    runs: RunManager = request.app.state.runs
    conv = db.get_conversation(conv_id, user.id)
    if not conv:
        raise HTTPException(404, "Conversation not found")
    feedback = db.feedback_for(conv_id, user.id)
    actions = db.actions_for(conv_id, user.id)
    msgs = []
    for m in db.get_messages(conv_id):
        meta = m["meta"] or {}
        for art in meta.get("artifacts", []):
            if art.get("type") == "action" and art.get("id") in actions:
                art["status"] = actions[art["id"]]["status"]
                art["result"] = actions[art["id"]]["result"]
        msgs.append({"id": m["id"], "role": m["role"], "content": m["content"], "sources": m["sources"],
                     "meta": meta, "feedback": feedback.get(m["id"]), "created_at": m["created_at"]})
    active = runs.active_for_conversation(conv_id, user.id)
    runs.mark_seen(conv_id, user.id)
    return {"id": conv["id"], "title": conv["title"], "pinned": bool(conv.get("pinned")), "messages": msgs,
            "active_run": {"id": active.id, "events": len(active.events)} if active else None}


@app.post("/api/conversations/{conv_id}/seen")
async def conversation_seen(conv_id: str, request: Request, user: UserContext = Depends(current_user)):
    request.app.state.runs.mark_seen(conv_id, user.id)
    return {"ok": True}


class ConversationPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    pinned: bool | None = None


@app.patch("/api/conversations/{conv_id}")
async def patch_conversation(conv_id: str, body: ConversationPatch, request: Request,
                             user: UserContext = Depends(current_user)):
    if not request.app.state.db.update_conversation(conv_id, user.id, title=body.title, pinned=body.pinned):
        raise HTTPException(404, "Conversation not found")
    return {"ok": True}


@app.delete("/api/conversations/{conv_id}")
async def delete_conversation(conv_id: str, request: Request, user: UserContext = Depends(current_user)):
    db: Database = request.app.state.db
    files = [a["file_path"] for a in db.conversation_attachments(conv_id, user.id) if a["file_path"]]
    request.app.state.runs.forget_conversation(conv_id, user.id)
    if not db.delete_conversation(conv_id, user.id):
        raise HTTPException(404, "Conversation not found")
    _unlink(files)
    return {"ok": True}


@app.delete("/api/conversations")
async def delete_all_conversations(request: Request, user: UserContext = Depends(current_user)):
    db: Database = request.app.state.db
    for c in db.list_conversations(user.id, limit=100_000):
        request.app.state.runs.forget_conversation(c["id"], user.id)
    files = db.attachment_files_for_user(user.id)
    count = db.delete_all_conversations(user.id)
    _unlink(files)
    db.audit(user.id, "conversations_delete_all", {"count": count})
    return {"deleted": count}


@app.get("/api/export")
async def export_conversations(request: Request, user: UserContext = Depends(current_user)):
    db: Database = request.app.state.db
    data = {"exported_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "user": user.public(),
            "conversations": [{"id": c["id"], "title": c["title"], "pinned": bool(c["pinned"]),
                               "messages": [{"role": m["role"], "content": m["content"], "sources": m["sources"],
                                             "created_at": m["created_at"]} for m in db.get_messages(c["id"])]}
                              for c in db.list_conversations(user.id, limit=10_000)]}
    return JSONResponse(data, headers={"Content-Disposition": 'attachment; filename="enfactum-ai-chats.json"'})


# ---------------------------------------------------------------------------------------------------------------
class FeedbackBody(BaseModel):
    rating: str = Field(pattern="^(up|down|none)$")
    comment: str = Field(default="", max_length=1000)


@app.post("/api/messages/{msg_id}/feedback")
async def message_feedback(msg_id: str, body: FeedbackBody, request: Request,
                           user: UserContext = Depends(current_user)):
    db: Database = request.app.state.db
    msg = db.get_message(msg_id, user.id)
    if not msg or msg["role"] != "assistant":
        raise HTTPException(404, "Message not found")
    db.set_feedback(msg_id, user.id, body.rating, body.comment)
    db.audit(user.id, "feedback", {"message": msg_id, "rating": body.rating, "comment": body.comment[:300]})
    return {"ok": True}


class ExportBody(BaseModel):
    format: str = Field(pattern="^(pdf|docx|md|txt|html)$")


@app.post("/api/messages/{msg_id}/export")
async def message_export(msg_id: str, body: ExportBody, request: Request, user: UserContext = Depends(current_user)):
    db: Database = request.app.state.db
    msg = db.get_message(msg_id, user.id)
    if not msg:
        raise HTTPException(404, "Message not found")
    conv = db.get_conversation(msg["conversation_id"], user.id)
    title = conv["title"] if conv else "Answer"
    content = msg["content"]
    if msg["sources"]:
        content += "\n\n## Sources\n" + "\n".join(
            f"{s['n']}. {s['title']}" + (f" - {s['url']}" if s.get("url") else "") for s in msg["sources"])
    data = await asyncio.to_thread(build_file, body.format, title=title, content=content)
    name = safe_filename(title, body.format, "answer")
    return Response(data, media_type=FORMATS[body.format], headers={"Content-Disposition": _disposition(name, True)})


# ---------------------------------------------------------------------------------------------------------------
@app.post("/api/actions/{action_id}/confirm")
async def confirm_action(action_id: str, request: Request, user: UserContext = Depends(current_user)):
    request.app.state.limiter.check(user.id)
    return await request.app.state.actions.confirm(action_id, user)


@app.post("/api/actions/{action_id}/cancel")
async def cancel_action(action_id: str, request: Request, user: UserContext = Depends(current_user)):
    return request.app.state.actions.cancel(action_id, user)


# ---------------------------------------------------------------------------------------------------------------
@app.post("/api/attachments")
async def upload_attachment(request: Request, file: UploadFile = File(...), conversation_id: str = Form(""),
                            user: UserContext = Depends(current_user)):
    db: Database = request.app.state.db
    if conversation_id and not db.get_conversation(conversation_id, user.id):
        raise HTTPException(404, "Conversation not found")
    limit = settings.max_attachment_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File exceeds {settings.max_attachment_mb} MB")
    filename = Path(file.filename or "file.txt").name
    try:
        return await save_attachment(settings, db, request.app.state.extractor, user_id=user.id,
                                     conversation_id=conversation_id or None, filename=filename, data=data,
                                     mime=file.content_type or "")
    except UnsupportedDocument as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/files/{att_id}")
@app.get("/api/attachments/{att_id}/file")
async def attachment_file(att_id: str, request: Request, download: bool = False,
                          user: UserContext = Depends(current_user)):
    """Uploaded attachments and agent-generated files (private to their owner)."""
    row = request.app.state.db.get_attachment(att_id, user.id)
    if not row or not row["file_path"] or not Path(row["file_path"]).exists():
        raise HTTPException(404, "File not found")
    force = download or (row["mime"] or "").startswith(("text/html", "image/svg"))
    return FileResponse(row["file_path"], media_type=row["mime"] or "application/octet-stream",
                        headers={"Cache-Control": "private, max-age=86400",
                                 "Content-Disposition": _disposition(row["name"], force)})


@app.get("/api/files/{att_id}/text")
async def attachment_text(att_id: str, request: Request, user: UserContext = Depends(current_user)):
    """Text preview for formats browsers cannot render (docx, pptx...): extracted / source text."""
    row = request.app.state.db.get_attachment(att_id, user.id)
    if not row:
        raise HTTPException(404, "File not found")
    text = row["text"] or ""
    return {"id": att_id, "name": row["name"], "mime": row["mime"], "text": text[:400_000],
            "truncated": len(text) > 400_000}


@app.delete("/api/attachments/{att_id}")
async def delete_attachment(att_id: str, request: Request, user: UserContext = Depends(current_user)):
    row = request.app.state.db.delete_attachment(att_id, user.id)
    if not row:
        raise HTTPException(404, "Attachment not found")
    _unlink([row["file_path"]] if row["file_path"] else [])
    return {"ok": True}


# ---------------------------------------------------------------------------------------------------------------
def _visible_document(request: Request, doc_id: str, user: UserContext) -> dict:
    doc = request.app.state.db.get_document(doc_id)
    if not doc or not can_view(doc["visibility"], user):
        raise HTTPException(404, "Document not found")
    return doc


@app.get("/api/documents")
async def list_documents(request: Request, user: UserContext = Depends(current_user)):
    docs = [d for d in request.app.state.db.list_documents() if can_view(d["visibility"], user)]
    return {"documents": [{**{k: d[k] for k in ("id", "title", "filename", "mime", "size_bytes", "chunk_count",
                                                "created_at", "visibility")},
                           "has_file": bool(d.get("file_path"))} for d in docs],
            "can_manage": user.can(settings.perm_documents_manage or None)}


@app.get("/api/documents/{doc_id}/file")
async def document_file(doc_id: str, request: Request, download: bool = False,
                        user: UserContext = Depends(current_user)):
    doc = _visible_document(request, doc_id, user)
    path = Path(doc["file_path"]) if doc.get("file_path") else None
    if path and path.exists():
        force = download or (doc["mime"] or "").startswith(("text/html", "image/svg"))
        return FileResponse(path, media_type=doc["mime"] or "application/octet-stream",
                            headers={"Cache-Control": "private, max-age=3600",
                                     "Content-Disposition": _disposition(doc["filename"], force)})
    # Documents indexed before originals were stored: serve the extracted text.
    text = request.app.state.db.document_text(doc_id)
    name = Path(doc["filename"]).stem + ".txt"
    return Response(text, media_type="text/plain; charset=utf-8",
                    headers={"Content-Disposition": _disposition(name, download)})


@app.get("/api/documents/{doc_id}/text")
async def document_text(doc_id: str, request: Request, user: UserContext = Depends(current_user)):
    doc = _visible_document(request, doc_id, user)
    text = request.app.state.db.document_text(doc_id)
    return {"id": doc_id, "title": doc["title"], "filename": doc["filename"], "mime": doc["mime"],
            "text": text[:400_000], "truncated": len(text) > 400_000}


@app.post("/api/documents")
async def upload_document(request: Request, file: UploadFile = File(...), title: str = Form(""),
                          visibility: str = Form("all"), roles: str = Form(""),
                          user: UserContext = Depends(current_user)):
    if not user.can(settings.perm_documents_manage or None):
        raise HTTPException(403, "You are not allowed to manage company documents")
    limit = settings.max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"File exceeds {settings.max_upload_mb} MB")
    vis = {"scope": "all"} if visibility != "restricted" else {"scope": "restricted", "roles": csv_list(roles)}
    if vis["scope"] == "restricted" and not vis["roles"]:
        raise HTTPException(422, "Restricted documents need at least one role")
    filename = Path(file.filename or "document.txt").name
    if Path(filename).suffix.lower() not in kb_extensions():
        raise HTTPException(422, f"Unsupported file type '{Path(filename).suffix}'")
    try:
        result = await request.app.state.ingestor.ingest(filename=filename, data=data, title=title or None,
                                                         visibility=vis, uploaded_by=user.id,
                                                         mime=file.content_type or "")
    except UnsupportedDocument as exc:
        raise HTTPException(422, str(exc)) from exc
    request.app.state.db.audit(user.id, "document_upload", {"id": result["id"], "title": result["title"]})
    return result


@app.delete("/api/documents/{doc_id}")
async def delete_document(doc_id: str, request: Request, user: UserContext = Depends(current_user)):
    if not user.can(settings.perm_documents_manage or None):
        raise HTTPException(403, "You are not allowed to manage company documents")
    if not request.app.state.db.get_document(doc_id):
        raise HTTPException(404, "Document not found")
    await request.app.state.ingestor.delete(doc_id)
    request.app.state.db.audit(user.id, "document_delete", {"id": doc_id})
    return {"ok": True}


# ---------------------------------------------------------------------------------------------------------------
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
@app.get("/c/{conv_id}", include_in_schema=False)
async def index(conv_id: str | None = None):
    return FileResponse(STATIC_DIR / "index.html", headers={"Cache-Control": "no-cache"})


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"


def _title(message: str) -> str:
    first = " ".join(message.split())
    return first[:60] + ("…" if len(first) > 60 else "")


def _unlink(paths: list[str]) -> None:
    root = (settings.data_dir / "attachments").resolve()
    for p in paths:
        path = Path(p).resolve()
        if root in path.parents:
            path.unlink(missing_ok=True)


async def _seed_samples(ingestor: Ingestor) -> None:
    manifest = BASE_DIR / "samples" / "manifest.yaml"
    if not manifest.exists():
        return
    for item in (yaml.safe_load(manifest.read_text()) or {}).get("documents", []):
        path = manifest.parent / item["file"]
        try:
            await ingestor.ingest(filename=path.name, data=path.read_bytes(), title=item.get("title"),
                                  visibility=item.get("visibility", {"scope": "all"}), uploaded_by="system")
            log.info("Seeded sample document: %s", item.get("title"))
        except Exception as exc:
            log.warning("Could not seed %s: %s", path.name, exc)
