"""Eigenes App-Fenster statt Systembrowser.

Warum überhaupt: Im Systembrowser läuft die Oberfläche in derselben
Umgebung wie jede andere geöffnete Webseite. Ein eigenes Fenster hat keine
Tabs, keine Erweiterungen und keine fremden Seiten daneben — die gesamte
Klasse browserseitiger Angriffe auf eine lokale App entfällt damit.

Drei Stufen, absteigend nach Güte:

1. **WebView2** über pywebview — ein echtes Fenster ohne Adresszeile.
2. **Edge/Chrome im App-Modus** mit eigenem Profilordner. Sieht aus wie ein
   Fenster, teilt sich aber nichts mit dem normalen Browserprofil.
3. **Normaler Browser** — nur, wenn nichts anderes verfügbar ist.
"""
from __future__ import annotations

import os
import subprocess
import sys
import webbrowser
from pathlib import Path
from typing import Optional

TITEL = "KnowHow Tool"
BREITE, HOEHE = 1280, 860


def zeigen(url: str, profil_ordner: Path) -> bool:
    """Öffnet die Oberfläche und kehrt zurück, wenn sie geschlossen wurde.

    ``False`` heißt: es ließ sich nur ein normaler Browser öffnen. Der
    Aufrufer muss dann selbst auf das Ende warten (Strg+C).
    """
    if _webview_fenster(url):
        return True
    prozess = _browser_fenster(url, profil_ordner)
    if prozess is not None:
        try:
            prozess.wait()
        except KeyboardInterrupt:
            pass
        return True
    webbrowser.open(url)
    return False


def _webview_fenster(url: str) -> bool:
    try:
        import webview
    except ImportError:
        return False
    try:
        webview.create_window(TITEL, url, width=BREITE, height=HOEHE,
                              min_size=(940, 620), fullscreen=False, maximized=True,
                              text_select=True)
        # private_mode: nichts wird auf die Platte geschrieben. Der
        # Sitzungsschlüssel lebt im Arbeitsspeicher und stirbt mit dem Fenster.
        webview.start(private_mode=True)
        return True
    except Exception as exc:  # kein WebView2, kein .NET, kein Desktop
        print(f"  Fenster:  WebView2 nicht verfügbar ({exc.__class__.__name__})")
        return False


def _browser_fenster(url: str, profil_ordner: Path) -> Optional[subprocess.Popen]:
    """Edge oder Chrome im App-Modus, mit eigenem, leerem Profil."""
    if sys.platform != "win32":
        return None
    programm = browser_programm()
    if not programm:
        return None
    try:
        profil_ordner.mkdir(parents=True, exist_ok=True)
        return subprocess.Popen([
            programm,
            f"--app={url}",
            f"--user-data-dir={profil_ordner}",
            "--start-maximized",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-extensions",
        ])
    except OSError:
        return None


def browser_programm() -> str:
    kandidaten = [
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Microsoft/Edge/Application/msedge.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Google/Chrome/Application/chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Google/Chrome/Application/chrome.exe",
    ]
    for kandidat in kandidaten:
        if kandidat.is_file():
            return str(kandidat)
    return ""
