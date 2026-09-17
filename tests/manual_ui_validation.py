"""Isolated browser fixture; synthetic Ollama metadata, no real model loading."""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import uuid


class Metadata(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        data = {'version': 'test'} if self.path == '/api/version' else {
            'models': [{'name': 'test-vision', 'size': 1, 'details': {}},
                       {'name': 'qwen3-vl:8b', 'size': 1, 'details': {}}]}
        self.reply(data)

    def do_POST(self):
        self.rfile.read(int(self.headers.get('Content-Length', 0)))
        self.reply({'capabilities': ['vision'], 'details': {}})

    def reply(self, data):
        content = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(content)))
        self.end_headers()
        self.wfile.write(content)


def main():
    root = Path.cwd()
    folder = root / '.test-runtime' / ('v13-ui-' + uuid.uuid4().hex[:8])
    folder.mkdir(parents=True)
    for name in ['backend', 'frontend', 'templates']:
        shutil.copytree(root / name, folder / name, ignore=shutil.ignore_patterns('__pycache__'))
    for name in ['run.py', 'desktop.py']:
        shutil.copy2(root / name, folder / name)
    server = ThreadingHTTPServer(('127.0.0.1', 0), Metadata)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    config = json.loads((root / 'config.example.json').read_text(encoding='utf-8'))
    profile = config['profiles'][0]
    config['profiles'] = [profile]
    profile['vault']['path'] = str(folder / 'vault')
    profile['ollama'].update(base_url=f'http://127.0.0.1:{server.server_port}', chat_model='test-vision', embed_model='')
    (folder / 'vault').mkdir()
    (folder / 'data').mkdir()
    (folder / 'data/config.json').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
    output = (folder / 'process.log').open('w', encoding='utf-8')
    process = subprocess.Popen([sys.executable, str(folder / 'run.py'), '--no-browser', '--no-ollama'],
        cwd=folder, stdout=output, stderr=output, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        deadline = time.monotonic() + 60
        runtime = folder / 'data/runtime.json'
        while not runtime.exists():
            assert process.poll() is None, (folder / 'process.log').read_text(encoding='utf-8')
            assert time.monotonic() < deadline
            time.sleep(.2)
        state = json.loads(runtime.read_text())
        print(json.dumps({'url': f"http://127.0.0.1:{state['port']}/?t={state['token']}", 'folder': str(folder)}), flush=True)
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline and not (folder / 'stop').exists():
            time.sleep(.5)
    finally:
        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
        process.wait(timeout=10)
        server.shutdown()
        output.close()


if __name__ == '__main__':
    main()
