Set-Location -Path "$PSScriptRoot\backend"
Get-CimInstance Win32_Process |
    Where-Object { $_.CommandLine -match [regex]::Escape("$PSScriptRoot\backend\.venv\Scripts\python.exe") -and $_.CommandLine -match "uvicorn app.main:app" } |
    ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
if (Test-Path ".env.local") {
    Get-Content ".env.local" | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
        }
    }
}
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    python -m venv .venv
    .venv\Scripts\python -m pip install -r requirements.txt
}
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
