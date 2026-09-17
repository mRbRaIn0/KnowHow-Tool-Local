"""Bounded SQL/FTS5 retrieval, with optional, rebuildable sqlite-vec tables."""
from __future__ import annotations

import hashlib
import json
import math
import re
import struct


class SearchIndex:
    def __init__(self, database):
        self.db = database
        self.vector_error = ""
        self.vec = False
        with database._lock:
            conn = database._conn
            try:
                import sqlite_vec
                conn.enable_load_extension(True)
                sqlite_vec.load(conn)
                self.vec = True
            except Exception as exc:
                self.vector_error = str(exc)
            finally:
                try:
                    conn.enable_load_extension(False)
                except AttributeError:
                    pass
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS search_chunks(
                    id INTEGER PRIMARY KEY, namespace TEXT NOT NULL, item TEXT NOT NULL,
                    part INTEGER NOT NULL, path TEXT NOT NULL, page INTEGER NOT NULL,
                    content TEXT NOT NULL, model TEXT NOT NULL DEFAULT '',
                    vector BLOB, UNIQUE(namespace,item,part));
                CREATE INDEX IF NOT EXISTS search_owner ON search_chunks(namespace,item);
                CREATE VIRTUAL TABLE IF NOT EXISTS search_fts USING fts5(
                    path, content, content=search_chunks, content_rowid=id,
                    tokenize='unicode61 remove_diacritics 2');
                CREATE TRIGGER IF NOT EXISTS search_insert AFTER INSERT ON search_chunks BEGIN
                    INSERT INTO search_fts(rowid,path,content) VALUES(new.id,new.path,new.content);
                END;
                CREATE TRIGGER IF NOT EXISTS search_delete AFTER DELETE ON search_chunks BEGIN
                    INSERT INTO search_fts(search_fts,rowid,path,content)
                    VALUES('delete',old.id,old.path,old.content);
                END;
                CREATE TABLE IF NOT EXISTS search_models(
                    name TEXT PRIMARY KEY, model TEXT NOT NULL, dimensions INTEGER NOT NULL);
            """)
            conn.commit()
            if self.vec and database.get_meta("search_vectors_dirty") == "1":
                self.rebuild_vectors()

    def rebuild_vectors(self):
        """Recreate disposable vectors after a run without the extension."""
        if not self.vec:
            return
        with self.db._lock, self.db._conn:
            conn = self.db._conn
            for row in conn.execute("SELECT name FROM search_models").fetchall():
                if re.fullmatch(r"vectors_[a-f0-9]{20}", row[0]):
                    conn.execute(f"DROP TABLE IF EXISTS {row[0]}")
            conn.execute("DELETE FROM search_models")
            for row in conn.execute("SELECT id,model,vector FROM search_chunks WHERE vector IS NOT NULL"):
                blob = row["vector"]
                if blob and len(blob) % 4 == 0:
                    table = self._table(row["model"], len(blob) // 4)
                    conn.execute(f"INSERT INTO {table}(rowid,embedding) VALUES(?,?)", (row["id"], blob))
            conn.execute("DELETE FROM app_meta WHERE key='search_vectors_dirty'")

    def _table(self, model, size):
        name = "vectors_" + hashlib.sha256(f"{model}:{size}".encode()).hexdigest()[:20]
        self.db._conn.execute(
            f"CREATE VIRTUAL TABLE IF NOT EXISTS {name} USING vec0(embedding float[{int(size)}])")
        self.db._conn.execute("INSERT OR IGNORE INTO search_models VALUES(?,?,?)", (name, model, size))
        return name

    def remove(self, namespace, item):
        with self.db._lock, self.db._conn:
            self._remove(namespace, item)

    def _remove(self, namespace, item):
        conn = self.db._conn
        if self.vec:
            ids = [r[0] for r in conn.execute(
                "SELECT id FROM search_chunks WHERE namespace=? AND item=?", (namespace, item))]
            for row in conn.execute("SELECT name FROM search_models"):
                if re.fullmatch(r"vectors_[a-f0-9]{20}", row[0]):
                    conn.executemany(f"DELETE FROM {row[0]} WHERE rowid=?", [(i,) for i in ids])
        else:
            conn.execute("INSERT OR REPLACE INTO app_meta VALUES('search_vectors_dirty','1')")
        conn.execute("DELETE FROM search_chunks WHERE namespace=? AND item=?", (namespace, item))

    def replace(self, namespace, item, path, chunks, model=""):
        with self.db._lock, self.db._conn:
            conn = self.db._conn
            self._remove(namespace, item)
            for part, chunk in enumerate(chunks):
                vector = chunk.get("embedding") or []
                if not all(isinstance(x, (float, int)) and math.isfinite(x) for x in vector):
                    vector = []
                blob = struct.pack(f"{len(vector)}f", *vector) if vector else None
                cursor = conn.execute(
                    "INSERT INTO search_chunks(namespace,item,part,path,page,content,model,vector)"
                    " VALUES(?,?,?,?,?,?,?,?)",
                    (namespace, item, part, path, chunk.get("page", 0), chunk["content"], model, blob))
                if blob and self.vec:
                    table = self._table(model, len(vector))
                    conn.execute(f"INSERT INTO {table}(rowid,embedding) VALUES(?,?)",
                                 (cursor.lastrowid, blob))

    def search(self, query, vector=None, model="", namespaces=("vault",), limit=8, paths=None):
        """Only candidate rows cross into Python; no arbitrary corpus cutoff."""
        words = re.findall(r"\w+", query, re.UNICODE)
        if not words or not namespaces:
            return []
        match = " OR ".join('"' + word + '"*' for word in words[:30])
        placeholders = ",".join("?" for _ in namespaces)
        if paths == () or paths == []:
            return []
        scope_sql, scope_args = '', []
        if paths is not None:
            clauses = []
            for path in paths:
                if path.endswith('/'):
                    # Literal prefix; % and _ in filenames are never SQL wildcards.
                    clauses.append('substr(lower(c.path),1,length(?))=lower(?)')
                    scope_args.extend([path, path])
                else:
                    clauses.append('lower(c.path)=lower(?)')
                    scope_args.append(path)
            scope_sql = ' AND (' + ' OR '.join(clauses) + ')'
        candidates = {}
        with self.db._lock:
            conn = self.db._conn
            lexical = conn.execute(
                f"SELECT c.*,bm25(search_fts,2,1) rank FROM search_fts "
                f"JOIN search_chunks c ON c.id=search_fts.rowid "
                f"WHERE search_fts MATCH ? AND c.namespace IN ({placeholders}){scope_sql} ORDER BY rank LIMIT ?",
                (match, *namespaces, *scope_args, max(40, limit * 8))).fetchall()
            for rank, row in enumerate(lexical):
                candidates[row["id"]] = [1 / (30 + rank), dict(row)]
            if vector and self.vec and all(math.isfinite(x) for x in vector):
                table = "vectors_" + hashlib.sha256(f"{model}:{len(vector)}".encode()).hexdigest()[:20]
                if conn.execute("SELECT 1 FROM search_models WHERE name=?", (table,)).fetchone():
                    # Restrict allowed IDs inside KNN, not after retrieving global top-k.
                    rows = conn.execute(
                        f"SELECT c.*,v.distance FROM {table} v JOIN search_chunks c ON c.id=v.rowid "
                        f"WHERE v.embedding MATCH ? AND k=? AND v.rowid IN "
                        f"(SELECT c.id FROM search_chunks c WHERE c.namespace IN ({placeholders}){scope_sql}) "
                        "ORDER BY v.distance",
                        (struct.pack(f"{len(vector)}f", *vector), max(40, limit * 8), *namespaces, *scope_args)).fetchall()
                    for rank, row in enumerate(rows):
                        # Ollama vectors are unit-normalized; L2 1.2 corresponds to cosine .28.
                        if row["distance"] > 1.2:
                            continue
                        entry = candidates.setdefault(row["id"], [0, dict(row)])
                        entry[0] += 1.5 / (30 + rank)
        out = []
        for score, item in sorted(candidates.values(), key=lambda x: x[0], reverse=True)[:limit]:
            content = item["content"]
            position = min((content.lower().find(w.lower()) for w in words
                            if w.lower() in content.lower()), default=0)
            out.append({
                "source": item["namespace"], "item_id": item["item"], "path": item["path"],
                "page": item["page"], "content": content,
                "snippet": content[max(0, position - 80):position + 350],
                "score": round(min(1, score * 12), 4),
            })
        return out

    def migrate_vault(self):
        """One-time additive import of the old index, without reading originals."""
        if self.db.get_meta("search_vault_imported") == "1":
            return
        for file in self.db.query("SELECT path FROM knowledge_files"):
            chunks = []
            for row in self.db.query("SELECT * FROM knowledge_chunks WHERE path=? ORDER BY chunk_no",
                                     (file["path"],)):
                chunks.append({"page": row["page"], "content": row["content"],
                               "embedding": json.loads(row["embedding"] or "[]")})
            self.replace("vault", file["path"], file["path"], chunks, "legacy")
        self.db.set_meta("search_vault_imported", "1")
