"""Isolated browser QA server; never opens the user's profile or Vault."""
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import backend.config as config

demo = config.SOURCE_ROOT / ".test-runtime" / "library-ui"
for name in ("pc", "nas", "vault", "app-data"):
    (demo / name).mkdir(parents=True, exist_ok=True)
(demo / "nas" / "Dokumente").mkdir(exist_ok=True)
config.DATA_DIR = demo / "app-data"
config.PROFILE_DATA_DIR = config.DATA_DIR / "profiles"
config.LOG_DIR = config.DATA_DIR / "logs"
config.store.path = config.DATA_DIR / "config.json"
config.store._config = config.AppConfig(
    active_profile="demo", profiles=[config.Profile(
        id="demo", name="Testbibliothek (isoliert)", vault={"path": str(demo / "vault")},
        library={"enabled": True}, ollama={"base_url": "http://127.0.0.1:59999"})])
profile = config.store.active_profile()
from backend.database import registry
from backend.library_store import LibraryStore
from backend.library_models import LibrarySource
lib = LibraryStore(profile, registry.get(profile.id, profile.db_path))
if not lib.sources():
    for name, text in [
        ("2026-08_NAS-Rechnung.txt", "NAS-Festplatten – Kaufbeleg für zwei Festplatten."),
        ("Versicherung.txt", "Unterlagen zur Versicherung. Vertragsjahr 2026."),
        ("Projektideen.md", "# Ideen\n\nLokale Wissensverwaltung ohne Cloud.")]:
        (demo / "pc" / name).write_text(text, encoding="utf-8")
    pc = lib.add_source(LibrarySource(name="PC · Eingang", root=str(demo / "pc"), writable=True))
    nas = lib.add_source(LibrarySource(name="NAS · Archiv", root=str(demo / "nas"),
                                      kind="nas", writable=True, backup=True))
    lib.save_entry("target", "Dokumente", {"source_id": nas["id"], "path": "Dokumente"})
    lib.scan(pc["id"])
    first = lib.listing()["items"][0]
    lib.metadata_proposal([first], {"tags": ["NAS", "Hardware", "Rechnung"],
                                   "description": "Kaufbeleg für die Festplatten des NAS."})
from backend.main import app
import uvicorn
print(f"QA_PID={os.getpid()}", flush=True)
uvicorn.run(app, host="127.0.0.1", port=5058, log_level="warning")
