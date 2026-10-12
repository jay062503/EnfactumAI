"""Hybrid (BM25 + dense vector) retrieval with document-level access control applied BEFORE ranking."""
import json
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass

import numpy as np

from ..auth import UserContext
from ..db import Database
from .embeddings import Embedder

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    "a an and are as at be by for from has have how i in is it its of on or that the this to was what when where "
    "which who why will with do does can our we you your my me about".split()
)


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 1]


def can_view(visibility: dict, user: UserContext) -> bool:
    """visibility = {"scope": "all"} or {"scope": "restricted", "roles": [...], "permissions": [...], "users": [...]}"""
    if user.is_admin or (visibility or {}).get("scope", "all") == "all":
        return True
    if user.id in {str(u) for u in visibility.get("users", [])}:
        return True
    if user.roles & set(visibility.get("roles", [])):
        return True
    return bool(user.permissions & set(visibility.get("permissions", [])))


@dataclass
class SearchHit:
    chunk_id: int
    document_id: str
    title: str
    page: int | None
    text: str
    score: float


class _State:
    def __init__(self, rows: list[dict]):
        self.n = len(rows)
        self.chunk_ids = [r["id"] for r in rows]
        self.doc_ids = [r["document_id"] for r in rows]
        self.titles = [r["title"] for r in rows]
        self.pages = [r["page"] for r in rows]
        self.texts = [r["text"] for r in rows]
        self.visibility = {r["document_id"]: json.loads(r["visibility"]) for r in rows}
        self.doc_list = list(self.visibility)
        pos = {d: i for i, d in enumerate(self.doc_list)}
        self.doc_idx = np.array([pos[d] for d in self.doc_ids], dtype=np.int64)

        self.postings: dict[str, list[tuple[int, int]]] = defaultdict(list)
        self.doc_len = np.zeros(self.n, dtype=np.float32)
        for i, r in enumerate(rows):
            toks = tokenize(f"{r['title']} {r['text']}")
            self.doc_len[i] = len(toks)
            for term, tf in Counter(toks).items():
                self.postings[term].append((i, tf))
        self.avgdl = float(self.doc_len.mean()) if self.n else 1.0
        self.idf = {t: math.log(1 + (self.n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.postings.items()}

        dims = Counter(len(r["embedding"]) // 4 for r in rows if r["embedding"])
        self.dim = dims.most_common(1)[0][0] if dims else 0
        self.emb = None
        if self.dim:
            self.emb = np.zeros((self.n, self.dim), dtype=np.float32)
            for i, r in enumerate(rows):
                if r["embedding"] and len(r["embedding"]) // 4 == self.dim:
                    self.emb[i] = np.frombuffer(r["embedding"], dtype=np.float32)


class DocumentIndex:
    def __init__(self, db: Database, embedder: Embedder):
        self.db = db
        self.embedder = embedder
        self._state = _State([])

    def reload(self) -> None:
        self._state = _State(self.db.all_chunks())

    @property
    def size(self) -> int:
        return self._state.n

    async def search(self, query: str, user: UserContext, k: int = 6) -> list[SearchHit]:
        st = self._state
        if not st.n or not query.strip():
            return []
        doc_ok = np.array([can_view(st.visibility[d], user) for d in st.doc_list], dtype=bool)
        allowed = doc_ok[st.doc_idx]
        if not allowed.any():
            return []
        pool = max(k * 4, 20)

        bm25 = np.zeros(st.n, dtype=np.float32)
        k1, b = 1.5, 0.75
        for term in set(tokenize(query)):
            idf = st.idf.get(term)
            if idf is None:
                continue
            for i, tf in st.postings[term]:
                bm25[i] += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * st.doc_len[i] / st.avgdl))
        bm25[~allowed] = 0
        lexical = [i for i in np.argsort(-bm25)[:pool] if bm25[i] > 0]

        dense: list[int] = []
        if st.emb is not None:
            qv = await self.embedder.embed_query(query)
            if qv is not None and qv.shape[0] == st.dim:
                sims = st.emb @ qv
                sims[~allowed] = -1.0
                dense = [i for i in np.argsort(-sims)[:pool] if sims[i] > 0]

        fused: dict[int, float] = defaultdict(float)
        for ranking in (lexical, dense):
            for rank, i in enumerate(ranking):
                fused[int(i)] += 1.0 / (60 + rank)
        best = sorted(fused.items(), key=lambda kv: -kv[1])[:k]
        return [SearchHit(st.chunk_ids[i], st.doc_ids[i], st.titles[i], st.pages[i], st.texts[i], score)
                for i, score in best]
