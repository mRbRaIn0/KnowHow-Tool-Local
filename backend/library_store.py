"""Profile-owned file catalog. Original files never live in this database."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from .database import new_id, now_iso
from .library_models import LibraryError, LibrarySource, Metadata
from .library_paths import safe_path, relative_path, under, is_link, fingerprint, IGNORED


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


SCHEMA = """
CREATE TABLE IF NOT EXISTS library_sources(
 id TEXT PRIMARY KEY, name TEXT NOT NULL, root TEXT NOT NULL UNIQUE COLLATE NOCASE,
 kind TEXT NOT NULL, writable INTEGER NOT NULL, backup INTEGER NOT NULL,
 watch INTEGER NOT NULL, revision INTEGER NOT NULL DEFAULT 1,
 available INTEGER NOT NULL DEFAULT 1, error TEXT NOT NULL DEFAULT '',
 backup_pending INTEGER NOT NULL DEFAULT 0, backup_at TEXT NOT NULL DEFAULT '');
CREATE TABLE IF NOT EXISTS library_items(
 id TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES library_sources(id),
 path TEXT NOT NULL COLLATE NOCASE, name TEXT NOT NULL, folder TEXT NOT NULL COLLATE NOCASE,
 extension TEXT NOT NULL, size INTEGER NOT NULL, modified_ns INTEGER NOT NULL,
 sha256 TEXT NOT NULL DEFAULT '', tags TEXT NOT NULL DEFAULT '[]',
 description TEXT NOT NULL DEFAULT '', reviewed INTEGER NOT NULL DEFAULT 0,
 revision INTEGER NOT NULL DEFAULT 1, missing INTEGER NOT NULL DEFAULT 0,
 seen TEXT NOT NULL DEFAULT '', index_enabled INTEGER NOT NULL DEFAULT 0,
 indexed_revision INTEGER NOT NULL DEFAULT 0, UNIQUE(source_id,path));
CREATE INDEX IF NOT EXISTS library_location ON library_items(source_id,folder,name,id);
CREATE INDEX IF NOT EXISTS library_extension ON library_items(extension,name,id);
CREATE INDEX IF NOT EXISTS library_review ON library_items(reviewed,missing,name,id);
CREATE INDEX IF NOT EXISTS library_hash ON library_items(sha256) WHERE sha256!='';
CREATE TABLE IF NOT EXISTS library_tags(item_id TEXT NOT NULL REFERENCES library_items(id),
 tag TEXT NOT NULL, PRIMARY KEY(item_id,tag));
CREATE INDEX IF NOT EXISTS library_tag_filter ON library_tags(tag,item_id);
CREATE VIRTUAL TABLE IF NOT EXISTS library_fts USING fts5(
 name,path,tags,description,content=library_items,content_rowid=rowid);
CREATE TRIGGER IF NOT EXISTS library_fts_insert AFTER INSERT ON library_items BEGIN
 INSERT INTO library_fts(rowid,name,path,tags,description)
 VALUES(new.rowid,new.name,new.path,new.tags,new.description);
END;
CREATE TRIGGER IF NOT EXISTS library_fts_delete AFTER DELETE ON library_items BEGIN
 INSERT INTO library_fts(library_fts,rowid,name,path,tags,description)
 VALUES('delete',old.rowid,old.name,old.path,old.tags,old.description);
END;
CREATE TRIGGER IF NOT EXISTS library_fts_update AFTER UPDATE OF name,path,tags,description ON library_items BEGIN
 INSERT INTO library_fts(library_fts,rowid,name,path,tags,description)
 VALUES('delete',old.rowid,old.name,old.path,old.tags,old.description);
 INSERT INTO library_fts(rowid,name,path,tags,description)
 VALUES(new.rowid,new.name,new.path,new.tags,new.description);
END;
CREATE TABLE IF NOT EXISTS library_entries(
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
 data TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS library_proposals(
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL,
 revision INTEGER NOT NULL DEFAULT 1, status TEXT NOT NULL DEFAULT 'pending',
 created_at TEXT NOT NULL, result TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS library_jobs(
 id TEXT PRIMARY KEY, kind TEXT NOT NULL, data TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'queued', cursor INTEGER NOT NULL DEFAULT 0,
 total INTEGER NOT NULL DEFAULT 0, error TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS library_operations(
 id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL, item_id TEXT NOT NULL,
 data TEXT NOT NULL, state TEXT NOT NULL, error TEXT NOT NULL DEFAULT '',
 created_at TEXT NOT NULL, UNIQUE(proposal_id,item_id));
"""


class LibraryStore:
    def __init__(self, profile, database):
        self.profile = profile
        self.db = database
        # All library mutations/operations for this profile share this lock.
        with database._lock:
            if not hasattr(database, "_library_lock"):
                database._library_lock = threading.RLock()
            self.lock = database._library_lock
            if database.get_meta("library_schema") != "1":
                database.backup_to(database.path.with_name("app.before-catalog-v1.db"))
                database._conn.executescript(SCHEMA)
                database._conn.commit()
                database.set_meta("library_schema", "1")

    def rows(self, sql, args=()):
        return [dict(r) for r in self.db.query(sql, args)]

    def one(self, sql, args=()):
        row = self.db.query_one(sql, args)
        if row is None:
            raise LibraryError("Eintrag gehört nicht zu diesem Profil oder existiert nicht.")
        return dict(row)

    def sources(self):
        return self.rows("SELECT * FROM library_sources ORDER BY name")

    def source(self, source_id):
        return self.one("SELECT * FROM library_sources WHERE id=?", (source_id,))

    def add_source(self, source: LibrarySource):
        root = Path(source.root).expanduser()
        if not root.is_absolute():
            raise LibraryError("Die Quelle muss ein absoluter Ordner- oder UNC-Pfad sein.")
        safe_path(root, "", self.profile.vault_path)
        root = root.resolve()
        from .config import DATA_DIR
        if under(root, DATA_DIR) or under(DATA_DIR, root):
            raise LibraryError("App-Daten dürfen nicht als Bibliotheksquelle erfasst werden.")
        for existing in self.sources():
            other = Path(existing["root"])
            if under(root, other) or under(other, root):
                raise LibraryError("Quellen dürfen sich nicht überschneiden.")
        if source.backup and not source.writable:
            raise LibraryError("JSON-Sicherung benötigt eine beschreibbare Quelle.")
        sid = new_id()
        self.db.execute(
            "INSERT INTO library_sources(id,name,root,kind,writable,backup,watch,backup_pending)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (sid, source.name, str(root), source.kind, source.writable, source.backup,
             source.watch, int(source.backup)))
        return self.source(sid)

    def item(self, item_id):
        row = self.one("SELECT * FROM library_items WHERE id=?", (item_id,))
        row["tags"] = json.loads(row["tags"])
        return row

    def path(self, item, check=True):
        source = self.source(item["source_id"])
        path = safe_path(source["root"], item["path"], self.profile.vault_path)
        if check and fingerprint(path) != {k: item[k] for k in ("size", "modified_ns")}:
            raise LibraryError("Datei hat sich geändert. Bitte neu erfassen und Vorschlag erneut prüfen.")
        return path

    def checked(self, refs):
        items = []
        for ref in refs:
            item = self.item(ref["id"] if isinstance(ref, dict) else ref.id)
            revision = ref["revision"] if isinstance(ref, dict) else ref.revision
            if item["revision"] != revision or item["missing"]:
                raise LibraryError("Veraltete Auswahl. Bitte Bibliothek aktualisieren.")
            self.path(item)
            items.append(item)
        if len({i["id"] for i in items}) != len(items):
            raise LibraryError("Eine Auswahl darf jede Datei nur einmal enthalten.")
        return items

    def dirty(self):
        self.db.execute("UPDATE library_sources SET backup_pending=1 WHERE backup=1")

    def listing(self, source_id="", folder="", extension="", tag="", review="",
                q="", duplicates=False, offset=0, limit=100):
        clauses, args = ["1=1"], []
        for column, value in (("source_id", source_id), ("folder", folder), ("extension", extension)):
            if value:
                clauses.append(f"i.{column}=?")
                args.append(value)
        if review in ("reviewed", "unreviewed"):
            clauses.append("i.reviewed=?")
            args.append(int(review == "reviewed"))
        if review == "missing":
            clauses.append("i.missing=1")
        if tag:
            clauses.append("EXISTS(SELECT 1 FROM library_tags t WHERE t.item_id=i.id AND t.tag=?)")
            args.append(tag.casefold())
        if duplicates:
            clauses.append("i.sha256!='' AND i.sha256 IN "
                           "(SELECT sha256 FROM library_items WHERE sha256!='' AND missing=0 "
                           "GROUP BY sha256 HAVING COUNT(*)>1)")
        if q.strip():
            import re
            words = re.findall(r"\w+", q)[:30]
            if words:
                clauses.append("i.rowid IN (SELECT rowid FROM library_fts WHERE library_fts MATCH ?)")
                args.append(" AND ".join('"' + w + '"*' for w in words))
        where = " AND ".join(clauses)
        total = self.one("SELECT count(*) n FROM library_items i WHERE " + where, tuple(args))["n"]
        rows = self.rows("SELECT i.*,s.name source_name FROM library_items i "
                         "JOIN library_sources s ON s.id=i.source_id WHERE " + where +
                         " ORDER BY i.name COLLATE NOCASE,i.id LIMIT ? OFFSET ?",
                         (*args, min(200, max(1, limit)), max(0, offset)))
        for row in rows:
            row["tags"] = json.loads(row["tags"])
        return {"items": rows, "total": total, "offset": offset}

    def scan(self, source_id, checkpoint=lambda: None, progress=lambda n: None):
        source = self.source(source_id)
        seen, count = new_id(), 0
        try:
            root = safe_path(source["root"], "", self.profile.vault_path)
            def failed(exc):
                raise exc
            for directory, folders, names in os.walk(root, followlinks=False, onerror=failed):
                checkpoint()
                folders[:] = [n for n in folders if n.casefold() not in IGNORED
                              and not is_link(Path(directory) / n)
                              and not (self.profile.vault_path
                                       and under(Path(directory) / n, self.profile.vault_path))]
                batch = []
                for name in names:
                    path = Path(directory) / name
                    if name.startswith(".lka-") or is_link(path):
                        continue
                    rel = path.relative_to(root).as_posix()
                    try:
                        relative_path(rel)
                    except LibraryError:
                        continue
                    info = fingerprint(path)
                    batch.append((path, rel, info))
                    if len(batch) == 200:
                        self._scan_batch(source_id, seen, batch)
                        count += len(batch)
                        batch = []
                        checkpoint()
                        progress(count)
                if batch:
                    self._scan_batch(source_id, seen, batch)
                    count += len(batch)
                    progress(count)
            with self.lock, self.db._lock, self.db._conn:
                lost = self.rows("SELECT id FROM library_items WHERE source_id=? AND seen!=? AND missing=0",
                                 (source_id, seen))
                for item in lost:
                    self.db.search.remove("library", item["id"])
                self.db._conn.execute(
                    "UPDATE library_items SET missing=1,revision=revision+1 WHERE source_id=? AND seen!=? AND missing=0",
                    (source_id, seen))
                self.db._conn.execute("UPDATE library_sources SET available=1,error='' WHERE id=?", (source_id,))
            self.dirty()
            return count
        except (OSError, LibraryError) as exc:
            self.db.execute("UPDATE library_sources SET available=0,error=? WHERE id=?", (str(exc), source_id))
            raise

    def _scan_batch(self, source_id, seen, batch):
        with self.lock, self.db._lock, self.db._conn:
            conn = self.db._conn
            for path, rel, info in batch:
                old = conn.execute("SELECT * FROM library_items WHERE source_id=? AND path=?",
                                   (source_id, rel)).fetchone()
                if old:
                    changed = old["size"] != info["size"] or old["modified_ns"] != info["modified_ns"]
                    if changed or old["missing"]:
                        self.db.search.remove("library", old["id"])
                        conn.execute(
                            "UPDATE library_items SET size=?,modified_ns=?,seen=?,missing=0,"
                            "sha256='',revision=revision+1,indexed_revision=0 WHERE id=?",
                            (info["size"], info["modified_ns"], seen, old["id"]))
                    else:
                        conn.execute("UPDATE library_items SET seen=? WHERE id=?", (seen, old["id"]))
                else:
                    conn.execute(
                        "INSERT INTO library_items(id,source_id,path,name,folder,extension,size,modified_ns,seen)"
                        " VALUES(?,?,?,?,?,?,?,?,?)",
                        (new_id(), source_id, rel, path.name,
                         "" if Path(rel).parent == Path(".") else Path(rel).parent.as_posix(),
                         path.suffix.lower(), info["size"], info["modified_ns"], seen))

    def entries(self, kind):
        rows = self.rows("SELECT * FROM library_entries WHERE kind=? ORDER BY name", (kind,))
        for row in rows:
            row["data"] = json.loads(row["data"])
        return rows

    def entry(self, entry_id, kind):
        row = self.one("SELECT * FROM library_entries WHERE id=? AND kind=?", (entry_id, kind))
        row["data"] = json.loads(row["data"])
        return row

    def save_entry(self, kind, name, data, entry_id="", revision=0):
        if kind not in {"target", "group", "collection", "rule", "index_scope"}:
            raise LibraryError("Unbekannte Einstellung.")
        if not name.strip() or len(name) > 150:
            raise LibraryError("Bitte einen Namen mit höchstens 150 Zeichen angeben.")
        if kind in {"target", "index_scope"}:
            source = self.source(data["source_id"])
            data["path"] = relative_path(data.get("path", ""))
            path = safe_path(source["root"], data["path"], self.profile.vault_path)
            if kind == "target" and not source["writable"]:
                raise LibraryError("Quelle ist nicht zum Schreiben freigegeben.")
            if not path.is_dir():
                raise LibraryError("Zielordner existiert nicht. Zuerst über Ordner anlegen erstellen.")
        if kind == "rule":
            data["tags"] = Metadata(tags=data.get("tags", [])).tags
            self.entry(data["target_id"], "target")
        if kind == "group":
            data["tags"] = Metadata(tags=data.get("tags", [])).tags
        with self.lock:
            if entry_id:
                existing = self.entry(entry_id, kind)
                if existing["revision"] != revision:
                    raise LibraryError("Einstellung wurde zwischenzeitlich geändert.")
                self.db.execute("UPDATE library_entries SET name=?,data=?,revision=revision+1 WHERE id=?",
                                (name.strip(), dump(data), entry_id))
            else:
                entry_id = new_id()
                self.db.execute("INSERT INTO library_entries(id,kind,name,data) VALUES(?,?,?,?)",
                                (entry_id, kind, name.strip(), dump(data)))
            self.dirty()
        return self.entry(entry_id, kind)

    def proposal(self, kind, data):
        pid = new_id()
        self.db.execute("INSERT INTO library_proposals(id,kind,data,created_at) VALUES(?,?,?,?)",
                        (pid, kind, dump(data), now_iso()))
        return self.get_proposal(pid)

    def get_proposal(self, pid):
        row = self.one("SELECT * FROM library_proposals WHERE id=?", (pid,))
        row["data"], row["result"] = json.loads(row["data"]), json.loads(row["result"])
        return row

    def metadata_proposal(self, refs, metadata):
        with self.lock:
            items = self.checked(refs)
            return self.proposal("metadata", {"items": [
                {"id": item["id"], "revision": item["revision"], "path": item["path"],
                 "before": {"tags": item["tags"], "description": item["description"],
                            "reviewed": item["reviewed"]},
                 "after": Metadata.model_validate(metadata).model_dump()} for item in items]})

    def apply_metadata(self, proposal):
        items = proposal["data"]["items"]
        with self.lock:
            self.checked(items)
            with self.db._lock, self.db._conn:
                for change in items:
                    self._metadata(change["id"], change["after"], True)
                self.db._conn.execute(
                    "UPDATE library_proposals SET status='applied',result=? WHERE id=?",
                    (dump({"updated": len(items)}), proposal["id"]))
            self.dirty()
        return self.get_proposal(proposal["id"])

    def _metadata(self, item_id, metadata, reviewed):
        values = Metadata.model_validate({k: metadata[k] for k in ("tags", "description")})
        conn = self.db._conn
        conn.execute("UPDATE library_items SET tags=?,description=?,reviewed=?,revision=revision+1 WHERE id=?",
                     (dump(values.tags), values.description, reviewed, item_id))
        conn.execute("DELETE FROM library_tags WHERE item_id=?", (item_id,))
        conn.executemany("INSERT INTO library_tags VALUES(?,?)",
                         [(item_id, tag.casefold()) for tag in values.tags])

    def undo_metadata(self, proposal):
        with self.lock, self.db._lock, self.db._conn:
            if proposal["status"] != "applied" or proposal["kind"] != "metadata":
                raise LibraryError("Metadatenänderung kann nicht zurückgenommen werden.")
            for change in proposal["data"]["items"]:
                if self.item(change["id"])["revision"] != change["revision"] + 1:
                    raise LibraryError("Datei wurde seit der Freigabe geändert.")
            for change in proposal["data"]["items"]:
                self._metadata(change["id"], change["before"], change["before"].get("reviewed", False))
            self.db._conn.execute("UPDATE library_proposals SET status='undone' WHERE id=?", (proposal["id"],))
        self.dirty()

    def allow_index(self, item):
        if item["missing"] or item["index_enabled"] == -1:
            return False
        if item["index_enabled"]:
            return True
        return any(entry["data"]["source_id"] == item["source_id"] and
                   (not entry["data"]["path"] or item["path"].casefold().startswith(entry["data"]["path"].casefold() + "/"))
                   for entry in self.entries("index_scope"))

    def index_candidates(self, source_id=""):
        scopes = self.entries("index_scope")
        rows = self.rows("SELECT id,source_id,path,index_enabled FROM library_items "
                         "WHERE missing=0 AND indexed_revision!=revision" +
                         (" AND source_id=?" if source_id else ""), (source_id,) if source_id else ())
        return [r["id"] for r in rows if r["index_enabled"] == 1 or (
            r["index_enabled"] == 0 and any(
                e["data"]["source_id"] == r["source_id"] and (
                    not e["data"]["path"] or r["path"].casefold().startswith(e["data"]["path"].casefold() + "/"))
                for e in scopes))]

    def purge_excluded(self):
        for row in self.rows("SELECT DISTINCT item FROM search_chunks WHERE namespace='library'"):
            if not self.allow_index(self.item(row["item"])):
                self.db.search.remove("library", row["item"])
                self.db.execute("UPDATE library_items SET indexed_revision=0 WHERE id=?", (row["item"],))
