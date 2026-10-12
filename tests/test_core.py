import asyncio

import httpx
import pytest

from app.auth import UserContext
from app.config import Settings
from app.db import Database
from app.rag.chunker import chunk_text
from app.rag.embeddings import Embedder
from app.rag.index import DocumentIndex, can_view
from app.tools.base import Citations, ToolContext
from app.tools.os_api import OSApiTool, redact
from app.tools.registry import ToolRegistry


def user(uid="1", roles=(), perms=(), token="t"):
    return UserContext(id=uid, name="Test", roles=frozenset(roles), permissions=frozenset(perms), os_token=token)


def test_chunker_respects_size_and_keeps_heading():
    text = "# Leave policy\n\n" + "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(10))
    chunks = chunk_text(text, size=500, overlap=80)
    assert len(chunks) > 3
    assert all(len(c) <= 700 for c in chunks)
    assert all("Leave policy" in c for c in chunks[1:])


def test_document_visibility():
    restricted = {"scope": "restricted", "roles": ["hr_manager"]}
    assert can_view({"scope": "all"}, user())
    assert not can_view(restricted, user(roles=["employee"]))
    assert can_view(restricted, user(roles=["hr_manager"]))
    assert can_view(restricted, user(roles=["super_admin"]))


def test_search_never_returns_restricted_chunks(tmp_path):
    s = Settings(data_dir=tmp_path, embedding_provider="none")
    db = Database(tmp_path / "t.db")
    db.add_document(title="Salary bands", filename="a.md", mime="", size_bytes=1, uploaded_by="x",
                    visibility={"scope": "restricted", "roles": ["hr_manager"]},
                    chunks=[(0, None, "Salary bands for engineers are confidential", None)])
    db.add_document(title="Leave", filename="b.md", mime="", size_bytes=1, uploaded_by="x",
                    visibility={"scope": "all"}, chunks=[(0, None, "Annual leave is 20 days", None)])
    index = DocumentIndex(db, Embedder(s))
    index.reload()
    employee_hits = asyncio.run(index.search("salary bands", user(roles=["employee"])))
    assert all(h.title != "Salary bands" for h in employee_hits)
    hr_hits = asyncio.run(index.search("salary bands", user(roles=["hr_manager"])))
    assert hr_hits and hr_hits[0].title == "Salary bands"


def test_os_tool_rejects_write_methods():
    s = Settings()
    with pytest.raises(ValueError):
        OSApiTool({"name": "x", "description": "d", "method": "POST", "path": "/api/x"}, "http://os", 5, s,
                  httpx.AsyncClient())
    with pytest.raises(ValueError):
        OSApiTool({"name": "x", "description": "d", "path": "https://evil.example/api"}, "http://os", 5, s,
                  httpx.AsyncClient())


def test_os_tool_forwards_user_token_and_filters_fields():
    seen = {}

    def handler(request: httpx.Request):
        seen["auth"] = request.headers.get("authorization")
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"data": [{"id": 1, "name": "A", "password": "p", "internal": "hide"}]})

    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    tool = OSApiTool({"name": "emp", "description": "d", "path": "/api/employees/{id}",
                      "parameters": {"type": "object", "properties": {"id": {"type": "integer"}}},
                      "response": {"root": "data", "fields": ["id", "name", "password"]}},
                     "http://os", 5, Settings(), http)
    ctx = ToolContext(user=user(token="user-token"), citations=Citations())
    out = asyncio.run(tool.run({"id": 7}, ctx))
    assert seen["auth"] == "Bearer user-token"
    assert seen["url"] == "http://os/api/employees/7"
    assert "internal" not in out and "\"p\"" not in out and "[redacted]" in out


def test_os_tool_reports_access_denied():
    http = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(403)))
    tool = OSApiTool({"name": "emp", "description": "d", "path": "/api/x"}, "http://os", 5, Settings(), http)
    out = asyncio.run(tool.run({}, ToolContext(user=user(), citations=Citations())))
    assert "ACCESS DENIED" in out


def test_registry_hides_unpermitted_tools():
    http = httpx.AsyncClient()
    tool = OSApiTool({"name": "salaries", "description": "d", "path": "/api/s", "required_permission": "finance.view"},
                     "http://os", 5, Settings(), http)
    reg = ToolRegistry([tool])
    assert reg.for_user(user(perms=[])) == []
    assert reg.for_user(user(perms=["finance.view"])) == [tool]
    assert reg.for_user(user(perms=["finance.view"]), mode="general") == []


def test_redact_nested():
    assert redact({"a": {"api_key": "x", "pin_code": "560001"}}) == {"a": {"api_key": "[redacted]", "pin_code": "560001"}}
