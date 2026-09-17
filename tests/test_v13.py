import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import AsyncMock

import pytest

from backend import attachments, tools
from backend.config import AISettings, Profile
from backend.database import Database
from backend.markdown_knowledge import MARKDOWN_INSTRUCTIONS
from backend.routers import chat
from backend.tools import ToolRunner
from backend.vault import create_unique_file
from backend.vault_guide import GUIDE_PATH, INDEX_START, INDEX_END, guide_context
from backend.workflow import simple_attachment_archive


@pytest.mark.parametrize('prompt,target', [
    ('Datei schnell ablegen', ''),
    ('Lege die Dateien einfach ab.', ''),
    ('Speichere das Bild nicht', None),
    ('Speichere die Anhänge im Vault.', ''),
    ('Kopiere die Dateien in "Projekt/Dateien".', 'Projekt/Dateien'),
    ('Lege die Bilder im Ordner "Projekt/Dateien" ab.', 'Projekt/Dateien'),
    ('Lege die Bilder ab und erstelle eine Notiz.', None),
    ('Wie kann ich die Dateien speichern?', None),
    ('Sortiere die Bilder nach Inhalt ein.', None),
])
def test_only_unambiguous_archive_commands_bypass_model(prompt, target):
    assert simple_attachment_archive(prompt) == target


def test_concurrent_same_name_never_overwrites(tmp_path):
    def save(index):
        return create_unique_file(tmp_path, 'image.png', lambda out: out.write(bytes([index])))
    with ThreadPoolExecutor(max_workers=8) as pool:
        names = list(pool.map(save, range(12)))
    assert set(names) == {'image.png'} | {f'image{i}.png' for i in range(1, 12)}
    assert {(tmp_path / name).read_bytes() for name in names} == {bytes([i]) for i in range(12)}


def test_upload_and_vault_numbering_and_repeat_call(tmp_path, monkeypatch):
    monkeypatch.setattr(attachments, 'UPLOAD_DIR', tmp_path / 'uploads')
    for expected in ['image.png', 'image1.png', 'image2.png']:
        assert attachments.store('abcdef', 'image.png', b'original')['name'] == expected
    root = tmp_path / 'vault'
    root.mkdir()
    (root / 'image.png').write_bytes(b'keep')
    runner = ToolRunner(root, chat_id='abcdef', attachment_dir='.')
    result = runner._anhang_in_vault_ablegen('image.png')
    assert result['abgelegt'] == 'image1.png'
    assert result['einbetten_als'] == '![[image1.png]]'
    assert runner._anhang_in_vault_ablegen('image.png') == result
    assert not (root / 'image2.png').exists()
    assert (root / 'image.png').read_bytes() == b'keep'


def test_archive_without_ollama_analysis_or_search(tmp_path, monkeypatch):
    root = tmp_path / 'vault'
    root.mkdir()
    monkeypatch.setattr(attachments, 'UPLOAD_DIR', tmp_path / 'uploads')
    profile = Profile(id='test', name='Test', vault={'path': str(root)})
    db = Database(tmp_path / 'app.db')
    model = AsyncMock()
    model.capabilities.side_effect = AssertionError('No Ollama for pure copying')
    search = AsyncMock(side_effect=AssertionError('No search for pure copying'))
    monkeypatch.setattr(chat, 'current_profile', lambda: profile)
    monkeypatch.setattr(chat, 'current_db', lambda profile=None: db)
    monkeypatch.setattr(chat, 'current_ollama', lambda profile=None: model)
    monkeypatch.setattr(chat, 'hybrid_search', search)
    monkeypatch.setattr(chat, '_auswerten', lambda *args: pytest.fail('No analysis for copying'))
    async def run():
        work = db.create_chat('Work', 'local', 'vault')
        attachments.store(work['id'], 'image.png', b'image')
        response = await chat.send_message(work['id'], chat.MessageRequest(preview_writes=False,
            content='Lege die Dateien in "Projekt/Dateien" ab.'))
        events = [json.loads(item[6:]) async for item in response.body_iterator]
        assert events[1]['execution'] == 'direct'
        assert events[-1]['changed_files'] == ['Projekt/Dateien/image.png']
        assert 'Projekt/Dateien/image.png' in events[-1]['content']
        assert (root / 'Projekt/Dateien/image.png').read_bytes() == b'image'
        assert not attachments.pending(work['id'])
        assert attachments.load_cache(work['id']) == {}
    try:
        asyncio.run(run())
    finally:
        db.close()


def test_guide_context_preserves_rules_after_large_index_without_scanning(tmp_path, monkeypatch):
    from backend import vault_guide
    content = 'Emojis: Nein\n' + INDEX_START + '\n' + ('[[Long.md]]\n' * 5000) + INDEX_END + '\nMeine Regel am Ende'
    (tmp_path / GUIDE_PATH).write_text(content, encoding='utf-8')
    monkeypatch.setattr(vault_guide, 'build_vault_index', lambda _: pytest.fail('No scan on context read'))
    context = guide_context(tmp_path)
    assert 'Meine Regel am Ende' in context
    assert 'Emojis: Nein' in context
    assert len(context) < 100
    assert (tmp_path / GUIDE_PATH).read_text(encoding='utf-8') == content


def test_batch_defers_index_and_note_without_sources_avoids_scan(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(tools, 'ensure_vault_guide', lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(tools, 'iter_files', lambda *args, **kwargs: pytest.fail('No source scan without links'))
    runner = ToolRunner(tmp_path, defer_guide=True)
    for _ in range(3):
        assert 'erstellt' in runner._notiz_erstellen('Test.md', '# Test\n')
    assert calls == []
    runner.refresh_guide()
    assert len(calls) == 1
    assert runner.note_files == ['Test.md', 'Test1.md', 'Test2.md']


def test_history_keeps_current_task_and_paths_without_old_write_payload(tmp_path):
    db = Database(tmp_path / 'history.db')
    try:
        work = db.create_chat('History', 'local', 'vault')
        for _ in range(5):
            db.add_message(work['id'], 'user', 'Old ' * 1000)
            db.add_message(work['id'], 'assistant', 'Done.')
        db.add_message(work['id'], 'user', 'Erstelle Alpha')
        db.add_message(work['id'], 'assistant', 'Gespeichert', sources=[{
            'tool': 'notiz_erstellen', 'arguments': {'pfad': 'Alpha.md', 'inhalt': 'REPEATED' * 10000},
            'result': {'erstellt': 'Alpha.md'}, 'ok': True}])
        db.add_message(work['id'], 'user', 'Ergänze dort Beta')
        history = chat._build_history(db, work['id'], 'System', max_chars=1000)
        serialized = json.dumps(history)
        assert 'Alpha.md' in serialized
        assert 'REPEATED' not in serialized
        assert history[-1]['content'] == 'Ergänze dort Beta'
        assert len(serialized) < 1200
        assert len(db.list_messages(work['id'])) == 13
    finally:
        db.close()


def test_markdown_rules_are_available_offline_and_thinking_stays_optional(tmp_path):
    prompt = chat._system_prompt('', tmp_path)
    assert MARKDOWN_INSTRUCTIONS in prompt
    assert '[[Ordner/Notiz#^block-id]]' in prompt
    assert '| --- | --- |' in prompt
    assert AISettings().thinking is False
    assert AISettings(thinking=True).thinking is True


def test_malformed_historical_tool_arguments_do_not_break_followup():
    assert chat._history_fields('invalid model arguments', {'pfad'}) == {}
    assert chat._history_fields(None, {'pfad'}) == {}


def test_failed_copy_stays_pending_and_reports_no_success(tmp_path, monkeypatch):
    monkeypatch.setattr(attachments, 'UPLOAD_DIR', tmp_path / 'uploads')
    root = tmp_path / 'vault'
    root.mkdir()
    profile = Profile(id='test', name='Test', vault={'path': str(root)})
    db = Database(tmp_path / 'app.db')
    monkeypatch.setattr(chat, 'current_profile', lambda: profile)
    monkeypatch.setattr(chat, 'current_db', lambda profile=None: db)
    monkeypatch.setattr(chat, 'current_ollama', lambda profile=None: object())
    async def run():
        work = db.create_chat('Work', 'local', 'vault')
        attachments.store(work['id'], 'file.txt', b'keep')
        response = await chat.send_message(work['id'], chat.MessageRequest(preview_writes=False,
            content='Lege die Dateien in "../escape" ab.'))
        events = [json.loads(item[6:]) async for item in response.body_iterator]
        assert events[-1]['changed_files'] == []
        assert 'Nicht abgelegt' in events[-1]['content']
        assert attachments.pending(work['id'])[0]['name'] == 'file.txt'
        assert not (tmp_path / 'escape').exists()
    try:
        asyncio.run(run())
    finally:
        db.close()


@pytest.mark.parametrize('prompt,names', [
    ('Speichere das Bild', ['a.png', 'b.png']),
    ('Speichere die Bilder', ['a.png', 'b.pdf']),
    ('Datei schnell ablegen', ['a.txt', 'b.txt']),
])
def test_ambiguous_subset_uses_model(tmp_path, monkeypatch, prompt, names):
    monkeypatch.setattr(attachments, 'UPLOAD_DIR', tmp_path / 'uploads')
    profile = Profile(id='test', name='Test', vault={'path': str(tmp_path)})
    db = Database(tmp_path / 'app.db')
    model = AsyncMock()
    model.capabilities.side_effect = RuntimeError('model route selected')
    monkeypatch.setattr(chat, 'current_profile', lambda: profile)
    monkeypatch.setattr(chat, 'current_db', lambda profile=None: db)
    monkeypatch.setattr(chat, 'current_ollama', lambda profile=None: model)
    work = db.create_chat('Work', 'local', 'vault')
    for name in names:
        attachments.store(work['id'], name, b'source')
    try:
        with pytest.raises(RuntimeError, match='model route selected'):
            asyncio.run(chat.send_message(work['id'], chat.MessageRequest(preview_writes=False, content=prompt)))
        assert len(attachments.pending(work['id'])) == len(names)
    finally:
        db.close()
