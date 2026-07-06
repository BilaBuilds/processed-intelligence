Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$py = "python"

Write-Host "Running Agent Operating System..."

$backupPath = & $py scripts/backup_code_to_text.py

$outreachValidationOutput = "skipped"
if ((Test-Path "scripts/generate_outreach.py") -and (Test-Path "scripts/validate_outreach_quality.py")) {
  # Keep outreach outputs current before task generation.
  # Deterministic mode: no AI enrichment, no external calls.
  & $py scripts/generate_outreach.py --save --no-ai

  $outreachValidationOutput = & $py scripts/validate_outreach_quality.py
  $outreachValidationExit = $LASTEXITCODE
  if ($outreachValidationExit -ne 0) {
    Write-Host ""
    Write-Host "Outreach quality validation failed; stopping Agent OS run."
    Write-Host ("Outreach QC: {0}" -f ($outreachValidationOutput -as [string]))
    exit $outreachValidationExit
  }
}

& $py scripts/build_agent_state.py
& $py scripts/create_agent_tasks.py
& $py scripts/run_agent_ops.py
& $py scripts/build_daily_sync.py

$validationOutput = & $py scripts/validate_agent_ops.py
$validationExit = $LASTEXITCODE

$statePath = Join-Path $repoRoot "agent_ops\\state\\current_state.json"
$runId = ""
if (Test-Path $statePath) {
  $state = Get-Content $statePath -Raw | ConvertFrom-Json
  $runId = $state.run_id
}

$taskSummaryPath = Join-Path $repoRoot "agent_ops\\state\\task_generation_summary.json"
$tasksCreated = 0
if (Test-Path $taskSummaryPath) {
  $taskSummary = Get-Content $taskSummaryPath -Raw | ConvertFrom-Json
  $tasksCreated = [int]$taskSummary.created_count
}

$tasksCompleted = 0
$doneDir = Join-Path $repoRoot "agent_ops\\tasks\\done"
if (Test-Path $doneDir) {
  $tasksCompleted = (Get-ChildItem $doneDir -Filter "*.json" -ErrorAction SilentlyContinue | Measure-Object).Count
}

$reportPath = Join-Path $repoRoot ("agent_ops\\reports\\daily\\daily_sync_{0}.md" -f (Get-Date -Format "yyyy-MM-dd"))

Write-Host ""
Write-Host ("Run ID: {0}" -f ($runId -as [string]))
Write-Host ("Backup: {0}" -f ($backupPath -as [string]))
Write-Host ("Tasks created: {0}" -f $tasksCreated)
Write-Host ("Tasks completed: {0}" -f $tasksCompleted)
Write-Host ("Report: {0}" -f $reportPath)
Write-Host ("Outreach QC: {0}" -f ($outreachValidationOutput -as [string]))
Write-Host ("Validation: {0}" -f ($validationOutput -as [string]))

exit $validationExit
