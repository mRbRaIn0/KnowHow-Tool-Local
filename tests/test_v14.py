"""V1.4: optionale Syntax und sofortige, kollisionssichere Vault-Ablage."""
import asyncio
import io

from fastapi import UploadFile

from backend import attachments
from backend.config import Profile
from backend.context_focus import VaultFocus
from backend.markdown_knowledge import MARKDOWN_INSTRUCTIONS
from backend.routers import files, uploads
from backend.tools import ToolRunner
from backend.vault_guide import ensure_vault_guide


def test_syntax_reference_is_created_once(tmp_path):
    ensure_vault_guide(tmp_path)
    syntax = tmp_path / "Obsidian_Syntax.md"
    assert "Fußnoten" in syntax.read_text(encoding="utf-8")
    assert "Fußnoten" not in MARKDOWN_INSTRUCTIONS
    syntax.write_text("eigene Regeln", encoding="utf-8")
    ensure_vault_guide(tmp_path)
    assert syntax.read_text(encoding="utf-8") == "eigene Regeln"
    runner = ToolRunner(tmp_path, focus=VaultFocus(()))
    assert runner._notiz_lesen("Obsidian_Syntax.md")["inhalt"] == "eigene Regeln"


def test_upload_goes_directly_to_vault_and_is_reused(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    root.mkdir()
    monkeypatch.setattr(attachments, "UPLOAD_DIR", tmp_path / "uploads")
    profile = Profile(id="test", name="Test", vault={"path": str(root)})
    monkeypatch.setattr(uploads, "current_profile", lambda: profile)
    monkeypatch.setattr(uploads, "current_vault", lambda profile: root)
    monkeypatch.setattr(uploads, "eigener_chat", lambda chat_id: {"purpose": "vault"})

    async def save():
        return await uploads.upload("abcdef", [UploadFile(filename="image.png", file=io.BytesIO(b"original"))])

    first = asyncio.run(save())["gespeichert"][0]
    second = asyncio.run(save())["gespeichert"][0]
    assert first["vault_path"] == "90 Anhänge/image.png"
    assert second["vault_path"] == "90 Anhänge/image1.png"
    assert (root / second["vault_path"]).read_bytes() == b"original"
    runner = ToolRunner(root, chat_id="abcdef")
    assert runner._anhang_in_vault_ablegen(second["name"])["abgelegt"] == second["vault_path"]
    assert not (root / "90 Anhänge/image2.png").exists()


def test_save_note_numbers_without_overwriting(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "current_vault", lambda: tmp_path)
    request = files.WriteRequest(path="Notiz.md", content="neu", auto_number=True)
    first = asyncio.run(files.write_file(request))
    second = asyncio.run(files.write_file(request))
    assert [first["path"], second["path"]] == ["Notiz.md", "Notiz1.md"]
    assert (tmp_path / "Notiz.md").read_text(encoding="utf-8") == "neu"
    assert (tmp_path / "Notiz1.md").read_text(encoding="utf-8") == "neu"
