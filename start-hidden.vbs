' Startet bevorzugt die gebaute EXE ohne sichtbares Konsolenfenster.
' Ohne Build bleibt start.bat als Rueckfall erhalten.
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
ordner = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = ordner
exePfad = ordner & "\dist\Lokale-Wissens-KI.exe"
If fso.FileExists(exePfad) Then
    shell.Run """" & exePfad & """", 0, False
Else
    shell.Run """" & ordner & "\start.bat""", 0, False
End If
