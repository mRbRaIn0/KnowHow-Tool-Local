"""Smoke-test the actual portable EXE using a fresh, isolated data directory."""
import json
import shutil
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx


def run():
    source = Path(sys.argv[1]).resolve()
    folder = Path.cwd() / ".test-runtime" / ("v13-frozen-" + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    executable = folder / source.name
    shutil.copy2(source, executable)
    report_path = folder / "self-test.json"
    subprocess.run([str(executable), "--self-test", str(report_path)],
                   creationflags=subprocess.CREATE_NO_WINDOW, timeout=60, check=True)
    assert json.loads(report_path.read_text())["ok"]
    process = subprocess.Popen([str(executable), "--no-browser", "--no-ollama"],
                               creationflags=subprocess.CREATE_NO_WINDOW, cwd=folder)
    try:
        runtime_file = folder / "data" / "runtime.json"
        deadline = time.monotonic() + 60
        while not runtime_file.exists():
            assert process.poll() is None, "EXE exited during startup"
            assert time.monotonic() < deadline, "EXE startup timeout"
            time.sleep(.2)
        runtime = json.loads(runtime_file.read_text())
        base = f"http://127.0.0.1:{runtime['port']}"
        with httpx.Client(base_url=base, trust_env=False, timeout=10) as client:
            for _ in range(50):
                try:
                    health = client.get("/api/health")
                    break
                except httpx.ConnectError:
                    time.sleep(.2)
            assert health.json()["version"] == "1.3"
            assert client.get("/api/settings").status_code == 403
            client.cookies.set("lka_sitzung", runtime["token"])
            page = client.get("/").text
            assert "Version 1.3" in page
            settings_module = client.get("/assets/js/views/settings.js")
            assert settings_module.status_code == 200
            subprocess.run(["node", "--input-type=module", "--check"],
                           input=settings_module.text, text=True, encoding="utf-8", check=True,
                           creationflags=subprocess.CREATE_NO_WINDOW)
            assert client.get("/api/library").status_code == 404
            assert client.get("/static/js/views/library.js").status_code == 404
            settings = client.get("/api/settings").json()
            assert "library" not in settings["profile"]
            assert settings['profile']['ai']['preview_writes']
            assert settings['profile']['ai']['source_notes']
            assert not settings['profile']['ai']['separate_vision']
            vault = folder / "vault"
            vault.mkdir()
            profile_id = settings["active_profile"]
            assert client.patch(f"/api/settings/profile/{profile_id}", json={
                "patch": {"vault": {"path": str(vault)}}}).status_code == 200
            assert client.post("/api/files/write", json={
                "path": "Smoke.md", "content": "Portabler Test: Kennung AB-128."}).status_code == 200
            assert "AB-128" in client.get("/api/files/read", params={"path": "Smoke.md"}).json()["content"]
            assert client.get("/api/search", params={"q": "AB-128"}).json()["total"] >= 1
            work = client.post("/api/chats", json={"purpose": "vault"}).json()
            direct_started = time.monotonic()
            for index in range(2):
                uploaded = client.post(f"/api/attachments/{work['id']}", files={
                    "files": ("image.png", b"synthetic image bytes", "image/png")})
                assert uploaded.status_code == 200
                expected = "image.png" if index == 0 else "image1.png"
                assert uploaded.json()["gespeichert"][0]["name"] == expected
                response = client.post(f"/api/chats/{work['id']}/message", json={
                    "content": 'Lege die Dateien in "Projekt/Dateien" ab.'})
                events = [json.loads(line[6:]) for line in response.text.splitlines()
                          if line.startswith("data: ")]
                assert events[1]["execution"] == "direct"
                assert events[-1]["changed_files"] == [f"Projekt/Dateien/{expected}"]
                assert (vault / "Projekt/Dateien" / expected).read_bytes() == b"synthetic image bytes"
            direct_seconds = time.monotonic() - direct_started
            # The real packaged server must wait before writing and accept edits.
            preview_work = client.post('/api/chats', json={'purpose': 'vault'}).json()
            path = f"/api/chats/{preview_work['id']}"
            with ThreadPoolExecutor(max_workers=1) as pool:
                for accept in [True, False]:
                    future = pool.submit(client.post, path + '/message', json={
                        'content': 'Lege eine Test "Review" md datei an im obersten ordner'})
                    deadline = time.monotonic() + 8
                    draft = None
                    while draft is None:
                        assert time.monotonic() < deadline, 'No write preview received'
                        draft = client.get(path + '/preview').json()['preview']
                        if draft is None:
                            time.sleep(.05)
                    assert not (vault / 'Review.md').exists()
                    assert client.post(path + '/preview/stale', json={'accept': True}).status_code == 409
                    result = client.post(path + '/preview/' + draft['id'], json={
                        'accept': accept, 'path': 'Reviewed.md', 'content': '# Reviewed\n\nZX-731: 0,05 mm.'})
                    assert result.status_code == 200
                    response = future.result(timeout=10)
                    events = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
                    if accept:
                        assert events[-1]['type'] == 'done'
                        assert (vault / 'Reviewed.md').read_text(encoding='utf-8').endswith('0,05 mm.')
                        assert client.get('/api/chats/vault/last-action').json()['available']
                        (vault / 'Reviewed.md').write_text('newer external change', encoding='utf-8')
                        assert client.post('/api/chats/vault/undo').status_code == 409
                        (vault / 'Reviewed.md').write_text('# Reviewed\n\nZX-731: 0,05 mm.', encoding='utf-8', newline='\n')
                        assert client.post('/api/chats/vault/undo').json()['undone']
                        assert not (vault / 'Reviewed.md').exists()
                    else:
                        assert events[-1]['kind'] == 'preview_cancelled'
                        assert not (vault / 'Review.md').exists()
                    assert not client.get('/api/chats/vault/last-action').json()['busy']
            assert client.get("/api/settings", headers={"Host": "evil.example"}).status_code == 403
            assert client.post("/api/files/write", headers={"Origin": "https://evil.example"},
                               json={"path": "bad.md", "content": "bad"}).status_code == 403
        (folder / "report.json").write_text(json.dumps({
            "ok": True, "version": "1.3", "portable": True,
            "two_direct_upload_and_archive_seconds": round(direct_seconds, 3),
            "checks": ["self-test", "startup", "session", "host", "origin", "frontend",
                       "settings", "write", "read", "search", "direct-archive", "collision-numbering",
                       "write-preview", "edited-approval", "stale-preview", "preview-cancel", "undo", "undo-conflict"],
        }, indent=2), encoding="utf-8")
        print("Frozen acceptance OK: " + str(folder / "report.json"), flush=True)
    finally:
        # Kill only this test's bootloader and child server; never a user instance.
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
        process.wait(timeout=10)


if __name__ == "__main__":
    run()
