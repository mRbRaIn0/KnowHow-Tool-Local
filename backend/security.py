"""Zugangsschutz der lokalen Oberfläche.

Die App hat bewusst keine Anmeldung — sie gehört einem Benutzer auf einem
Rechner. Trotzdem lauscht sie auf einem TCP-Port, und ein Port ist von jeder
Webseite im selben Browser erreichbar. Drei Kontrollen schließen das:

* **Sitzungsschlüssel** — bei jedem Start neu erzeugt. Nur wer ihn kennt,
  bekommt Daten. Das Fenster erhält ihn einmal über die Startadresse und
  danach als striktes Cookie; fremde Seiten kennen ihn nie.
* **Host-Prüfung** — schützt gegen DNS-Rebinding, bei dem eine fremde Domain
  auf 127.0.0.1 zeigt und dem Browser dadurch als gleicher Ursprung gilt.
* **Ursprungs-Prüfung** — weist jeden schreibenden Zugriff ab, der von einer
  anderen Seite ausgelöst wurde (CSRF).
"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from typing import Optional

COOKIE_NAME = "lka_sitzung"
HEADER_NAME = "X-LKA-Sitzung"
QUERY_NAME = "t"

# Diese Adressen dürfen im Host-Header stehen. Alles andere ist ein Hinweis
# darauf, dass die Anfrage über eine fremde Domain hereinkam.
LOCAL_HOSTNAMES = {"127.0.0.1", "localhost", "::1", "[::1]", "0.0.0.0"}

# Ohne Sitzungsschlüssel erreichbar: die Lebenszeichen-Antwort — sie verrät
# nichts über Inhalte und wird beim Start gebraucht, um eine bereits laufende
# Instanz zu erkennen — sowie das mitgelieferte App-Symbol. Browser fordern
# das Symbol an, bevor sie das Cookie aus der Startadresse übernommen haben;
# es ist Teil des Programms, keine Nutzerdatei.
OPEN_PATHS = {"/api/health", "/favicon.ico", "/assets/favicon.svg"}

SESSION_TOKEN = secrets.token_urlsafe(32)


def hostname_of(host_header: str) -> str:
    """Reiner Hostname aus einem Host-Header (Port und IPv6-Klammern weg)."""
    value = (host_header or "").strip()
    if not value:
        return ""
    if value.startswith("["):                      # [::1]:5000
        return value[: value.find("]") + 1].lower() if "]" in value else value.lower()
    return value.rsplit(":", 1)[0].lower() if ":" in value else value.lower()


def host_is_local(host_header: str) -> bool:
    """Fehlender Host ist kein Browser — nur ein gesetzter, fremder Host zählt."""
    name = hostname_of(host_header)
    return not name or name in LOCAL_HOSTNAMES


def token_matches(value: str) -> bool:
    return bool(value) and secrets.compare_digest(value, SESSION_TOKEN)


def request_is_authorised(request) -> bool:
    """Schlüssel aus Startadresse, Kopfzeile oder Cookie — eine Quelle genügt.

    Bewusst alle drei prüfen statt nur die erste vorhandene: Cookies gelten
    portübergreifend, also trägt der Browser nach einem Neustart noch den
    Schlüssel der vorigen Sitzung. Ohne diese Reihenfolge würde ausgerechnet
    das veraltete Cookie den frischen Schlüssel aus der Startadresse
    verdrängen und die App bliebe verschlossen.
    """
    return any(token_matches(wert) for wert in (
        request.query_params.get(QUERY_NAME),
        request.headers.get(HEADER_NAME),
        request.cookies.get(COOKIE_NAME),
    ))


def same_origin(request) -> bool:
    """Origin fehlt bei Nicht-Browser-Aufrufen; nur ein fremder zählt."""
    origin = request.headers.get("origin")
    if not origin:
        return True
    return origin == f"{request.url.scheme}://{request.url.netloc}"


def start_url(host: str, port: int) -> str:
    """Adresse, die das Fenster öffnet — mit dem Schlüssel dieser Sitzung."""
    return f"http://{host}:{port}/?{QUERY_NAME}={SESSION_TOKEN}"


# ------------------------------------------------------- Laufzeitdatei

def runtime_path(data_dir: Path) -> Path:
    return data_dir / "runtime.json"


def write_runtime(data_dir: Path, host: str, port: int, build: str) -> None:
    """Hält Port und Schlüssel fest, damit ein zweiter Start die laufende
    Instanz findet — bei zufälligem Port geht das sonst nicht."""
    data_dir.mkdir(parents=True, exist_ok=True)
    target = runtime_path(data_dir)
    payload = {"pid": os.getpid(), "host": host, "port": port,
               "token": SESSION_TOKEN, "build": build}
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(target)


def read_runtime(data_dir: Path) -> Optional[dict]:
    try:
        data = json.loads(runtime_path(data_dir).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and data.get("port") else None


def clear_runtime(data_dir: Path) -> None:
    """Nur die eigene Datei entfernen — eine fremde Instanz bleibt auffindbar."""
    existing = read_runtime(data_dir)
    if existing and existing.get("pid") not in (None, os.getpid()):
        return
    try:
        runtime_path(data_dir).unlink(missing_ok=True)
    except OSError:
        pass
