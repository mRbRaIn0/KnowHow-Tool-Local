$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot

$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    throw 'Die .venv fehlt. Bitte start.bat einmal ausführen.'
}

& $python -m pip install -r requirements-build.txt
if ($LASTEXITCODE -ne 0) { throw 'Build-Abhängigkeiten konnten nicht installiert werden.' }
& $python -c "import sqlite3, sqlite_vec; c=sqlite3.connect(':memory:'); c.enable_load_extension(True); sqlite_vec.load(c); print(c.execute('select vec_version()').fetchone()[0])"
if ($LASTEXITCODE -ne 0) { throw 'sqlite-vec fehlt. Bitte requirements.txt installieren.' }
& $python -m PyInstaller --noconfirm --clean 'Lokale-Wissens-KI.spec'
if ($LASTEXITCODE -ne 0) { throw 'Windows-Build fehlgeschlagen.' }
$hauptExe = Join-Path $PSScriptRoot 'dist\Lokale-Wissens-KI.exe'
$releaseExe = Join-Path $PSScriptRoot 'dist\KnowHow Tool v1.0.exe'
Copy-Item -LiteralPath $hauptExe -Destination $releaseExe -Force
foreach ($bundleDoc in @('setup-docling.ps1', 'requirements-docling.txt', 'README.md', 'KI.md')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $bundleDoc) -Destination (Join-Path $PSScriptRoot 'dist')
}
New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot 'dist\docs') -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'docs\NAS-VALIDIERUNG.md') -Destination (Join-Path $PSScriptRoot 'dist\docs')

Write-Host ''
Write-Host 'Fertig: dist\Lokale-Wissens-KI.exe' -ForegroundColor Green
Write-Host 'Kopie:  dist\KnowHow Tool v1.0.exe' -ForegroundColor Green
