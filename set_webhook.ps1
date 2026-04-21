param(
    [switch]$SkipTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

Write-Host "Set Discord webhook for ProcessEd (user-level env var)."
$url = Read-Host "Paste full Discord webhook URL"

if ([string]::IsNullOrWhiteSpace($url)) {
    throw "Webhook URL cannot be empty."
}

if ($url -notmatch "^https://discord\.com/api/webhooks/[^/]+/.+$") {
    throw "Webhook URL format is invalid."
}

[Environment]::SetEnvironmentVariable("TENDER_WEBHOOK_URL", $url, "User")
${env:TENDER_WEBHOOK_URL} = $url
Write-Host "Saved TENDER_WEBHOOK_URL to user environment."
Write-Host "Applied TENDER_WEBHOOK_URL to current session as well."

if (-not $SkipTest) {
    Write-Host ""
    Write-Host "Sending Discord webhook test message..."
    $payload = @{
        content = "ProcessEd webhook check: connected at $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
    } | ConvertTo-Json

    try {
        $resp = Invoke-WebRequest -Uri $url -Method Post -Body $payload -ContentType "application/json" -TimeoutSec 12
        if ($resp.StatusCode -ge 200 -and $resp.StatusCode -lt 300) {
            Write-Host "Discord test succeeded (HTTP $($resp.StatusCode))." -ForegroundColor Green
        } else {
            Write-Host "Discord test returned HTTP $($resp.StatusCode)." -ForegroundColor Yellow
        }
    } catch {
        Write-Host "Discord test failed: $($_.Exception.Message)" -ForegroundColor Red
        Write-Host "Tip: webhook may be rotated/deleted, or blocked in this runtime." -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "If you run this script via 'powershell -File', that current session is a child process."
Write-Host "To sync your open terminal, run:"
Write-Host '$env:TENDER_WEBHOOK_URL = [Environment]::GetEnvironmentVariable("TENDER_WEBHOOK_URL","User")'
/