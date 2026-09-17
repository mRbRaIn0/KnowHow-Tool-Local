"""Optionaler, serieller Vision-Block; spätere Werkzeuge bleiben beim Chatmodell."""
import threading
from .ollama_client import OllamaError

_model_locks = {}
_lock_guard = threading.Lock()


def model_lock(base_url):
    with _lock_guard:
        return _model_locks.setdefault(base_url.rstrip('/'), threading.Lock())


class VisionBatch:
    def __init__(self, client, chat_model, alternate, enabled, chat_vision, generate):
        self.client = client
        self.chat_model = chat_model
        self.alternate = alternate
        self.enabled = enabled and bool(alternate) and alternate != chat_model
        self.chat_vision = chat_vision
        self.generate = generate
        self.checked = False
        self.selected = False
        self.loaded = False
        self.capabilities = []

    async def __call__(self, prompt, image):
        if not self.checked:
            self.checked = True
            if self.enabled:
                try:
                    names = {item['name'] for item in await self.client.list_models()}
                    if self.alternate in names or self.alternate + ':latest' in names:
                        self.capabilities = await self.client.capabilities(self.alternate)
                        self.selected = 'vision' in self.capabilities
                except OllamaError:
                    self.selected = False
        if self.selected:
            if not self.loaded:
                await self.client.unload(self.chat_model)
                self.loaded = True
            try:
                return await self.generate(self.alternate, self.capabilities, prompt, image)
            except OllamaError as exc:
                if exc.status != 404:
                    raise
                await self.close()
                self.selected = False
        if self.chat_vision is None:
            raise ValueError('Kein verfügbares Modell mit Bildunterstützung. Quelltext bleibt gespeichert.')
        return await self.chat_vision(prompt, image)

    async def close(self):
        if self.loaded:
            # Erst nach bestätigtem Entladen darf der Chat weiterlaufen.
            await self.client.unload(self.alternate)
            self.loaded = False
