"""V1.4 Funktion C: Varianten vor größeren Änderungen."""
import asyncio
import json

import pytest
from fastapi import HTTPException

from backend import attachments
from backend.config import Profile
from backend.database import Database
from backend.routers import chat
from backend.vault_actions import last_action, undo_last


@pytest.fixture
def setup(tmp_path, monkeypatch):
    root = tmp_path / 'vault'
    (root / 'Projekt').mkdir(parents=True)
    (root / 'Projekt/Notiz.md').write_text('# Notiz\n\nalt\n', encoding='utf-8')
    monkeypatch.setattr(attachments, 'UPLOAD_DIR', tmp_path / 'uploads')
    profile = Profile(id='test', name='Test', vault={'path': str(root)})
    db = Database(tmp_path / 'app.db')
    calls = []

    class Model:
        async def capabilities(self, model):
            return ['thinking', 'tools']

        async def chat_stream(self, model, messages, **kwargs):
            calls.append({'messages': messages, **kwargs})
            system = messages[0]['content']
            label = next(word for word in ('STRIKT', 'STRUKTURIERT', 'ERWEITERT', 'ÜBERARBEITUNG')
                         if word in system)
            yield {'message': {'content': f'```markdown\n# Notiz\n\n{label}\n```'}, 'done': True}

    monkeypatch.setattr(chat, 'current_profile', lambda: profile)
    monkeypatch.setattr(chat, 'current_db', lambda profile=None: db)
    monkeypatch.setattr(chat, 'current_ollama', lambda profile=None: Model())
    monkeypatch.setattr(chat, 'current_vault', lambda profile=None: root)
    yield root, db, calls
    db.close()


def send(db, chat_id, **body):
    async def run():
        response = await chat.send_message(chat_id, chat.MessageRequest(preview_writes=False, **body))
        return [json.loads(item[6:]) async for item in response.body_iterator]
    return asyncio.run(run())


def test_three_variants_without_writing_then_apply_and_undo(setup):
    root, db, calls = setup
    work = db.create_chat('Work', 'm', 'vault')
    events = send(db, work['id'], content='Überarbeite [[Projekt/Notiz]] komplett.', variants=True)
    assert [e['title'] for e in events if e['type'] == 'variant_start'] == [
        'Variante 1 – Strikt', 'Variante 2 – Strukturiert', 'Variante 3 – Erweitert']
    step = next(e for e in events if e.get('tool') == 'varianten')
    assert [v['inhalt'] for v in step['result']['varianten']] == [
        '# Notiz\n\nSTRIKT\n', '# Notiz\n\nSTRUKTURIERT\n', '# Notiz\n\nERWEITERT\n']
    assert step['result']['ziel'] == 'Projekt/Notiz.md' and not step['result']['neu']
    assert (root / 'Projekt/Notiz.md').read_text(encoding='utf-8') == '# Notiz\n\nalt\n'
    assert all(call.get('tools') is None and call['think'] is False for call in calls)
    assert 'alt' in calls[0]['messages'][1]['content']
    assert events[-1]['type'] == 'done' and events[-1]['changed_files'] == []

    result = asyncio.run(chat.apply_variant(work['id'], chat.VariantApply(
        message_id=step['result']['message_id'], index=1)))
    assert result == {'path': 'Projekt/Notiz.md', 'overwritten': True}
    assert (root / 'Projekt/Notiz.md').read_text(encoding='utf-8') == '# Notiz\n\nSTRUKTURIERT\n'
    assert 'übernommen' in db.list_messages(work['id'])[-1]['content']
    assert last_action(root, db.path.parent)
    undo_last(root, db.path.parent)
    assert (root / 'Projekt/Notiz.md').read_text(encoding='utf-8') == '# Notiz\n\nalt\n'

    (root / 'Projekt/Notiz.md').write_text('extern geändert', encoding='utf-8')
    with pytest.raises(HTTPException) as conflict:
        asyncio.run(chat.apply_variant(work['id'], chat.VariantApply(
            message_id=step['result']['message_id'], index=0)))
    assert conflict.value.status_code == 409
    assert (root / 'Projekt/Notiz.md').read_text(encoding='utf-8') == 'extern geändert'


def test_new_note_variant_is_numbered_and_can_be_refined(setup):
    root, db, calls = setup
    work = db.create_chat('Work', 'm', 'vault')
    events = send(db, work['id'], content='Erstelle eine Notiz über Docker Volumes.', variants=True)
    step = next(e for e in events if e.get('tool') == 'varianten')
    target = step['result']['ziel']
    assert target.startswith('02 KI-Notizen/') and step['result']['neu']
    first = asyncio.run(chat.apply_variant(work['id'], chat.VariantApply(
        message_id=step['result']['message_id'], index=0)))
    second = asyncio.run(chat.apply_variant(work['id'], chat.VariantApply(
        message_id=step['result']['message_id'], index=2, content='# Eigen\n')))
    assert first['path'] == target
    assert second['path'] == target[:-3] + '1.md'
    assert (root / second['path']).read_text(encoding='utf-8') == '# Eigen\n'

    calls.clear()
    events = send(db, work['id'], content='Mach sie kürzer.',
                  variant_base={'message_id': step['result']['message_id'], 'index': 1})
    refined = next(e for e in events if e.get('tool') == 'varianten')
    assert [v['titel'] for v in refined['result']['varianten']] == ['Überarbeitete Fassung']
    # Zuletzt übernommen wurde second['path']: genau diese Notiz wird ersetzt, keine weitere Kopie.
    assert refined['result']['ziel'] == second['path'] and not refined['result']['neu']
    assert len(calls) == 1 and 'STRUKTURIERT' in calls[0]['messages'][1]['content']
    assert 'Mach sie kürzer.' in calls[0]['messages'][1]['content']
    replaced = asyncio.run(chat.apply_variant(work['id'], chat.VariantApply(
        message_id=refined['result']['message_id'], index=0)))
    assert replaced == {'path': second['path'], 'overwritten': True}
    assert (root / second['path']).read_text(encoding='utf-8') == '# Notiz\n\nÜBERARBEITUNG\n'
    assert not (root / (target[:-3] + '2.md')).exists()


def test_simple_messages_ignore_variant_switch(setup):
    root, db, calls = setup
    work = db.create_chat('Work', 'm', 'vault')

    async def plain(model, messages, **kwargs):
        calls.append(kwargs)
        yield {'message': {'content': 'Bitte nutze Wissen fragen.'}, 'done': True}
    chat.current_ollama().__class__.chat_stream = staticmethod(plain)
    events = send(db, work['id'], content='Hallo, wie geht es?', variants=True)
    assert not any(e['type'] == 'variant_start' for e in events)
