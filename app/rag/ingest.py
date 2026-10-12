import asyncio
import uuid
from pathlib import Path

import numpy as np

from ..config import Settings
from ..db import Database
from .chunker import chunk_text
from .embeddings import Embedder
from .extract import Extractor
from .index import DocumentIndex
from .parsers import IMAGE_TYPES, MIME_TYPES, SUPPORTED_EXTENSIONS


def kb_extensions() -> set[str]:
    return SUPPORTED_EXTENSIONS | set(IMAGE_TYPES)


class Ingestor:
    def __init__(self, settings: Settings, db: Database, embedder: Embedder, index: DocumentIndex,
                 extractor: Extractor):
        self.s = settings
        self.db = db
        self.embedder = embedder
        self.index = index
        self.extractor = extractor
        self.files_dir = settings.data_dir / "documents"
        self._lock = asyncio.Lock()

    async def ingest(self, *, filename: str, data: bytes, title: str | None, visibility: dict, uploaded_by: str,
                     mime: str = "") -> dict:
        sections, used_ocr = await self.extractor.extract(filename, data)
        title = (title or Path(filename).stem.replace("_", " ").replace("-", " ")).strip()[:200]
        pieces: list[tuple[int | None, str]] = []
        for text, page in sections:
            for chunk in chunk_text(text, self.s.rag_chunk_size, self.s.rag_chunk_overlap):
                pieces.append((page, chunk))
        vectors = await self.embedder.embed_documents([f"{title}\n{c}" for _, c in pieces])
        rows = [(i, page, text, vectors[i].astype(np.float32).tobytes() if vectors else None)
                for i, (page, text) in enumerate(pieces)]
        content = "\n\n".join(f"[Page {p}]\n{t}" if p else t for t, p in sections)

        doc_id = uuid.uuid4().hex
        ext = Path(filename).suffix.lower()
        self.files_dir.mkdir(parents=True, exist_ok=True)
        path = self.files_dir / f"{doc_id}{ext}"
        await asyncio.to_thread(path.write_bytes, data)
        async with self._lock:
            self.db.add_document(doc_id=doc_id, title=title, filename=filename, mime=MIME_TYPES.get(ext, mime),
                                 size_bytes=len(data), uploaded_by=uploaded_by, visibility=visibility, chunks=rows,
                                 file_path=str(path), content=content)
            await asyncio.to_thread(self.index.reload)
        return {"id": doc_id, "title": title, "chunks": len(rows), "embedded": bool(vectors), "ocr": used_ocr}

    async def delete(self, doc_id: str) -> None:
        doc = self.db.get_document(doc_id)
        async with self._lock:
            self.db.delete_document(doc_id)
            await asyncio.to_thread(self.index.reload)
        if doc and doc.get("file_path"):
            p = Path(doc["file_path"]).resolve()
            if self.files_dir.resolve() in p.parents:
                p.unlink(missing_ok=True)
