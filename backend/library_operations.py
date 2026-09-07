"""Reviewed file actions with durable publication and source-removal journal."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .database import new_id, now_iso
from .library_models import LibraryError
from .library_paths import safe_path, relative_path, fingerprint, digest, is_link
from .library_store import dump


def prepare(catalog, request):
    with catalog.lock:
        items = catalog.checked(request.items)
        if request.name and len(items) != 1:
            raise LibraryError("Ein neuer Dateiname ist nur für eine einzelne Datei möglich.")
        target = catalog.entry(request.target_id, "target") if request.action != "rename" else None
        changes, destinations = [], set()
        for item in items:
            source = catalog.source(item["source_id"])
            if request.action in {"move", "rename"} and not source["writable"]:
                raise LibraryError("Quelle ist nur zum Lesen freigegeben.")
            target_source = catalog.source(target["data"]["source_id"]) if target else source
            if not target_source["writable"]:
                raise LibraryError("Ziel ist nicht zum Schreiben freigegeben.")
            folder = target["data"]["path"] if target else item["folder"]
            name = request.name or item["name"]
            relative_path(name, False)
            if "/" in name or "\\" in name or Path(name).suffix.lower() != item["extension"]:
                raise LibraryError("Nur der Dateiname darf geändert werden; die Endung bleibt erhalten.")
            destination = "/".join(p for p in (folder, name) if p)
            path = safe_path(target_source["root"], destination, catalog.profile.vault_path)
            if path.exists() or not path.parent.is_dir():
                raise LibraryError(f"Ziel existiert bereits oder Zielordner fehlt: {destination}")
            key = (target_source["id"], destination.casefold())
            if key in destinations:
                raise LibraryError("Mehrere ausgewählte Dateien hätten dasselbe Ziel.")
            destinations.add(key)
            changes.append({
                "id": item["id"], "revision": item["revision"], "source_id": source["id"],
                "source_revision": source["revision"], "path": item["path"],
                "size": item["size"], "modified_ns": item["modified_ns"],
                "target_source_id": target_source["id"], "target_source_revision": target_source["revision"],
                "destination": destination, "target_id": target["id"] if target else "",
                "target_revision": target["revision"] if target else 0,
            })
        return catalog.proposal("operation", {"action": request.action, "items": changes})


def _journal(catalog, operation_id, data, state):
    catalog.db.execute("UPDATE library_operations SET data=?,state=?,error='' WHERE id=?",
                       (dump(data), state, operation_id))


def _publish(temp: Path, destination: Path):
    """No overwrite on either platform. Windows rename is exclusive."""
    if os.name == "nt":
        os.rename(temp, destination)
    else:
        os.link(temp, destination)
        temp.unlink()


def execute_one(catalog, proposal, change, checkpoint=lambda: None):
    # Serializes metadata changes and file actions; hashing/copying never holds the DB lock.
    with catalog.lock:
        source = catalog.source(change["source_id"])
        target = catalog.source(change["target_source_id"])
        if source["revision"] != change["source_revision"] or target["revision"] != change["target_source_revision"]:
            raise LibraryError("Quellenfreigabe wurde geändert. Neuen Vorschlag erstellen.")
        if not target["writable"] or (proposal["data"]["action"] != "copy" and not source["writable"]):
            raise LibraryError("Schreibfreigabe fehlt.")
        if change["target_id"]:
            if catalog.entry(change["target_id"], "target")["revision"] != change["target_revision"]:
                raise LibraryError("Zielstruktur wurde geändert. Neuen Vorschlag erstellen.")
        original = safe_path(source["root"], change["path"], catalog.profile.vault_path)
        destination = safe_path(target["root"], change["destination"], catalog.profile.vault_path)
        existing = catalog.rows("SELECT * FROM library_operations WHERE proposal_id=? AND item_id=?",
                                (proposal["id"], change["id"]))
        if existing:
            operation = existing[0]
            data = json.loads(operation["data"])
            if operation["state"] == "done":
                return
            current = catalog.item(change["id"])
            if (current["revision"] != change["revision"] or current["source_id"] != change["source_id"]
                    or current["path"] != change["path"]):
                raise LibraryError("Dateieintrag nach Unterbrechung geändert. Beide Dateien bleiben erhalten; neu prüfen.")
        else:
            catalog.checked([change])
            operation = {"id": new_id(), "state": "planned"}
            data = {**change, "action": proposal["data"]["action"]}
            catalog.db.execute(
                "INSERT INTO library_operations(id,proposal_id,item_id,data,state,created_at) VALUES(?,?,?,?,?,?)",
                (operation["id"], proposal["id"], change["id"], dump(data), "planned", now_iso()))
        oid = operation["id"]
        temp = destination.parent / f".lka-{oid}.partial"
        if is_link(temp):
            raise LibraryError("Unsichere temporäre Zieldatei.")
        expected = {key: change[key] for key in ("size", "modified_ns")}
        state = operation["state"]
        try:
            checkpoint()
            if state in {"planned", "copying"}:
                catalog.checked([change])
                if destination.exists():
                    raise LibraryError("Ziel wurde nach der Vorschau belegt; nichts überschrieben.")
                if temp.exists():
                    temp.unlink()  # exclusively owned, journaled scratch file
                _journal(catalog, oid, data, "copying")
                sha = hashlib.sha256()
                with original.open("rb") as src, temp.open("xb") as dst:
                    while block := src.read(1024 * 1024):
                        checkpoint()
                        dst.write(block)
                        sha.update(block)
                    dst.flush()
                    os.fsync(dst.fileno())
                if fingerprint(original) != expected:
                    raise LibraryError("Quelle während des Kopierens verändert; Original bleibt erhalten.")
                data["sha256"] = sha.hexdigest()
                if digest(temp, checkpoint) != data["sha256"]:
                    raise LibraryError("Zielprüfung fehlgeschlagen; Original bleibt erhalten.")
                data["published_fingerprint"] = fingerprint(temp)
                _journal(catalog, oid, data, "verified")
                state = "verified"
            if state == "verified":
                # A crash after exclusive publication can leave the journal one step behind.
                if destination.exists():
                    if temp.exists() or fingerprint(destination) != data["published_fingerprint"]:
                        raise LibraryError("Zielkonflikt nach Unterbrechung; bitte manuell prüfen.")
                    if digest(destination, checkpoint) != data["sha256"]:
                        raise LibraryError("Ziel wurde nach Unterbrechung verändert.")
                else:
                    if digest(temp, checkpoint) != data["sha256"]:
                        raise LibraryError("Temporäre Datei wurde verändert.")
                    safe_path(target["root"], change["destination"], catalog.profile.vault_path)
                    _publish(temp, destination)
                _journal(catalog, oid, data, "published")
                state = "published"
            if state == "published":
                if digest(destination, checkpoint) != data["sha256"]:
                    raise LibraryError("Zieldatei verändert. Quelle wird nicht entfernt.")
                if data["action"] != "copy" and original.exists():
                    safe_path(source["root"], change["path"], catalog.profile.vault_path)
                    if fingerprint(original) != expected or digest(original, checkpoint) != data["sha256"]:
                        raise LibraryError("Quelle verändert. Beide Dateien bleiben erhalten.")
                    checkpoint()
                    original.unlink()
                _journal(catalog, oid, data, "source_kept" if data["action"] == "copy" else "source_removed")
            info = fingerprint(destination)
            if digest(destination, checkpoint) != data["sha256"]:
                raise LibraryError("Ziel nach Veröffentlichung verändert; Katalogabgleich erforderlich.")
            item = catalog.item(change["id"])
            with catalog.db._lock, catalog.db._conn:
                conn = catalog.db._conn
                if data["action"] == "copy":
                    result_id = data.get("result_id") or new_id()
                    data["result_id"] = result_id
                    conn.execute(
                        "INSERT INTO library_items(id,source_id,path,name,folder,extension,size,modified_ns,"
                        "sha256,tags,description,reviewed) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (result_id, target["id"], change["destination"], destination.name,
                         str(Path(change["destination"]).parent).replace("\\", "/")
                         if "/" in change["destination"] else "", item["extension"],
                         info["size"], info["modified_ns"], data["sha256"], dump(item["tags"]),
                         item["description"], item["reviewed"]))
                    conn.executemany("INSERT INTO library_tags VALUES(?,?)",
                                     [(result_id, tag.casefold()) for tag in item["tags"]])
                else:
                    data["result_id"] = item["id"]
                    catalog.db.search.remove("library", item["id"])
                    conn.execute(
                        "UPDATE library_items SET source_id=?,path=?,name=?,folder=?,size=?,modified_ns=?,"
                        "sha256=?,missing=0,revision=revision+1,indexed_revision=0 WHERE id=?",
                        (target["id"], change["destination"], destination.name,
                         Path(change["destination"]).parent.as_posix() if "/" in change["destination"] else "",
                         info["size"], info["modified_ns"], data["sha256"], item["id"]))
                data["result_revision"] = catalog.item(data["result_id"])["revision"]
                conn.execute("UPDATE library_operations SET state='done',data=?,error='' WHERE id=?",
                             (dump(data), oid))
            catalog.dirty()
        except Exception as exc:
            catalog.db.execute("UPDATE library_operations SET error=? WHERE id=?", (str(exc), oid))
            raise


def undo_proposal(catalog, proposal):
    changes = []
    with catalog.lock:
        if proposal["status"] != "applied" or proposal["data"].get("action") not in {"move", "rename"}:
            raise LibraryError("Nur abgeschlossene Verschiebungen/Umbenennungen sind rückgängig machbar.")
        for row in catalog.rows("SELECT data FROM library_operations WHERE proposal_id=? AND state='done'",
                                (proposal["id"],)):
            data = json.loads(row["data"])
            item = catalog.item(data["result_id"])
            catalog.checked([{"id": item["id"], "revision": data["result_revision"]}])
            if digest(catalog.path(item)) != data["sha256"]:
                raise LibraryError("Datei wurde seit dem Verschieben verändert.")
            original_source = catalog.source(data["source_id"])
            if safe_path(original_source["root"], data["path"], catalog.profile.vault_path).exists():
                raise LibraryError("Ursprünglicher Platz ist inzwischen belegt.")
            current_source = catalog.source(item["source_id"])
            changes.append({
                "id": item["id"], "revision": item["revision"],
                "source_id": item["source_id"], "source_revision": current_source["revision"],
                "path": item["path"], "size": item["size"], "modified_ns": item["modified_ns"],
                "target_source_id": data["source_id"], "target_source_revision": original_source["revision"],
                "destination": data["path"], "target_id": "", "target_revision": 0,
            })
        return catalog.proposal("operation", {"action": "move", "items": changes, "undo_of": proposal["id"]})
