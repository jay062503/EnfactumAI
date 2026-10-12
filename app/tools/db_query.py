"""Pre-approved, parameterised SQL queries against a READ-ONLY company database (config/db_tools.yaml).

The LLM never writes SQL. It can only pick a query an administrator wrote and fill its declared, JSON-Schema
validated parameters, which are bound by the driver (never string-formatted). Every query runs inside a
READ ONLY transaction with a statement timeout, and the connection must use a read-only database role.

Because this bypasses Laravel policies, each query must enforce access itself, typically by filtering on the
injected :current_user_id / :current_user_email, and by gating the tool with required_permission.
"""
import json
import logging
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import jsonschema
import yaml

from ..config import Settings
from .base import Tool, ToolContext, untrusted
from .os_api import MAX_RESULT_CHARS, _NAME, _expand_env, redact

log = logging.getLogger(__name__)
_PLACEHOLDER = re.compile(r"%\((\w+)\)s")
_FORBIDDEN = re.compile(r"\b(insert|update|delete|merge|upsert|drop|alter|create|grant|revoke|truncate|copy|call|do|"
                        r"execute|vacuum|analyze|lock|set|reset|comment|refresh|pg_sleep|pg_read_file|lo_import|"
                        r"dblink)\b", re.I)
CONTEXT_PARAMS = {"current_user_id", "current_user_email"}


def _json_default(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, Decimal):
        return float(v)
    return str(v)


class SQLTemplateTool(Tool):
    def __init__(self, spec: dict, settings: Settings):
        name = spec["name"]
        if not _NAME.match(name):
            raise ValueError(f"Invalid tool name: {name}")
        sql = spec["sql"].strip().rstrip(";").strip()
        if ";" in sql:
            raise ValueError(f"DB tool {name}: only a single statement is allowed")
        if not re.match(r"^(select|with)\b", sql, re.I):
            raise ValueError(f"DB tool {name}: query must start with SELECT or WITH")
        stripped = re.sub(r"'(?:[^']|'')*'", "''", sql)
        if _FORBIDDEN.search(stripped):
            raise ValueError(f"DB tool {name}: forbidden keyword '{_FORBIDDEN.search(stripped).group(0)}'")
        params = spec.get("parameters") or {"type": "object", "properties": {}}
        jsonschema.Draft202012Validator.check_schema(params)
        declared = set(params.get("properties", {}))
        unknown = set(_PLACEHOLDER.findall(sql)) - declared - CONTEXT_PARAMS
        if unknown:
            raise ValueError(f"DB tool {name}: undeclared placeholders {sorted(unknown)}")
        super().__init__(name=name, description=spec["description"].strip(), parameters=params,
                         label=spec.get("label", name.replace("_", " ").capitalize()), kind="company",
                         required_permission=spec.get("required_permission"))
        self.sql = sql
        self.declared = declared
        self.max_rows = int(spec.get("max_rows", 50))
        self.s = settings
        self._validator = jsonschema.Draft202012Validator(params)

    def status_text(self, args: dict) -> str:
        detail = ", ".join(str(v) for v in args.values() if isinstance(v, (str, int)) and str(v))
        return self.label + (f" \u2014 {detail}" if detail else "")

    async def run(self, args: dict, ctx: ToolContext) -> str:
        errors = [e.message for e in self._validator.iter_errors(args)]
        if errors:
            return f"Invalid arguments: {'; '.join(errors)}"
        import psycopg
        from psycopg.rows import dict_row

        bind = {k: args.get(k) for k in self.declared}
        bind.update(current_user_id=ctx.user.id, current_user_email=ctx.user.email)
        timeout = int(self.s.db_statement_timeout_ms)
        async with await psycopg.AsyncConnection.connect(self.s.company_db_dsn, row_factory=dict_row,
                                                         connect_timeout=5) as conn:
            async with conn.transaction():
                await conn.execute("SET TRANSACTION READ ONLY")
                await conn.execute(f"SET LOCAL statement_timeout = {timeout}")
                cur = await conn.execute(self.sql, bind)
                rows = await cur.fetchmany(self.max_rows + 1)
        more = len(rows) > self.max_rows
        rows = redact(rows[: self.max_rows])
        n = ctx.citations.add(kind="os", title=f"Company database \u00b7 {self.label}",
                              key=f"db:{self.name}:{json.dumps(args, sort_keys=True, default=str)}")
        body = json.dumps({"rows": rows, "returned": len(rows), "truncated": more}, default=_json_default,
                          ensure_ascii=False)
        if len(body) > MAX_RESULT_CHARS:
            body = body[:MAX_RESULT_CHARS] + " …[truncated; ask the user to narrow the query]"
        return untrusted(f"company_db:{self.name}", f"[{n}] Company database \u00b7 {self.label}\n{body}")


def load_db_tools(settings: Settings) -> list[SQLTemplateTool]:
    path: Path = settings.db_tools_file
    if not settings.company_db_dsn or not path.exists():
        return []
    try:
        import psycopg  # noqa: F401
    except ImportError as exc:
        raise RuntimeError("COMPANY_DB_DSN is set but psycopg is missing: pip install 'psycopg[binary]'") from exc
    spec = yaml.safe_load(_expand_env(path.read_text(), settings)) or {}
    tools = [SQLTemplateTool(t, settings) for t in spec.get("tools") or [] if t.get("enabled", True)]
    log.info("Loaded %d company-database tools from %s", len(tools), path.name)
    return tools
