"""Starter für das KnowHow Tool.

Prüft Port und Ollama, startet das Backend und öffnet die Oberfläche in einem
eigenen Fenster.
Aufruf: python run.py [--no-browser] [--port 5000]
"""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

RUNTIME_ROOT = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
sys.path.insert(0, str(RUNTIME_ROOT))

# Konsolenausgabe nie an der Codepage scheitern lassen.
for name, mode in (("stdout", "w"), ("stderr", "w"), ("stdin", "r")):
    if getattr(sys, name) is None:
        # PyInstaller --windowed has no streams; Uvicorn still checks isatty().
        setattr(sys, name, open(os.devnull, mode, encoding="utf-8"))
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(errors="replace")
    except (AttributeError, ValueError):
        pass

import desktop  # noqa: E402
from backend import security  # noqa: E402
from backend.config import DATA_DIR, build_fingerprint, store  # noqa: E402
from backend.routers.system import _find_ollama  # noqa: E402


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def melden(text: str) -> None:
    """Wichtige Meldung ausgeben. Die gepackte App hat keine Konsole —
    dort erscheint stattdessen ein Fenster, sonst bliebe der Start stumm."""
    print(text)
    if not (getattr(sys, "frozen", False) and sys.platform == "win32"):
        return
    try:
        import ctypes
        if ctypes.windll.kernel32.GetConsoleWindow() == 0:
            ctypes.windll.user32.MessageBoxW(0, text, "KnowHow Tool", 0x30)
    except (OSError, AttributeError):
        pass


def running_instance(host: str, port: int) -> dict | None:
    """Antwort der App, die schon auf dem Port lauscht — sonst None."""
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/api/health", timeout=1.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return payload if payload.get("app") in {"KnowHow Tool", "Lokale Wissens-KI"} else None


def free_port(host: str) -> int:
    """Einen freien Port vom Betriebssystem erfragen.

    Ein fester, überall gleicher Port ist von jeder Webseite im selben Browser
    adressierbar. Ein bei jedem Start anderer ist es praktisch nicht.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, 0))
        return sock.getsockname()[1]


def find_free_port(host: str, start: int, attempts: int = 20) -> int:
    for candidate in range(start, start + attempts):
        if not port_in_use(host, candidate):
            return candidate
    return free_port(host)


def ollama_online(base_url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/api/version", timeout=1.5):
            return True
    except (urllib.error.URLError, OSError):
        return False


def ensure_ollama(base_url: str) -> None:
    """Ollama best effort starten. Fehlschlag ist kein Grund, die App nicht zu starten."""
    if ollama_online(base_url):
        print(f"  Ollama:  online ({base_url})")
        return
    executable = _find_ollama()
    if not executable:
        print("  Ollama:  nicht gefunden - bitte manuell starten (ollama serve)")
        return
    print("  Ollama:  wird gestartet ...")
    try:
        creationflags = 0x08000000 if sys.platform == "win32" else 0  # CREATE_NO_WINDOW
        subprocess.Popen([executable, "serve"], creationflags=creationflags,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        print(f"  Ollama:  Start fehlgeschlagen ({exc})")
        return
    for _ in range(16):
        time.sleep(0.5)
        if ollama_online(base_url):
            print("  Ollama:  online")
            return
    print("  Ollama:  antwortet noch nicht - die App startet trotzdem")


def bereits_offen(args) -> bool:
    """Läuft schon eine Instanz? Dann deren Fenster öffnen statt einer zweiten.

    Bei wechselndem Port hilft kein Absuchen mehr — die laufende Instanz
    hinterlegt Port und Sitzungsschlüssel in data/runtime.json.
    """
    laufzeit = security.read_runtime(DATA_DIR)
    if not laufzeit:
        return False
    host, port = laufzeit.get("host", "127.0.0.1"), int(laufzeit["port"])
    antwort = running_instance(host, port)
    if antwort is None:
        return False  # veraltete Datei, die Instanz ist längst beendet
    if antwort.get("build") != build_fingerprint():
        # Nach einem Update würde das Fenster sonst still die alte Instanz
        # öffnen — inklusive fehlender neuer Funktionen.
        melden(
            f"Auf Port {port} laeuft noch eine aeltere Version dieser App.\n\n"
            "Bitte zuerst die laufende App beenden: ihr Fenster schliessen oder "
            "im Task-Manager den zugehoerigen Prozess beenden. Danach diese "
            "Version erneut starten.\n\n"
            f"(laufend: {antwort.get('build', 'unbekannt')}, hier: {build_fingerprint()})"
        )
        raise SystemExit(1)
    print(f"  Laeuft bereits auf Port {port}")
    if not args.no_browser:
        adresse = f"http://{host}:{port}/?{security.QUERY_NAME}={laufzeit.get('token', '')}"
        desktop.zeigen(adresse, DATA_DIR / "fenster")
    return True


def selbsttest(bericht: str) -> None:
    """Offline-Prüfung des gepackten Stands, ohne Server und ohne Fenster."""
    import logging.config
    import sqlite3
    import sqlite_vec
    from backend.main import app
    from uvicorn.config import LOGGING_CONFIG
    logging.config.dictConfig(LOGGING_CONFIG)
    with sqlite3.connect(":memory:") as conn:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        conn.execute("CREATE VIRTUAL TABLE test_fts USING fts5(content)")
        conn.execute("CREATE VIRTUAL TABLE test_vec USING vec0(embedding float[2])")
        report = {"ok": True, "sqlite_vec": conn.execute("SELECT vec_version()").fetchone()[0],
                  "sqlite": sqlite3.sqlite_version, "routes": len(app.routes),
                  "sitzungsschutz": len(security.SESSION_TOKEN) >= 32,
                  "fenster": fenster_art(),
                  "frozen": bool(getattr(sys, "frozen", False))}
    for relative in ("frontend/js/views/chat.js", "frontend/js/views/knowledge.js", "templates/Standard.md", "LICENSE"):
        if not (RUNTIME_ROOT / relative).is_file():
            raise RuntimeError("Paketdatei fehlt: " + relative)
    Path(bericht).write_text(json.dumps(report, indent=2), encoding="utf-8")


def fenster_art() -> str:
    """Welche Fensterstufe dieser Stand erreicht — für den Paketbericht."""
    try:
        import webview  # noqa: F401
        return "webview2"
    except ImportError:
        return "browser-app-modus" if desktop.browser_programm() else "browser"


def main() -> None:
    parser = argparse.ArgumentParser(description="KnowHow Tool starten")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--host", default=None)
    parser.add_argument("--no-browser", action="store_true", help="Oberflaeche nicht oeffnen")
    parser.add_argument("--no-ollama", action="store_true", help="Ollama nicht automatisch starten")
    parser.add_argument("--reload", action="store_true", help="Entwicklungsmodus")
    parser.add_argument("--self-test", metavar="REPORT", help="Offline-Paketprüfung; JSON-Bericht schreiben und beenden")
    args = parser.parse_args()

    if args.self_test:
        selbsttest(args.self_test)
        return

    try:
        config = store.load()
    except OSError as exc:
        # Ohne beschreibbaren data-Ordner geht nichts. Ohne diese Meldung
        # verschwaende die gepackte App wortlos: kein Fenster, kein Logbuch.
        melden(f"Die App kann ihren Datenordner nicht anlegen:\n\n{DATA_DIR}\n\n{exc}\n\n"
               "Bitte die App an einen beschreibbaren Ort legen, zum Beispiel "
               "unter %LOCALAPPDATA%.")
        raise SystemExit(1)

    host = args.host or config.server.host
    profile = store.active_profile()

    print("=" * 58)
    print("  KnowHow Tool")
    print("=" * 58)
    print(f"  Profil:  {profile.name}")
    print(f"  Vault:   {profile.vault.path or '(noch nicht gesetzt)'}")

    if bereits_offen(args):
        return

    if not args.no_ollama:
        ensure_ollama(profile.ollama.base_url)

    gewuenscht = args.port if args.port is not None else config.server.port
    if not gewuenscht:
        port = free_port(host)
    elif port_in_use(host, gewuenscht):
        port = find_free_port(host, gewuenscht + 1)
        print(f"  Port {gewuenscht} belegt - nutze {port}")
    else:
        port = gewuenscht

    print(f"  Adresse: http://{host}:{port}  (Zugang nur ueber das App-Fenster)")
    print("=" * 58)

    import uvicorn

    if args.reload and not getattr(sys, "frozen", False):
        security.write_runtime(DATA_DIR, host, port, build_fingerprint())
        try:
            uvicorn.run("backend.main:app", host=host, port=port, reload=True,
                        log_level="warning", access_log=False)
        finally:
            security.clear_runtime(DATA_DIR)
        return

    from backend.main import app

    einstellungen = uvicorn.Config(app, host=host, port=port,
                                   log_level="warning", access_log=False)
    server = uvicorn.Server(einstellungen)
    # Die Signalbehandlung gehoert dem Hauptthread, in dem gleich das Fenster laeuft.
    server.install_signal_handlers = lambda: None
    dienst = threading.Thread(target=server.run, name="server", daemon=True)
    dienst.start()

    for _ in range(200):
        if server.started or not dienst.is_alive():
            break
        time.sleep(0.05)
    if not server.started:
        melden("Der lokale Server konnte nicht gestartet werden. "
               "Details stehen in data/logs/app.log.")
        raise SystemExit(1)

    security.write_runtime(DATA_DIR, host, port, build_fingerprint())
    try:
        eigenes_fenster = False
        if not args.no_browser and config.server.open_browser:
            eigenes_fenster = desktop.zeigen(security.start_url(host, port),
                                             DATA_DIR / "fenster")
        if not eigenes_fenster:
            # Ohne eigenes Fenster laeuft der Server weiter, bis Strg+C kommt.
            print("  Beenden mit Strg+C")
            try:
                while dienst.is_alive():
                    time.sleep(0.5)
            except KeyboardInterrupt:
                pass
    finally:
        server.should_exit = True
        dienst.join(timeout=15)
        security.clear_runtime(DATA_DIR)


if __name__ == "__main__":
    main()
