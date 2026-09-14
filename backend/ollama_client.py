"""Schmale Anbindung an die lokale Ollama-REST-API.

Bewusst ohne SDK: nur httpx gegen http://localhost:11434. `trust_env=False`
verhindert, dass Proxy-Umgebungsvariablen Anfragen nach außen umleiten.
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional
from urllib.parse import urlparse

import httpx

log = logging.getLogger(__name__)

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0", "[::1]"}

DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=600.0, write=60.0, pool=5.0)
QUICK_TIMEOUT = httpx.Timeout(connect=2.0, read=5.0, write=5.0, pool=2.0)

# Modellfähigkeiten ändern sich zur Laufzeit nicht — einmal abfragen genügt.
_CAPABILITIES: Dict[str, List[str]] = {}


class OllamaError(Exception):
    """Verständlicher Fehler aus der Ollama-Kommunikation."""

    def __init__(self, message: str, *, kind: str = "error", status: int = 502):
        super().__init__(message)
        self.message = message
        self.kind = kind  # offline | not_found | blocked | error
        self.status = status


def assert_local(base_url: str, offline_mode: bool) -> None:
    """Im Offline-Modus sind ausschließlich lokale Ollama-Server erlaubt."""
    if not offline_mode:
        return
    host = (urlparse(base_url).hostname or "").lower()
    if host not in LOCAL_HOSTS:
        raise OllamaError(
            f"Offline-Modus ist aktiv: Der Server '{base_url}' ist nicht lokal und "
            f"wurde blockiert.",
            kind="blocked",
            status=403,
        )


class OllamaClient:
    def __init__(self, base_url: str, offline_mode: bool = True):
        self.base_url = (base_url or "http://127.0.0.1:11434").rstrip("/")
        self.offline_mode = offline_mode
        assert_local(self.base_url, offline_mode)

    def _client(self, timeout: httpx.Timeout = DEFAULT_TIMEOUT) -> httpx.AsyncClient:
        # trust_env=False: keine Proxys, keine Netrc, kein Umweg über die Umgebung.
        return httpx.AsyncClient(base_url=self.base_url, timeout=timeout, trust_env=False)

    # ---------------------------------------------------------------- Status

    async def health(self) -> Dict[str, Any]:
        """Prüft, ob Ollama erreichbar ist. Wirft nie — gibt immer einen Status zurück."""
        try:
            async with self._client(QUICK_TIMEOUT) as client:
                response = await client.get("/api/version")
                response.raise_for_status()
                return {"online": True, "version": response.json().get("version", "")}
        except Exception as exc:
            log.info("Ollama nicht erreichbar: %s", exc)
            return {"online": False, "version": "", "error": str(exc)}

    async def list_models(self) -> List[Dict[str, Any]]:
        data = await self._get_json("/api/tags", QUICK_TIMEOUT)
        models = data.get("models", []) or []
        return [
            {
                "name": m.get("name", ""),
                "size": m.get("size", 0),
                "modified": m.get("modified_at", ""),
                "family": (m.get("details") or {}).get("family", ""),
                "parameters": (m.get("details") or {}).get("parameter_size", ""),
                "quantization": (m.get("details") or {}).get("quantization_level", ""),
            }
            for m in models
        ]

    async def show(self, model: str) -> Dict[str, Any]:
        """Modelldetails inkl. capabilities (vision, tools, thinking, embedding)."""
        try:
            async with self._client(QUICK_TIMEOUT) as client:
                response = await client.post("/api/show", json={"model": model})
                if response.status_code == 404:
                    raise OllamaError(
                        f"Das Modell '{model}' ist in Ollama nicht installiert.",
                        kind="not_found",
                        status=404,
                    )
                response.raise_for_status()
                data = response.json()
        except OllamaError:
            raise
        except httpx.HTTPError as exc:
            raise self._connection_error(exc) from exc
        details = data.get("details") or {}
        return {
            "model": model,
            "capabilities": data.get("capabilities", []) or [],
            "family": details.get("family", ""),
            "parameters": details.get("parameter_size", ""),
            "quantization": details.get("quantization_level", ""),
            "context_length": _find_context_length(data.get("model_info") or {}),
        }

    # ------------------------------------------------------------------ Chat

    async def capabilities(self, model: str) -> List[str]:
        """Fähigkeiten eines Modells, im Prozess zwischengespeichert."""
        key = f"{self.base_url}|{model}"
        if key not in _CAPABILITIES:
            _CAPABILITIES[key] = (await self.show(model)).get("capabilities", [])
        return _CAPABILITIES[key]

    async def chat_stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        options: Optional[Dict[str, Any]] = None,
        think: Optional[bool] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Streamt die Antwort von /api/chat als Folge von JSON-Objekten.

        `think=None` überlässt die Entscheidung dem Modell; True/False setzt sie
        ausdrücklich. Modelle ohne Thinking-Fähigkeit lehnen das Feld ab —
        deshalb wird es nur gesetzt, wenn die Fähigkeit bekannt ist.
        """
        payload: Dict[str, Any] = {"model": model, "messages": messages, "stream": True}
        if options:
            payload["options"] = options
        if think is not None:
            payload["think"] = think
        if tools:
            payload["tools"] = tools

        try:
            async with self._client() as client:
                async with client.stream("POST", "/api/chat", json=payload) as response:
                    if response.status_code == 404:
                        await response.aread()
                        raise OllamaError(
                            f"Das Modell '{model}' ist in Ollama nicht installiert.",
                            kind="not_found",
                            status=404,
                        )
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", "replace")
                        raise OllamaError(_extract_error(body), status=response.status_code)
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            log.warning("Ungültige Streamzeile von Ollama: %r", line[:200])
        except OllamaError:
            raise
        except httpx.HTTPError as exc:
            raise self._connection_error(exc) from exc

    async def embed(self, model: str, inputs: List[str]) -> List[List[float]]:
        """Embeddings über /api/embed (Batch wird von Ollama unterstützt)."""
        try:
            async with self._client() as client:
                response = await client.post("/api/embed", json={"model": model, "input": inputs})
                if response.status_code == 404:
                    raise OllamaError(
                        f"Das Embedding-Modell '{model}' ist nicht installiert.",
                        kind="not_found",
                        status=404,
                    )
                response.raise_for_status()
                return response.json().get("embeddings", [])
        except OllamaError:
            raise
        except httpx.HTTPError as exc:
            raise self._connection_error(exc) from exc

    async def pull_stream(self, model: str) -> AsyncIterator[Dict[str, Any]]:
        """Lädt ein Modell über Ollama herunter und streamt den Fortschritt.

        Hinweis: Das ist der einzige Vorgang, bei dem Ollama selbst ins Internet
        geht. Er wird immer bewusst vom Benutzer ausgelöst, nie automatisch.
        """
        timeout = httpx.Timeout(connect=5.0, read=3600.0, write=60.0, pool=5.0)
        try:
            async with self._client(timeout) as client:
                async with client.stream("POST", "/api/pull", json={"model": model, "stream": True}) as response:
                    if response.status_code >= 400:
                        body = (await response.aread()).decode("utf-8", "replace")
                        raise OllamaError(_extract_error(body), status=response.status_code)
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            continue
        except OllamaError:
            raise
        except httpx.HTTPError as exc:
            raise self._connection_error(exc) from exc

    # --------------------------------------------------------------- Helpers

    async def _get_json(self, path: str, timeout: httpx.Timeout) -> Dict[str, Any]:
        try:
            async with self._client(timeout) as client:
                response = await client.get(path)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            raise self._connection_error(exc) from exc

    def _connection_error(self, exc: Exception) -> OllamaError:
        return OllamaError(
            f"Ollama ist unter {self.base_url} nicht erreichbar. "
            f"Läuft der Ollama-Dienst? ({exc.__class__.__name__})",
            kind="offline",
            status=503,
        )


def _extract_error(body: str) -> str:
    try:
        return json.loads(body).get("error") or body[:400]
    except json.JSONDecodeError:
        return body[:400] or "Unbekannter Fehler von Ollama."


def _find_context_length(model_info: Dict[str, Any]) -> int:
    for key, value in model_info.items():
        if key.endswith(".context_length") and isinstance(value, int):
            return value
    return 0
