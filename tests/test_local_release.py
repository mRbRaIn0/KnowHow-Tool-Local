"""V1.1 regression: existing profiles, local ingestion and immediate retrieval."""
import asyncio
import json

from fastapi.testclient import TestClient

from backend import attachments, config, deps, main, security
from backend.database import Database
from backend.knowledge import hybrid_search
from backend.routers import chat, uploads


def test_old_catalog_is_ignored_without_losing_local_data(tmp_path):
    profile = config.Profile.model_validate({
        "id": "work", "name": "Work", "library": {"enabled": True},
        "vault": {"path": str(tmp_path)},
    })
    assert "library" not in profile.model_dump()
    db_path = tmp_path / "app.db"
    db = Database(db_path)
    saved = db.create_chat("Existing chat", "", "vault")
    db.search.replace("library", "old", "remote.pdf", [{"content": "Zephyr SECRET"}])
    db.close()
    (tmp_path / "Local.md").write_text("Zephyr LOCAL", encoding="utf-8")
    db = Database(db_path)
    try:
        result = asyncio.run(hybrid_search(tmp_path, db, "Zephyr", None, ""))
        assert db.get_chat(saved["id"])["title"] == "Existing chat"
        assert [r["path"] for r in result["results"]] == ["Local.md"]
        assert db.query("SELECT id FROM search_chunks WHERE namespace='library'")
    finally:
        db.close()


def test_immediate_question_gets_new_local_information(tmp_path, monkeypatch):
    profile = config.Profile(id="release", name="Release", vault={"path": str(tmp_path)})
    profile.ollama.embed_model = ""
    db = Database(tmp_path / "app.db")
    captured = []

    class LocalModel:
        async def capabilities(self, model):
            return []

        async def chat_stream(self, model, messages, **kwargs):
            captured.extend(messages)
            yield {"message": {"content": "Zephyr hat Kennung ZP-731. [[Zephyr.md]]"}, "done": True}

    monkeypatch.setattr(deps, "current_profile", lambda: profile)
    monkeypatch.setattr(deps, "current_db", lambda profile=None: db)
    monkeypatch.setattr(chat, "current_profile", lambda: profile)
    monkeypatch.setattr(chat, "current_db", lambda profile=None: db)
    monkeypatch.setattr(uploads, "current_db", lambda profile=None: db)
    monkeypatch.setattr(chat, "current_ollama", lambda profile=None: LocalModel())
    monkeypatch.setattr(attachments, "UPLOAD_DIR", tmp_path / "uploads")
    client = TestClient(main.app, base_url="http://127.0.0.1",
                        cookies={security.COOKIE_NAME: security.SESSION_TOKEN})
    try:
        work = client.post("/api/chats", json={"purpose": "vault"}).json()
        upload = client.post(f"/api/attachments/{work['id']}", files={
            "files": ("source.txt", b"Zephyr hat Kennung ZP-731.", "text/plain")})
        assert upload.status_code == 200
        assert len(upload.json()["gespeichert"]) == 1
        write = client.post("/api/files/write", json={
            "path": "Zephyr.md", "content": "Zephyr hat Kennung ZP-731."})
        assert write.status_code == 200
        question = client.post("/api/chats", json={"purpose": "ask"}).json()
        response = client.post(f"/api/chats/{question['id']}/message",
                               json={"content": "Welche Kennung hat Zephyr?", "use_rag": False})
        assert response.status_code == 200
        assert "ZP-731" in json.dumps(captured)
        assert "Quelle: Zephyr.md" in json.dumps(captured)
        assert '"type": "error"' not in response.text
        assert client.post(f"/api/attachments/{question['id']}", files={
            "files": ("blocked.txt", b"x", "text/plain")}).status_code == 400
        assert client.get("/api/library").status_code == 404
    finally:
        client.close()
        db.close()
