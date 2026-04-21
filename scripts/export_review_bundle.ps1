param(
    [string]$OutDir = "exports"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path | Split-Path -Parent
Set-Location $projectRoot

$timestamp = (Get-Date).ToString("yyyyMMdd_HHmmss")
$bundleRoot = Join-Path $projectRoot $OutDir
$bundleDir = Join-Path $bundleRoot ("process_ed_review_bundle_" + $timestamp)
$zipPath = "$bundleDir.zip"

New-Item -ItemType Directory -Path $bundleDir -Force | Out-Null

$files = @(
    "run_pipeline.py",
    "src\select.py",
    "src\decision.py",
    "src\dedupe.py",
    "src\notify\discord.py",
    "src\leads_compliance.py",
    "tests\test_select_filters.py",
    "tests\test_decision.py",
    "tests\test_dedupe.py",
    "tests\test_leads_compliance.py",
    "docs\PROCESS_ED_EXECUTION_PLAN_V1.md",
    "docs\PROCESS_ED_COMPLIANCE_AUDIT_2026-03-31.md",
    "docs\PROCESS_ED_EXTERNAL_REVIEW_PACK.md",
    "docs\PROCESS_ED_REVIEW_PROMPT_CLAUDE.md",
    "docs\PROCESS_ED_REVIEW_PROMPT_GEMINI.md"
)

foreach ($rel in $files) {
    $src = Join-Path $projectRoot $rel
    if (-not (Test-Path $src)) {
        throw "Missing required file: $rel"
    }
    $dest = Join-Path $bundleDir $rel
    $destParent = Split-Path -Parent $dest
    if (-not (Test-Path $destParent)) {
        New-Item -ItemType Directory -Path $destParent -Force | Out-Null
    }
    Copy-Item -LiteralPath $src -Destination $dest -Force
}

if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -Path (Join-Path $bundleDir "*") -DestinationPath $zipPath -CompressionLevel Optimal -Force

Write-Host "Bundle directory: $bundleDir"
Write-Host "Bundle zip:       $zipPath"
Write-Host "Included files:"
$files | ForEach-Object { Write-Host " - $_" }

