"""Anhänge: Verbrauch je Eingabe und die Ausnahme 'nur ansehen'."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import attachments  # noqa: E402
from backend.workflow import analyse_request  # noqa: E402

CHAT = "abc123def456"


@pytest.fixture()
def chat_ordner(tmp_path, monkeypatch):
    """Isolierter Zwischenbereich, damit echte Uploads unberührt bleiben."""
    monkeypatch.setattr(attachments, "UPLOAD_DIR", tmp_path / "uploads")
    return tmp_path


def _ablegen(name: str, inhalt: bytes = b"x") -> None:
    attachments.store(CHAT, name, inhalt)


# ------------------------------------------------- Verbrauch je Eingabe

def test_neue_anhaenge_sind_offen(chat_ordner):
    _ablegen("a.png")
    _ablegen("b.pdf")
    assert [item["name"] for item in attachments.pending(CHAT)] == ["a.png", "b.pdf"]


def test_verwendete_anhaenge_verlassen_die_naechste_eingabe(chat_ordner):
    _ablegen("a.png")
    _ablegen("b.pdf")
    attachments.mark_used(CHAT, ["a.png", "b.pdf"])

    assert attachments.pending(CHAT) == []
    # Die Historie bleibt vollständig erhalten.
    assert [item["name"] for item in attachments.listing(CHAT)] == ["a.png", "b.pdf"]


def test_nur_die_neue_datei_ist_offen(chat_ordner):
    _ablegen("alt.png")
    attachments.mark_used(CHAT, ["alt.png"])
    _ablegen("neu.png")

    assert [item["name"] for item in attachments.pending(CHAT)] == ["neu.png"]


def test_verwaltungsdateien_tauchen_nicht_als_anhang_auf(chat_ordner):
    _ablegen("a.png")
    attachments.mark_used(CHAT, ["a.png"])
    attachments.save_cache(CHAT, {"a.png": "Beschreibung"})

    namen = [item["name"] for item in attachments.listing(CHAT)]
    assert namen == ["a.png"]


def test_obergrenze_gilt_je_eingabe(chat_ordner, monkeypatch):
    monkeypatch.setattr(attachments, "MAX_FILES", 2)
    _ablegen("1.png")
    _ablegen("2.png")
    with pytest.raises(attachments.AttachmentError):
        _ablegen("3.png")

    # Nach dem Abschicken ist wieder Platz, ohne dass etwas gelöscht wurde.
    attachments.mark_used(CHAT, ["1.png", "2.png"])
    _ablegen("3.png")
    assert [item["name"] for item in attachments.pending(CHAT)] == ["3.png"]
    assert len(attachments.listing(CHAT)) == 3


# ------------------------------------------- Ablegen: Regel und Ausnahme

@pytest.mark.parametrize("text", [
    "Schau dir den Screenshot nur an.",
    "Bild nicht hochladen.",
    "Nur analysieren, nicht einsortieren.",
    "Lies die PDF nur aus, ohne sie zu speichern.",
    "Werte das Bild nur aus.",
    "Nicht in den Vault speichern.",
    "Don't upload this, just look at it.",
])
def test_ausnahme_verhindert_ablage(text):
    ergebnis = analyse_request(text, ("bild.png",))
    assert ergebnis.keep_out_of_vault is True
    assert ergebnis.archive_attachments is False
    assert "NICHT in den Vault" in ergebnis.contract()


@pytest.mark.parametrize("text", [
    "Was zeigt der Screenshot?",
    "Erstelle eine Notiz dazu.",
    "Fasse die PDF zusammen.",
    "Lies die PDF und erstelle nur eine kurze Notiz.",
    "Sortiere die Dateien ein.",
])
def test_standard_legt_ab(text):
    ergebnis = analyse_request(text, ("bild.png",))
    assert ergebnis.archive_attachments is True
    assert ergebnis.keep_out_of_vault is False


def test_ohne_anhaenge_wird_nichts_abgelegt():
    ergebnis = analyse_request("Schau dir das nur an.", ())
    assert ergebnis.archive_attachments is False
    assert ergebnis.keep_out_of_vault is False
