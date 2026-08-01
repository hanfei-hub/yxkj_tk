Set-Location -Path "$PSScriptRoot\desktop"
$env:TK_SELECTION_API_BASE_URL = "http://120.26.207.89"
$python = "$PSScriptRoot\desktop\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "D:\python\python.exe"
}
Get-CimInstance Win32_Process |
    Where-Object {
        ($_.CommandLine -match [regex]::Escape("$PSScriptRoot\desktop\.venv\Scripts\python.exe") -and $_.CommandLine -match "app\\main.py|app/main.py") -or
        ($_.CommandLine -match "codex-primary-runtime" -and $_.CommandLine -match "app\\main.py|app/main.py")
    } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
& $python app\main.py
