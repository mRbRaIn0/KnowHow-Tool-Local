import asyncio
import json
import threading
from unittest.mock import AsyncMock

import pytest

from backend import attachments
from backend.config import Profile
from backend.database import Database
from backend.routers import chat
from backend.tools import ToolRunner, _organize_vault_files
from backend.vault import create_unique_file, write_text_file
from backend.vault_actions import VaultAction, active_action, last_action, undo_last, vault_io, vault_lock
from backend.write_preview import PreviewCancelled, pending, reviewed_call


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / 'vault'
    root.mkdir()
    return root


def action_run(root, data, callback):
    action = VaultAction(root, data, 'chat')
    token = active_action.set(action)
    try:
        callback()
        action.finish()
    finally:
        active_action.reset(token)
    return action


def test_undo_restores_notes_moves_links_and_created_files(vault, tmp_path):
    original = '# Gerät\n\n![[image.png]]\nKennung ZX-17\n'
    (vault / 'Note.md').write_text(original, encoding='utf-8')
    (vault / 'image.png').write_bytes(b'image')
    def work():
        write_text_file(vault, 'Note.md', original + '\nErgänzung\n', overwrite=True)
        assert _organize_vault_files(vault, 'Dateien')['verschoben_anzahl'] == 1
        create_unique_file(vault, 'New.md', lambda out: out.write(b'new'))
    action = action_run(vault, tmp_path, work)
    assert 'Dateien/image.png' in (vault / 'Note.md').read_text(encoding='utf-8')
    assert last_action(vault, tmp_path)[1]['id'] == action.id
    assert undo_last(vault, tmp_path)['undone']
    assert (vault / 'Note.md').read_text(encoding='utf-8') == original
    assert (vault / 'image.png').read_bytes() == b'image'
    assert not (vault / 'Dateien/image.png').exists()
    assert not (vault / 'New.md').exists()
    assert not undo_last(vault, tmp_path)['undone']


def test_undo_conflict_checks_every_file_before_writing(vault, tmp_path):
    def work():
        write_text_file(vault, 'A.md', 'ours')
        write_text_file(vault, 'B.md', 'ours')
    action_run(vault, tmp_path, work)
    (vault / 'B.md').write_text('new user edit', encoding='utf-8')
    with pytest.raises(ValueError, match='neuere Änderungen'):
        undo_last(vault, tmp_path)
    assert (vault / 'A.md').read_text() == 'ours'
    assert (vault / 'B.md').read_text() == 'new user edit'


def test_undo_rejects_corrupt_original_and_busy_vault(vault, tmp_path):
    (vault / 'A.md').write_text('original')
    action = action_run(vault, tmp_path, lambda: write_text_file(vault, 'A.md', 'changed', overwrite=True))
    (action.folder / '0.bin').write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='unvollständig'):
        undo_last(vault, tmp_path)
    assert (vault / 'A.md').read_text() == 'changed'
    lock = vault_lock(vault)
    lock.acquire()
    try:
        with pytest.raises(ValueError, match='läuft noch'):
            undo_last(vault, tmp_path)
    finally:
        lock.release()


def test_noop_task_keeps_previous_undo(vault, tmp_path):
    first = action_run(vault, tmp_path, lambda: write_text_file(vault, 'A.md', 'keep'))
    def work():
        write_text_file(vault, 'A.md', 'transient', overwrite=True)
        write_text_file(vault, 'A.md', 'keep', overwrite=True)
    action_run(vault, tmp_path, work)
    assert last_action(vault, tmp_path)[1]['id'] == first.id
    assert last_action(vault, tmp_path / 'other-profile') is None


def test_cancelled_io_finishes_before_action_unlock(vault, tmp_path):
    async def run():
        started, release, finished = threading.Event(), threading.Event(), threading.Event()
        def write():
            started.set()
            release.wait(2)
            write_text_file(vault, 'A.md', 'complete')
            finished.set()
        action = VaultAction(vault, tmp_path, 'chat')
        token = active_action.set(action)
        try:
            task = asyncio.create_task(vault_io(write))
            await asyncio.to_thread(started.wait, 2)
            task.cancel()
            await asyncio.sleep(.01)
            assert not task.done()
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert finished.is_set()
            action.finish()
            assert undo_last(vault, tmp_path)['undone']
        finally:
            active_action.reset(token)
    asyncio.run(run())


def test_preview_create_adjust_then_accept(vault):
    runner = ToolRunner(vault, preview_writes=True, defer_guide=True)
    async def run():
        stream = reviewed_call(runner, 'p', 'c', lambda: runner.run('notiz_erstellen', {'pfad': 'A.md', 'inhalt': '# Draft'}))
        draft = (await anext(stream))['preview']
        assert not (vault / 'A.md').exists()
        assert '+# Draft' in draft['diff']
        pending[('p', 'c')]['future'].set_result({'accept': True, 'path': 'B.md', 'content': '# Angepasst\nAB-21'})
        result = (await anext(stream))['result']
        await stream.aclose()
        assert result['erstellt'] == 'B.md'
        assert (vault / 'B.md').read_text(encoding='utf-8') == '# Angepasst\nAB-21'
        assert ('p', 'c') not in pending
    asyncio.run(run())


@pytest.mark.parametrize('operation,args', [
    ('notiz_ergaenzen', {'pfad': 'A.md', 'inhalt': 'Zusatz'}),
    ('notiz_bearbeiten', {'pfad': 'A.md', 'modus': 'text_ersetzen', 'alter_text': 'Alt', 'neuer_inhalt': 'Neu'}),
])
def test_preview_edit_does_not_write_before_acceptance(vault, operation, args):
    (vault / 'A.md').write_text('Alt\n', encoding='utf-8')
    runner = ToolRunner(vault, preview_writes=True, allow_edit=True, defer_guide=True)
    runner._notiz_lesen('A.md')
    async def run():
        stream = reviewed_call(runner, 'p', 'c', lambda: runner.run(operation, args))
        preview = (await anext(stream))['preview']
        assert preview['before'].replace('\r\n', '\n') == 'Alt\n'
        assert (vault / 'A.md').read_text() == 'Alt\n'
        pending[('p', 'c')]['future'].set_result({'accept': False})
        with pytest.raises(PreviewCancelled):
            await anext(stream)
        assert (vault / 'A.md').read_text() == 'Alt\n'
        assert ('p', 'c') not in pending
    asyncio.run(run())


def test_preview_external_edit_requires_fresh_review(vault):
    (vault / 'A.md').write_text('Alt\n', encoding='utf-8')
    runner = ToolRunner(vault, preview_writes=True, defer_guide=True)
    async def run():
        stream = reviewed_call(runner, 'p', 'c', lambda: runner.run('notiz_ergaenzen', {'pfad': 'A.md', 'inhalt': 'Zusatz'}))
        first = (await anext(stream))['preview']
        (vault / 'A.md').write_text('Externe Änderung\n', encoding='utf-8')
        pending[('p', 'c')]['future'].set_result({'accept': True})
        second = (await anext(stream))['preview']
        assert second['id'] != first['id']
        assert second['before'].replace('\r\n', '\n') == 'Externe Änderung\n'
        await stream.aclose()
        assert ('p', 'c') not in pending
    asyncio.run(run())


def test_preview_router_cancel_rolls_back_earlier_changes(vault, tmp_path, monkeypatch):
    profile = Profile(id='test', name='Test', vault={'path': str(vault)})
    db = Database(tmp_path / 'app.db')
    monkeypatch.setattr(chat, 'current_profile', lambda: profile)
    monkeypatch.setattr(chat, 'current_db', lambda profile=None: db)
    monkeypatch.setattr(chat, 'current_ollama', lambda profile=None: AsyncMock())
    monkeypatch.setattr(attachments, 'UPLOAD_DIR', tmp_path / 'uploads')
    original = ToolRunner._notiz_erstellen
    def write_first(self, *args, **kwargs):
        if not (vault / 'earlier.md').exists():
            write_text_file(vault, 'earlier.md', 'earlier action')
        return original(self, *args, **kwargs)
    monkeypatch.setattr(ToolRunner, '_notiz_erstellen', write_first)
    async def run():
        work = db.create_chat('Work', 'local', 'vault')
        response = await chat.send_message(work['id'], chat.MessageRequest(content='Lege eine Test "Test" md datei an im obersten ordner'))
        events = []
        async for line in response.body_iterator:
            event = json.loads(line[6:])
            events.append(event)
            if event['type'] == 'write_preview':
                assert (vault / 'earlier.md').exists()
                assert not (vault / 'Test.md').exists()
                with pytest.raises(Exception) as caught:
                    await chat.decide_preview(work['id'], 'stale-id', chat.PreviewDecision(accept=True))
                assert caught.value.status_code == 409
                await chat.decide_preview(work['id'], event['preview']['id'], chat.PreviewDecision(accept=False))
        assert events[-1]['kind'] == 'preview_cancelled'
        assert not (vault / 'earlier.md').exists()
        assert not (vault / 'Test.md').exists()
        assert not vault_lock(vault).locked()
        assert 'zurückgenommen' in db.list_messages(work['id'])[-1]['content']
    try:
        asyncio.run(run())
    finally:
        db.close()
