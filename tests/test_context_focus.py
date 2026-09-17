import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from backend import context_focus, attachments
from backend.config import Profile
from backend.context_focus import VaultFocus, resolve_focus
from backend.database import Database
from backend.knowledge import sync_index, hybrid_search
from backend.routers import chat
from backend.tools import ToolRunner, _batch_clean_markdown


@pytest.fixture
def vault(tmp_path):
    for folder in ['Projekt', 'Projekt2', 'Privat']:
        (tmp_path / folder).mkdir()
        (tmp_path / folder / 'Note.md').write_text('# Kennung\nZX-731\n', encoding='utf-8', newline='\n')
    return tmp_path


def test_exact_path_does_not_scan_other_folders(vault, monkeypatch):
    monkeypatch.setattr(context_focus, 'iter_files', lambda *_a, **_k: pytest.fail('No full scan needed'))
    focus = resolve_focus(vault, 'Ergänze [[Projekt/Note.md]] um 5 mm.')
    assert focus.paths == ('Projekt/Note.md',)
    assert not focus.allows('Privat/Note.md')


@pytest.mark.parametrize('prompt', ['Arbeite im Ordner "Projekt".', 'Bearbeite Ordner Projekt', 'Ergänze [[Projekt]].'])
def test_folder_focus_has_path_boundaries(vault, prompt):
    focus = resolve_focus(vault, prompt)
    assert focus.paths == ('Projekt/',)
    assert focus.allows('Projekt/Note.md')
    assert not focus.allows('Projekt2/Note.md')
    assert len(list(focus.files(vault))) == 1


def test_ambiguous_basename_requires_path(vault):
    focus = resolve_focus(vault, 'Ändere Note.md')
    assert focus.ambiguous
    assert not focus.paths
    assert 'Privat/Note.md' in focus.instruction()


def test_no_reference_is_minimal_but_explicit_global_and_new_folder_work(vault):
    assert resolve_focus(vault, 'Meine Kennung ist ZX-731').paths == ()
    assert resolve_focus(vault, 'Entferne Emojis aus allen Markdown-Dateien').paths is None
    assert resolve_focus(vault, 'Suche im gesamten Vault').paths is None
    assert resolve_focus(vault, 'Erstelle eine Notiz im Ordner "Neues Projekt"').paths == ('Neues Projekt/',)
    assert resolve_focus(vault, 'Alle Dateien im Ordner "Projekt" prüfen').paths == ('Projekt/',)


def test_scoped_tools_never_read_unmentioned_content(vault):
    runner = ToolRunner(vault, focus=VaultFocus(('Projekt/',)), defer_guide=True)
    assert [item['pfad'] for item in runner._vault_suchen('ZX-731')['treffer']] == ['Projekt/Note.md']
    assert 'fehler' in runner._notiz_lesen('Privat/Note.md')
    assert 'fehler' in runner._ordner_auflisten('')
    assert 'fehler' in runner._notiz_ergaenzen('Privat/Note.md', 'no')
    assert runner._notiz_lesen('Projekt/Note.md')['inhalt'].startswith('# Kennung')


def test_full_read_requires_all_pages(vault):
    (vault / 'Projekt/Long.md').write_text('A' * 6200 + ' UNIQUE-TAIL', encoding='utf-8')
    runner = ToolRunner(vault, focus=VaultFocus(('Projekt/',)))
    first = runner._notiz_lesen('Projekt/Long.md')
    assert first['naechster_offset'] == 6000
    assert 'Projekt/Long.md' not in runner.read_notes
    second = runner._notiz_lesen('Projekt/Long.md', first['naechster_offset'])
    assert second['inhalt'].endswith('UNIQUE-TAIL')
    assert second['naechster_offset'] is None
    assert 'Projekt/Long.md' in runner.read_notes


def test_search_filters_before_top_k_and_partial_index_keeps_other_paths(vault):
    db = Database(vault / 'index.db')
    focus = VaultFocus(('Projekt/',))
    async def run():
        await sync_index(vault, db, None)
        (vault / 'Projekt/Note.md').write_text('ZX-731 erneuert', encoding='utf-8')
        await sync_index(vault, db, None, focus=focus)
        assert 'Privat/Note.md' in db.knowledge_manifest()
        results = await hybrid_search(vault, db, 'ZX-731', None, '', limit=1, focus=focus, refresh=False)
        assert [item['path'] for item in results['results']] == ['Projekt/Note.md']
        assert db.search.search('ZX-731', paths=()) == []
    try:
        asyncio.run(run())
    finally:
        db.close()


def test_vector_scope_filters_candidates_inside_knn(vault):
    db = Database(vault / 'vectors.db')
    try:
        if not db.search.vec:
            pytest.skip('sqlite-vec unavailable')
        for index in range(60):
            db.search.replace('vault', str(index), f'Privat/{index}.md', [{'content': 'Kennung', 'embedding': [1., 0.]}], 'model')
        db.search.replace('vault', 'target', 'Projekt/Note.md', [{'content': 'Relevant', 'embedding': [.9, .1]}], 'model')
        result = db.search.search('Kennung', [1., 0.], 'model', limit=1, paths=('Projekt/',))
        assert result[0]['path'] == 'Projekt/Note.md'
    finally:
        db.close()


def test_scoped_mechanical_edits_preserve_other_folders(vault):
    for folder in ['Projekt', 'Privat']:
        (vault / folder / 'Note.md').write_text('# Kennung 😀', encoding='utf-8')
    result = _batch_clean_markdown(vault, {'remove_emojis'}, VaultFocus(('Projekt/',)))
    assert result['geaenderte_dateien'] == ['Projekt/Note.md']
    assert '😀' in (vault / 'Privat/Note.md').read_text(encoding='utf-8')


def test_working_context_keeps_user_info_but_not_unrelated_assistant_sources(vault, monkeypatch):
    db = Database(vault / 'chat.db')
    profile = Profile(id='test', name='Test', vault={'path': str(vault)})
    captured = []
    class Model:
        async def capabilities(self, model):
            return []
        async def chat_stream(self, model, messages, **kwargs):
            captured.extend(messages)
            yield {'message': {'content': 'Erledigt.'}, 'done': True}
    monkeypatch.setattr(chat, 'current_profile', lambda: profile)
    monkeypatch.setattr(chat, 'current_db', lambda profile=None: db)
    monkeypatch.setattr(chat, 'current_ollama', lambda profile=None: Model())
    monkeypatch.setattr(attachments, 'UPLOAD_DIR', vault / 'uploads')
    search = AsyncMock(side_effect=AssertionError('No broad RAG for a plain input'))
    monkeypatch.setattr(chat, 'hybrid_search', search)
    async def run():
        work = db.create_chat('Work', 'local', 'vault')
        db.add_message(work['id'], 'user', 'Meine Kennung: ZX-731; 0,05 mm.')
        db.add_message(work['id'], 'assistant', 'Unrelated-source-body: PRIVATE-OLD-DATA')
        response = await chat.send_message(work['id'], chat.MessageRequest(content='Zusätzliche Information: 7 Seiten.', preview_writes=False))
        async for _ in response.body_iterator:
            pass
        payload = json.dumps(captured, ensure_ascii=False)
        assert 'ZX-731; 0,05 mm' in payload
        assert '7 Seiten' in payload
        assert 'PRIVATE-OLD-DATA' not in payload
        assert 'Ordnerstruktur des Vaults' not in payload
    try:
        asyncio.run(run())
    finally:
        db.close()
