import asyncio
import time

import httpx
import pytest

from app.auth import UserContext, resolve_user_type
from app.config import Settings
from app.db import Database
from app.files.generator import build_file, parse_markdown, safe_filename
from app.runs import ConversationBusy, RunManager
from app.tools.actions import ActionService, ActionTool
from app.tools.base import Citations, ToolContext

REPORT = """# Q3 summary

Revenue grew **12%** quarter on quarter.

- Northwind launched
- Helios kicked off

| Project | Status | Budget |
|---|---|---|
| Northwind | in_progress | 420000 |
| Helios | planning | 610000 |
"""


def user(perms=(), user_type="employee", token="tok"):
    return UserContext(id="7", name="Test User", permissions=frozenset(perms), user_type=user_type, os_token=token)


# ---- employee-only app -------------------------------------------------------------------------------------
def test_user_type_resolution():
    assert resolve_user_type("employee", frozenset()) == "employee"
    assert resolve_user_type("Client", frozenset()) == "client"
    assert resolve_user_type(None, frozenset({"client"})) == "client"
    assert resolve_user_type(None, frozenset({"client", "employee"})) == "employee"
    assert resolve_user_type(None, frozenset()) == "employee"


def test_clients_are_not_allowed_in_app():
    assert user().allowed_in_app
    assert not user(user_type="client").allowed_in_app


# ---- edit / regenerate -------------------------------------------------------------------------------------
def test_delete_messages_from_truncates_conversation(tmp_path):
    db = Database(tmp_path / "t.db")
    conv = db.create_conversation("7", "chat")
    ids = []
    for i in range(4):
        ids.append(db.add_message(conv, "user" if i % 2 == 0 else "assistant", f"m{i}"))
        time.sleep(0.002)
    assert db.delete_messages_from(conv, ids[2]) == 2
    assert [m["content"] for m in db.get_messages(conv)] == ["m0", "m1"]
    assert db.get_message(ids[0], "someone-else") is None


# ---- confirmed actions -------------------------------------------------------------------------------------
def _leave_tool(settings, db):
    return ActionTool({
        "name": "create_leave_request", "label": "Apply for leave", "description": "Apply for leave.",
        "method": "POST", "path": "/api/leave-requests", "required_permission": "leave.create",
        "summary": "{leave_type} leave from {start_date} to {end_date}",
        "parameters": {"type": "object", "required": ["leave_type", "start_date", "end_date"],
                       "properties": {"leave_type": {"type": "string"}, "start_date": {"type": "string"},
                                      "end_date": {"type": "string"}}},
    }, "http://os.test", 5, settings, db)


def test_action_requires_permission_declaration(tmp_path):
    s = Settings(data_dir=tmp_path)
    with pytest.raises(ValueError):
        ActionTool({"name": "x", "description": "d", "method": "POST", "path": "/api/x"}, "http://os", 5, s,
                   Database(tmp_path / "t.db"))
    with pytest.raises(ValueError):
        ActionTool({"name": "x", "description": "d", "method": "GET", "path": "/api/x", "required_permission": "p"},
                   "http://os", 5, s, Database(tmp_path / "t.db"))


def test_action_is_only_prepared_then_executed_once_on_confirm(tmp_path):
    s = Settings(data_dir=tmp_path)
    db = Database(tmp_path / "t.db")
    tool = _leave_tool(s, db)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(201, json={"data": {"id": 1, "status": "pending_approval"}})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    u = user(perms=["leave.create"], token="employee-token")
    conv = db.create_conversation(u.id, "leave")
    ctx = ToolContext(user=u, citations=Citations(), conversation_id=conv)
    out = asyncio.run(tool.run({"leave_type": "annual", "start_date": "2026-10-12", "end_date": "2026-10-13"}, ctx))
    assert "NOT executed" in out and not calls
    action = ctx.artifacts[0]
    assert action["type"] == "action" and action["summary"] == "annual leave from 2026-10-12 to 2026-10-13"

    service = ActionService(s, db, http, [tool])
    first = asyncio.run(service.confirm(action["id"], u))
    second = asyncio.run(service.confirm(action["id"], u))
    assert first["ok"] and first["status"] == "done"
    assert second["status"] == "done" and len(calls) == 1
    assert calls[0].headers["authorization"] == "Bearer employee-token"
    assert calls[0].method == "POST"


def test_action_confirm_rechecks_permission_and_owner(tmp_path):
    s = Settings(data_dir=tmp_path)
    db = Database(tmp_path / "t.db")
    tool = _leave_tool(s, db)
    owner = user(perms=["leave.create"])
    ctx = ToolContext(user=owner, citations=Citations())
    asyncio.run(tool.run({"leave_type": "sick", "start_date": "2026-10-12", "end_date": "2026-10-12"}, ctx))
    action_id = ctx.artifacts[0]["id"]
    service = ActionService(s, db, httpx.AsyncClient(), [tool])
    stranger = UserContext(id="8", name="Other", permissions=frozenset(["leave.create"]))
    assert asyncio.run(service.confirm(action_id, stranger))["status"] == "missing"
    revoked = user(perms=[])
    assert asyncio.run(service.confirm(action_id, revoked))["status"] == "failed"


# ---- file generation ---------------------------------------------------------------------------------------
def test_markdown_parser_blocks():
    kinds = [b.kind for b in parse_markdown(REPORT)]
    assert kinds == ["h1", "p", "ul", "table"]
    assert safe_filename("../../etc/passwd", "pdf") == "passwd.pdf"
    assert safe_filename("Q3 report: final?", "docx") == "Q3 report final.docx"


@pytest.mark.parametrize("fmt,magic", [("docx", b"PK"), ("xlsx", b"PK"), ("pptx", b"PK"), ("pdf", b"%PDF"),
                                       ("csv", b"\xef\xbb\xbf"), ("html", b"<!doctype"), ("txt", b"Report")])
def test_build_file_formats(fmt, magic):
    pytest.importorskip({"docx": "docx", "xlsx": "openpyxl", "pptx": "pptx", "pdf": "fpdf"}.get(fmt, "json"))
    data = build_file(fmt, title="Report", content=REPORT)
    assert data.startswith(magic)


def test_csv_neutralises_formula_injection():
    data = build_file("csv", title="x", columns=["name"], rows=[["=HYPERLINK(\"http://evil\")"], [""]]).decode("utf-8-sig")
    assert "'=HYPERLINK" in data


# ---- background runs ---------------------------------------------------------------------------------------
def test_run_continues_without_subscriber_and_replays():
    async def scenario():
        runs = RunManager()

        async def agent(should_stop):
            for word in ("Hello", " world"):
                await asyncio.sleep(0.01)
                yield {"type": "token", "text": word}
            yield {"type": "done"}

        run = runs.start("u1", "c1", agent, [{"type": "conversation", "id": "c1"}])
        with pytest.raises(ConversationBusy):
            runs.start("u1", "c1", agent, [])
        await run.task  # nobody is listening: the answer still completes
        assert run.status == "done"
        replay = [e async for e in runs.subscribe(run, 1)]
        assert "".join(e.get("text", "") for e in replay) == "Hello world"
        assert replay[-1]["type"] == "run_end"
        assert [r.id for r in runs.for_user("u1")] == [run.id]
        runs.mark_seen("c1", "u1")
        assert runs.for_user("u1") == []
        assert runs.get(run.id, "someone-else") is None

    asyncio.run(scenario())


def test_run_can_be_stopped():
    async def scenario():
        runs = RunManager()

        async def agent(should_stop):
            for i in range(100):
                if should_stop():
                    return
                await asyncio.sleep(0.01)
                yield {"type": "token", "text": str(i)}

        run = runs.start("u1", "c1", agent, [])
        await asyncio.sleep(0.03)
        assert runs.cancel(run.id, "u1")
        await run.task
        assert run.status == "cancelled"
        assert sum(1 for e in run.events if e["type"] == "token") < 100

    asyncio.run(scenario())
