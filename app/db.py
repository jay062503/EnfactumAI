import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    filename TEXT NOT NULL,
    mime TEXT,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    uploaded_by TEXT NOT NULL,
    visibility TEXT NOT NULL,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ord INTEGER NOT NULL,
    page INTEGER,
    text TEXT NOT NULL,
    embedding BLOB
);
CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(document_id);
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    title TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conv_user ON conversations(user_id, updated_at DESC);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    sources TEXT,
    meta TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, created_at);
CREATE TABLE IF NOT EXISTS attachments (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,
    mime TEXT,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    text TEXT,
    file_path TEXT,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_att_conv ON attachments(conversation_id);
CREATE TABLE IF NOT EXISTS user_settings (
    user_id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    updated_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS feedback (
    message_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    rating TEXT NOT NULL,
    comment TEXT,
    created_at REAL NOT NULL,
    PRIMARY KEY (message_id, user_id)
);
CREATE TABLE IF NOT EXISTS pending_actions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    conversation_id TEXT,
    tool TEXT NOT NULL,
    args TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL,
    result TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_actions_conv ON pending_actions(conversation_id);
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    detail TEXT
);
"""


class Database:
    """Thin thread-safe SQLite store. All queries are parameterised; no LLM-generated SQL ever reaches it."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(SCHEMA)
            cols = {r[1] for r in self._conn.execute("PRAGMA table_info(conversations)")}
            if "pinned" not in cols:
                self._conn.execute("ALTER TABLE conversations ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
            doc_cols = {r[1] for r in self._conn.execute("PRAGMA table_info(documents)")}
            if "file_path" not in doc_cols:
                self._conn.execute("ALTER TABLE documents ADD COLUMN file_path TEXT")
            if "content" not in doc_cols:
                self._conn.execute("ALTER TABLE documents ADD COLUMN content TEXT")
            self._conn.commit()

    def _exec(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def _all(self, sql: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(r) for r in self._conn.execute(sql, params).fetchall()]

    def _one(self, sql: str, params: tuple = ()) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute(sql, params).fetchone()
            return dict(row) if row else None

    # ---- documents -------------------------------------------------------
    def add_document(self, *, title: str, filename: str, mime: str, size_bytes: int, uploaded_by: str,
                     visibility: dict, chunks: list[tuple[int, int | None, str, bytes | None]],
                     doc_id: str | None = None, file_path: str | None = None, content: str | None = None) -> str:
        doc_id = doc_id or uuid.uuid4().hex
        with self._lock:
            self._conn.execute(
                "INSERT INTO documents (id, title, filename, mime, size_bytes, uploaded_by, visibility, chunk_count,"
                " created_at, file_path, content) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (doc_id, title, filename, mime, size_bytes, uploaded_by, json.dumps(visibility), len(chunks),
                 time.time(), file_path, content),
            )
            self._conn.executemany(
                "INSERT INTO chunks (document_id, ord, page, text, embedding) VALUES (?,?,?,?,?)",
                [(doc_id, ord_, page, text, emb) for ord_, page, text, emb in chunks],
            )
            self._conn.commit()
        return doc_id

    def document_text(self, doc_id: str) -> str:
        row = self._one("SELECT content FROM documents WHERE id=?", (doc_id,))
        if row and row["content"]:
            return row["content"]
        return "\n\n".join(r["text"] for r in self._all("SELECT text FROM chunks WHERE document_id=? ORDER BY ord",
                                                        (doc_id,)))

    def list_documents(self) -> list[dict[str, Any]]:
        rows = self._all("SELECT id, title, filename, mime, size_bytes, uploaded_by, visibility, chunk_count,"
                         " created_at, file_path FROM documents ORDER BY created_at DESC")
        for r in rows:
            r["visibility"] = json.loads(r["visibility"])
        return rows

    def get_document(self, doc_id: str) -> dict[str, Any] | None:
        row = self._one("SELECT * FROM documents WHERE id=?", (doc_id,))
        if row:
            row["visibility"] = json.loads(row["visibility"])
        return row

    def delete_document(self, doc_id: str) -> None:
        self._exec("DELETE FROM documents WHERE id=?", (doc_id,))

    def all_chunks(self) -> list[dict[str, Any]]:
        return self._all(
            "SELECT c.id, c.document_id, c.ord, c.page, c.text, c.embedding, d.title, d.visibility"
            " FROM chunks c JOIN documents d ON d.id = c.document_id ORDER BY c.document_id, c.ord"
        )

    def count_documents(self) -> int:
        row = self._one("SELECT COUNT(*) AS n FROM documents")
        return int(row["n"]) if row else 0

    # ---- conversations ---------------------------------------------------
    def create_conversation(self, user_id: str, title: str) -> str:
        conv_id = uuid.uuid4().hex
        now = time.time()
        self._exec("INSERT INTO conversations (id, user_id, title, created_at, updated_at) VALUES (?,?,?,?,?)",
                   (conv_id, user_id, title, now, now))
        return conv_id

    def get_conversation(self, conv_id: str, user_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM conversations WHERE id=? AND user_id=?", (conv_id, user_id))

    def list_conversations(self, user_id: str, limit: int = 300) -> list[dict[str, Any]]:
        return self._all("SELECT id, title, pinned, updated_at FROM conversations WHERE user_id=?"
                         " ORDER BY pinned DESC, updated_at DESC LIMIT ?", (user_id, limit))

    def update_conversation(self, conv_id: str, user_id: str, *, title: str | None = None,
                            pinned: bool | None = None) -> bool:
        sets, params = [], []
        if title is not None:
            sets.append("title=?")
            params.append(title)
        if pinned is not None:
            sets.append("pinned=?")
            params.append(1 if pinned else 0)
        if not sets:
            return True
        return self._exec(f"UPDATE conversations SET {', '.join(sets)} WHERE id=? AND user_id=?",
                          (*params, conv_id, user_id)).rowcount > 0

    def delete_conversation(self, conv_id: str, user_id: str) -> bool:
        return self._exec("DELETE FROM conversations WHERE id=? AND user_id=?", (conv_id, user_id)).rowcount > 0

    def delete_all_conversations(self, user_id: str) -> int:
        return self._exec("DELETE FROM conversations WHERE user_id=?", (user_id,)).rowcount

    # ---- attachments -----------------------------------------------------
    def add_attachment(self, *, user_id: str, conversation_id: str | None, name: str, kind: str, mime: str,
                       size_bytes: int, text: str | None, file_path: str | None) -> str:
        att_id = uuid.uuid4().hex
        self._exec("INSERT INTO attachments (id, user_id, conversation_id, name, kind, mime, size_bytes, text, file_path,"
                   " created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (att_id, user_id, conversation_id, name, kind, mime, size_bytes, text, file_path, time.time()))
        return att_id

    def get_attachment(self, att_id: str, user_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM attachments WHERE id=? AND user_id=?", (att_id, user_id))

    def link_attachment(self, att_id: str, user_id: str, conversation_id: str) -> None:
        self._exec("UPDATE attachments SET conversation_id=? WHERE id=? AND user_id=? AND conversation_id IS NULL",
                   (conversation_id, att_id, user_id))

    def conversation_attachments(self, conversation_id: str, user_id: str) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM attachments WHERE conversation_id=? AND user_id=? ORDER BY created_at",
                         (conversation_id, user_id))

    def delete_attachment(self, att_id: str, user_id: str) -> dict[str, Any] | None:
        row = self.get_attachment(att_id, user_id)
        if row:
            self._exec("DELETE FROM attachments WHERE id=? AND user_id=?", (att_id, user_id))
        return row

    def attachment_files_for_user(self, user_id: str) -> list[str]:
        return [r["file_path"] for r in self._all("SELECT file_path FROM attachments WHERE user_id=? AND file_path"
                                                  " IS NOT NULL", (user_id,))]

    # ---- user settings ---------------------------------------------------
    def get_settings(self, user_id: str) -> dict[str, Any]:
        row = self._one("SELECT data FROM user_settings WHERE user_id=?", (user_id,))
        return json.loads(row["data"]) if row else {}

    def save_settings(self, user_id: str, data: dict[str, Any]) -> None:
        self._exec("INSERT INTO user_settings (user_id, data, updated_at) VALUES (?,?,?)"
                   " ON CONFLICT(user_id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
                   (user_id, json.dumps(data), time.time()))

    def add_message(self, conv_id: str, role: str, content: str, sources: list | None = None,
                    meta: dict | None = None) -> str:
        msg_id = uuid.uuid4().hex
        now = time.time()
        with self._lock:
            self._conn.execute(
                "INSERT INTO messages (id, conversation_id, role, content, sources, meta, created_at) VALUES (?,?,?,?,?,?,?)",
                (msg_id, conv_id, role, content, json.dumps(sources or []), json.dumps(meta or {}), now),
            )
            self._conn.execute("UPDATE conversations SET updated_at=? WHERE id=?", (now, conv_id))
            self._conn.commit()
        return msg_id

    def get_message(self, msg_id: str, user_id: str) -> dict[str, Any] | None:
        row = self._one("SELECT m.* FROM messages m JOIN conversations c ON c.id = m.conversation_id"
                        " WHERE m.id=? AND c.user_id=?", (msg_id, user_id))
        if row:
            row["sources"] = json.loads(row["sources"] or "[]")
            row["meta"] = json.loads(row["meta"] or "{}")
        return row

    def delete_messages_from(self, conv_id: str, msg_id: str) -> int:
        """Delete a message and everything after it (used by edit / regenerate)."""
        with self._lock:
            row = self._conn.execute("SELECT created_at FROM messages WHERE id=? AND conversation_id=?",
                                     (msg_id, conv_id)).fetchone()
            if not row:
                return 0
            n = self._conn.execute("DELETE FROM messages WHERE conversation_id=? AND created_at>=?",
                                   (conv_id, row["created_at"])).rowcount
            self._conn.commit()
            return n

    def set_feedback(self, msg_id: str, user_id: str, rating: str, comment: str = "") -> None:
        if rating == "none":
            self._exec("DELETE FROM feedback WHERE message_id=? AND user_id=?", (msg_id, user_id))
            return
        self._exec("INSERT INTO feedback (message_id, user_id, rating, comment, created_at) VALUES (?,?,?,?,?)"
                   " ON CONFLICT(message_id, user_id) DO UPDATE SET rating=excluded.rating, comment=excluded.comment",
                   (msg_id, user_id, rating, comment, time.time()))

    def feedback_for(self, conv_id: str, user_id: str) -> dict[str, str]:
        return {r["message_id"]: r["rating"] for r in self._all(
            "SELECT f.message_id, f.rating FROM feedback f JOIN messages m ON m.id = f.message_id"
            " WHERE m.conversation_id=? AND f.user_id=?", (conv_id, user_id))}

    # ---- pending actions -------------------------------------------------
    def add_action(self, *, user_id: str, conversation_id: str | None, tool: str, args: dict, summary: str) -> str:
        action_id = uuid.uuid4().hex
        now = time.time()
        self._exec("INSERT INTO pending_actions (id, user_id, conversation_id, tool, args, summary, status, created_at,"
                   " updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                   (action_id, user_id, conversation_id, tool, json.dumps(args), summary, "pending", now, now))
        return action_id

    def get_action(self, action_id: str, user_id: str) -> dict[str, Any] | None:
        row = self._one("SELECT * FROM pending_actions WHERE id=? AND user_id=?", (action_id, user_id))
        if row:
            row["args"] = json.loads(row["args"])
            row["result"] = json.loads(row["result"]) if row["result"] else None
        return row

    def claim_action(self, action_id: str, user_id: str) -> bool:
        """Atomically move pending -> running so an action can never execute twice."""
        return self._exec("UPDATE pending_actions SET status='running', updated_at=? WHERE id=? AND user_id=?"
                          " AND status='pending'", (time.time(), action_id, user_id)).rowcount == 1

    def finish_action(self, action_id: str, status: str, result: dict | None) -> None:
        self._exec("UPDATE pending_actions SET status=?, result=?, updated_at=? WHERE id=?",
                   (status, json.dumps(result, default=str) if result is not None else None, time.time(), action_id))

    def actions_for(self, conv_id: str, user_id: str) -> dict[str, dict]:
        out = {}
        for r in self._all("SELECT id, status, result FROM pending_actions WHERE conversation_id=? AND user_id=?",
                           (conv_id, user_id)):
            out[r["id"]] = {"status": r["status"], "result": json.loads(r["result"]) if r["result"] else None}
        return out

    def get_messages(self, conv_id: str, limit: int | None = None) -> list[dict[str, Any]]:
        if limit:
            rows = self._all("SELECT * FROM (SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at DESC LIMIT ?)"
                             " ORDER BY created_at ASC", (conv_id, limit))
        else:
            rows = self._all("SELECT * FROM messages WHERE conversation_id=? ORDER BY created_at ASC", (conv_id,))
        for r in rows:
            r["sources"] = json.loads(r["sources"] or "[]")
            r["meta"] = json.loads(r["meta"] or "{}")
        return rows

    # ---- audit -----------------------------------------------------------
    def audit(self, user_id: str, action: str, detail: dict | None = None) -> None:
        self._exec("INSERT INTO audit_log (ts, user_id, action, detail) VALUES (?,?,?,?)",
                   (time.time(), user_id, action, json.dumps(detail or {}, default=str)[:4000]))
