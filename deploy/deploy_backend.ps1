param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,

    [string]$User = "root",
    [string]$KeyPath = "D:\yxkj_tk\backend\runtime\keys\yxkj_deploy.pem",
    [string]$RemoteDir = "/opt/tk-selection"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Archive = Join-Path $env:TEMP ("tk-selection-backend-" + [guid]::NewGuid().ToString("N") + ".tar.gz")

Push-Location $Root
try {
    $files = @("backend", "deploy")
    tar --exclude="backend/.venv" --exclude="backend/runtime" --exclude="backend/data/*.db" --exclude="backend/data/*.sqlite*" --exclude="*.log" -czf $Archive @files
} finally {
    Pop-Location
}

ssh -i $KeyPath "${User}@${HostName}" "mkdir -p $RemoteDir"
scp -i $KeyPath $Archive "${User}@${HostName}:/tmp/tk-selection-backend.tar.gz"
ssh -i $KeyPath "${User}@${HostName}" "tar -xzf /tmp/tk-selection-backend.tar.gz -C $RemoteDir && sed -i 's/\r$//' $RemoteDir/deploy/install_backend_linux.sh $RemoteDir/deploy/tk-selection-backend.service && bash $RemoteDir/deploy/install_backend_linux.sh"

Remove-Item -LiteralPath $Archive -Force -ErrorAction SilentlyContinue
Write-Host "Uploaded backend to ${User}@${HostName}:${RemoteDir}"
