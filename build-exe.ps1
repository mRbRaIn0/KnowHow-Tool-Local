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
& $python 'collect-licenses.py'
if ($LASTEXITCODE -ne 0) { throw 'Drittanbieter-Lizenzhinweise konnten nicht gesammelt werden.' }
& $python -m PyInstaller --noconfirm --clean 'Lokale-Wissens-KI.spec'
if ($LASTEXITCODE -ne 0) { throw 'Windows-Build fehlgeschlagen.' }
$hauptExe = Join-Path $PSScriptRoot 'dist\Lokale-Wissens-KI.exe'
$stableExe = Join-Path $PSScriptRoot 'dist\KnowHow Tool.exe'
$releaseExe = Join-Path $PSScriptRoot 'dist\KnowHow Tool v1.1.exe'
Copy-Item -LiteralPath $hauptExe -Destination $stableExe -Force
Copy-Item -LiteralPath $hauptExe -Destination $releaseExe -Force
foreach ($bundleDoc in @('README.md', 'KI.md', 'LICENSE', 'THIRD_PARTY_NOTICES.txt')) {
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot $bundleDoc) -Destination (Join-Path $PSScriptRoot 'dist')
}
$releaseFiles = @($stableExe) + @('README.md', 'KI.md', 'LICENSE', 'THIRD_PARTY_NOTICES.txt') | ForEach-Object {
    if ([IO.Path]::IsPathRooted($_)) { $_ } else { Join-Path $PSScriptRoot "dist\$_" }
}
$releaseZip = Join-Path $PSScriptRoot 'dist\KnowHow-Tool-v1.1-Windows.zip'
Compress-Archive -LiteralPath $releaseFiles -DestinationPath $releaseZip -Force
$zipArchive = [IO.Compression.ZipFile]::Open($releaseZip, [IO.Compression.ZipArchiveMode]::Update)
try {
    [IO.Compression.ZipFileExtensions]::CreateEntryFromFile(
        $zipArchive, (Join-Path $PSScriptRoot 'docs\RELEASE-V1.1.md'), 'docs/RELEASE-V1.1.md') | Out-Null
} finally {
    $zipArchive.Dispose()
}
Get-FileHash -LiteralPath $stableExe, $releaseZip -Algorithm SHA256 |
    ForEach-Object { "$($_.Hash)  $([IO.Path]::GetFileName($_.Path))" } |
    Set-Content -LiteralPath (Join-Path $PSScriptRoot 'dist\SHA256SUMS.txt') -Encoding ascii
Write-Host ''
Write-Host 'Fertig: dist\Lokale-Wissens-KI.exe' -ForegroundColor Green
Write-Host 'Kopie:  dist\KnowHow Tool.exe' -ForegroundColor Green
Write-Host 'Paket:  dist\KnowHow-Tool-v1.1-Windows.zip' -ForegroundColor Green
