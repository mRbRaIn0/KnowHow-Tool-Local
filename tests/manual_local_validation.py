"""Opt-in local Ollama acceptance check; uses only synthetic, isolated data.

Run from the repository root: .venv/Scripts/python tests/manual_local_validation.py
"""
import io
import json
import sys
import uuid
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from docx import Document
from PIL import Image, ImageDraw, ImageFont
from fastapi.testclient import TestClient
from backend import attachments, deps, main, security
from backend.config import Profile
from backend.database import Database
from backend.routers import chat, uploads


def run():
    output = Path.cwd() / ".test-runtime" / ("v11-live-" + uuid.uuid4().hex[:8])
    vault = output / "vault"
    vault.mkdir(parents=True)
    db = Database(output / "app.db")
    profile = Profile(id="acceptance", name="Synthetic acceptance", vault={"path": str(vault)})
    profile.ai.temperature = 0
    doc = Document()
    doc.add_paragraph("Projekt Zephyr: Die Wartung findet dienstags um 14:30 Uhr statt.")
    doc_bytes = io.BytesIO()
    doc.save(doc_bytes)
    picture = Image.new("RGB", (1200, 320), "white")
    ImageDraw.Draw(picture).text((40, 80), "Zephyr: Inventarnummer ZP-731",
                               font=ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 48), fill="black")
    image_bytes = io.BytesIO()
    picture.save(image_bytes, format="PNG")
    print("OUTPUT " + str(output), flush=True)
    with ExitStack() as stack:
        for module in (deps, chat):
            stack.enter_context(patch.object(module, "current_profile", lambda: profile))
            stack.enter_context(patch.object(module, "current_db", lambda profile=None: db))
        stack.enter_context(patch.object(uploads, "current_db", lambda profile=None: db))
        stack.enter_context(patch.object(attachments, "UPLOAD_DIR", output / "uploads"))
        client = TestClient(main.app, base_url="http://127.0.0.1",
                            cookies={security.COOKIE_NAME: security.SESSION_TOKEN})
        try:
            work = client.post("/api/chats", json={"purpose": "vault"}).json()
            response = client.post(f"/api/attachments/{work['id']}", files=[
                ("files", ("Wartung.docx", doc_bytes.getvalue(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")),
                ("files", ("Inventar.png", image_bytes.getvalue(), "image/png")),
            ])
            assert response.status_code == 200 and len(response.json()["gespeichert"]) == 2, response.text
            print("Uploads OK; local vision and note workflow running", flush=True)
            response = client.post(f"/api/chats/{work['id']}/message", json={"content":
                "Erstelle eine Wissensnotiz zum Projekt Zephyr aus beiden Anhaengen. "
                "Lies die Inventarnummer im Bild und den Wartungstermin im Dokument. "
                "Zusaetzliche Information: Ansprechpartner ist Mara Test. Speichere alle "
                "drei Fakten in der Notiz und lege beide Originaldateien im Vault ab."})
            (output / "write.sse").write_text(response.text, encoding="utf-8")
            assert response.status_code == 200 and '"type": "error"' not in response.text
            notes = "\n".join(p.read_text(encoding="utf-8") for p in vault.rglob("*.md"))
            for fact in ("ZP-731", "14:30", "Mara"):
                assert fact in notes, f"Missing persisted fact: {fact}"
            assert list(vault.rglob("*.png")) and list(vault.rglob("*.docx"))
            before = {str(p.relative_to(vault)): p.read_bytes() for p in vault.rglob("*") if p.is_file()}
            print("Persisted notes and originals OK; immediate question running", flush=True)
            question = client.post("/api/chats", json={"purpose": "ask"}).json()
            response = client.post(f"/api/chats/{question['id']}/message", json={"content":
                "Welche Inventarnummer hat Zephyr, wann ist die Wartung und wer ist Ansprechpartner? Nenne Quellen."})
            (output / "question.sse").write_text(response.text, encoding="utf-8")
            events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
            answer = "".join(e.get("delta", "") for e in events if e.get("type") == "content")
            for fact in ("ZP-731", "14:30", "Mara"):
                assert fact in answer, f"Missing answer fact: {fact}"
            assert "[[" in answer and any(e.get("sources", 0) for e in events if e.get("type") == "knowledge_ready")
            after = {str(p.relative_to(vault)): p.read_bytes() for p in vault.rglob("*") if p.is_file()}
            assert before == after, "Question modified Vault files"
            report = {"ok": True, "model": profile.ollama.chat_model,
                      "embed_model": profile.ollama.embed_model, "answer": answer,
                      "vault_files": sorted(before), "question_read_only": True}
            (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False), flush=True)
        finally:
            client.close()
            db.close()


if __name__ == "__main__":
    run()
