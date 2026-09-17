import asyncio
from contextlib import suppress

from backend import chat_runs
from backend.config import Profile
from backend.database import Database
from backend.ollama_client import OllamaClient
from backend.routers import chat
from backend.knowledge_worker import KnowledgeWorker


def test_stop_closes_live_ollama_connection_and_persists_status(tmp_path, monkeypatch):
    profile = Profile(id='stop', name='Stop')
    db = Database(tmp_path / 'app.db')
    monkeypatch.setattr(chat, 'current_profile', lambda: profile)
    monkeypatch.setattr(chat, 'current_db', lambda profile=None: db)
    monkeypatch.setattr(chat.knowledge_worker, 'pause', lambda: None)
    async def run():
        started, disconnected = asyncio.Event(), asyncio.Event()
        async def serve(reader, writer):
            try:
                header = await reader.readuntil(b'\r\n\r\n')
                size = next(int(line.split(b':')[1]) for line in header.split(b'\r\n') if line.lower().startswith(b'content-length:'))
                await reader.readexactly(size)
                writer.write(b'HTTP/1.1 200 OK\r\nContent-Type: application/x-ndjson\r\nConnection: close\r\n\r\n{"message":{"thinking":"working"}}\n')
                await writer.drain()
                started.set()
                try:
                    await reader.read()
                except ConnectionResetError:
                    pass  # Windows may report cancellation as a reset rather than EOF.
                disconnected.set()
            finally:
                writer.close()
                with suppress(ConnectionResetError):
                    await writer.wait_closed()
        server = await asyncio.start_server(serve, '127.0.0.1', 0)
        client = OllamaClient(f'http://127.0.0.1:{server.sockets[0].getsockname()[1]}')
        async def capabilities(model):
            return ['thinking']
        monkeypatch.setattr(client, 'capabilities', capabilities)
        monkeypatch.setattr(chat, 'current_ollama', lambda profile=None: client)
        work = db.create_chat('Stop', 'fake', 'ask')
        async def consume():
            response = await chat.send_message(work['id'], chat.MessageRequest(preview_writes=False, content='Hello'))
            async for _ in response.body_iterator:
                pass
        task = asyncio.create_task(consume())
        try:
            await asyncio.wait_for(started.wait(), 5)
            assert (await chat.stop_message(work['id']))['stopped']
            with suppress(asyncio.CancelledError):
                await task
            await asyncio.wait_for(disconnected.wait(), 5)
            assert not chat_runs.runs
            assert 'unterbrochen' in db.list_messages(work['id'])[-1]['content']
        finally:
            task.cancel()
            server.close()
            await server.wait_closed()
    try:
        asyncio.run(run())
    finally:
        db.close()


def test_pause_cancels_background_embedding_and_blocks_restart(monkeypatch):
    from backend import knowledge_worker as module
    worker = KnowledgeWorker()
    async def run():
        started, closed = asyncio.Event(), asyncio.Event()
        async def sync(*args, **kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                closed.set()
        monkeypatch.setattr(module, 'sync_index', sync)
        task = asyncio.create_task(worker._index(None, None, None, Profile(id='x', name='X')))
        await started.wait()
        worker.pause()
        with suppress(asyncio.CancelledError):
            await task
        assert closed.is_set()
        assert worker.paused.is_set()
        started.clear()
        await worker._index(None, None, None, Profile(id='x', name='X'))
        assert not started.is_set()
    asyncio.run(run())
