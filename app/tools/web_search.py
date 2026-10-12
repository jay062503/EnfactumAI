import asyncio
import logging
from urllib.parse import urlparse

import httpx

from ..config import Settings
from ..rag.parsers import html_to_text
from .base import Tool, ToolContext, untrusted

log = logging.getLogger(__name__)

_TAVILY_RANGE = {"day": "day", "week": "week", "month": "month", "year": "year"}
_DDG_RANGE = {"day": "d", "week": "w", "month": "m", "year": "y"}


class WebSearchTool(Tool):
    def __init__(self, settings: Settings, http: httpx.AsyncClient):
        super().__init__(
            name="web_search",
            label="Searching the web",
            kind="web",
            required_permission=settings.perm_web_search or None,
            description=(
                "Search the public internet for current or public information: news, recent events, prices, "
                "market data, public companies, regulations, product releases, or anything that may have changed "
                "after your training data. Never use for Enfactum-internal information."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Concise, specific search-engine query."},
                    "recency": {"type": "string", "enum": ["any", "day", "week", "month", "year"],
                                "description": "Restrict to recent results when the question is time-sensitive."},
                },
                "required": ["query"],
            },
        )
        self.s = settings
        self.http = http
        provider = settings.web_search_provider.lower()
        if provider == "auto":
            provider = "tavily" if settings.tavily_api_key else "duckduckgo"
        self.provider = provider

    @property
    def enabled(self) -> bool:
        return self.provider in ("tavily", "duckduckgo")

    def status_text(self, args: dict) -> str:
        return f"Searching the web for \u201c{args.get('query', '')}\u201d"

    async def run(self, args: dict, ctx: ToolContext) -> str:
        query = str(args.get("query", "")).strip()[:400]
        recency = args.get("recency") or "any"
        if not query:
            return "Error: empty query."
        try:
            results = await (self._tavily(query, recency) if self.provider == "tavily" else self._ddg(query, recency))
        except Exception as exc:
            log.warning("Web search failed: %s", exc)
            return "Web search is temporarily unavailable. Tell the user you could not verify current information."
        if not results:
            return "No web results found."
        blocks = []
        for r in results:
            n = ctx.citations.add(kind="web", title=r["title"] or urlparse(r["url"]).netloc, url=r["url"],
                                  snippet=r["content"][:300])
            date = f" (published {r['date']})" if r.get("date") else ""
            blocks.append(f"[{n}] {r['title']}{date}\nURL: {r['url']}\n{r['content']}")
        return untrusted("web_search", "\n\n".join(blocks))

    async def _tavily(self, query: str, recency: str) -> list[dict]:
        body = {"query": query, "max_results": self.s.web_search_max_results, "search_depth": "basic",
                "include_answer": False, "include_raw_content": False,
                "topic": "news" if recency in ("day", "week") else "general"}
        if recency in _TAVILY_RANGE:
            body["time_range"] = _TAVILY_RANGE[recency]
        r = await self.http.post("https://api.tavily.com/search", json=body, timeout=self.s.web_timeout_seconds,
                                 headers={"Authorization": f"Bearer {self.s.tavily_api_key}"})
        r.raise_for_status()
        return [{"title": x.get("title", ""), "url": x.get("url", ""), "content": (x.get("content") or "")[:2500],
                 "date": x.get("published_date")} for x in r.json().get("results", [])]

    async def _ddg(self, query: str, recency: str) -> list[dict]:
        def search():
            try:
                from ddgs import DDGS
            except ImportError:
                from duckduckgo_search import DDGS
            return list(DDGS().text(query, max_results=self.s.web_search_max_results,
                                    timelimit=_DDG_RANGE.get(recency)))

        raw = await asyncio.wait_for(asyncio.to_thread(search), timeout=self.s.web_timeout_seconds)
        results = [{"title": x.get("title", ""), "url": x.get("href", ""), "content": x.get("body", "")} for x in raw]
        top = results[: self.s.web_fetch_pages]
        pages = await asyncio.gather(*(asyncio.wait_for(self._fetch(r["url"]), 2.5) for r in top),
                                     return_exceptions=True)
        for r, page in zip(top, pages):
            if isinstance(page, str) and len(page) > len(r["content"]):
                r["content"] = page
        return results

    async def _fetch(self, url: str) -> str:
        if not url.startswith(("http://", "https://")):
            return ""
        r = await self.http.get(url, timeout=2.5, follow_redirects=True,
                                headers={"User-Agent": "Mozilla/5.0 (compatible; EnfactumAssistant/1.0)"})
        if r.status_code != 200 or "html" not in r.headers.get("content-type", ""):
            return ""
        return html_to_text(r.text[:600_000])[:3000]
