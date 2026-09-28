"""V1.4 Funktion E: schnelle Ablage aus den Tabs Notizen, Bilder und Dateien."""
import asyncio
import io

from fastapi import UploadFile

from backend import attachments
from backend.config import Profile
from backend.routers import files, uploads
from backend.tools import ToolRunner


def _files(*names):
    return [UploadFile(filename=name, file=io.BytesIO(name.encode())) for name in names]


def test_tab_upload_numbers_without_dialog(tmp_path, monkeypatch):
    profile = Profile(id='test', name='Test', vault={'path': str(tmp_path)})
    monkeypatch.setattr(files, 'current_profile', lambda: profile)
    monkeypatch.setattr(files, 'current_vault', lambda: tmp_path)
    first = asyncio.run(files.upload_files(_files('image.png', 'image.png'), None))
    assert [item['path'] for item in first['gespeichert']] == ['90 Anhänge/image.png', '90 Anhänge/image1.png']
    assert first['gespeichert'][0]['kind'] == 'image'
    into = asyncio.run(files.upload_files(_files('Notiz.md', 'Notiz.md'), 'Projekt/Dateien'))
    assert [item['path'] for item in into['gespeichert']] == ['Projekt/Dateien/Notiz.md', 'Projekt/Dateien/Notiz1.md']
    root_level = asyncio.run(files.upload_files(_files('a.txt'), ''))
    assert root_level['gespeichert'][0]['path'] == 'a.txt'
    assert (tmp_path / '90 Anhänge/image.png').read_bytes() == b'image.png'


def test_tab_upload_rejects_escape_and_keeps_going(tmp_path, monkeypatch):
    profile = Profile(id='test', name='Test', vault={'path': str(tmp_path / 'vault')})
    (tmp_path / 'vault').mkdir()
    monkeypatch.setattr(files, 'current_profile', lambda: profile)
    monkeypatch.setattr(files, 'current_vault', lambda: tmp_path / 'vault')
    result = asyncio.run(files.upload_files(_files('x.txt'), '../draußen'))
    assert result['gespeichert'] == [] and result['fehler']
    assert not (tmp_path / 'draußen').exists()


def test_vault_image_attached_to_chat_is_not_duplicated(tmp_path, monkeypatch):
    root = tmp_path / 'vault'
    (root / 'Bilder').mkdir(parents=True)
    (root / 'Bilder/foto.png').write_bytes(b'pixels')
    monkeypatch.setattr(attachments, 'UPLOAD_DIR', tmp_path / 'uploads')
    profile = Profile(id='test', name='Test', vault={'path': str(root)})
    monkeypatch.setattr(uploads, 'current_profile', lambda: profile)
    monkeypatch.setattr(uploads, 'current_vault', lambda profile: root)
    monkeypatch.setattr(uploads, 'eigener_chat', lambda chat_id: {'purpose': 'vault'})
    item = asyncio.run(uploads.attach_from_vault('abcdef', uploads.FromVault(path='Bilder/foto.png')))
    assert item['vault_path'] == 'Bilder/foto.png'
    assert attachments.pending('abcdef')[0]['name'] == 'foto.png'
    assert sorted(p.name for p in root.rglob('*') if p.is_file()) == ['foto.png']
    runner = ToolRunner(root, chat_id='abcdef', attachment_dir='90 Anhänge')
    assert runner._anhang_in_vault_ablegen('foto.png', zielordner='90 Anhänge')['abgelegt'] == 'Bilder/foto.png'
