import asyncio
import json
import time

import pytest

from backend import attachments
from backend.config import Profile
from backend.database import Database
from backend.file_actions import FileAction, parse_file_action, resolve_file, execute_file_action
from backend.routers import chat
from backend.tools import ToolRunner
from backend.vault import VaultError
from backend.vault_actions import VaultAction, active_action, undo_last
from backend.write_preview import pending


@pytest.mark.parametrize('prompt,action,file,content', [
    ('Füge diesen Text zu `SPS/delete2.md` hinzu:\n# Fertig\n\n**Wert**: 42\n', 'append', 'SPS/delete2.md', '# Fertig\n\n**Wert**: 42\n'),
    ('Bitte hänge den Text an delete2.md an: Hallo', 'append', 'delete2.md', 'Hallo'),
    ('Ergänze die Datei "SPS/Meine Notiz.md" mit folgendem Text:\nHallo', 'append', 'SPS/Meine Notiz.md', 'Hallo'),
    ('Erstelle `Neu.md`: Fertiger Text', 'create', 'Neu.md', 'Fertiger Text'),
    ('Erstelle Neu.md.', 'create', 'Neu.md', None),
    ('Lösche die Datei delete2.md.', 'delete', 'delete2.md', None),
    ('Finde [[SPS/delete2]]', 'find', 'SPS/delete2', None),
    ('Benenne delete2.md in Neu.md um', 'rename', 'delete2.md', None),
    ('Verschiebe delete2.md in den Ordner "SPS/Archiv"', 'move', 'delete2.md', None),
])
def test_literal_parser(prompt, action, file, content):
    plan = parse_file_action(prompt)
    assert plan is not None
    assert (plan.action, plan.file, plan.content) == (action, file, content)


@pytest.mark.parametrize('prompt', [
    'Erstelle eine Notiz', 'Erstelle eine Zusammenfassung', 'Lösche alle Dateien',
    'Lösche A.md und B.md', 'Füge eine Zusammenfassung zu A.md hinzu',
    'Wie lösche ich A.md?', 'Erstelle A.md über Steuerungen',
])
def test_freeform_never_guessed(prompt):
    assert parse_file_action(prompt) is None


def put(root, path, content=''):
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding='utf-8')
    return target


def test_exact_priority_and_empty_files(tmp_path):
    put(tmp_path, 'SPS/delete2.md')
    put(tmp_path, 'SPS/delete21.md', 'do not touch')
    assert resolve_file(tmp_path, 'delete2').matches == ['SPS/delete2.md']
    assert resolve_file(tmp_path, 'SPS/delete2.md').matches == ['SPS/delete2.md']
    put(tmp_path, 'Other/delete2.md')
    assert len(resolve_file(tmp_path, 'delete2.md').matches) == 2
    assert resolve_file(tmp_path, 'delete2.md', 'SPS').matches == ['SPS/delete2.md']
    assert resolve_file(tmp_path, 'Missing/delete2.md').matches == []
    put(tmp_path, 'delete2.md')
    assert resolve_file(tmp_path, 'delete2.md').matches == ['delete2.md']
    put(tmp_path, 'exact')
    put(tmp_path, 'SPS/exact.md')
    assert resolve_file(tmp_path, 'exact').matches == ['exact']


def test_append_preserves_literal_and_missing_creates_exact(tmp_path):
    target = put(tmp_path, 'SPS/delete2.md')
    other = put(tmp_path, 'SPS/delete21.md', 'unchanged')
    runner = ToolRunner(tmp_path, defer_guide=True)
    literal = '# Titel\n\n😃 **Fett**\n[Link](relative.md)\n  Ende  \n'
    execute_file_action(runner, FileAction('append', 'SPS/delete2.md', content=literal))
    assert target.read_text(encoding='utf-8') == literal
    assert other.read_text() == 'unchanged'
    execute_file_action(runner, FileAction('append', 'Missing/delete2.md', content='Neu'))
    assert (tmp_path / 'Missing/delete2.md').read_text() == 'Neu'
    assert not (tmp_path / 'SPS/delete22.md').exists()
    assert ToolRunner(tmp_path)._vault_suchen('delete21.md')['exakt']


@pytest.mark.parametrize('action,destination,new_path', [
    ('rename', 'Neu.md', 'SPS/Neu.md'),
    ('move', 'Archiv', 'Archiv/delete2.md'),
    ('delete', '', None),
])
def test_file_actions_undo_and_links(tmp_path, action, destination, new_path):
    root = tmp_path / 'vault'
    source = put(root, 'SPS/delete2.md', '[PDF](./manual.pdf)\n')
    put(root, 'SPS/manual.pdf', 'fake')
    links = put(root, 'Index.md', '[[SPS/delete2#Abschnitt|Gerät]]\n[[delete2]]\n')
    originals = (source.read_bytes(), links.read_bytes())
    journal = VaultAction(root, tmp_path / 'data', 'chat')
    token = active_action.set(journal)
    try:
        execute_file_action(ToolRunner(root), FileAction(action, 'SPS/delete2.md', destination=destination))
        journal.finish()
    finally:
        active_action.reset(token)
    assert not source.exists()
    if new_path:
        assert 'SPS/manual.pdf' in (root / new_path).read_text()
        assert new_path + '#Abschnitt|Gerät' in links.read_text(encoding='utf-8')
        assert '[[' + new_path + ']]' in links.read_text(encoding='utf-8')
    assert undo_last(root, tmp_path / 'data')['undone']
    assert (source.read_bytes(), links.read_bytes()) == originals
    if new_path:
        assert not (root / new_path).exists()


def test_no_overwrite_or_escape(tmp_path):
    put(tmp_path, 'A.md', 'A')
    put(tmp_path, 'B.md', 'B')
    runner = ToolRunner(tmp_path)
    execute_file_action(runner, FileAction('create', 'A.md', content='new'))
    assert (tmp_path / 'A.md').read_text() == 'A'
    with pytest.raises(VaultError):
        execute_file_action(runner, FileAction('rename', 'A.md', destination='B.md'))
    with pytest.raises(VaultError):
        execute_file_action(runner, FileAction('delete', '../outside.md'))
    assert not (tmp_path / 'A1.md').exists()


def test_model_append_cannot_create_numbered_replacement(tmp_path):
    from backend.context_focus import VaultFocus
    put(tmp_path, 'SPS/delete2.md')
    runner = ToolRunner(tmp_path, update_only=True, focus=VaultFocus(('SPS/delete2.md',)), defer_guide=True)
    assert 'fehler' in runner._notiz_erstellen('SPS/delete2.md', 'wrong')
    assert 'fehler' in runner._notiz_erstellen('SPS/delete21.md', 'wrong')
    assert runner._notiz_ergaenzen('delete2.md', 'correct')['ergaenzt'] == 'SPS/delete2.md'
    assert not (tmp_path / 'SPS/delete21.md').exists()


def test_stream_keepalive_and_timings_without_logging_content(monkeypatch, caplog):
    import httpx
    import logging
    from backend.ollama_client import OllamaClient
    seen = []
    def handle(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, text=json.dumps({'message': {'content': 'PRIVATE'}}) + '\n' +
                              json.dumps({'done': True, 'load_duration': 123, 'eval_count': 1}) + '\n')
    client = OllamaClient('http://localhost:11434', keep_alive='15m')
    monkeypatch.setattr(client, '_client', lambda: httpx.AsyncClient(transport=httpx.MockTransport(handle), base_url=client.base_url))
    async def run():
        return [chunk async for chunk in client.chat_stream('model', [{'role': 'user', 'content': 'SECRET'}])]
    with caplog.at_level(logging.INFO):
        chunks = asyncio.run(run())
    assert chunks[0]['message']['content'] == 'PRIVATE'
    assert seen[0]['stream'] is True and seen[0]['keep_alive'] == '15m'
    assert 'load_duration' in caplog.text and 'first_output_ms' in caplog.text
    assert 'PRIVATE' not in caplog.text and 'SECRET' not in caplog.text


@pytest.fixture
def direct_chat(tmp_path, monkeypatch):
    root = tmp_path / 'vault'
    root.mkdir()
    profile = Profile(id='test', name='Test', vault={'path': str(root)})
    db = Database(tmp_path / 'app.db')
    monkeypatch.setattr(attachments, 'UPLOAD_DIR', tmp_path / 'uploads')
    monkeypatch.setattr(chat, 'current_profile', lambda: profile)
    monkeypatch.setattr(chat, 'current_db', lambda profile=None: db)
    for name in ('current_ollama', 'hybrid_search', 'guide_context', 'resolve_focus', '_build_history'):
        monkeypatch.setattr(chat, name, lambda *a, **kw: pytest.fail('Direct I/O must not call model, search, guide or history'))
    work = db.create_chat('Direct', 'local', 'vault')
    yield root, db, work['id']
    db.close()


def test_chat_offline_ambiguity_followup_and_empty_exact(direct_chat):
    root, db, chat_id = direct_chat
    put(root, 'SPS/delete2.md')
    put(root, 'Other/delete2.md', 'other')
    put(root, 'SPS/delete21.md', 'wrong')
    async def send(prompt):
        response = await chat.send_message(chat_id, chat.MessageRequest(content=prompt, preview_writes=False))
        return [json.loads(item[6:]) async for item in response.body_iterator]
    async def run():
        events = await send('Füge diesen Text zu delete2.md hinzu: **Original**')
        assert 'In welchem Ordner' in events[-1]['content']
        assert events[-1]['changed_files'] == []
        events = await send('Ordner SPS')
        assert events[-1]['changed_files'] == ['SPS/delete2.md']
        assert (root / 'SPS/delete2.md').read_text() == '**Original**'
        assert (root / 'Other/delete2.md').read_text() == 'other'
        assert (root / 'SPS/delete21.md').read_text() == 'wrong'
        start = time.perf_counter()
        events = await send('Füge diesen Text zu `SPS/delete2.md` hinzu: Zweiter Absatz')
        print(f'Exact append end-to-end: {(time.perf_counter()-start)*1000:.1f} ms')
        assert events[-1]['type'] == 'done'
        assert (root / 'SPS/delete2.md').read_text() == '**Original**\n\nZweiter Absatz'
    asyncio.run(run())


@pytest.mark.parametrize('accept', [True, False])
def test_direct_preview_literal_and_cancel(direct_chat, accept):
    root, db, chat_id = direct_chat
    target = put(root, 'SPS/delete2.md')
    async def run():
        response = await chat.send_message(chat_id, chat.MessageRequest(
            content='Füge diesen Text zu `SPS/delete2.md` hinzu: [Link](relative.md)', preview_writes=True))
        events = []
        async for item in response.body_iterator:
            event = json.loads(item[6:])
            events.append(event)
            if event['type'] == 'write_preview':
                assert target.read_text() == ''
                assert event['preview']['path_locked']
                pending[('test', chat_id)]['future'].set_result({'accept': accept})
        assert events[-1]['type'] == ('done' if accept else 'error')
    asyncio.run(run())
    assert target.read_text() == ('[Link](relative.md)' if accept else '')


def test_move_failure_rolls_back_every_mutation(direct_chat, monkeypatch):
    from backend import file_actions
    root, db, chat_id = direct_chat
    target = put(root, 'SPS/delete2.md', 'original')
    link = put(root, 'Index.md', '[[SPS/delete2]]')
    def fail(*a, **kw):
        raise OSError('Simulierter Schreibfehler')
    monkeypatch.setattr(file_actions, 'write_text_file', fail)
    async def run():
        response = await chat.send_message(chat_id, chat.MessageRequest(content='Verschiebe `SPS/delete2.md` nach Archiv'))
        return [json.loads(item[6:]) async for item in response.body_iterator]
    events = asyncio.run(run())
    assert events[-1]['type'] == 'error'
    assert target.read_text() == 'original'
    assert link.read_text() == '[[SPS/delete2]]'
    assert not (root / 'Archiv/delete2.md').exists()
