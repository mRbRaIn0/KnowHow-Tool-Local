import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from backend import attachments
from backend.config import Profile
from backend.database import Database
from backend.knowledge import sync_index, hybrid_search
from backend.ollama_client import OllamaError
from backend.routers import chat
from backend.source_notes import has_visual_content, save_source_note
from backend.tools import ToolRunner
from backend.vision_batch import VisionBatch


def test_vision_batch_switches_only_once_and_returns_to_primary():
    calls = []
    class Client:
        async def list_models(self):
            calls.append('list')
            return [{'name': 'qwen3-vl:8b'}]
        async def capabilities(self, name):
            return ['vision']
        async def unload(self, name):
            calls.append('unload:' + name)
    async def primary(prompt, image):
        calls.append('primary:' + image)
        return image
    async def generate(name, caps, prompt, image):
        calls.append(name + ':' + image)
        return image
    async def run():
        batch = VisionBatch(Client(), 'chat', 'qwen3-vl:8b', True, primary, generate)
        for page in ['1', '2', '3']:
            assert await batch('OCR', page) == page
        await batch.close()
        await primary('Later tool', '4')
    asyncio.run(run())
    assert calls == ['list', 'unload:chat', 'qwen3-vl:8b:1', 'qwen3-vl:8b:2',
                     'qwen3-vl:8b:3', 'unload:qwen3-vl:8b', 'primary:4']


@pytest.mark.parametrize('enabled,installed,capabilities', [(False, True, ['vision']), (True, False, ['vision']), (True, True, [])])
def test_missing_disabled_or_nonvision_model_falls_back(enabled, installed, capabilities):
    client = AsyncMock()
    client.list_models.return_value = [{'name': 'vl'}] if installed else []
    client.capabilities.return_value = capabilities
    primary = AsyncMock(return_value='primary OCR')
    generate = AsyncMock()
    async def run():
        batch = VisionBatch(client, 'chat', 'vl', enabled, primary, generate)
        assert await batch('OCR', 'page') == 'primary OCR'
        await batch.close()
    asyncio.run(run())
    generate.assert_not_awaited()
    client.unload.assert_not_awaited()
    if not enabled:
        client.list_models.assert_not_awaited()


def test_vl_disappears_then_falls_back_and_stays_on_primary():
    client = AsyncMock()
    client.list_models.return_value = [{'name': 'vl'}]
    client.capabilities.return_value = ['vision']
    primary = AsyncMock(return_value='fallback')
    generate = AsyncMock(side_effect=OllamaError('missing', status=404))
    async def run():
        batch = VisionBatch(client, 'chat', 'vl', True, primary, generate)
        assert await batch('OCR', '1') == 'fallback'
        assert await batch('OCR', '2') == 'fallback'
        await batch.close()
    asyncio.run(run())
    assert [call.args[0] for call in client.unload.await_args_list] == ['chat', 'vl']
    assert generate.await_count == 1
    assert primary.await_count == 2


def test_cached_batch_does_not_load_or_unload_models():
    client = AsyncMock()
    async def run():
        batch = VisionBatch(client, 'chat', 'vl', True, AsyncMock(), AsyncMock())
        await batch.close()
    asyncio.run(run())
    client.list_models.assert_not_awaited()
    client.unload.assert_not_awaited()


def test_unload_failure_prevents_primary_continuation():
    client = AsyncMock()
    client.list_models.return_value = [{'name': 'vl'}]
    client.capabilities.return_value = ['vision']
    primary = AsyncMock()
    async def run():
        batch = VisionBatch(client, 'chat', 'vl', True, primary, AsyncMock(return_value='OCR'))
        await batch('OCR', '1')
        client.unload.side_effect = OllamaError('unload failed')
        with pytest.raises(OllamaError):
            await batch.close()
        assert batch.loaded
    asyncio.run(run())
    primary.assert_not_awaited()


@pytest.mark.parametrize('key', ['image', 'image:partial', 'page:2:vision', 'word/media/image1.png'])
def test_visual_source_detection(key):
    assert has_visual_content({'parts': {key: 'text'}})
    assert not has_visual_content({'parts': {'text': 'plain'}})


def test_source_note_preserves_ocr_and_is_searchable_without_vision(tmp_path, monkeypatch):
    monkeypatch.setattr(attachments, 'UPLOAD_DIR', tmp_path / 'uploads')
    root = tmp_path / 'vault'
    root.mkdir()
    attachments.store('abcd', 'scan.png', b'original')
    runner = ToolRunner(root, chat_id='abcd', defer_guide=True)
    text = '--- Seite 7: Bildauswertung ---\nGerätekennung ZX-731; Messwert 0,05 mm.\nUnlesbar: Seriennummer.'
    record = {'parts': {'page:7:vision': text}, 'complete': False}
    result = save_source_note(runner, 'scan.png', text, record, tmp_path)
    note = (root / result['quellennotiz']).read_text(encoding='utf-8')
    assert text in note
    assert 'unvollständig' in note
    assert '[[90 Anhänge/scan.png]]' in note
    assert not runner.note_files
    assert save_source_note(runner, 'scan.png', text, record, tmp_path)['wiederverwendet']
    assert len(list((root / '91 Quellenwissen').glob('*.md'))) == 1
    db = Database(tmp_path / 'search.db')
    async def run():
        await sync_index(root, db, None, '')
        result = await hybrid_search(root, db, 'ZX-731', None, '', refresh=False)
        assert any(item['path'].startswith('91 Quellenwissen/') for item in result['results'])
    try:
        asyncio.run(run())
    finally:
        db.close()


@pytest.mark.parametrize('save', [True, False])
def test_source_note_opt_out_in_chat_pipeline(tmp_path, monkeypatch, save):
    root = tmp_path / 'vault'
    root.mkdir()
    profile = Profile(id='test', name='Test', vault={'path': str(root)})
    db = Database(tmp_path / 'app.db')
    monkeypatch.setattr(attachments, 'UPLOAD_DIR', tmp_path / 'uploads')
    class Model:
        async def capabilities(self, model):
            return ['vision']
        async def chat_stream(self, *args, **kwargs):
            yield {'message': {'content': 'Gerätekennung ZX-731.'}, 'done': True}
    monkeypatch.setattr(chat, 'current_profile', lambda: profile)
    monkeypatch.setattr(chat, 'current_db', lambda profile=None: db)
    monkeypatch.setattr(chat, 'current_ollama', lambda profile=None: Model())
    monkeypatch.setattr(chat, 'hybrid_search', AsyncMock(return_value={}))
    monkeypatch.setattr(attachments, 'image_base64', lambda _: 'image')
    async def run():
        work = db.create_chat('Work', 'local', 'vault')
        attachments.store(work['id'], 'scan.png', b'image')
        response = await chat.send_message(work['id'], chat.MessageRequest(
            content='Erkenne die Gerätekennung auf diesem Bild.', source_notes=save, preview_writes=False))
        events = [json.loads(line[6:]) async for line in response.body_iterator]
        assert not any(event['type'] == 'error' for event in events), events
        assert bool(list(root.glob('91 Quellenwissen/*.md'))) == save
    try:
        asyncio.run(run())
    finally:
        db.close()
