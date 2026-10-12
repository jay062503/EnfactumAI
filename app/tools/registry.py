from ..auth import UserContext
from .base import Tool

MODES = ("auto", "general", "web", "company")
DATA_KINDS = {"web", "documents", "company", "action"}


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self._tools = {t.name: t for t in tools}

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def for_user(self, user: UserContext, mode: str = "auto") -> list[Tool]:
        """Tools the LLM may see for this user and mode. Tools the user is not permitted to use are never offered.
        File/chart/image creation ("files") is available in every mode."""
        allowed = [t for t in self._tools.values() if t.available_for(user)]
        if mode == "general":
            return [t for t in allowed if t.kind == "files"]
        if mode == "web":
            return [t for t in allowed if t.kind in ("web", "files")]
        if mode == "company":
            return [t for t in allowed if t.kind in ("documents", "company", "action", "files")]
        return allowed
