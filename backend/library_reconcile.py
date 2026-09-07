"""Explicit reconciliation after moves made outside the app."""
from .library_models import LibraryError
from .library_paths import safe_path, digest


def prepare(catalog, old_id, new_id):
    with catalog.lock:
        old, new = catalog.item(old_id), catalog.item(new_id)
        if not old["missing"] or new["missing"] or new["reviewed"] or old_id == new_id:
            raise LibraryError("Wähle einen fehlenden alten und einen ungeprüften neuen Eintrag.")
        source = catalog.source(old["source_id"])
        if not source["available"]:
            raise LibraryError("Alte Quelle ist offline. Ein Ausfall ist keine Verschiebung.")
        if safe_path(source["root"], old["path"], catalog.profile.vault_path).exists():
            raise LibraryError("Die ursprüngliche Datei existiert noch.")
        new_path = catalog.path(new)
        if old["size"] != new["size"]:
            raise LibraryError("Dateigrößen stimmen nicht überein.")
        verified = False
        if old["sha256"]:
            if digest(new_path) != old["sha256"]:
                raise LibraryError("Dateiinhalt stimmt nicht mit dem alten Hash überein.")
            verified = True
        return catalog.proposal("reconcile", {
            "items": [{"id": new_id, "revision": new["revision"], "path": new["path"]}],
            "old_id": old_id, "old_revision": old["revision"], "old_path": old["path"],
            "hash_verified": verified,
            "warning": "" if verified else "Kein früherer Hash vorhanden: Zuordnung ausschließlich nach deiner manuellen Prüfung.",
        })


def apply(catalog, proposal):
    with catalog.lock:
        data = proposal["data"]
        old = catalog.item(data["old_id"])
        if old["revision"] != data["old_revision"] or not old["missing"]:
            raise LibraryError("Alter Eintrag wurde verändert.")
        new = catalog.checked(data["items"])[0]
        # Revalidate source availability, missing original and content before remapping.
        fresh = prepare(catalog, old["id"], new["id"])
        catalog.db.execute("DELETE FROM library_proposals WHERE id=?", (fresh["id"],))
        catalog.db.search.remove("library", new["id"])
        with catalog.db._lock, catalog.db._conn:
            conn = catalog.db._conn
            conn.execute("DELETE FROM library_tags WHERE item_id=?", (new["id"],))
            conn.execute("DELETE FROM library_items WHERE id=?", (new["id"],))
            conn.execute("UPDATE library_items SET source_id=?,path=?,name=?,folder=?,size=?,modified_ns=?,"
                         "missing=0,revision=revision+1,indexed_revision=0 WHERE id=?",
                         (new["source_id"], new["path"], new["name"], new["folder"],
                          new["size"], new["modified_ns"], old["id"]))
            conn.execute("UPDATE library_proposals SET status='applied' WHERE id=?", (proposal["id"],))
        catalog.dirty()
        return {"id": old["id"]}
