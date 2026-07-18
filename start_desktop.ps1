Set-Location -Path "$PSScriptRoot\desktop"
if (-not $env:TK_SELECTION_API_BASE_URL) {
    $userApiBase = [Environment]::GetEnvironmentVariable("TK_SELECTION_API_BASE_URL", "User")
    $env:TK_SELECTION_API_BASE_URL = if ($userApiBase) { $userApiBase } else { "http://127.0.0.1:8000" }
}
Get-CimInstance Win32_Process |
    Where-Object {
        ($_.CommandLine -match [regex]::Escape("$PSScriptRoot\desktop\.venv\Scripts\python.exe") -and $_.CommandLine -match "app\\main.py|app/main.py") -or
        ($_.CommandLine -match "codex-primary-runtime" -and $_.CommandLine -match "app\\main.py|app/main.py")
    } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
& "$PSScriptRoot\desktop\.venv\Scripts\python.exe" app\main.py
