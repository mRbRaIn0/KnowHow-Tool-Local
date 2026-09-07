param(
    [string]$Python = '',
    [switch]$WithoutModels
)
$ErrorActionPreference = 'Stop'
$doclingEnv = Join-Path $PSScriptRoot '.venv-docling'
$doclingModels = Join-Path $PSScriptRoot 'data\models\docling'
if (-not $Python) {
    $Python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
}
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
    throw 'Python fehlt. -Python mit dem absoluten Pfad zu einer installierten Python-3.12-python.exe angeben.'
}
Write-Host 'Explizite Einrichtung: Python-Pakete und ggf. Modelle werden aus dem Internet geladen.'
if (-not (Test-Path -LiteralPath (Join-Path $doclingEnv 'Scripts\python.exe'))) {
    & $Python -m venv $doclingEnv
    if ($LASTEXITCODE -ne 0) { throw 'Docling-Umgebung konnte nicht erstellt werden.' }
}
$doclingPython = Join-Path $doclingEnv 'Scripts\python.exe'
& $doclingPython -m pip install -r (Join-Path $PSScriptRoot 'requirements-docling.txt')
if ($LASTEXITCODE -ne 0) { throw 'Docling-Installation fehlgeschlagen.' }
if (-not $WithoutModels) {
    & (Join-Path $doclingEnv 'Scripts\docling-tools.exe') models download layout tableformer easyocr --easyocr-lang de --easyocr-lang en --output-dir $doclingModels
    if ($LASTEXITCODE -ne 0) { throw 'Modelle konnten nicht vollständig heruntergeladen werden.' }
}
Write-Host 'In NAS-Bibliothek > Quellen & Sicherung > Docling einrichten eintragen:'
Write-Host "Python: $doclingPython"
Write-Host "Modelle: $doclingModels"
