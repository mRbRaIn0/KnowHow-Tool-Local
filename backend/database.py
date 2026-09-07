"""Lokale SQLite-Datenbank — eine eigene Datei pro Profil.

Gespeichert werden nur App-Daten (Chats, Nachrichten, Indexmetadaten).
Vault-Dateien bleiben unangetastet; es wird lediglich ihr Pfad referenziert.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS chat_folders (
        id          TEXT PRIMARY KEY,
        name        TEXT NOT NULL DEFAULT 'Neuer Ordner',
        purpose     TEXT NOT NULL DEFAULT 'vault',
        position    INTEGER NOT NULL DEFAULT 0,
        collapsed   INTEGER NOT NULL DEFAULT 0,
        created_at  TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chats (
        id          TEXT PRIMARY KEY,
        title       TEXT NOT NULL DEFAULT 'Neuer Chat',
        model       TEXT NOT NULL DEFAULT '',
        purpose     TEXT NOT NULL DEFAULT 'vault',
        folder_id   TEXT,
        archived    INTEGER NOT NULL DEFAULT 0,
        created_at  TEXT NOT NULL,
        updated_at  TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        chat_id     TEXT NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
        role        TEXT NOT NULL,
        content     TEXT NOT NULL DEFAULT '',
        thinking    TEXT NOT NULL DEFAULT '',
        attachments TEXT NOT NULL DEFAULT '[]',
        sources     TEXT NOT NULL DEFAULT '[]',
        model       TEXT NOT NULL DEFAULT '',
        created_at  TEXT NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, id)",
    """
    CREATE TABLE IF NOT EXISTS app_meta (
        key   TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS knowledge_files (
        path        TEXT PRIMARY KEY,
        modified_ns INTEGER NOT NULL,
        size        INTEGER NOT NULL,
        indexed_at  TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS knowledge_chunks (
        path        TEXT NOT NULL REFERENCES knowledge_files(path) ON DELETE CASCADE,
        chunk_no    INTEGER NOT NULL,
        page        INTEGER NOT NULL DEFAULT 0,
        content     TEXT NOT NULL,
        embedding   TEXT NOT NULL DEFAULT '[]',
        PRIMARY KEY (path, chunk_no)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_knowledge_path ON knowledge_chunks(path)",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id() -> str:
    return uuid.uuid4().hex[:16]


class Database:
    """Dünne SQLite-Hülle. Single-User, deshalb eine Verbindung mit Lock."""

    def __init__(self, path: Path):
        existing = path.exists()
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._migrate()
        if existing and self.get_meta("search_schema") != "1":
            self.backup_to(path.with_name("app.before-library-v1.db"))
        from .search_index import SearchIndex
        self.search = SearchIndex(self)
        self.search.migrate_vault()
        self.set_meta("search_schema", "1")

    def _migrate(self) -> None:
        with self._lock:
            for statement in SCHEMA:
                self._conn.execute(statement)
            # Vorhandene Installationen hatten nur einen allgemeinen Chat. Diese
            # Verläufe gehören nach der Trennung weiterhin zum Vault-Arbeitschat.
            chat_columns = {
                row["name"] for row in self._conn.execute("PRAGMA table_info(chats)")
            }
            if "purpose" not in chat_columns:
                self._conn.execute(
                    "ALTER TABLE chats ADD COLUMN purpose TEXT NOT NULL DEFAULT 'vault'"
                )
            if "folder_id" not in chat_columns:
                self._conn.execute("ALTER TABLE chats ADD COLUMN folder_id TEXT")
            if "archived" not in chat_columns:
                self._conn.execute(
                    "ALTER TABLE chats ADD COLUMN archived INTEGER NOT NULL DEFAULT 0"
                )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chats_purpose_updated "
                "ON chats(purpose, updated_at DESC)"
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_chats_folder ON chats(folder_id)"
            )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._conn.execute(sql, params)
            self._conn.commit()
            return cursor

    def query(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def query_one(self, sql: str, params: tuple = ()) -> Optional[sqlite3.Row]:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    # ----------------------------------------------------------------- Chats

    def create_chat(self, title: str = "Neuer Chat", model: str = "",
                    purpose: str = "vault", folder_id: str = "") -> Dict[str, Any]:
        purpose = purpose if purpose in {"vault", "ask"} else "vault"
        folder = folder_id if folder_id and self.get_folder(folder_id) else None
        chat_id, stamp = new_id(), now_iso()
        self.execute(
            "INSERT INTO chats (id, title, model, purpose, folder_id, archived, created_at, updated_at) "
            "VALUES (?,?,?,?,?,0,?,?)",
            (chat_id, title, model, purpose, folder, stamp, stamp),
        )
        return {"id": chat_id, "title": title, "model": model, "purpose": purpose,
                "folder_id": folder, "archived": False,
                "created_at": stamp, "updated_at": stamp, "message_count": 0}

    def list_chats(self, limit: int = 200, search: str = "",
                   purpose: str = "") -> List[Dict[str, Any]]:
        sql = """
            SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.chat_id = c.id) AS message_count
            FROM chats c
        """
        filters = []
        params: tuple = ()
        if purpose in {"vault", "ask"}:
            filters.append("c.purpose = ?")
            params += (purpose,)
        if search:
            filters.append("""(c.title LIKE ? OR EXISTS (
                         SELECT 1 FROM messages m WHERE m.chat_id = c.id AND m.content LIKE ?))""")
            params += (f"%{search}%", f"%{search}%")
        if filters:
            sql += " WHERE " + " AND ".join(filters)
        sql += " ORDER BY c.updated_at DESC LIMIT ?"
        params = params + (limit,)
        return [_row_to_chat(row) for row in self.query(sql, params)]

    def get_chat(self, chat_id: str) -> Optional[Dict[str, Any]]:
        row = self.query_one("SELECT * FROM chats WHERE id = ?", (chat_id,))
        return _row_to_chat(row) if row else None

    def rename_chat(self, chat_id: str, title: str) -> None:
        self.execute("UPDATE chats SET title = ?, updated_at = ? WHERE id = ?",
                     (title, now_iso(), chat_id))

    def touch_chat(self, chat_id: str, model: str = "") -> None:
        if model:
            self.execute("UPDATE chats SET updated_at = ?, model = ? WHERE id = ?",
                         (now_iso(), model, chat_id))
        else:
            self.execute("UPDATE chats SET updated_at = ? WHERE id = ?", (now_iso(), chat_id))

    def move_chat(self, chat_id: str, folder_id: str = "") -> None:
        """Verschiebt einen Chat in einen Ordner. Leere ID heißt: keine Zuordnung."""
        target = folder_id if folder_id and self.get_folder(folder_id) else None
        self.execute("UPDATE chats SET folder_id = ? WHERE id = ?", (target, chat_id))

    def set_chat_archived(self, chat_id: str, archived: bool) -> None:
        self.execute("UPDATE chats SET archived = ? WHERE id = ?",
                     (1 if archived else 0, chat_id))

    def delete_chat(self, chat_id: str) -> None:
        self.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        self.execute("DELETE FROM chats WHERE id = ?", (chat_id,))

    # ---------------------------------------------------------- Chat-Ordner

    def list_folders(self, purpose: str = "") -> List[Dict[str, Any]]:
        sql = """
            SELECT f.*, (SELECT COUNT(*) FROM chats c WHERE c.folder_id = f.id) AS chat_count
            FROM chat_folders f
        """
        params: tuple = ()
        if purpose in {"vault", "ask"}:
            sql += " WHERE f.purpose = ?"
            params = (purpose,)
        sql += " ORDER BY f.position ASC, f.created_at ASC"
        return [_row_to_folder(row) for row in self.query(sql, params)]

    def get_folder(self, folder_id: str) -> Optional[Dict[str, Any]]:
        row = self.query_one("SELECT * FROM chat_folders WHERE id = ?", (folder_id,))
        return _row_to_folder(row) if row else None

    def create_folder(self, name: str = "Neuer Ordner", purpose: str = "vault") -> Dict[str, Any]:
        purpose = purpose if purpose in {"vault", "ask"} else "vault"
        row = self.query_one(
            "SELECT COALESCE(MAX(position), -1) + 1 AS next FROM chat_folders WHERE purpose = ?",
            (purpose,),
        )
        position = int(row["next"]) if row else 0
        folder_id, stamp = new_id(), now_iso()
        self.execute(
            "INSERT INTO chat_folders (id, name, purpose, position, collapsed, created_at) "
            "VALUES (?,?,?,?,0,?)",
            (folder_id, name, purpose, position, stamp),
        )
        return {"id": folder_id, "name": name, "purpose": purpose, "position": position,
                "collapsed": False, "created_at": stamp, "chat_count": 0}

    def update_folder(self, folder_id: str, name: Optional[str] = None,
                      collapsed: Optional[bool] = None,
                      position: Optional[int] = None) -> None:
        sets, params = [], []
        if name is not None:
            sets.append("name = ?")
            params.append(name)
        if collapsed is not None:
            sets.append("collapsed = ?")
            params.append(1 if collapsed else 0)
        if position is not None:
            sets.append("position = ?")
            params.append(int(position))
        if not sets:
            return
        params.append(folder_id)
        self.execute(f"UPDATE chat_folders SET {', '.join(sets)} WHERE id = ?", tuple(params))

    def delete_folder(self, folder_id: str) -> None:
        """Löscht nur den Ordner — die enthaltenen Chats rutschen nach oben."""
        self.execute("UPDATE chats SET folder_id = NULL WHERE folder_id = ?", (folder_id,))
        self.execute("DELETE FROM chat_folders WHERE id = ?", (folder_id,))

    # ------------------------------------------------------------- Nachrichten

    def add_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        thinking: str = "",
        attachments: Optional[List[dict]] = None,
        sources: Optional[List[dict]] = None,
        model: str = "",
    ) -> Dict[str, Any]:
        stamp = now_iso()
        cursor = self.execute(
            """INSERT INTO messages (chat_id, role, content, thinking, attachments, sources, model, created_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (chat_id, role, content, thinking,
             json.dumps(attachments or [], ensure_ascii=False),
             json.dumps(sources or [], ensure_ascii=False),
             model, stamp),
        )
        self.touch_chat(chat_id, model)
        return {"id": cursor.lastrowid, "chat_id": chat_id, "role": role, "content": content,
                "thinking": thinking, "attachments": attachments or [], "sources": sources or [],
                "model": model, "created_at": stamp}

    def update_message(self, message_id: int, **fields: Any) -> None:
        allowed = {"content", "thinking", "sources", "model"}
        sets, params = [], []
        for key, value in fields.items():
            if key not in allowed:
                continue
            sets.append(f"{key} = ?")
            params.append(json.dumps(value, ensure_ascii=False) if key == "sources" else value)
        if not sets:
            return
        params.append(message_id)
        self.execute(f"UPDATE messages SET {', '.join(sets)} WHERE id = ?", tuple(params))

    def list_messages(self, chat_id: str) -> List[Dict[str, Any]]:
        rows = self.query("SELECT * FROM messages WHERE chat_id = ? ORDER BY id ASC", (chat_id,))
        return [_row_to_message(row) for row in rows]

    def delete_message(self, message_id: int) -> None:
        self.execute("DELETE FROM messages WHERE id = ?", (message_id,))

    def search_messages(self, term: str, limit: int = 50) -> List[Dict[str, Any]]:
        rows = self.query(
            """SELECT m.*, c.title AS chat_title FROM messages m
               JOIN chats c ON c.id = m.chat_id
               WHERE m.content LIKE ? ORDER BY m.id DESC LIMIT ?""",
            (f"%{term}%", limit),
        )
        out = []
        for row in rows:
            item = _row_to_message(row)
            item["chat_title"] = row["chat_title"]
            out.append(item)
        return out

    def count(self, table: str) -> int:
        if table not in {"chats", "messages"}:
            raise ValueError(table)
        row = self.query_one(f"SELECT COUNT(*) AS n FROM {table}")
        return int(row["n"]) if row else 0

    # ------------------------------------------------------------------ Meta

    def get_meta(self, key: str, default: str = "") -> str:
        row = self.query_one("SELECT value FROM app_meta WHERE key = ?", (key,))
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO app_meta (key, value) VALUES (?,?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    # ---------------------------------------------------------- Wissensindex

    def knowledge_manifest(self) -> Dict[str, Dict[str, int]]:
        rows = self.query("SELECT path, modified_ns, size FROM knowledge_files")
        return {
            row["path"]: {"modified_ns": int(row["modified_ns"]), "size": int(row["size"])}
            for row in rows
        }

    def replace_knowledge_file(self, path: str, modified_ns: int, size: int,
                               chunks: List[Dict[str, Any]], model: str = "") -> None:
        with self._lock:
            self._conn.execute("DELETE FROM knowledge_chunks WHERE path = ?", (path,))
            self._conn.execute(
                "INSERT INTO knowledge_files(path, modified_ns, size, indexed_at) VALUES (?,?,?,?) "
                "ON CONFLICT(path) DO UPDATE SET modified_ns=excluded.modified_ns, "
                "size=excluded.size, indexed_at=excluded.indexed_at",
                (path, modified_ns, size, now_iso()),
            )
            self._conn.executemany(
                "INSERT INTO knowledge_chunks(path, chunk_no, page, content, embedding) "
                "VALUES (?,?,?,?,?)",
                [
                    (path, index, int(chunk.get("page", 0)), chunk.get("content", ""),
                     json.dumps(chunk.get("embedding") or []))
                    for index, chunk in enumerate(chunks)
                ],
            )
            self._conn.commit()
        self.search.replace("vault", path, path, chunks, model)

    def delete_knowledge_paths(self, paths: List[str]) -> None:
        if not paths:
            return
        with self._lock:
            for path in paths:
                self.search.remove("vault", path)
            self._conn.executemany("DELETE FROM knowledge_files WHERE path = ?",
                                   [(path,) for path in paths])
            self._conn.commit()

    def knowledge_chunks(self, limit: int | None = None) -> List[Dict[str, Any]]:
        rows = self.query(
            "SELECT path, chunk_no, page, content, embedding FROM knowledge_chunks"
            + (" LIMIT ?" if limit is not None else ""),
            (limit,) if limit is not None else (),
        )
        return [
            {
                "path": row["path"], "chunk_no": row["chunk_no"],
                "page": row["page"], "content": row["content"],
                "embedding": _json_or(row["embedding"], []),
            }
            for row in rows
        ]

    def knowledge_stats(self) -> Dict[str, int]:
        files = self.query_one("SELECT COUNT(*) AS n FROM knowledge_files")
        chunks = self.query_one("SELECT COUNT(*) AS n FROM knowledge_chunks")
        embedded = self.query_one(
            "SELECT COUNT(*) AS n FROM knowledge_chunks WHERE embedding != '[]'"
        )
        return {
            "files": int(files["n"]) if files else 0,
            "chunks": int(chunks["n"]) if chunks else 0,
            "embedded": int(embedded["n"]) if embedded else 0,
        }

    def backup_to(self, target: Path) -> None:
        """Konsistente SQLite-Kopie, auch während WAL aktiv ist."""
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            destination = sqlite3.connect(str(target))
            try:
                self._conn.backup(destination)
            finally:
                destination.close()


def _row_to_chat(row: sqlite3.Row) -> Dict[str, Any]:
    chat = dict(row)
    chat["folder_id"] = chat.get("folder_id") or None
    chat["archived"] = bool(chat.get("archived"))
    return chat


def _row_to_folder(row: sqlite3.Row) -> Dict[str, Any]:
    folder = dict(row)
    folder["collapsed"] = bool(folder.get("collapsed"))
    folder["chat_count"] = int(folder.get("chat_count") or 0)
    return folder


def _row_to_message(row: sqlite3.Row) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "chat_id": row["chat_id"],
        "role": row["role"],
        "content": row["content"],
        "thinking": row["thinking"],
        "attachments": _json_or(row["attachments"], []),
        "sources": _json_or(row["sources"], []),
        "model": row["model"],
        "created_at": row["created_at"],
    }


def _json_or(raw: Any, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return fallback


class DatabaseRegistry:
    """Hält je Profil genau eine Datenbankverbindung offen."""

    def __init__(self) -> None:
        self._databases: Dict[str, Database] = {}
        self._lock = threading.Lock()

    def get(self, profile_id: str, path: Path) -> Database:
        with self._lock:
            database = self._databases.get(profile_id)
            if database is None:
                log.info("Öffne Datenbank für Profil '%s': %s", profile_id, path)
                database = Database(path)
                self._databases[profile_id] = database
            return database

    def close(self, profile_id: str) -> None:
        """Verbindung eines Profils schließen — sonst bleibt die Datei gesperrt."""
        with self._lock:
            database = self._databases.pop(profile_id, None)
            if database is not None:
                log.info("Schließe Datenbank für Profil '%s'", profile_id)
                database.close()

    def close_all(self) -> None:
        with self._lock:
            for database in self._databases.values():
                database.close()
            self._databases.clear()


registry = DatabaseRegistry()
