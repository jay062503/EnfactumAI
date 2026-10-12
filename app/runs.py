"""Background agent runs.

A chat answer is produced by a server-side task that is independent of the HTTP connection. The browser only
subscribes to the run's event log, so closing the tab, switching chats, minimising or refreshing never stops the
answer: the client re-attaches (replaying events from any offset) or simply loads the saved message.

In-memory and per-process: run the app with a single worker (the default), or put sticky sessions in front of
several workers.
"""
import asyncio
import logging
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field

log = logging.getLogger(__name__)
FINISHED_TTL_SECONDS = 6 * 3600
MAX_RUN_SECONDS = 15 * 60


@dataclass
class Run:
    id: str
    user_id: str
    conversation_id: str
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    status: str = "running"  # running | done | error | cancelled
    seen: bool = False
    events: list[dict] = field(default_factory=list)
    stop_requested: bool = False
    task: asyncio.Task | None = None
    cond: asyncio.Condition = field(default_factory=asyncio.Condition)

    @property
    def finished(self) -> bool:
        return self.finished_at is not None

    def public(self) -> dict:
        return {"id": self.id, "conversation_id": self.conversation_id, "status": self.status,
                "started_at": self.started_at, "finished_at": self.finished_at, "seen": self.seen,
                "events": len(self.events)}


class ConversationBusy(RuntimeError):
    pass


class RunManager:
    def __init__(self):
        self._runs: dict[str, Run] = {}

    def start(self, user_id: str, conversation_id: str,
              factory: Callable[[Callable[[], bool]], AsyncIterator[dict]], first_events: list[dict]) -> Run:
        if self.active_for_conversation(conversation_id, user_id):
            raise ConversationBusy("An answer is already being generated in this conversation")
        self._cleanup()
        run = Run(id=uuid.uuid4().hex, user_id=user_id, conversation_id=conversation_id)
        run.events.extend({**e, "seq": i} for i, e in enumerate(first_events))
        self._runs[run.id] = run
        run.task = asyncio.create_task(self._drive(run, factory(lambda: run.stop_requested)))
        return run

    async def _drive(self, run: Run, events: AsyncIterator[dict]) -> None:
        status = "done"

        async def consume():
            nonlocal status
            async for event in events:
                if event.get("type") == "error":
                    status = "error"
                await self._emit(run, event)

        try:
            await asyncio.wait_for(consume(), MAX_RUN_SECONDS)
        except asyncio.TimeoutError:
            status = "error"
            await self._emit(run, {"type": "error", "message": "The answer took too long and was stopped."})
        except asyncio.CancelledError:
            status = "cancelled"
        except Exception:
            log.exception("Run %s crashed", run.id)
            status = "error"
            await self._emit(run, {"type": "error", "message": "Something went wrong while generating the answer."})
        finally:
            if run.stop_requested and status == "done":
                status = "cancelled"
            run.status = status
            run.finished_at = time.time()
            await self._emit(run, {"type": "run_end", "status": status})

    async def _emit(self, run: Run, event: dict) -> None:
        async with run.cond:
            run.events.append({**event, "seq": len(run.events)})
            run.cond.notify_all()

    async def subscribe(self, run: Run, start: int = 0) -> AsyncIterator[dict]:
        i = max(0, start)
        while True:
            async with run.cond:
                await run.cond.wait_for(lambda: len(run.events) > i or run.finished)
                batch = run.events[i:]
            for event in batch:
                yield event
            i += len(batch)
            if run.finished and i >= len(run.events):
                return

    # ---- queries ---------------------------------------------------------------------------------------------
    def get(self, run_id: str, user_id: str) -> Run | None:
        run = self._runs.get(run_id)
        return run if run and run.user_id == user_id else None

    def active_for_conversation(self, conversation_id: str, user_id: str) -> Run | None:
        return next((r for r in self._runs.values() if r.conversation_id == conversation_id
                     and r.user_id == user_id and not r.finished), None)

    def latest_for_conversation(self, conversation_id: str, user_id: str) -> Run | None:
        runs = [r for r in self._runs.values() if r.conversation_id == conversation_id and r.user_id == user_id]
        return max(runs, key=lambda r: r.started_at) if runs else None

    def for_user(self, user_id: str) -> list[Run]:
        """Running runs + finished runs the employee has not looked at yet (sidebar spinner / blue tick)."""
        return [r for r in self._runs.values() if r.user_id == user_id and (not r.finished or not r.seen)]

    def mark_seen(self, conversation_id: str, user_id: str) -> None:
        for r in self._runs.values():
            if r.conversation_id == conversation_id and r.user_id == user_id and r.finished:
                r.seen = True

    def cancel(self, run_id: str, user_id: str) -> bool:
        run = self.get(run_id, user_id)
        if not run or run.finished:
            return False
        run.stop_requested = True
        return True

    def forget_conversation(self, conversation_id: str, user_id: str) -> None:
        for r in list(self._runs.values()):
            if r.conversation_id == conversation_id and r.user_id == user_id:
                r.stop_requested = True
                if r.finished:
                    self._runs.pop(r.id, None)

    def _cleanup(self) -> None:
        now = time.time()
        for rid, r in list(self._runs.items()):
            if r.finished and (now - r.finished_at > FINISHED_TTL_SECONDS or (r.seen and now - r.finished_at > 300)):
                self._runs.pop(rid, None)

    async def shutdown(self) -> None:
        for r in self._runs.values():
            r.stop_requested = True
        tasks = [r.task for r in self._runs.values() if r.task and not r.task.done()]
        if tasks:
            await asyncio.wait(tasks, timeout=5)
