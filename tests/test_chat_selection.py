import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from backend.config import Profile
from backend.database import Database
from backend.routers import chat
from backend.text_cache import read_search_text
from backend.workflow import simple_root_note


@pytest.mark.parametrize('name', ['qwen359b', 'Test 4b.md'])
def test_direct_command_requires_complete_unambiguous_instruction(name):
    prompt = f'Lege eine Test "{name}" md datei an im obersten ordner'
    assert simple_root_note(prompt) == (name if name.endswith('.md') else name + '.md')
    for other in [f'Nicht: {prompt}', prompt + ' mit einer Zusammenfassung',
                  'Wie kann ich ' + prompt, prompt.replace(name, '../escape'),
                  prompt + ' und lösche andere Dateien']:
        assert simple_root_note(other) is None


def test_text_cache_reuses_reads_but_observes_edits(tmp_path, monkeypatch):
    path = tmp_path / 'note.md'
    path.write_text('Alpha', encoding='utf-8')
    assert read_search_text(path) == ('Alpha', 'alpha')
    original = type(path).read_text
    def unexpected(*args, **kwargs):
        raise AssertionError('unchanged text should be cached')
    monkeypatch.setattr(type(path), 'read_text', unexpected)
    assert read_search_text(path) == ('Alpha', 'alpha')
    monkeypatch.setattr(type(path), 'read_text', original)
    path.write_text('Beta updated', encoding='utf-8')
    assert read_search_text(path) == ('Beta updated', 'beta updated')


def test_request_selection_and_direct_action(tmp_path, monkeypatch):
    profile = Profile(id='test', name='Test', vault={'path': str(tmp_path)})
    db = Database(tmp_path / 'app.db')
    calls = []
    class Model:
        async def capabilities(self, model):
            calls.append(('capabilities', model))
            return ['thinking']
        async def chat_stream(self, model, messages, **kwargs):
            calls.append((model, kwargs['think']))
            yield {'message': {'content': 'Fertig.'}, 'done': True}
    monkeypatch.setattr(chat, 'current_profile', lambda: profile)
    monkeypatch.setattr(chat, 'current_db', lambda profile=None: db)
    monkeypatch.setattr(chat, 'current_ollama', lambda profile=None: Model())
    monkeypatch.setattr(chat.attachments, 'pending', lambda *_: [])
    monkeypatch.setattr(chat.attachments, 'listing', lambda *_: [])
    monkeypatch.setattr(chat, 'hybrid_search', AsyncMock(return_value={}))
    async def send(chat_id, **body):
        response = await chat.send_message(chat_id, chat.MessageRequest(**body))
        return [json.loads(item.removeprefix('data: ').strip()) async for item in response.body_iterator]
    try:
        question = db.create_chat('Question', 'old', 'ask')
        for enabled in [False, True]:
            profile.ai.thinking = not enabled
            events = asyncio.run(send(question['id'], content='Hallo', model='chosen', thinking=enabled))
            assert ('chosen', enabled) in calls
            assert next(e for e in events if e['type'] == 'start')['thinking'] is enabled
        calls.clear()
        work = db.create_chat('Work', 'old', 'vault')
        prompt = 'Lege eine Test "qwen359b" md datei an im obersten ordner'
        events = asyncio.run(send(work['id'], content=prompt, model='chosen', thinking=True))
        assert not calls
        assert (tmp_path / 'qwen359b.md').read_text(encoding='utf-8').strip() == '# qwen359b'
        assert events[-1]['changed_files'] == ['qwen359b.md']
        (tmp_path / 'qwen359b.md').write_text('Keep me', encoding='utf-8')
        events = asyncio.run(send(work['id'], content=prompt))
        assert 'existiert bereits' in events[-1]['content']
        assert (tmp_path / 'qwen359b.md').read_text(encoding='utf-8') == 'Keep me'
    finally:
        db.close()

def test_exact_search_avoids_embedding_model(tmp_path):
    from backend.knowledge import hybrid_search, sync_index
    db = Database(tmp_path / 'search.db')
    (tmp_path / 'Zephyr.md').write_text('Zephyr hat Kennung ZP-731.', encoding='utf-8')
    class UnexpectedModel:
        async def embed(self, *args):
            raise AssertionError('exact lexical search must not call Ollama')
    try:
        asyncio.run(sync_index(tmp_path, db, None, 'embed'))
        results = asyncio.run(hybrid_search(tmp_path, db, 'Zephyr', UnexpectedModel(), 'embed', refresh=False))
        assert results['results'][0]['path'] == 'Zephyr.md'
        assert results['semantic'] is False
    finally:
        db.close()
