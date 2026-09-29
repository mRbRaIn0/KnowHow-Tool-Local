"""Gemeinsame Testeinstellungen."""
import pytest

from backend import i18n


@pytest.fixture(autouse=True)
def german_ui_by_default(monkeypatch):
    """Die Serversprache hängt an der echten Konfiguration; Tests laufen deterministisch auf Deutsch."""
    monkeypatch.setattr(i18n, 'language', lambda: 'de')
