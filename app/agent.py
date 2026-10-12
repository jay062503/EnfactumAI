import asyncio
import json
import logging
import re
import time
from collections.abc import AsyncIterator, Callable

from .attachments import IMAGE_TOKEN_ESTIMATE, build_document_context, estimate_tokens, image_parts
from .auth import UserContext
from .config import Settings
from .db import Database
from .llm import LLM, friendly_error
from .prompts import build_system_prompt
from .tools.base import Citations, Tool, ToolContext
from .tools.registry import ToolRegistry

log = logging.getLogger(__name__)
_CITE = re.compile(r"\[(\d{1,3})\]")
TOOL_RESERVE_TOKENS = 6000
SLOW_TOOLS = {"create_file": 60, "create_chart": 30, "generate_image": 120}


def _never() -> bool:
    return False


class Agent:
    def __init__(self, settings: Settings, llm: LLM, registry: ToolRegistry, db: Database):
        self.s = settings
        self.llm = llm
        self.registry = registry
        self.db = db

    @property
    def context_window(self) -> int:
        return self.llm.profile.context_window

    async def run(self, user: UserContext, conversation_id: str, message: str, mode: str,
                  new_attachments: list[dict] | None = None, prefs: dict | None = None,
                  should_stop: Callable[[], bool] = _never) -> AsyncIterator[dict]:
        t0 = time.perf_counter()
        timing = {"first_token_ms": None, "llm_ms": 0, "tools_ms": 0, "rounds": 0}
        tools = self.registry.for_user(user, mode)
        allowed = {t.name: t for t in tools}
        new_attachments = new_attachments or []
        history = self.db.get_messages(conversation_id, limit=self.s.history_turns * 2)
        user_msg_id = self.db.add_message(conversation_id, "user", message, meta={
            "mode": mode, "attachments": [{"id": a["id"], "name": a["name"], "kind": a["kind"]} for a in new_attachments]})
        yield {"type": "user_message", "id": user_msg_id}

        ctx = ToolContext(user=user, citations=Citations(), conversation_id=conversation_id)
        system = build_system_prompt(user, tools, mode, prefs)

        all_atts = [a for a in self.db.conversation_attachments(conversation_id, user.id) if a["kind"] != "generated"]
        budget = min(self.s.attachment_context_chars, max(4000, (self.context_window - self.s.llm_max_tokens) * 2))
        doc_context = build_document_context(all_atts, message, budget, ctx.citations)
        text = f"{doc_context}\n\n{message}" if doc_context else message
        images = image_parts(new_attachments) if self.s.llm_supports_vision else []
        if not self.s.llm_supports_vision and any(a["kind"] == "image" and not a.get("text") for a in new_attachments):
            text += "\n\n(The employee attached an image, but it could not be read. Say so.)"
        user_content = [{"type": "text", "text": text}, *images] if images else text

        fixed = estimate_tokens(system) + estimate_tokens(text) + len(images) * IMAGE_TOKEN_ESTIMATE
        history_budget = self.context_window - self.s.llm_max_tokens - TOOL_RESERVE_TOKENS - fixed
        past: list[dict] = []
        for m in reversed(history):
            content = _CITE.sub("", m["content"]).strip()
            meta = m.get("meta") or {}
            names = [a["name"] for a in meta.get("attachments", [])]
            if names:
                content = f"[attached: {', '.join(names)}] {content}"
            made = [a["name"] for a in meta.get("artifacts", []) if a.get("type") in ("file", "image")]
            if made:
                content += f"\n[created for the user: {', '.join(made)}]"
            cost = estimate_tokens(content) + 4
            if history_budget - cost < 0:
                break
            history_budget -= cost
            past.insert(0, {"role": m["role"], "content": content})

        messages: list[dict] = [{"role": "system", "content": system}, *past, {"role": "user", "content": user_content}]
        used: list[str] = []
        answer_parts: list[str] = []
        usage = {"prompt": 0, "completion": 0, "reported": False}
        stopped = failed = False
        sent_artifacts = 0

        try:
            forced = [n for n in (("web_search",) if mode == "web" else ("search_company_documents",)
                                  if mode == "company" else ()) if n in allowed]
            if forced:
                calls = [{"id": f"prefetch_{i}", "name": n, "arguments": json.dumps({"query": message})}
                         for i, n in enumerate(forced)]
                t = time.perf_counter()
                async for event in self._execute(calls, allowed, ctx, messages, used, ""):
                    yield event
                timing["tools_ms"] += int((time.perf_counter() - t) * 1000)

            for round_no in range(self.s.max_tool_rounds):
                if should_stop():
                    stopped = True
                    break
                timing["rounds"] += 1
                offer = tools if round_no < self.s.max_tool_rounds - 1 else []
                t = time.perf_counter()
                stream = await self.llm.stream(messages, [x.schema() for x in offer] or None)
                text_parts: list[str] = []
                calls: dict[int, dict] = {}
                try:
                    async for chunk in stream:
                        if should_stop():
                            stopped = True
                            break
                        if getattr(chunk, "usage", None):
                            usage.update(prompt=chunk.usage.prompt_tokens or 0,
                                         completion=chunk.usage.completion_tokens or 0, reported=True)
                        if not chunk.choices:
                            continue
                        delta = chunk.choices[0].delta
                        if delta.content:
                            if timing["first_token_ms"] is None:
                                timing["first_token_ms"] = int((time.perf_counter() - t0) * 1000)
                            text_parts.append(delta.content)
                            yield {"type": "token", "text": delta.content}
                        for tc in delta.tool_calls or []:
                            slot = calls.setdefault(tc.index or 0, {"id": "", "name": "", "arguments": ""})
                            if tc.id:
                                slot["id"] = tc.id
                            if tc.function:
                                if tc.function.name and tc.function.name != slot["name"]:
                                    slot["name"] += tc.function.name
                                if tc.function.arguments:
                                    slot["arguments"] += tc.function.arguments
                finally:
                    timing["llm_ms"] += int((time.perf_counter() - t) * 1000)
                    if stopped:
                        await _close(stream)
                text_out = "".join(text_parts)
                if text_out:
                    answer_parts.append(text_out)
                if stopped or not calls:
                    break
                ordered = []
                for i, (_, c) in enumerate(sorted(calls.items())):
                    c["id"] = c["id"] or f"call_{round_no}_{i}"
                    ordered.append(c)
                if text_out:
                    yield {"type": "token", "text": "\n\n"}
                t = time.perf_counter()
                async for event in self._execute(ordered, allowed, ctx, messages, used, text_out):
                    yield event
                timing["tools_ms"] += int((time.perf_counter() - t) * 1000)
                for art in ctx.artifacts[sent_artifacts:]:
                    yield {"type": "artifact", "artifact": art}
                sent_artifacts = len(ctx.artifacts)
        except Exception as exc:
            failed = True
            log.exception("Agent run failed")
            yield {"type": "error", "message": friendly_error(exc)}

        for art in ctx.artifacts[sent_artifacts:]:
            yield {"type": "artifact", "artifact": art}
        answer = "\n\n".join(answer_parts).strip()
        cited = {int(n) for n in _CITE.findall(answer)}
        sources = [s for s in ctx.citations.items if s["n"] in cited]
        latency_ms = int((time.perf_counter() - t0) * 1000)
        timing["total_ms"] = latency_ms
        if not usage["reported"]:
            usage["prompt"] = sum(_estimate_message(m) for m in messages)
            usage["completion"] = estimate_tokens(answer)
        context = {"used": usage["prompt"] + usage["completion"], "window": self.context_window,
                   "estimated": not usage["reported"]}
        yield {"type": "usage", **context}
        msg_id = None
        if answer or ctx.artifacts:
            msg_id = self.db.add_message(
                conversation_id, "assistant", answer or "Here you go.", sources=sources,
                meta={"mode": mode, "tools": used, "latency_ms": latency_ms, "context": context, "timing": timing,
                      "artifacts": ctx.artifacts, "stopped": stopped, "incomplete": failed})
        log.info("answer user=%s conv=%s total=%dms first_token=%sms llm=%dms tools=%dms rounds=%d tools=%s%s",
                 user.id, conversation_id[:8], latency_ms, timing["first_token_ms"], timing["llm_ms"],
                 timing["tools_ms"], timing["rounds"], used, " (stopped)" if stopped else "")
        yield {"type": "sources", "sources": sources}
        yield {"type": "done", "message_id": msg_id, "user_message_id": user_msg_id, "latency_ms": latency_ms,
               "tools": used, "timing": timing, "stopped": stopped}

    async def _execute(self, calls: list[dict], allowed: dict[str, Tool], ctx: ToolContext, messages: list[dict],
                       used: list[str], assistant_text: str) -> AsyncIterator[dict]:
        messages.append({
            "role": "assistant", "content": assistant_text or None,
            "tool_calls": [{"id": c["id"], "type": "function",
                            "function": {"name": c["name"], "arguments": c["arguments"] or "{}"}} for c in calls],
        })
        parsed = []
        for c in calls:
            try:
                args = json.loads(c["arguments"] or "{}")
                if not isinstance(args, dict):
                    raise ValueError
            except ValueError:
                args = None
            tool = allowed.get(c["name"])
            parsed.append((c, tool, args))
            label = tool.status_text(args or {}) if tool else c["name"]
            yield {"type": "status", "id": c["id"], "state": "running", "label": label,
                   "kind": tool.kind if tool else "unknown"}

        results = await asyncio.gather(*(self._run_one(c, tool, args, ctx) for c, tool, args in parsed))
        for (c, tool, _), result in zip(parsed, results):
            if tool:
                used.append(tool.name)
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": result})
            yield {"type": "status", "id": c["id"], "state": "done"}

    async def _run_one(self, call: dict, tool: Tool | None, args: dict | None, ctx: ToolContext) -> str:
        if tool is None:
            self.db.audit(ctx.user.id, "tool_denied", {"tool": call["name"]})
            return f"Error: tool '{call['name']}' is not available to this user."
        if args is None:
            return "Error: arguments were not valid JSON. Retry with a valid JSON object."
        self.db.audit(ctx.user.id, "tool_call", {"tool": tool.name, "args": _audit_args(args)})
        timeout = SLOW_TOOLS.get(tool.name, self.s.tool_timeout_seconds)
        try:
            return await asyncio.wait_for(tool.run(args, ctx), timeout=timeout)
        except asyncio.TimeoutError:
            return f"Error: {tool.name} timed out. Tell the user this source is slow right now."
        except Exception as exc:
            log.exception("Tool %s failed", tool.name)
            return f"Error: {tool.name} failed ({type(exc).__name__})."


async def _close(stream) -> None:
    try:
        await stream.close()
    except Exception:
        pass


def _audit_args(args: dict) -> dict:
    return {k: (v[:200] + "…" if isinstance(v, str) and len(v) > 200 else v) for k, v in args.items()
            if k not in ("rows", "sheets")}


def _estimate_message(m: dict) -> int:
    content = m.get("content") or ""
    if isinstance(content, list):
        return sum(estimate_tokens(p.get("text", "")) if p.get("type") == "text" else IMAGE_TOKEN_ESTIMATE
                   for p in content) + 4
    extra = sum(estimate_tokens(c["function"]["arguments"]) + 10 for c in m.get("tool_calls", []))
    return estimate_tokens(content) + extra + 4
