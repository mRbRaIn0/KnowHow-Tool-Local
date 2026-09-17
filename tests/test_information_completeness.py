import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from backend import attachments
from backend.config import Profile
from backend.database import Database
from backend.routers import chat
from backend.tools import BASE_INSTRUCTIONS, clean_generated_text


def test_old_user_details_survive_long_assistant_answers(tmp_path):
    db = Database(tmp_path / 'chat.db')
    try:
        work = db.create_chat('Wissen', 'local', 'vault')
        inputs = [
            'Kennung ABC-731, Spannung 24 V. Nicht bei Frost einschalten.',
            'Ausnahme: Im Wartungsmodus nur 12 V; Link https://example.org/handbuch.',
            'Korrektur: Die Kennung lautet ABC-732. Die Spannungen bleiben gleich.',
            'Erstelle daraus eine vollständig strukturierte Notiz.',
        ]
        for text in inputs[:-1]:
            db.add_message(work['id'], 'user', text)
            db.add_message(work['id'], 'assistant', 'Lange Erklärung ' * 1000)
        db.add_message(work['id'], 'user', inputs[-1])
        history = chat._build_history(db, work['id'], 'System', max_chars=1000,
                                      preserve_user_inputs=True)
        assert [m['content'] for m in history if m['role'] == 'user'] == inputs
        assert 'Lange Erklärung' not in json.dumps(history)
        assert len(db.list_messages(work['id'])) == 7
    finally:
        db.close()


def test_user_input_over_budget_is_explicit_instead_of_partial(tmp_path):
    db = Database(tmp_path / 'chat.db')
    try:
        work = db.create_chat('Wissen', 'local', 'vault')
        db.add_message(work['id'], 'user', 'A' * 600)
        db.add_message(work['id'], 'user', 'B' * 600)
        with pytest.raises(chat.UserInputContextTooLarge, match='vollständig im Chat gespeichert'):
            chat._build_history(db, work['id'], '', max_chars=1000, preserve_user_inputs=True)
        assert [m['content'] for m in db.list_messages(work['id'])] == ['A' * 600, 'B' * 600]
    finally:
        db.close()


def test_context_limit_stream_persists_all_input_and_skips_model(tmp_path, monkeypatch):
    profile = Profile(id='test', name='Test', vault={'path': str(tmp_path)})
    db = Database(tmp_path / 'chat.db')
    model = AsyncMock()
    model.capabilities.return_value = ['tools']
    monkeypatch.setattr(chat, 'current_profile', lambda: profile)
    monkeypatch.setattr(chat, 'current_db', lambda profile=None: db)
    monkeypatch.setattr(chat, 'current_ollama', lambda profile=None: model)
    monkeypatch.setattr(attachments, 'UPLOAD_DIR', tmp_path / 'uploads')
    search = AsyncMock(side_effect=AssertionError('No expensive search after context limit'))
    monkeypatch.setattr(chat, 'hybrid_search', search)
    async def run():
        work = db.create_chat('Wissen', 'local', 'vault')
        original = 'Sachinformation ' * 1500
        db.add_message(work['id'], 'user', original)
        response = await chat.send_message(work['id'], chat.MessageRequest(preview_writes=False,
            content='Erstelle daraus eine vollständige Notiz.'))
        events = [json.loads(item[6:]) async for item in response.body_iterator]
        assert events[-1]['kind'] == 'context_full'
        assert db.list_messages(work['id'])[0]['content'] == original
        assert 'Kontextgröße' in db.list_messages(work['id'])[-1]['content']
        model.chat_stream.assert_not_called()
        search.assert_not_called()
        assert not list(tmp_path.glob('**/Neue*.md'))
    try:
        asyncio.run(run())
    finally:
        db.close()


@pytest.mark.parametrize('text', [
    'Diese Notiz basiert auf der PDF Wartung.pdf. Die Anlage benötigt 24 V.',
    'Diese Dokumentation beruht auf den bereitgestellten Dateien; Ausnahme: kein Betrieb bei Frost.',
    'Diese Notiz basiert ausschließlich auf den angehängten PDFs und Bildern. Kennung: ABC-732.',
    '> Diese Notiz basiert ausschließlich auf den angehängten PDFs und Bildern.',
    '```text\nDiese Notiz basiert ausschließlich auf den angehängten PDFs und Bildern.\n\n\nWert: 12\n```',
    '````markdown\n```text\nDiese Notiz basiert ausschließlich auf den angehängten PDFs und Bildern.\n```\n````',
])
def test_cleanup_never_discards_facts_quotes_or_code(text):
    assert clean_generated_text(text) == text


def test_only_generic_standalone_boilerplate_is_removed():
    assert clean_generated_text('*Diese Notiz basiert ausschließlich auf den angehängten PDFs und Bildern.*') == ''


def test_complete_information_policy_is_in_write_prompt(tmp_path):
    prompt = chat._system_prompt('', tmp_path)
    assert BASE_INSTRUCTIONS in prompt
    assert 'ALLE vom Nutzer' in prompt
    assert 'Spätere ausdrückliche Korrekturen' in prompt
    assert 'niemals erfinden' in prompt
    assert 'Abdeckung aller Nutzerangaben' in prompt


def test_compacted_assistant_keeps_confirmed_note_path(tmp_path):
    db = Database(tmp_path / 'chat.db')
    try:
        work = db.create_chat('Wissen', 'local', 'vault')
        db.add_message(work['id'], 'user', 'Kennung ABC-731.')
        db.add_message(work['id'], 'assistant', 'Lange Notiz ' * 1000, sources=[{
            'tool': 'notiz_erstellen', 'arguments': {'pfad': 'Projekt/Anlage.md'},
            'result': {'erstellt': 'Projekt/Anlage.md'}, 'ok': True}])
        db.add_message(work['id'], 'user', 'Ergänze dort: Versorgung 24 V.')
        history = chat._build_history(db, work['id'], '', max_chars=1000, preserve_user_inputs=True)
        text = json.dumps(history, ensure_ascii=False)
        assert 'ABC-731' in text and '24 V' in text and 'Projekt/Anlage.md' in text
        assert 'Lange Notiz' not in text
    finally:
        db.close()
