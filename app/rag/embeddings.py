import asyncio
import logging
import time
from collections import OrderedDict

import httpx
import numpy as np
from openai import AsyncOpenAI

from ..config import Settings, get_llm_profile

log = logging.getLogger(__name__)


class Embedder:
    """Produces L2-normalised float32 vectors, or None when embeddings are unavailable (retrieval then uses BM25)."""

    def __init__(self, settings: Settings):
        self.s = settings
        self.provider = settings.embedding_provider.lower()
        self._client: AsyncOpenAI | None = None
        self._query_client: AsyncOpenAI | None = None
        self._local = None
        self._disabled_until = 0.0
        self._cache: OrderedDict[str, np.ndarray] = OrderedDict()
        profile = get_llm_profile()
        self.model = profile.embedding_model
        if self.provider == "llm":
            if not self.model and not settings.embedding_base_url:
                log.info("Provider '%s' has no embeddings API; document search uses keyword ranking "
                         "(set EMBEDDING_PROVIDER=local for semantic search)", profile.provider)
                self.provider = "none"
            else:
                self._client = AsyncOpenAI(
                    base_url=settings.embedding_base_url or profile.base_url or None,
                    api_key=settings.embedding_api_key or settings.llm_api_key or "local-no-key",
                    timeout=httpx.Timeout(20, connect=4), max_retries=1,
                )
                # Query embeddings sit on the answer's critical path: fail fast, fall back to keyword search.
                self._query_client = self._client.with_options(timeout=httpx.Timeout(4, connect=2), max_retries=0)

    @property
    def enabled(self) -> bool:
        return self.provider in ("llm", "local") and time.time() >= self._disabled_until

    async def embed_documents(self, texts: list[str]) -> list[np.ndarray] | None:
        if not self.enabled or not texts:
            return None
        out: list[np.ndarray] = []
        try:
            for i in range(0, len(texts), 64):
                out.extend(await self._embed(texts[i:i + 64]))
            return out
        except Exception as exc:
            self._fail(exc)
            return None

    async def embed_query(self, text: str) -> np.ndarray | None:
        if not self.enabled:
            return None
        if text in self._cache:
            self._cache.move_to_end(text)
            return self._cache[text]
        try:
            vec = (await self._embed([text], query=True))[0]
        except Exception as exc:
            self._fail(exc)
            return None
        self._cache[text] = vec
        if len(self._cache) > 512:
            self._cache.popitem(last=False)
        return vec

    async def _embed(self, texts: list[str], query: bool = False) -> list[np.ndarray]:
        if self.provider == "local":
            vectors = await asyncio.to_thread(self._local_embed, texts)
        else:
            client = self._query_client if query else self._client
            resp = await client.embeddings.create(model=self.model or "text-embedding-3-small", input=texts)
            vectors = [np.asarray(d.embedding, dtype=np.float32) for d in resp.data]
        return [v / (np.linalg.norm(v) or 1.0) for v in vectors]

    def _local_embed(self, texts: list[str]) -> list[np.ndarray]:
        if self._local is None:
            from fastembed import TextEmbedding

            self._local = TextEmbedding(model_name=self.s.local_embedding_model)
        return [np.asarray(v, dtype=np.float32) for v in self._local.embed(texts)]

    def _fail(self, exc: Exception) -> None:
        log.warning("Embeddings unavailable (%s); using keyword search for 5 minutes", exc)
        self._disabled_until = time.time() + 300
