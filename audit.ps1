param(
    [int]$Runs = 2,
    [switch]$ForceNotify
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Test-WebhookLooksValid([string]$value) {
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $false
    }
    if ($value.Contains("<") -or $value.Contains(">")) {
        return $false
    }
    if ($value.ToUpperInvariant().Contains("PASTE")) {
        return $false
    }
    if ($value.Contains("REAL_ROTATED_WEBHOOK") -or $value.Contains("NEW_TOKEN")) {
        return $false
    }
    return $value -match "^https://discord\.com/api/webhooks/[^/]+/.+$"
}

function Initialize-WebhookEnv {
    $sessionWebhook = $env:TENDER_WEBHOOK_URL
    $userWebhook = [Environment]::GetEnvironmentVariable("TENDER_WEBHOOK_URL", "User")

    if (Test-WebhookLooksValid $sessionWebhook) {
        return
    }

    if (Test-WebhookLooksValid $userWebhook) {
        $env:TENDER_WEBHOOK_URL = $userWebhook
        Write-Host "Loaded TENDER_WEBHOOK_URL from user environment for this audit session."
    }
}

function Resolve-Python {
    $pythonCmd = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCmd) {
        return "python"
    }

    $fallback = "C:\Users\bilal\AppData\Local\Python\pythoncore-3.14-64\python.exe"
    if (Test-Path $fallback) {
        return $fallback
    }

    throw "Python not found in PATH and fallback path not found."
}

function Mask-Webhook([string]$value) {
    if ([string]::IsNullOrWhiteSpace($value)) {
        return "<unset>"
    }
    if ($value.Length -lt 20) {
        return "<set>"
    }
    return "{0}...{1}" -f $value.Substring(0, 32), $value.Substring($value.Length - 8)
}

function Run-Pipeline([string]$pythonExe, [string]$label) {
    Write-Host ""
    Write-Host "=== $label ==="
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $output = & $pythonExe run_pipeline.py *>&1
    $exitCode = $LASTEXITCODE
    $ErrorActionPreference = $oldPreference

    $outputLines = @($output | ForEach-Object {
        if ($_ -is [System.Management.Automation.ErrorRecord]) {
            $_.ToString()
        } else {
            $_.ToString()
        }
    })
    $outputLines | ForEach-Object { Write-Host $_ }

    $runId = $null
    $runLine = $outputLines | Select-String -Pattern "run:\s+([0-9_-]+)" | Select-Object -First 1
    if ($runLine) {
        $runId = $runLine.Matches[0].Groups[1].Value
    }

    return [pscustomobject]@{
        Label = $label
        RunId = $runId
        ExitCode = $exitCode
        RawOutput = $outputLines
    }
}

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectRoot
Initialize-WebhookEnv

$pythonExe = Resolve-Python
$results = @()

for ($i = 1; $i -le $Runs; $i++) {
    $results += Run-Pipeline -pythonExe $pythonExe -label ("Pipeline Run {0}/{1}" -f $i, $Runs)
}

if ($ForceNotify) {
    Write-Host ""
    Write-Host "=== Forced Notify Preparation ==="
    Remove-Item "state\sent_log.sqlite" -ErrorAction SilentlyContinue
    Write-Host "Removed state\sent_log.sqlite (if it existed)."
    $results += Run-Pipeline -pythonExe $pythonExe -label "Pipeline Forced Notify Run"
}

$reportRows = @()
foreach ($r in $results) {
    if (-not $r.RunId) {
        $reportRows += [pscustomobject]@{
            RunLabel = $r.Label
            RunId = "<unknown>"
            Status = "unknown"
            Notify = "unknown"
            NewCount = "unknown"
            Duration = "unknown"
            Manifest = "<missing>"
        }
        continue
    }

    $manifestPath = Join-Path $projectRoot ("data\runs\{0}\run_manifest.json" -f $r.RunId)
    if (-not (Test-Path $manifestPath)) {
        $reportRows += [pscustomobject]@{
            RunLabel = $r.Label
            RunId = $r.RunId
            Status = "manifest_missing"
            Notify = "manifest_missing"
            NewCount = "manifest_missing"
            Duration = "manifest_missing"
            Manifest = $manifestPath
        }
        continue
    }

    $manifest = Get-Content -Raw $manifestPath | ConvertFrom-Json
    $reportRows += [pscustomobject]@{
        RunLabel = $r.Label
        RunId = $manifest.run_id
        Status = $manifest.status
        Notify = $manifest.steps.notify.status
        NewCount = $manifest.new_count
        Duration = $manifest.total_duration_s
        Manifest = $manifestPath
    }
}

$lastFtsRun = "<missing>"
if (Test-Path "data\last_fts_run.txt") {
    $lastFtsRun = (Get-Content "data\last_fts_run.txt" -ErrorAction SilentlyContinue | Select-Object -First 1)
}

$sentLogCount = "<missing>"
if (Test-Path "state\sent_log.sqlite") {
    $sentLogCount = (& $pythonExe -c "import sqlite3; c=sqlite3.connect('state/sent_log.sqlite'); print(c.execute('select count(*) from sent_log').fetchone()[0]); c.close()" 2>$null)
}

$runIdCollision = "no"
$knownRunIds = @($reportRows | ForEach-Object { $_.RunId } | Where-Object { $_ -and $_ -ne "<unknown>" })
if ($knownRunIds.Count -gt 0) {
    $dupes = $knownRunIds | Group-Object | Where-Object { $_.Count -gt 1 }
    if ($dupes) {
        $runIdCollision = "yes"
    }
}

Write-Host ""
Write-Host "======================================="
Write-Host "Project BigBoi Audit Report"
Write-Host "======================================="
Write-Host ("Timestamp (UTC): {0}" -f (Get-Date).ToUniversalTime().ToString("yyyy-MM-ddTHH:mm:ssZ"))
Write-Host ("Project Root: {0}" -f $projectRoot)
Write-Host ("Python: {0}" -f $pythonExe)
Write-Host ("Webhook: {0}" -f (Mask-Webhook $env:TENDER_WEBHOOK_URL))
Write-Host ("Runs Requested: {0}" -f $Runs)
Write-Host ("Force Notify: {0}" -f $ForceNotify.IsPresent)
Write-Host ""
Write-Host "Run Results:"
$reportRows | Format-Table RunLabel, RunId, Status, Notify, NewCount, Duration -AutoSize
Write-Host ""
Write-Host ("Run ID collision detected: {0}" -f $runIdCollision)
Write-Host ("last_fts_run.txt: {0}" -f $lastFtsRun)
Write-Host ("sent_log row count: {0}" -f $sentLogCount)
Write-Host ""
Write-Host "Manifest Paths:"
$reportRows | ForEach-Object { Write-Host ("- {0}" -f $_.Manifest) }
Write-Host ""
Write-Host "Done."
