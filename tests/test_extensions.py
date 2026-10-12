import pytest

from app.attachments import build_document_context
from app.config import Settings, _detect_provider
from app.tools.base import Citations
from app.tools.db_query import SQLTemplateTool


@pytest.mark.parametrize("key,base,expected", [
    ("sk-proj-abc", "", "openai"),
    ("gsk_abc", "", "groq"),
    ("AIzaSyabc", "", "gemini"),
    ("sk-or-v1-abc", "", "openrouter"),
    ("sk-ant-abc", "", "anthropic"),
    ("", "http://localhost:11434/v1", "ollama"),
    ("x", "https://my-vllm.internal/v1", "custom"),
])
def test_provider_detection(key, base, expected):
    assert _detect_provider(Settings(llm_api_key=key, llm_base_url=base, llm_provider="auto")) == expected


def test_settings_strip_quotes_and_bearer():
    assert Settings(llm_api_key='"Bearer sk-123 "').llm_api_key == "sk-123"


def sql_tool(sql, params=None):
    return SQLTemplateTool({"name": "t", "description": "d", "sql": sql,
                            "parameters": params or {"type": "object", "properties": {}}}, Settings())


def test_sql_template_accepts_select_with_context_params():
    sql_tool("SELECT id FROM leave WHERE user_id = %(current_user_id)s")


@pytest.mark.parametrize("sql", [
    "DELETE FROM users",
    "SELECT 1; DROP TABLE users",
    "WITH x AS (DELETE FROM users RETURNING *) SELECT * FROM x",
    "SELECT pg_sleep(10)",
    "UPDATE users SET name = 'a'",
])
def test_sql_template_rejects_writes(sql):
    with pytest.raises(ValueError):
        sql_tool(sql)


def test_sql_template_rejects_undeclared_placeholder():
    with pytest.raises(ValueError):
        sql_tool("SELECT * FROM v WHERE name = %(search)s")


def test_attachment_context_small_and_large():
    small = [{"id": "a", "name": "notes.txt", "kind": "document", "text": "The launch date is 12 May."}]
    c = Citations()
    ctx = build_document_context(small, "launch date", 10_000, c)
    assert "12 May" in ctx and c.items[0]["type"] == "attachment"

    filler = "\n\n".join(f"Section {i}. " + "lorem ipsum " * 100 for i in range(60))
    big = [{"id": "b", "name": "big.pdf", "kind": "document",
            "text": filler + "\n\nThe penalty clause is 5 percent per week."}]
    ctx = build_document_context(big, "penalty clause percent", 6_000, Citations())
    assert "penalty clause is 5 percent" in ctx
    assert len(ctx) < 9_000
