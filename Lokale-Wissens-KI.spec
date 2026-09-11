# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all, collect_submodules
import os

pypdfium_datas, pypdfium_binaries, pypdfium_hidden = collect_all('pypdfium2')
pil_datas, pil_binaries, pil_hidden = collect_all('PIL')
vec_datas, vec_binaries, vec_hidden = collect_all('sqlite_vec')
# Das App-Fenster laedt seine Oberflaechenbruecke zur Laufzeit nach.
webview_datas, webview_binaries, webview_hidden = collect_all('webview')
clr_datas, clr_binaries, clr_hidden = collect_all('clr_loader')

hidden = (
    collect_submodules('uvicorn')
    + collect_submodules('watchdog')
    + collect_submodules('pypdf')
    + collect_submodules('pypdfium2')
    + collect_submodules('docx')
    + pypdfium_hidden
    + pil_hidden
    + vec_hidden
    + webview_hidden
    + clr_hidden
    + ['pythonnet', 'clr_loader', 'webview.platforms.edgechromium']
)

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=pypdfium_binaries + pil_binaries + vec_binaries + webview_binaries + clr_binaries,
    datas=[
        ('frontend', 'frontend'),
        ('templates', 'templates'),
        ('config.example.json', '.'),
        ('LICENSE', '.'),
        ('THIRD_PARTY_NOTICES.txt', '.'),
    ] + pypdfium_datas + pil_datas + vec_datas + webview_datas + clr_datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [('X utf8', None, 'OPTION')],
    name='Lokale-Wissens-KI',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=os.environ.get('LKA_BUILD_CONSOLE') == '1',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/Lokale-Wissens-KI.ico',
)
