Set shell = CreateObject("WScript.Shell")
root = CreateObject("Scripting.FileSystemObject").GetParentFolderName(WScript.ScriptFullName)
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & root & "\start_backend.ps1" & """", 0, False
WScript.Sleep 3000
shell.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & root & "\start_desktop.ps1" & """", 0, False
