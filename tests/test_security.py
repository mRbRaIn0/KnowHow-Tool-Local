"""Zugangsschutz: Sitzungsschlüssel, Host- und Ursprungsprüfung.

Diese Tests halten die drei Kontrollen fest, die eine lokal lauschende App
von jeder Webseite im selben Browser trennen. Fällt eine davon aus, ist der
gesamte Vault über den Browser des Nutzers erreichbar.

Geprüft wird die echte Middleware aus backend.main, aber vor harmlosen
Platzhalter-Routen mit den Pfaden der wirklich betroffenen Endpunkte. So
berührt der Test weder Konfiguration noch Vault noch Datenbank.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import main, security  # noqa: E402

SCHLUESSEL = security.SESSION_TOKEN
FREMD = "https://beispiel-angreifer.test"

# Genau die Endpunkte, die früher ohne Rumpf und damit ohne Vorabprüfung des
# Browsers von jeder fremden Seite auslösbar waren.
SCHREIBENDE_PFADE = [
    "/api/templates/install",
    "/api/backups",
    "/api/knowledge/reindex",
    "/api/settings/profiles/privat/activate",
    "/api/system/browse-folder",
]


@pytest.fixture()
def client():
    pruefstand = FastAPI()
    pruefstand.middleware("http")(main.security_headers)
    pruefstand.get("/api/health")(main.health)
    pruefstand.get("/")(main.index)

    @pruefstand.get("/api/settings")
    async def settings():
        return {"vault": "geheimer-pfad"}

    for pfad in SCHREIBENDE_PFADE:
        pruefstand.post(pfad)(lambda: {"ausgefuehrt": True})

    # base_url mit lokalem Host: der Standard "testserver" wird von der
    # Host-Pruefung zu Recht abgewiesen.
    with TestClient(pruefstand, base_url="http://127.0.0.1") as verbindung:
        yield verbindung


# ------------------------------------------------------- Sitzungsschlüssel

def test_ohne_schluessel_keine_daten(client):
    antwort = client.get("/api/settings")
    assert antwort.status_code == 403
    assert "geheimer-pfad" not in antwort.text


def test_lebenszeichen_bleibt_offen(client):
    """Der zweite Start muss eine laufende Instanz erkennen können."""
    antwort = client.get("/api/health")
    assert antwort.status_code == 200
    assert antwort.json()["app"] == "KnowHow Tool"
    assert SCHLUESSEL not in antwort.text


def test_app_symbol_bleibt_offen(client):
    """Der Browser holt das Symbol, bevor er das Cookie hat. Es gehört zum
    Programm — würde es abgewiesen, bliebe das Fenster ohne Symbol."""
    assert security.OPEN_PATHS >= {"/favicon.ico", "/assets/favicon.svg"}


def test_schluessel_als_kopfzeile(client):
    antwort = client.get("/api/settings", headers={security.HEADER_NAME: SCHLUESSEL})
    assert antwort.status_code == 200


def test_falscher_schluessel_wird_abgewiesen(client):
    antwort = client.get("/api/settings", headers={security.HEADER_NAME: "x" * 43})
    assert antwort.status_code == 403


def test_startadresse_setzt_cookie_und_traegt_danach(client):
    antwort = client.get(f"/?{security.QUERY_NAME}={SCHLUESSEL}")
    assert antwort.status_code == 200
    gesetzt = antwort.headers["set-cookie"].lower()
    # Nur mit striktem SameSite bleibt das Cookie fremden Seiten fern,
    # nur mit HttpOnly kommt kein Skript daran.
    assert "samesite=strict" in gesetzt and "httponly" in gesetzt
    # Der Client hat das Cookie übernommen; Folgeanfragen brauchen nichts mehr.
    assert client.get("/api/settings").status_code == 200


def test_veraltetes_cookie_blockiert_den_neustart_nicht(client):
    """Cookies gelten portübergreifend: nach einem Neustart trägt der Browser
    noch den Schlüssel der vorigen Sitzung. Der frische aus der Startadresse
    muss gewinnen, sonst bleibt die App nach jedem zweiten Start zu."""
    client.cookies.set(security.COOKIE_NAME, "alter-schluessel-aus-vorheriger-sitzung")
    antwort = client.get(f"/?{security.QUERY_NAME}={SCHLUESSEL}")
    assert antwort.status_code == 200
    assert client.get("/api/settings").status_code == 200


def test_startseite_ohne_schluessel_erklaert_sich(client):
    antwort = client.get("/")
    assert antwort.status_code == 403
    assert "Sitzungsschlüssel" in antwort.text


# ------------------------------------------------------------ DNS-Rebinding

def test_fremder_host_wird_abgewiesen(client):
    """Zeigt eine fremde Domain auf 127.0.0.1, gilt sie dem Browser als
    gleicher Ursprung. Nur der Host-Header verrät es dann noch."""
    antwort = client.get("/api/health", headers={"Host": "beispiel-angreifer.test"})
    assert antwort.status_code == 403


def test_lokale_hosts_sind_erlaubt(client):
    for host in ("127.0.0.1:5000", "localhost:8080", "[::1]:5000"):
        antwort = client.get("/api/health", headers={"Host": host})
        assert antwort.status_code == 200, host


# --------------------------------------------------------------------- CSRF

def test_schutz_gilt_fuer_alle_bereiche_nicht_nur_die_bibliothek(client):
    """Alle schreibenden API-Routen müssen fremde Ursprünge abweisen."""
    client.get(f"/?{security.QUERY_NAME}={SCHLUESSEL}")          # Cookie holen
    for pfad in SCHREIBENDE_PFADE:
        antwort = client.post(pfad, headers={"Origin": FREMD})
        assert antwort.status_code == 403, pfad
        assert "ausgefuehrt" not in antwort.text, pfad


def test_eigener_ursprung_darf_schreiben(client):
    client.get(f"/?{security.QUERY_NAME}={SCHLUESSEL}")
    antwort = client.post("/api/backups", headers={"Origin": "http://127.0.0.1"})
    assert antwort.status_code == 200
    assert antwort.json() == {"ausgefuehrt": True}


def test_schreiben_ohne_schluessel_bleibt_verwehrt(client):
    """Der Ursprung allein genügt nicht — der Schlüssel muss ebenfalls stimmen."""
    antwort = client.post("/api/backups", headers={"Origin": "http://127.0.0.1"})
    assert antwort.status_code == 403


# ------------------------------------------------------------ Laufzeitdatei

def test_laufzeitdatei_wird_geschrieben_und_geraeumt(tmp_path):
    security.write_runtime(tmp_path, "127.0.0.1", 51234, "src-1")
    gelesen = security.read_runtime(tmp_path)
    assert gelesen["port"] == 51234
    assert gelesen["token"] == SCHLUESSEL
    security.clear_runtime(tmp_path)
    assert security.read_runtime(tmp_path) is None


def test_fremde_laufzeitdatei_bleibt_liegen(tmp_path):
    """Eine zweite Instanz darf den Wegweiser der ersten nicht löschen."""
    import os

    security.write_runtime(tmp_path, "127.0.0.1", 51234, "src-1")
    pfad = security.runtime_path(tmp_path)
    pfad.write_text(pfad.read_text(encoding="utf-8").replace(
        f'"pid": {os.getpid()}', '"pid": 999999'), encoding="utf-8")
    security.clear_runtime(tmp_path)
    assert security.read_runtime(tmp_path) is not None
