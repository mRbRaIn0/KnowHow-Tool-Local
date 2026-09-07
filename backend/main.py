"""FastAPI-Anwendung: bindet Router ein und liefert das Frontend aus.

Der Server lauscht ausschließlich auf 127.0.0.1 und beantwortet nur Anfragen
mit gültigem Sitzungsschlüssel (siehe security.py). Eine strikte
Content-Security-Policy stellt sicher, dass das Frontend keine externen
Ressourcen nachladen kann.
"""
from __future__ import annotations

import logging
import logging.handlers
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from . import attachments, security
from .config import BUNDLE_ROOT, LOG_DIR, build_fingerprint, store
from .database import registry
from .watcher import watcher
from .vault_guide import ensure_vault_guide
from .routers import backups, chat, files, knowledge, search, settings, system, templates, uploads, library
from .library_models import LibraryError
from .library_jobs import manager as library_manager
from .knowledge_worker import knowledge_worker

FRONTEND_DIR = BUNDLE_ROOT / "frontend"

# Windows liest MIME-Typen aus der Registry und liefert für .js oft text/plain.
# Browser lehnen ES-Module dann ab — deshalb hier fest setzen.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("text/css", ".css")
mimetypes.add_type("image/svg+xml", ".svg")
mimetypes.add_type("application/json", ".json")

CSP = (
    "default-src 'self'; "
    "img-src 'self' data: blob:; "
    "media-src 'self' blob:; "
    "style-src 'self' 'unsafe-inline'; "
    "script-src 'self'; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    "object-src 'self'; "
    "frame-src 'self'; "
    "base-uri 'none'; "
    "form-action 'none'"
)

log = logging.getLogger("lka")


def setup_logging() -> None:
    """Logging ausschließlich lokal in data/logs/app.log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / "app.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        root.addHandler(handler)
    # Sonst protokolliert httpx jede einzelne Ollama-Anfrage. Die Statusleiste
    # fragt alle 12 Sekunden — die Nachweiszeilen (angelegte Notizen,
    # abgewiesene Zugriffe) waeren binnen Stunden aus der Rotation gedraengt.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    config = store.load()
    profile = store.active_profile()
    registry.get(profile.id, profile.db_path)  # DB anlegen/öffnen
    if profile.vault_path is not None and profile.vault_path.is_dir():
        try:
            ensure_vault_guide(profile.vault_path, create=True)
        except OSError as exc:
            log.warning("Vault-Hauptdatei konnte nicht gepflegt werden: %s", exc)
    watcher.ensure(profile.id, profile.vault_path)
    library_manager.start()
    knowledge_worker.start()
    entfernt = attachments.cleanup_old()
    if entfernt:
        log.info("Alte Anhang-Zwischenablagen entfernt: %d", entfernt)
    log.info("Start — Profil '%s', Vault '%s'", profile.name, profile.vault.path or "(nicht gesetzt)")
    yield
    watcher.stop()
    library_manager.stop()
    knowledge_worker.stop()
    if (not library_manager.thread or not library_manager.thread.is_alive()) and (
            not knowledge_worker.thread or not knowledge_worker.thread.is_alive()):
        registry.close_all()
    log.info("Beendet.")


app = FastAPI(title="KnowHow Tool", version="1.0", lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)


ABWEISUNG_SEITE = """<!doctype html><meta charset="utf-8">
<title>KnowHow Tool</title>
<div style="font:15px/1.6 'Segoe UI',system-ui,sans-serif;max-width:34em;margin:12vh auto;padding:0 1.5em;color:#1c1f24">
<h1 style="font-size:1.35em">Diese Adresse ist ohne Sitzungsschlüssel geöffnet</h1>
<p>%(grund)s</p>
<p>Der Schlüssel wird bei jedem Start neu erzeugt und nur an das App-Fenster
übergeben. Bitte die App über ihre Verknüpfung starten statt über ein
Lesezeichen — der Port wechselt ebenfalls bei jedem Start.</p>
</div>"""


def _abweisung(request: Request, grund: str) -> Response:
    """Fremde Anfragen erhalten nie Inhalte — aber eine erklärbare Antwort."""
    log.warning("Abgewiesen: %s %s (%s)", request.method, request.url.path, grund)
    if request.url.path.startswith("/api"):
        return JSONResponse(status_code=403,
                            content={"detail": {"message": grund, "kind": "forbidden"}})
    return Response(content=ABWEISUNG_SEITE % {"grund": grund}, status_code=403,
                    media_type="text/html; charset=utf-8")


def _zugang_pruefen(request: Request) -> Response | None:
    """Host, Ursprung und Sitzungsschlüssel — in dieser Reihenfolge."""
    if not security.host_is_local(request.headers.get("host", "")):
        # DNS-Rebinding: fremde Domain zeigt auf 127.0.0.1 und gilt dem
        # Browser dadurch als gleicher Ursprung. Nur der Host verrät es.
        return _abweisung(request, "Diese App ist ausschließlich über 127.0.0.1 erreichbar.")
    if (request.url.path.startswith("/api") and request.method not in {"GET", "HEAD"}
            and not security.same_origin(request)):
        return _abweisung(request, "Der Schreibzugriff kam von einer fremden Seite.")
    if request.url.path in security.OPEN_PATHS:
        return None
    if not security.request_is_authorised(request):
        return _abweisung(request, "Der Sitzungsschlüssel fehlt oder gehört zu einem früheren Start.")
    return None


@app.middleware("http")
async def security_headers(request: Request, call_next):
    verweigert = _zugang_pruefen(request)
    if verweigert is not None:
        response = verweigert
    else:
        response = await call_next(request)
        if (request.url.path == "/"
                and security.token_matches(request.query_params.get(security.QUERY_NAME, ""))
                and request.cookies.get(security.COOKIE_NAME) != security.SESSION_TOKEN):
            # Ab jetzt trägt das Fenster den Schlüssel von selbst. SameSite=strict
            # hält ihn von jeder fremden Seite fern, http_only von jedem Skript.
            response.set_cookie(security.COOKIE_NAME, security.SESSION_TOKEN,
                                httponly=True, samesite="strict", path="/")
    response.headers.setdefault("Content-Security-Policy", CSP)
    response.headers["X-Content-Type-Options"] = "nosniff"
    # Lokale App: nach einem Update soll sofort die neue Oberfläche laufen.
    if request.url.path.startswith(("/assets", "/api")) or request.url.path == "/":
        response.headers["Cache-Control"] = "no-store, must-revalidate"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), microphone=(), camera=()"
    return response


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    """Kein Absturz bei unerwarteten Fehlern — verständliche Meldung zurückgeben."""
    log.exception("Unbehandelter Fehler bei %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content={"detail": {"message": f"Unerwarteter Fehler: {exc}", "kind": "error"}},
    )


app.include_router(system.router)
app.include_router(chat.router)
app.include_router(files.router)
app.include_router(search.router)
app.include_router(knowledge.router)
app.include_router(templates.router)
app.include_router(uploads.router)
app.include_router(settings.router)
app.include_router(backups.router)
app.include_router(library.router)


@app.exception_handler(LibraryError)
async def library_error(request: Request, exc: LibraryError):
    return JSONResponse(status_code=409, content={"detail": {"message": str(exc), "kind": "library"}})


BUILD = build_fingerprint()


@app.get("/api/health")
async def health():
    return {"ok": True, "app": "KnowHow Tool", "version": app.version, "build": BUILD}


# Frontend zuletzt registrieren, damit /api/* Vorrang hat.
#
# Bewusst kein StaticFiles: dessen 304-Antworten lassen den Browser den alten
# (unter Windows falschen) MIME-Typ weiterverwenden, wodurch ES-Module nicht
# laden. Der eigene Handler setzt den Typ fest und cached nichts.
ASSET_TYPES = {
    ".js": "text/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
    ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8",
    ".png": "image/png",
    ".webp": "image/webp",
    ".woff2": "font/woff2",
}


def _asset(relative: str) -> Path | None:
    """Löst einen Frontend-Pfad auf und verhindert Ausbrüche aus dem Ordner."""
    target = (FRONTEND_DIR / relative).resolve()
    if not str(target).startswith(str(FRONTEND_DIR.resolve())):
        return None
    return target if target.is_file() else None


@app.get("/assets/{path:path}")
async def asset(path: str):
    target = _asset(path)
    if target is None:
        return JSONResponse(status_code=404, content={"detail": "Datei nicht gefunden"})
    media_type = ASSET_TYPES.get(target.suffix.lower(), "application/octet-stream")
    return Response(content=target.read_bytes(), media_type=media_type)


@app.get("/")
async def index():
    target = FRONTEND_DIR / "index.html"
    if not target.is_file():
        return JSONResponse(status_code=500, content={"detail": "Frontend fehlt"})
    return Response(content=target.read_bytes(), media_type="text/html; charset=utf-8")


@app.get("/favicon.ico")
async def favicon():
    target = FRONTEND_DIR / "favicon.svg"
    if not target.is_file():
        return JSONResponse(status_code=404, content={"detail": "kein Favicon"})
    return Response(content=target.read_bytes(), media_type="image/svg+xml")
