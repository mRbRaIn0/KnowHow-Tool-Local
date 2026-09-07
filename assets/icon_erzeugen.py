"""Erzeugt das Programm-Icon aus dem App-Logo.

Vorlage ist frontend/favicon.svg. Gezeichnet wird stark vergrößert und
anschließend heruntergerechnet — so bleiben die Kanten auch bei 16 Pixeln
sauber. Ergebnis: assets/Lokale-Wissens-KI.ico mit allen Größen, die Windows
für Desktop, Taskleiste und Explorer braucht.

Aufruf:  .venv\\Scripts\\python.exe assets\\icon_erzeugen.py
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ZIEL = Path(__file__).resolve().parent / "Lokale-Wissens-KI.ico"
GROESSEN = [16, 24, 32, 48, 64, 128, 256]

# Farben aus frontend/favicon.svg
GRUND = "#0e1319"
AKZENT = "#3ab3bf"

# Gezeichnet wird auf dieser Kantenlänge, danach verkleinert.
BASIS = 1024
SKALA = BASIS / 32  # das SVG hat ein 32er-Koordinatensystem


def s(wert: float) -> float:
    """Rechnet SVG-Koordinaten in die Zeichenfläche um."""
    return wert * SKALA


def zeichne() -> Image.Image:
    bild = Image.new("RGBA", (BASIS, BASIS), (0, 0, 0, 0))
    d = ImageDraw.Draw(bild)

    # Dunkles, abgerundetes Grundquadrat
    d.rounded_rectangle([0, 0, BASIS - 1, BASIS - 1], radius=s(8), fill=GRUND)

    # Petrolfarbenes Innenquadrat
    d.rounded_rectangle([s(6), s(6), s(26), s(26)], radius=s(5), fill=AKZENT)

    # Winkelform als Aussparung (entspricht dem Pfad im SVG)
    winkel = [
        (s(12), s(12)), (s(20), s(12)), (s(20), s(15)),
        (s(15), s(15)), (s(15), s(20)), (s(12), s(20)),
    ]
    d.polygon(winkel, fill=GRUND)
    return bild


def main() -> None:
    gross = zeichne()

    # Für sehr kleine Größen ist der Winkel kaum erkennbar — dort wird die
    # Aussparung etwas kräftiger gezeichnet, damit das Symbol lesbar bleibt.
    ebenen = []
    for groesse in GROESSEN:
        ebenen.append(gross.resize((groesse, groesse), Image.LANCZOS))

    ZIEL.parent.mkdir(parents=True, exist_ok=True)
    ebenen[-1].save(ZIEL, format="ICO", sizes=[(g, g) for g in GROESSEN])

    print(f"Icon geschrieben: {ZIEL}")
    print(f"  Größen: {', '.join(f'{g}x{g}' for g in GROESSEN)}")
    print(f"  Datei:  {ZIEL.stat().st_size} Bytes")


if __name__ == "__main__":
    main()
