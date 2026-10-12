"""Write actions in Enfactum OS ("agentic" tools), declared in the `actions:` section of the OS tools YAML.

Safety model:
  1. The LLM can only PREPARE an action. Preparing validates arguments and stores a pending action; nothing is sent.
  2. The employee sees a confirmation card with the exact values and must click Confirm.
  3. On confirm the server re-checks permission + expiry, atomically claims the action (no double execution) and
     calls Enfactum OS with the EMPLOYEE'S OWN credentials, so Laravel validation/policies still decide.
  4. Every prepare / confirm / cancel / result is written to the audit log.
"""
import json
import logging
import time
from typing import Any
from urllib.parse import quote

import httpx
import jsonschema

from ..auth import UserContext
from ..config import Settings
from ..db import Database
from .base import Tool, ToolContext
from .os_api import _NAME, _PATH_PARAM, load_os_spec, os_headers, redact

log = logging.getLogger(__name__)
WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class _SafeDict(dict):
    def __missing__(self, key):
        return "\u2014"


class ActionTool(Tool):
    def __init__(self, spec: dict, base_url: str, timeout: float, settings: Settings, db: Database):
        name = spec["name"]
        if not _NAME.match(name):
            raise ValueError(f"Invalid action name: {name}")
        method = spec.get("method", "POST").upper()
        if method not in WRITE_METHODS:
            raise ValueError(f"Action {name}: method must be one of {sorted(WRITE_METHODS)}")
        path = spec["path"]
        if not path.startswith("/") or "://" in path:
            raise ValueError(f"Action {name}: path must be relative to OS base_url")
        if not spec.get("required_permission"):
            raise ValueError(f"Action {name}: required_permission is mandatory for write actions")
        params = spec.get("parameters") or {"type": "object", "properties": {}}
        jsonschema.Draft202012Validator.check_schema(params)
        description = (spec["description"].strip() + " This PREPARES the action; the employee must confirm it in "
                       "the UI before anything is changed.")
        super().__init__(name=name, description=description, parameters=params,
                         label=spec.get("label", name.replace("_", " ").capitalize()), kind="action",
                         required_permission=spec["required_permission"])
        self.method = method
        self.path = path
        self.summary_template = spec.get("summary") or self.label
        self.field_labels: dict = spec.get("field_labels") or {}
        self.success_message = spec.get("success_message") or "Done."
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.s = settings
        self.db = db
        self._validator = jsonschema.Draft202012Validator(params)

    def status_text(self, args: dict) -> str:
        return f"Preparing: {self.label}"

    def summary(self, args: dict) -> str:
        try:
            return self.summary_template.format_map(_SafeDict({k: v for k, v in args.items()}))[:300]
        except (ValueError, IndexError):
            return self.label

    def fields(self, args: dict) -> list[dict]:
        props = self.parameters.get("properties", {})
        return [{"label": self.field_labels.get(k) or props.get(k, {}).get("title") or k.replace("_", " ").capitalize(),
                 "value": v} for k, v in args.items() if v not in (None, "")]

    async def run(self, args: dict, ctx: ToolContext) -> str:
        declared = self.parameters.get("properties") or {}
        args = {k: v for k, v in args.items() if k in declared}
        errors = [e.message for e in self._validator.iter_errors(args)]
        if errors:
            return f"Invalid arguments: {'; '.join(errors)}. Ask the user for the missing/incorrect details."
        summary = self.summary(args)
        action_id = self.db.add_action(user_id=ctx.user.id, conversation_id=ctx.conversation_id, tool=self.name,
                                       args=args, summary=summary)
        self.db.audit(ctx.user.id, "action_prepared", {"action": action_id, "tool": self.name, "args": args})
        ctx.artifacts.append({"type": "action", "id": action_id, "title": self.label, "summary": summary,
                              "fields": self.fields(args), "status": "pending",
                              "expires_in_minutes": self.s.action_expiry_minutes})
        return ("The action is PREPARED but NOT executed. A confirmation card is shown to the employee. Tell them, in "
                "one or two sentences, to review the details and click Confirm. Do not say it is done.")

    async def execute(self, args: dict, user: UserContext, http: httpx.AsyncClient) -> tuple[bool, dict]:
        path_keys = set(_PATH_PARAM.findall(self.path))
        if any(args.get(k) in (None, "") for k in path_keys):
            return False, {"message": "Missing identifier for this action."}
        path = _PATH_PARAM.sub(lambda m: quote(str(args[m.group(1)]), safe=""), self.path)
        body = {k: v for k, v in args.items() if k not in path_keys}
        headers = {**os_headers(user), "Content-Type": "application/json"}
        try:
            r = await http.request(self.method, self.base_url + path, headers=headers, timeout=self.timeout,
                                   content=json.dumps(body) if self.method != "DELETE" else None)
        except httpx.HTTPError as exc:
            log.warning("Action %s failed: %s", self.name, exc)
            return False, {"message": "Enfactum OS could not be reached. Nothing was changed."}
        try:
            data: Any = r.json()
        except ValueError:
            data = None
        if r.status_code in (401, 403):
            return False, {"message": "Enfactum OS denied this action for your account. Nothing was changed."}
        if r.status_code == 422:
            errs = data.get("errors") if isinstance(data, dict) else None
            detail = "; ".join(f"{k}: {', '.join(v) if isinstance(v, list) else v}" for k, v in (errs or {}).items())
            return False, {"message": "Enfactum OS rejected the request" + (f": {detail}" if detail else ".")}
        if r.status_code >= 400:
            return False, {"message": f"Enfactum OS returned an error (HTTP {r.status_code}). Nothing was changed."}
        return True, {"message": self.success_message, "data": redact(data) if data is not None else None}


class ActionService:
    def __init__(self, settings: Settings, db: Database, http: httpx.AsyncClient, tools: list[ActionTool]):
        self.s = settings
        self.db = db
        self.http = http
        self.tools = {t.name: t for t in tools}

    async def confirm(self, action_id: str, user: UserContext) -> dict:
        row = self.db.get_action(action_id, user.id)
        if not row:
            return {"ok": False, "status": "missing", "message": "Action not found."}
        if row["status"] != "pending":
            return {"ok": row["status"] == "done", "status": row["status"], "message": "This action was already handled.",
                    "result": row["result"]}
        tool = self.tools.get(row["tool"])
        if tool is None or not tool.available_for(user):
            self.db.finish_action(action_id, "failed", {"message": "You are not allowed to perform this action."})
            return {"ok": False, "status": "failed", "message": "You are not allowed to perform this action."}
        if time.time() - row["created_at"] > self.s.action_expiry_minutes * 60:
            self.db.finish_action(action_id, "expired", {"message": "This confirmation expired."})
            return {"ok": False, "status": "expired", "message": "This confirmation expired. Ask the assistant again."}
        if not self.db.claim_action(action_id, user.id):
            return {"ok": False, "status": "running", "message": "This action is already being processed."}
        self.db.audit(user.id, "action_confirmed", {"action": action_id, "tool": tool.name})
        ok, result = await tool.execute(row["args"], user, self.http)
        status = "done" if ok else "failed"
        self.db.finish_action(action_id, status, result)
        self.db.audit(user.id, "action_" + status, {"action": action_id, "tool": tool.name,
                                                    "message": result.get("message")})
        if row["conversation_id"]:
            icon = "\u2705" if ok else "\u26a0\ufe0f"
            self.db.add_message(row["conversation_id"], "assistant", f"{icon} **{tool.label}** \u2014 {result['message']}",
                                meta={"action_result": {"id": action_id, "status": status}})
        return {"ok": ok, "status": status, "message": result["message"], "result": result}

    def cancel(self, action_id: str, user: UserContext) -> dict:
        row = self.db.get_action(action_id, user.id)
        if not row:
            return {"ok": False, "status": "missing"}
        if row["status"] != "pending":
            return {"ok": False, "status": row["status"]}
        self.db.finish_action(action_id, "cancelled", {"message": "Cancelled by the employee."})
        self.db.audit(user.id, "action_cancelled", {"action": action_id, "tool": row["tool"]})
        return {"ok": True, "status": "cancelled"}


def load_action_tools(settings: Settings, db: Database) -> list[ActionTool]:
    if not settings.ai_actions_enabled:
        return []
    spec, base_url = load_os_spec(settings)
    tools = [ActionTool(a, base_url, float(spec.get("timeout_seconds", 10)), settings, db)
             for a in spec.get("actions") or [] if a.get("enabled", True)]
    names = [t.name for t in tools]
    if len(names) != len(set(names)):
        raise RuntimeError("Duplicate action names in " + str(settings.os_tools_file))
    if tools:
        log.info("Loaded %d Enfactum OS write actions (confirmation required)", len(tools))
    return tools
