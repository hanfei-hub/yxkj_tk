Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = root & "\desktop"
apiBase = shell.Environment("USER")("TK_SELECTION_API_BASE_URL")
If apiBase = "" Then
    shell.Environment("PROCESS")("TK_SELECTION_API_BASE_URL") = "http://120.26.207.89"
Else
    shell.Environment("PROCESS")("TK_SELECTION_API_BASE_URL") = apiBase
End If
cmd = """" & root & "\desktop\.venv\Scripts\pythonw.exe"" app\main.py"
shell.Run cmd, 1, False
