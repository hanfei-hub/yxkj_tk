param(
    [Parameter(Mandatory = $true)]
    [string]$ApiBaseUrl
)

[Environment]::SetEnvironmentVariable("TK_SELECTION_API_BASE_URL", $ApiBaseUrl.TrimEnd("/"), "User")
Write-Host "TK_SELECTION_API_BASE_URL set to $($ApiBaseUrl.TrimEnd('/'))"
Write-Host "Restart the desktop app to use the server backend."
