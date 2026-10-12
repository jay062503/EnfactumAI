"""Read-only Enfactum OS API tools, declared in YAML (see config/os_tools.yaml).

Every call is made WITH THE END USER'S OWN CREDENTIALS, so Laravel middleware, policies, gates and query scopes
decide what comes back. The agent-side `required_permission` is only a pre-filter that hides tools the user
could never use; it is not the security boundary.
"""
import json
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

import httpx
import jsonschema
import yaml

from ..config import Settings
from .base import Tool, ToolContext, untrusted

log = logging.getLogger(__name__)

_ENV = re.compile(r"\$\{([A-Z0-9_]+)(?::-([^}]*))?\}")
_NAME = re.compile(r"^[a-zA-Z0-9_]{1,64}$")
_PATH_PARAM = re.compile(r"\{([a-zA-Z0-9_]+)\}")
SENSITIVE_KEYS = re.compile(
    r"(password|passwd|secret|token|api[_-]?key|private[_-]?key|remember|two[_-]?factor|(^|_)(otp|pin|cvv)$|"
    r"card[_-]?number|iban|account[_-]?number|aadhaar|pan[_-]?number|(^|_)ssn($|_))", re.I)
MAX_RESULT_CHARS = 12_000


def _expand_env(text: str, settings: Settings) -> str:
    def lookup(m: re.Match) -> str:
        value = os.environ.get(m.group(1)) or getattr(settings, m.group(1).lower(), None)
        return str(value) if value not in (None, "") else (m.group(2) or "")

    return _ENV.sub(lookup, text)


def _dig(data: Any, path: str | None) -> Any:
    for part in (path.split(".") if path else []):
        data = data.get(part) if isinstance(data, dict) else None
    return data


def _pick(item: Any, fields: list[str]) -> Any:
    if not isinstance(item, dict):
        return item
    out: dict[str, Any] = {}
    for f in fields:
        value = _dig(item, f)
        if value is None:
            continue
        node = out
        parts = f.split(".")
        for p in parts[:-1]:
            node = node.setdefault(p, {})
        node[parts[-1]] = value
    return out


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("[redacted]" if SENSITIVE_KEYS.search(k) else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    return value


class OSApiTool(Tool):
    def __init__(self, spec: dict, base_url: str, timeout: float, settings: Settings, http: httpx.AsyncClient):
        name = spec["name"]
        if not _NAME.match(name):
            raise ValueError(f"Invalid tool name: {name}")
        if spec.get("method", "GET").upper() != "GET":
            raise ValueError(f"Tool {name}: only GET (read-only) tools are allowed")
        path = spec["path"]
        if not path.startswith("/") or "://" in path:
            raise ValueError(f"Tool {name}: path must be relative to OS base_url")
        params = spec.get("parameters") or {"type": "object", "properties": {}}
        jsonschema.Draft202012Validator.check_schema(params)
        super().__init__(name=name, description=spec["description"].strip(), parameters=params,
                         label=spec.get("label", name.replace("_", " ").capitalize()), kind="company",
                         required_permission=spec.get("required_permission"))
        self.path = path
        self.query_params = spec.get("query")
        self.response = spec.get("response") or {}
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.s = settings
        self.http = http
        self._validator = jsonschema.Draft202012Validator(params)

    def status_text(self, args: dict) -> str:
        detail = ", ".join(f"{v}" for v in args.values() if isinstance(v, (str, int)) and str(v))
        return f"{self.label}" + (f" \u2014 {detail}" if detail else "")

    async def run(self, args: dict, ctx: ToolContext) -> str:
        errors = [e.message for e in self._validator.iter_errors(args)]
        if errors:
            return f"Invalid arguments: {'; '.join(errors)}"
        path_keys = set(_PATH_PARAM.findall(self.path))
        missing = [k for k in path_keys if args.get(k) in (None, "")]
        if missing:
            return f"Missing required parameter(s): {', '.join(missing)}"
        path = _PATH_PARAM.sub(lambda m: quote(str(args[m.group(1)]), safe=""), self.path)
        qkeys = self.query_params if self.query_params is not None else [k for k in args if k not in path_keys]
        query = {k: args[k] for k in qkeys if k in args and args[k] not in (None, "")}

        try:
            r = await self.http.get(self.base_url + path, params=query, headers=os_headers(ctx.user),
                                    timeout=self.timeout)
        except httpx.HTTPError as exc:
            log.warning("OS tool %s failed: %s", self.name, exc)
            return "Enfactum OS could not be reached. Tell the user the live data is temporarily unavailable."
        if r.status_code in (401, 403):
            return ("ACCESS DENIED by Enfactum OS for this employee. Tell the user they do not have permission "
                    "to view this information. Do not speculate about the data.")
        if r.status_code == 404:
            return "Not found in Enfactum OS."
        if r.status_code == 422:
            return f"Enfactum OS rejected the request parameters: {r.text[:500]}"
        if r.status_code >= 400:
            return f"Enfactum OS returned an error (HTTP {r.status_code})."
        try:
            data = r.json()
        except ValueError:
            return "Enfactum OS returned a non-JSON response."

        body = self._shape(data)
        n = ctx.citations.add(kind="os", title=f"Enfactum OS \u00b7 {self.label}",
                              url=None, key=f"os:{self.name}:{json.dumps(query, sort_keys=True)}:{path}",
                              snippet=f"{path}" + (f"?{'&'.join(f'{k}={v}' for k, v in query.items())}" if query else ""))
        text = json.dumps(body, ensure_ascii=False, default=str)
        if len(text) > MAX_RESULT_CHARS:
            text = text[:MAX_RESULT_CHARS] + " …[truncated; ask the user to narrow the query]"
        return untrusted(f"enfactum_os:{self.name}", f"[{n}] Enfactum OS \u00b7 {self.label}\n{text}")

    def _shape(self, data: Any) -> Any:
        total = _dig(data, self.response.get("total")) if self.response.get("total") else None
        root = _dig(data, self.response.get("root")) if self.response.get("root") else data
        fields = self.response.get("fields")
        max_items = int(self.response.get("max_items", 25))
        if isinstance(root, list):
            items = root[:max_items]
            shaped: Any = [_pick(i, fields) for i in items] if fields else items
            result: Any = {"items": redact(shaped), "returned": len(items)}
            if total is not None:
                result["total"] = total
            elif len(root) > max_items:
                result["total"] = len(root)
            return result
        return redact(_pick(root, fields) if fields else root)


def os_headers(ctx_user) -> dict:
    """Requests to Enfactum OS carry the END USER's credentials, never a service account."""
    headers = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest", "X-Enfactum-Agent": "1"}
    if ctx_user.os_token:
        headers["Authorization"] = f"Bearer {ctx_user.os_token}"
    if ctx_user.os_cookies:
        headers["Cookie"] = ctx_user.os_cookies
    return headers


def load_os_spec(settings: Settings) -> tuple[dict, str]:
    path: Path = settings.os_tools_file
    if not path.exists():
        log.info("No OS tools file at %s; Enfactum OS tools disabled", path)
        return {}, ""
    spec = yaml.safe_load(_expand_env(path.read_text(), settings)) or {}
    base_url = spec.get("base_url") or settings.os_base_url
    if not base_url and (spec.get("tools") or spec.get("actions")):
        raise RuntimeError("OS tools configured but no base_url / OS_BASE_URL set")
    return spec, base_url


def load_os_tools(settings: Settings, http: httpx.AsyncClient) -> list[OSApiTool]:
    spec, base_url = load_os_spec(settings)
    tools = [OSApiTool(t, base_url, float(spec.get("timeout_seconds", 10)), settings, http)
             for t in spec.get("tools") or [] if t.get("enabled", True)]
    names = [t.name for t in tools]
    if len(names) != len(set(names)):
        raise RuntimeError("Duplicate OS tool names in " + str(settings.os_tools_file))
    log.info("Loaded %d Enfactum OS read tools from %s", len(tools), settings.os_tools_file.name)
    return tools
