# Legt eine Desktop-Verknuepfung "KnowHow Tool" mit dem Programm-Icon an.
# Einmal ausfuehren - danach reicht ein Doppelklick.
#
#   .\Verknuepfung-erstellen.ps1                 startet bevorzugt die EXE, sonst start.bat
#   .\Verknuepfung-erstellen.ps1 -MitFenster     startet start.bat sichtbar (zum Mitlesen)
#   .\Verknuepfung-erstellen.ps1 -Exe            zeigt auf dist\Lokale-Wissens-KI.exe
#   .\Verknuepfung-erstellen.ps1 -Name "KI"      anderer Name auf dem Desktop

[CmdletBinding()]
param(
    [switch]$MitFenster,
    [switch]$Exe,
    [string]$Name = "KnowHow Tool"
)

$ErrorActionPreference = "Stop"
$projekt = $PSScriptRoot
$desktop = [Environment]::GetFolderPath("Desktop")
$linkPfad = Join-Path $desktop ($Name + ".lnk")

# --- Icon sicherstellen -------------------------------------------------
$icon = Join-Path $projekt "assets\Lokale-Wissens-KI.ico"
if (-not (Test-Path -LiteralPath $icon)) {
    $python = Join-Path $projekt ".venv\Scripts\python.exe"
    $erzeuger = Join-Path $projekt "assets\icon_erzeugen.py"
    if ((Test-Path -LiteralPath $python) -and (Test-Path -LiteralPath $erzeuger)) {
        Write-Host "Icon fehlt - wird erzeugt ..." -ForegroundColor Yellow
        & $python $erzeuger | Out-Null
    }
}

# --- Ziel bestimmen -----------------------------------------------------
if ($Exe) {
    $ziel = Join-Path $projekt "dist\Lokale-Wissens-KI.exe"
    if (-not (Test-Path -LiteralPath $ziel)) {
        throw "dist\Lokale-Wissens-KI.exe gibt es noch nicht. Erst .\build-exe.ps1 ausfuehren - oder die Verknuepfung ohne -Exe anlegen."
    }
    $argumente = ""
    $beschreibung = "KnowHow Tool (eigenstaendige Anwendung)"
}
elseif ($MitFenster) {
    # Direkt auf die Batchdatei: Konsolenfenster bleibt sichtbar.
    $ziel = Join-Path $projekt "start.bat"
    $argumente = ""
    $beschreibung = "KnowHow Tool (mit Konsolenfenster)"
}
else {
    # Standard: aktuelle EXE (mit start.bat als Rueckfall) ohne schwarzes Fenster.
    $starter = Join-Path $projekt "start-hidden.vbs"
    if (-not (Test-Path -LiteralPath $starter)) {
        throw "start-hidden.vbs fehlt im Projektordner."
    }
    $ziel = Join-Path $env:SystemRoot "System32\wscript.exe"
    $argumente = '"' + $starter + '"'
    $beschreibung = "KnowHow Tool (aktuelle EXE, stiller Start)"
}

# --- Verknuepfung schreiben --------------------------------------------
$shell = New-Object -ComObject WScript.Shell
$verknuepfung = $shell.CreateShortcut($linkPfad)
$verknuepfung.TargetPath = $ziel
if ($argumente) { $verknuepfung.Arguments = $argumente }
$verknuepfung.WorkingDirectory = $projekt
$verknuepfung.Description = $beschreibung
if (Test-Path -LiteralPath $icon) {
    $verknuepfung.IconLocation = "$icon,0"
}
else {
    Write-Host "Hinweis: Kein Icon gefunden - Windows nutzt das Standardsymbol." -ForegroundColor Yellow
}
$verknuepfung.Save()

Write-Host ""
Write-Host "Verknuepfung angelegt:" -ForegroundColor Green
Write-Host "  $linkPfad"
Write-Host "  Ziel:  $ziel"
if (Test-Path -LiteralPath $icon) { Write-Host "  Icon:  $icon" }
Write-Host ""
Write-Host "Doppelklick startet bevorzugt die aktuelle EXE, das Backend und das App-Fenster."
Write-Host ""
