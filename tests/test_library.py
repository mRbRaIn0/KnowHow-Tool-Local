from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
import shutil
import time
import unittest
from unittest.mock import AsyncMock, patch
import uuid

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from backend.config import Profile
from backend.database import Database
from backend.library_store import LibraryStore
from backend.library_models import LibrarySource, LibraryError, FileOperation
from backend.library_paths import digest, safe_path, relative_path
from backend.library_operations import prepare, execute_one, undo_proposal
from backend.library_jobs import enqueue, run_job
from backend.library_backup import snapshot, restore_preview, apply_restore
from backend.library_content import analyze, index_item
from backend.library_reconcile import prepare as reconcile_prepare, apply as reconcile_apply


class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path.cwd().resolve() / ".test-runtime" / ("library-" + uuid.uuid4().hex)
        self.root.mkdir(parents=True)
        self.pc, self.nas, self.vault = (self.root / name for name in ("pc", "nas", "vault"))
        for folder in (self.pc, self.nas, self.vault):
            folder.mkdir()
        (self.nas / "Dokumente").mkdir()
        self.profile = Profile(id="test", name="Test", vault={"path": str(self.vault)},
                               library={"enabled": True})
        self.db = Database(self.root / "app.db")
        self.lib = LibraryStore(self.profile, self.db)
        self.source = self.lib.add_source(LibrarySource(name="PC", root=str(self.pc), writable=True))
        self.target = self.lib.add_source(LibrarySource(name="NAS", root=str(self.nas),
                                                       kind="nas", writable=True, backup=True))
        self.folder = self.lib.save_entry("target", "Dokumente", {"source_id": self.target["id"],
                                                                "path": "Dokumente"})

    def tearDown(self):
        self.db.close()
        workspace = Path.cwd().resolve()
        assert self.root.resolve().is_relative_to(workspace / ".test-runtime")
        shutil.rmtree(self.root)

    def file(self, name="Rechnung.txt", text="Eine Rechnung für das NAS."):
        (self.pc / name).write_text(text, encoding="utf-8")
        self.lib.scan(self.source["id"])
        return self.lib.item(self.lib.listing(q=Path(name).stem)["items"][0]["id"])

    def metadata(self, item, tags=None):
        p = self.lib.metadata_proposal([item], {"tags": tags or ["NAS"], "description": "Bestätigt"})
        self.lib.apply_metadata(p)
        return p, self.lib.item(item["id"])

    def operation(self, item, action="copy"):
        return prepare(self.lib, FileOperation(items=[{"id": item["id"], "revision": item["revision"]}],
                                             action=action, target_id=self.folder["id"]))

    def test_scan_is_read_only_and_metadata_needs_review(self):
        item = self.file()
        before = (self.pc / item["name"]).read_bytes()
        proposal = self.lib.metadata_proposal([item], {"tags": ["NAS"], "description": "Entwurf"})
        self.assertEqual(self.lib.item(item["id"])["tags"], [])
        self.assertEqual(self.lib.listing(q="Entwurf")["total"], 0)
        self.assertEqual(list(self.pc.iterdir()), [self.pc / item["name"]])
        self.assertEqual((self.pc / item["name"]).read_bytes(), before)
        self.lib.apply_metadata(proposal)
        self.assertEqual(self.lib.listing(tag="nas")["total"], 1)
        self.lib.undo_metadata(self.lib.get_proposal(proposal["id"]))
        self.assertEqual(self.lib.item(item["id"])["tags"], [])

    def test_pending_proposals_survive_reopening(self):
        item = self.file()
        p = self.lib.metadata_proposal([item], {"tags": ["Entwurf"], "description": ""})
        self.db.close()
        self.db = Database(self.root / "app.db")
        self.lib = LibraryStore(self.profile, self.db)
        self.assertEqual(self.lib.get_proposal(p["id"])["status"], "pending")
        self.assertFalse(self.lib.item(item["id"])["reviewed"])

    def test_changed_source_rejects_approval(self):
        item = self.file()
        p = self.lib.metadata_proposal([item], {"tags": ["NAS"], "description": ""})
        (self.pc / item["name"]).write_text("Verändert und länger")
        with self.assertRaises(LibraryError):
            self.lib.apply_metadata(p)
        self.assertEqual(self.lib.item(item["id"])["tags"], [])

    def test_source_offline_does_not_mark_files_deleted(self):
        item = self.file()
        displaced = self.root / "disconnected"
        self.pc.rename(displaced)
        try:
            with self.assertRaises(LibraryError):
                self.lib.scan(self.source["id"])
            self.assertFalse(self.lib.item(item["id"])["missing"])
            self.assertFalse(self.lib.source(self.source["id"])["available"])
        finally:
            displaced.rename(self.pc)

    def test_duplicate_names_and_hashes_keep_distinct_ids(self):
        item = self.file()
        (self.nas / item["name"]).write_bytes((self.pc / item["name"]).read_bytes())
        self.lib.scan(self.target["id"])
        ids = [i["id"] for i in self.lib.listing()["items"]]
        run_job(self.lib, enqueue(self.lib, "hash", {"items": ids}))
        self.assertEqual(len(set(ids)), 2)
        self.assertEqual(self.lib.listing(duplicates=True)["total"], 2)

    def test_copy_preserves_original_and_metadata(self):
        _, item = self.metadata(self.file())
        p = self.operation(item)
        execute_one(self.lib, p, p["data"]["items"][0])
        execute_one(self.lib, p, p["data"]["items"][0])  # idempotent retry
        self.assertTrue((self.pc / item["name"]).exists())
        self.assertEqual(digest(self.pc / item["name"]), digest(self.nas / "Dokumente" / item["name"]))
        self.assertEqual(self.lib.listing(tag="nas")["total"], 2)

    def test_no_overwrite_when_target_appears_after_preview(self):
        item = self.file()
        p = self.operation(item, "move")
        target = self.nas / "Dokumente" / item["name"]
        target.write_text("Fremde Datei")
        with self.assertRaises(LibraryError):
            execute_one(self.lib, p, p["data"]["items"][0])
        self.assertTrue((self.pc / item["name"]).exists())
        self.assertEqual(target.read_text(), "Fremde Datei")

    def test_resume_after_crash_between_publication_and_journal(self):
        from backend import library_operations
        item = self.file()
        p = self.operation(item, "move")
        publish = library_operations._publish
        def crash(temp, destination):
            publish(temp, destination)
            raise OSError("Simulierter Prozessabbruch")
        with patch.object(library_operations, "_publish", crash):
            with self.assertRaises(OSError):
                execute_one(self.lib, p, p["data"]["items"][0])
        self.assertTrue((self.pc / item["name"]).exists())
        execute_one(self.lib, p, p["data"]["items"][0])
        self.assertFalse((self.pc / item["name"]).exists())
        self.assertEqual(self.lib.item(item["id"])["source_id"], self.target["id"])

    def test_changed_original_after_publication_is_never_removed(self):
        from backend import library_operations
        item = self.file()
        p = self.operation(item, "move")
        journal = library_operations._journal
        def mutate(catalog, oid, data, state):
            journal(catalog, oid, data, state)
            if state == "published":
                (self.pc / item["name"]).write_text("Neue Quelldaten")
        with patch.object(library_operations, "_journal", mutate):
            with self.assertRaises(LibraryError):
                execute_one(self.lib, p, p["data"]["items"][0])
        self.assertEqual((self.pc / item["name"]).read_text(), "Neue Quelldaten")
        self.assertTrue((self.nas / "Dokumente" / item["name"]).exists())

    def test_move_undo_requires_unchanged_destination(self):
        item = self.file()
        p = self.operation(item, "move")
        execute_one(self.lib, p, p["data"]["items"][0])
        self.db.execute("UPDATE library_proposals SET status='applied' WHERE id=?", (p["id"],))
        inverse = undo_proposal(self.lib, self.lib.get_proposal(p["id"]))
        execute_one(self.lib, inverse, inverse["data"]["items"][0])
        self.assertTrue((self.pc / item["name"]).exists())
        self.assertFalse((self.nas / "Dokumente" / item["name"]).exists())

    def test_resumed_move_rejects_catalog_changes_after_publication(self):
        from backend import library_operations
        item = self.file()
        proposal = self.operation(item, "move")
        publish = library_operations._publish
        def crash(temp, destination):
            publish(temp, destination)
            raise OSError("Unterbrechung")
        with patch.object(library_operations, "_publish", crash), self.assertRaises(OSError):
            execute_one(self.lib, proposal, proposal["data"]["items"][0])
        self.metadata(item, ["Später geändert"])
        with self.assertRaises(LibraryError):
            execute_one(self.lib, proposal, proposal["data"]["items"][0])
        self.assertTrue((self.pc / item["name"]).exists())
        self.assertTrue((self.nas / "Dokumente" / item["name"]).exists())

    def test_scan_events_during_scan_queue_one_followup(self):
        first = enqueue(self.lib, "scan", {"source_id": self.source["id"]})
        self.db.execute("UPDATE library_jobs SET status='running' WHERE id=?", (first["id"],))
        next_job = enqueue(self.lib, "scan", {"source_id": self.source["id"]})
        repeated = enqueue(self.lib, "scan", {"source_id": self.source["id"]})
        self.assertNotEqual(first["id"], next_job["id"])
        self.assertEqual(next_job["id"], repeated["id"])

    def test_job_enqueue_does_not_commit_outer_approval_transaction(self):
        item = self.file()
        proposal = self.operation(item)
        with self.assertRaises(RuntimeError):
            with self.db._lock, self.db._conn:
                self.db._conn.execute("UPDATE library_proposals SET status='approved' WHERE id=?", (proposal["id"],))
                enqueue(self.lib, "execute", {"proposal_id": proposal["id"]})
                raise RuntimeError("Abbruch vor Commit")
        self.assertEqual(self.lib.get_proposal(proposal["id"])["status"], "pending")
        self.assertEqual(self.lib.rows("SELECT id FROM library_jobs WHERE kind='execute'"), [])

    def test_vectors_rebuild_after_extension_was_unavailable(self):
        self.assertTrue(self.db.search.vec)
        self.db.search.replace("library", "old", "old.txt", [{"content": "alt", "embedding": [1., 0.]}], "test")
        self.db.search.vec = False
        self.db.search.remove("library", "old")
        self.db.search.replace("library", "new", "new.txt", [{"content": "neu", "embedding": [0., 1.]}], "test")
        self.db.close()
        self.db = Database(self.root / "app.db")
        self.lib = LibraryStore(self.profile, self.db)
        self.assertEqual(self.db.search.search("unbekannt", [1., 0.], "test", ("library",)), [])
        result = self.db.search.search("unbekannt", [0., 1.], "test", ("library",))
        self.assertEqual(result[0]["item_id"], "new")

    def test_paths_reject_traversal_streams_reserved_names_and_vault(self):
        for name in ("../x", "/absolute", "C:/outside", "\\\\server\\share", "a/../b",
                     "x:stream", "CON.txt", ".wissens-ki/test", "a.", "a//b"):
            with self.subTest(name=name), self.assertRaises(LibraryError):
                relative_path(name)
        with self.assertRaises(LibraryError):
            self.lib.add_source(LibrarySource(name="Vault", root=str(self.vault)))
        with self.assertRaises(LibraryError):
            safe_path(self.vault, "", self.vault)

    def test_json_only_contains_accepted_metadata(self):
        item = self.file()
        p, item = self.metadata(item)
        self.db.search.replace("library", item["id"], item["path"],
                               [{"page": 1, "content": "NICHT EXPORTIEREN", "embedding": [1., 0.]}], "test")
        self.lib.metadata_proposal([item], {"tags": ["GEHEIMER_ENTWURF"], "description": ""})
        self.assertEqual(snapshot(self.lib), 1)
        path = self.nas / ".wissens-ki" / "test" / "catalog.json"
        text = path.read_text(encoding="utf-8")
        self.assertNotIn("NICHT EXPORTIEREN", text)
        self.assertNotIn("GEHEIMER_ENTWURF", text)
        self.assertNotIn("embedding", text)
        self.assertEqual(json.loads(text)["items"][0]["id"], item["id"])

    def test_restore_with_source_mapping_preserves_stable_ids(self):
        _, item = self.metadata(self.file())
        snapshot(self.lib)
        # Recreate only the catalog; files and original snapshot are retained.
        self.db.close()
        self.db = Database(self.root / "restored.db")
        self.lib = LibraryStore(self.profile, self.db)
        source = self.lib.add_source(LibrarySource(name="PC neu", root=str(self.pc), writable=True))
        target = self.lib.add_source(LibrarySource(name="NAS neu", root=str(self.nas),
                                                  writable=True, backup=True))
        self.lib.scan(source["id"])
        proposal = restore_preview(self.lib, target["id"],
                                   {self.source["id"]: source["id"], self.target["id"]: target["id"]})
        apply_restore(self.lib, proposal)
        restored = self.lib.item(item["id"])
        self.assertEqual(restored["tags"], ["NAS"])
        self.assertEqual(restored["source_id"], source["id"])
        self.assertEqual(len(self.lib.entries("target")), 1)

    def test_manual_reconciliation_preserves_old_id(self):
        _, item = self.metadata(self.file())
        self.db.execute("UPDATE library_items SET sha256=? WHERE id=?", (digest(self.pc / item["name"]), item["id"]))
        (self.pc / item["name"]).rename(self.pc / "Anders.txt")
        self.lib.scan(self.source["id"])
        new = self.lib.listing(q="Anders")["items"][0]
        p = reconcile_prepare(self.lib, item["id"], new["id"])
        reconcile_apply(self.lib, p)
        self.assertEqual(self.lib.item(item["id"])["path"], "Anders.txt")
        self.assertEqual(self.lib.item(item["id"])["tags"], ["NAS"])

    def test_ai_produces_draft_only_and_rejects_unknown_target(self):
        item = self.file()
        result = {"tags": ["Vorschlag"], "description": "Nicht bestätigt", "target_id": "outside"}
        with patch("backend.ollama_client.OllamaClient.structured", new=AsyncMock(return_value=result)):
            asyncio.run(analyze(self.lib, item))
        self.assertEqual(self.lib.item(item["id"])["tags"], [])
        p = self.lib.get_proposal(self.lib.rows("SELECT id FROM library_proposals")[0]["id"])
        self.assertEqual(p["status"], "pending")
        self.assertEqual(p["data"]["ai"]["target_id"], "")

    def test_index_opt_in_and_revoke_folder_scope(self):
        item = self.file()
        asyncio.run(index_item(self.lib, item))
        self.assertEqual(self.db.search.search("Rechnung", namespaces=("library",)), [])
        scope = self.lib.save_entry("index_scope", "PC", {"source_id": self.source["id"], "path": ""})
        with patch("backend.ollama_client.OllamaClient.embed", new=AsyncMock(side_effect=RuntimeError("offline"))):
            asyncio.run(index_item(self.lib, item))
        self.assertTrue(self.db.search.search("Rechnung", namespaces=("library",)))
        self.db.execute("UPDATE library_items SET index_enabled=-1 WHERE id=?", (item["id"],))
        self.lib.purge_excluded()
        self.assertEqual(self.db.search.search("Rechnung", namespaces=("library",)), [])

    def test_search_beyond_20000_chunks_and_namespace_isolation(self):
        chunks = [{"content": "Unwichtig " + str(i), "page": 0} for i in range(20001)]
        chunks.append({"content": "EinzigartigerNachweis", "page": 87})
        self.db.search.replace("vault", "Test.md", "Test.md", chunks)
        self.db.search.replace("library", "secret", "Privat.pdf", [{"content": "EinzigartigerNachweis", "page": 1}])
        result = self.db.search.search("EinzigartigerNachweis", namespaces=("vault",))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["page"], 87)

    def test_vault_switch_never_returns_old_index_even_with_same_relative_path(self):
        from backend.knowledge import sync_index, hybrid_search
        old = self.vault / "Notiz.md"
        old.write_text("AltesGeheimnis", encoding="utf-8")
        asyncio.run(sync_index(self.vault, self.db, None))
        fresh_root = self.root / "new-vault"
        fresh_root.mkdir()
        fresh = fresh_root / "Notiz.md"
        fresh.write_text("NeuesGeheimnis", encoding="utf-8")
        os.utime(fresh, ns=(old.stat().st_atime_ns, old.stat().st_mtime_ns))
        result = asyncio.run(hybrid_search(fresh_root, self.db, "AltesGeheimnis", None, "", refresh=False))
        self.assertEqual(result["results"], [])
        result = asyncio.run(hybrid_search(fresh_root, self.db, "NeuesGeheimnis", None, ""))
        self.assertEqual(result["results"][0]["path"], "Notiz.md")
        result = asyncio.run(hybrid_search(None, self.db, "NeuesGeheimnis", None, "", refresh=False))
        self.assertEqual(result["results"], [])

    def test_vector_filters_before_topk(self):
        if not self.db.search.vec:
            self.skipTest("sqlite-vec nicht installiert")
        for i in range(60):
            self.db.search.replace("library", str(i), str(i), [{"content": "Privat", "embedding": [1., 0.]}], "model")
        self.db.search.replace("vault", "allowed", "Allowed.md",
                               [{"content": "Erlaubt", "embedding": [.99, .01]}], "model")
        result = self.db.search.search("ähnliche Bedeutung", [1., 0.], "model", ("vault",))
        self.assertEqual(result[0]["item_id"], "allowed")

    def test_100000_catalog_entries_are_paged(self):
        with self.db._lock, self.db._conn:
            self.db._conn.executemany(
                "INSERT INTO library_items(id,source_id,path,name,folder,extension,size,modified_ns)"
                " VALUES(?,?,?,?,?,?,?,?)",
                ((f"{i:016x}", self.source["id"], f"Datei-{i:06d}.txt", f"Datei-{i:06d}.txt", "", ".txt", 1, 1)
                 for i in range(100000)))
        started = time.monotonic()
        result = self.lib.listing(offset=99900, limit=100)
        elapsed = time.monotonic() - started
        self.assertEqual(result["total"], 100000)
        self.assertEqual(len(result["items"]), 100)
        self.assertLess(elapsed, 5, "Lokale Katalogseite sollte nicht mehrere Sekunden blockieren")

    def test_api_cannot_apply_other_profile_or_bypass_preview(self):
        from backend.routers import library
        from backend.config import ConfigStore, AppConfig
        app = FastAPI()
        app.include_router(library.router)
        @app.exception_handler(LibraryError)
        async def error(request, exc):
            return JSONResponse(status_code=409, content={"detail": str(exc)})
        config = ConfigStore(self.root / "config.json")
        config._config = AppConfig(active_profile="test", profiles=[self.profile])
        item = self.file()
        p = self.lib.metadata_proposal([item], {"tags": ["API"], "description": ""})
        with patch.object(library, "store", config), patch.object(library.registry, "get", return_value=self.db):
            client = TestClient(app)
            self.assertEqual(client.get("/api/library/items", params={"profile_id": "other"}).status_code, 409)
            url = "/api/library/proposals/" + p["id"] + "/approve?profile_id=test"
            self.assertEqual(client.post(url, json={"revision": 1, "confirm": False}).status_code, 422)
            self.assertEqual(client.post(url, json={"revision": 1, "confirm": True}).status_code, 200)
            self.assertEqual(client.post(url, json={"revision": 1, "confirm": True}).status_code, 409)

    def test_settings_cannot_make_entire_library_source_a_vault(self):
        from backend.routers import settings
        from backend.config import ConfigStore, AppConfig
        config = ConfigStore(self.root / "config.json")
        config._config = AppConfig(active_profile="test", profiles=[self.profile])
        app = FastAPI()
        app.include_router(settings.router)
        with patch.object(settings, "store", config), patch.object(settings.registry, "get", return_value=self.db):
            response = TestClient(app).patch("/api/settings/profile/test", json={"patch": {"vault": {"path": str(self.nas)}}})
        self.assertEqual(response.status_code, 400)
        self.assertFalse((self.nas / "00 Inhalt.md").exists())
