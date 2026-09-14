"""Refresh the selected Vault in the background, never on a search request."""
import asyncio
import logging
import threading

from .config import store
from .database import registry
from .watcher import watcher
from .knowledge import sync_index
from .ollama_client import OllamaClient

log = logging.getLogger(__name__)


class KnowledgeWorker:
    def __init__(self):
        self.stopped = threading.Event()
        self.thread = None
        self.paused = threading.Event()
        self._lock = threading.Lock()
        self._loop = None
        self._task = None

    def start(self):
        self.stopped.clear()
        self.paused.clear()
        self.thread = threading.Thread(target=self.run, daemon=True, name="vault-index")
        self.thread.start()

    def pause(self):
        self.paused.set()
        with self._lock:
            if self._loop and self._task:
                self._loop.call_soon_threadsafe(self._task.cancel)

    async def _index(self, root, database, client, profile):
        with self._lock:
            self._loop = asyncio.get_running_loop()
            self._task = asyncio.current_task()
        try:
            if not self.paused.is_set():
                await sync_index(root, database, client, profile.ollama.embed_model,
                                 excluded_dirs=(profile.vault.templates_dir,))
        finally:
            with self._lock:
                self._loop = self._task = None

    def stop(self):
        self.stopped.set()
        self.pause()
        if self.thread:
            self.thread.join(timeout=3)

    def run(self):
        last = None
        while not self.stopped.wait(2):
            if self.paused.is_set():
                continue
            try:
                profile = store.active_profile().model_copy(deep=True)
                root = profile.vault_path
                if not root or not root.is_dir():
                    continue
                revision = watcher.changes(0)["revision"]
                key = (profile.id, str(root), revision, profile.ollama.embed_model, profile.vault.templates_dir)
                if key == last:
                    continue
                database = registry.get(profile.id, profile.db_path)
                client = OllamaClient(profile.ollama.base_url, profile.privacy.offline_mode)
                asyncio.run(self._index(root, database, client, profile))
                last = key
            except asyncio.CancelledError:
                continue
            except Exception:
                log.exception("Vault-Hintergrundindex")


knowledge_worker = KnowledgeWorker()
