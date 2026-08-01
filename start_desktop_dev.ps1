$ErrorActionPreference = "Stop"
Set-Location -Path "$PSScriptRoot\desktop"
$env:TK_SELECTION_API_BASE_URL = "http://120.26.207.89:8002"
$python = "$PSScriptRoot\desktop\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "D:\python\python.exe"
}
& $python app\main.py
