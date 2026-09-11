"""Smoke-test the actual portable EXE using a fresh, isolated data directory."""
import json
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path

import httpx


def run():
    source = Path(sys.argv[1]).resolve()
    folder = Path.cwd() / ".test-runtime" / ("v11-frozen-" + uuid.uuid4().hex[:8])
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
            assert health.json()["version"] == "1.1"
            assert client.get("/api/settings").status_code == 403
            client.cookies.set("lka_sitzung", runtime["token"])
            page = client.get("/").text
            assert "Version 1.1" in page
            assert client.get("/api/library").status_code == 404
            assert client.get("/static/js/views/library.js").status_code == 404
            settings = client.get("/api/settings").json()
            assert "library" not in settings["profile"]
            vault = folder / "vault"
            vault.mkdir()
            profile_id = settings["active_profile"]
            assert client.patch(f"/api/settings/profile/{profile_id}", json={
                "patch": {"vault": {"path": str(vault)}}}).status_code == 200
            assert client.post("/api/files/write", json={
                "path": "Smoke.md", "content": "Portabler Test: Kennung AB-128."}).status_code == 200
            assert "AB-128" in client.get("/api/files/read", params={"path": "Smoke.md"}).json()["content"]
            assert client.get("/api/search", params={"q": "AB-128"}).json()["total"] >= 1
            assert client.get("/api/settings", headers={"Host": "evil.example"}).status_code == 403
            assert client.post("/api/files/write", headers={"Origin": "https://evil.example"},
                               json={"path": "bad.md", "content": "bad"}).status_code == 403
        (folder / "report.json").write_text(json.dumps({
            "ok": True, "version": "1.1", "portable": True,
            "checks": ["self-test", "startup", "session", "host", "origin", "frontend",
                       "settings", "write", "read", "search"],
        }, indent=2), encoding="utf-8")
        print("Frozen acceptance OK: " + str(folder / "report.json"), flush=True)
    finally:
        # Kill only this test's bootloader and child server; never a user instance.
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
        process.wait(timeout=10)


if __name__ == "__main__":
    run()
