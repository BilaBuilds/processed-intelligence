param(
    [switch]$ForceRun
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$PipelinePath = Join-Path $ProjectRoot "run_pipeline.py"
$RunsDir = Join-Path $ProjectRoot "data\runs"

if (-not (Test-Path -LiteralPath $PipelinePath)) {
    Write-Host "[FATAL] run_pipeline.py not found at: $PipelinePath" -ForegroundColor Red
    exit 1
}

if ([string]::IsNullOrWhiteSpace($env:TENDER_BASE_DIR)) {
    $env:TENDER_BASE_DIR = $ProjectRoot
}

function Resolve-PythonCommand {
    if (Get-Command python -ErrorAction SilentlyContinue) {
        return @("python")
    }
    if (Get-Command py -ErrorAction SilentlyContinue) {
        return @("py", "-3")
    }
    throw "Python not found. Install Python 3 and ensure 'python' or 'py' is on PATH."
}

function Test-Endpoint([string]$Url) {
    try {
        $resp = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 10 -UseBasicParsing
        return @{
            ok     = $true
            status = [int]$resp.StatusCode
            error  = ""
        }
    } catch {
        $statusCode = -1
        try {
            if ($_.Exception.Response.StatusCode) {
                $statusCode = [int]$_.Exception.Response.StatusCode
            }
        } catch {}
        return @{
            ok     = $false
            status = $statusCode
            error  = $_.Exception.Message
        }
    }
}

function Get-LatestManifestPath([string]$RootRunsDir) {
    if (-not (Test-Path -LiteralPath $RootRunsDir)) {
        return $null
    }
    $latestRun = Get-ChildItem -LiteralPath $RootRunsDir -Directory |
        Sort-Object Name -Descending |
        Select-Object -First 1
    if (-not $latestRun) {
        return $null
    }
    $manifest = Join-Path $latestRun.FullName "run_manifest.json"
    if (Test-Path -LiteralPath $manifest) {
        return $manifest
    }
    return $null
}

Write-Host ""
Write-Host "=== Tender Engine: robust local run ===" -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot"
Write-Host "TENDER_BASE_DIR: $($env:TENDER_BASE_DIR)"

$pythonCmd = @(Resolve-PythonCommand)
Write-Host "Python command: $($pythonCmd -join ' ')"

$discordWebhook = $env:TENDER_WEBHOOK_URL
if ([string]::IsNullOrWhiteSpace($discordWebhook)) {
    $discordWebhook = [Environment]::GetEnvironmentVariable("TENDER_WEBHOOK_URL", "User")
}
if ([string]::IsNullOrWhiteSpace($discordWebhook)) {
    Write-Host "[WARN] TENDER_WEBHOOK_URL is not set in this shell or user environment. Notify may skip/fail when new tenders exist." -ForegroundColor Yellow
} else {
    $maskedWebhook = if ($discordWebhook.Length -gt 40) { $discordWebhook.Substring(0, 40) + "..." } else { "[set]" }
    Write-Host "Discord webhook: configured ($maskedWebhook)"
}

$fts = Test-Endpoint "https://www.find-tender.service.gov.uk"
$cf = Test-Endpoint "https://www.contractsfinder.service.gov.uk"

Write-Host ""
Write-Host "Network preflight:"
Write-Host ("  FTS: {0}" -f ($(if ($fts.ok) { "OK ($($fts.status))" } else { "FAILED ($($fts.error))" })))
Write-Host ("  Contracts Finder: {0}" -f ($(if ($cf.ok) { "OK ($($cf.status))" } else { "FAILED ($($cf.error))" })))

if (-not $ForceRun -and -not $fts.ok -and -not $cf.ok) {
    Write-Host ""
    Write-Host "[SKIP] Both upstream endpoints failed preflight. Likely restricted egress/sandbox in this runtime." -ForegroundColor Yellow
    Write-Host "Use -ForceRun to attempt anyway."
    exit 0
}

Write-Host ""
Write-Host "Running pipeline..." -ForegroundColor Cyan
Push-Location $ProjectRoot
try {
    $pythonExe = $pythonCmd[0]
    $pythonArgs = @()
    if ($pythonCmd.Length -gt 1) {
        $pythonArgs = $pythonCmd[1..($pythonCmd.Length - 1)]
    }
    & $pythonExe @pythonArgs $PipelinePath
    $pipelineExit = $LASTEXITCODE
} finally {
    Pop-Location
}

Write-Host ""
$manifestPath = Get-LatestManifestPath $RunsDir
if ($manifestPath) {
    try {
        $manifest = Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
        Write-Host "Latest manifest: $manifestPath"
        Write-Host ("Run ID: {0}" -f $manifest.run_id)
        Write-Host ("Status: {0}" -f $manifest.status)
        Write-Host ("New count: {0}" -f $manifest.new_count)
        $notifyStatus = $manifest.steps.notify.status
        Write-Host ("Notify: {0}" -f $notifyStatus)

        if ($manifest.steps.notify.channels.discord) {
            Write-Host ("Discord channel: {0}" -f $manifest.steps.notify.channels.discord)
        }

        if ($notifyStatus -in @("failed", "error")) {
            Write-Host "[ACTION] Discord notify failed. Validate webhook with: powershell -NoProfile -ExecutionPolicy Bypass -File `"$ProjectRoot\set_webhook.ps1`"" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "[WARN] Could not parse latest manifest: $($_.Exception.Message)" -ForegroundColor Yellow
    }
} else {
    Write-Host "[WARN] No manifest found under $RunsDir"
}

if ($pipelineExit -ne 0) {
    Write-Host ""
    Write-Host "[FAIL] Pipeline exited with code $pipelineExit" -ForegroundColor Red
    exit $pipelineExit
}

Write-Host ""
Write-Host "[OK] Pipeline run completed." -ForegroundColor Green
exit 0
