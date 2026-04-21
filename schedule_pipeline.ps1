# =============================================================================
# ProcessEd Tender Engine - Windows Task Scheduler Setup
# Run this ONCE in PowerShell as Administrator to register 3x daily runs.
#
# Usage:
#   Right-click PowerShell -> Run as Administrator
#   cd C:\Users\bilal\tender_engine
#   .\schedule_pipeline.ps1
#
# Creates three scheduled tasks:
#   ProcessEd_Morning   -> 06:00 daily
#   ProcessEd_Midday    -> 13:00 daily
#   ProcessEd_Evening   -> 20:00 daily
#
# To remove all tasks later:
#   Unregister-ScheduledTask -TaskName "ProcessEd_Morning","ProcessEd_Midday","ProcessEd_Evening" -Confirm:$false
# =============================================================================

$PipelineDir  = "C:\Users\bilal\tender_engine"
$PythonExe    = "python"   # assumes python is on PATH; replace with full path if needed e.g. "C:\Python311\python.exe"
$LogDir       = "$PipelineDir\logs"
$TaskUser     = $env:USERNAME

# Create logs folder if it doesn't exist
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir | Out-Null
    Write-Host "Created logs folder: $LogDir"
}

# The command each task runs - pipes stdout+stderr to a dated log file
$Action = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c `"cd /d $PipelineDir && $PythonExe run_pipeline.py >> $LogDir\pipeline_%date:~-4,4%-%date:~-7,2%-%date:~0,2%.log 2>&1`""

$Settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -RestartCount 2 `
    -RestartInterval (New-TimeSpan -Minutes 5) `
    -StartWhenAvailable `
    -RunOnlyIfNetworkAvailable

$Principal = New-ScheduledTaskPrincipal `
    -UserId $TaskUser `
    -LogonType Interactive `
    -RunLevel Highest

# --- Morning 06:00 ---
$TriggerMorning = New-ScheduledTaskTrigger -Daily -At "06:00"
Register-ScheduledTask `
    -TaskName "ProcessEd_Morning" `
    -Action $Action `
    -Trigger $TriggerMorning `
    -Settings $Settings `
    -Principal $Principal `
    -Description "ProcessEd tender pipeline - morning run 06:00" `
    -Force | Out-Null
Write-Host "Registered: ProcessEd_Morning  (06:00 daily)"

# --- Midday 13:00 ---
$TriggerMidday = New-ScheduledTaskTrigger -Daily -At "13:00"
Register-ScheduledTask `
    -TaskName "ProcessEd_Midday" `
    -Action $Action `
    -Trigger $TriggerMidday `
    -Settings $Settings `
    -Principal $Principal `
    -Description "ProcessEd tender pipeline - midday run 13:00" `
    -Force | Out-Null
Write-Host "Registered: ProcessEd_Midday   (13:00 daily)"

# --- Evening 20:00 ---
$TriggerEvening = New-ScheduledTaskTrigger -Daily -At "20:00"
Register-ScheduledTask `
    -TaskName "ProcessEd_Evening" `
    -Action $Action `
    -Trigger $TriggerEvening `
    -Settings $Settings `
    -Principal $Principal `
    -Description "ProcessEd tender pipeline - evening run 20:00" `
    -Force | Out-Null
Write-Host "Registered: ProcessEd_Evening  (20:00 daily)"

Write-Host ""
Write-Host "All three tasks registered. Verifying..."
Write-Host ""

Get-ScheduledTask | Where-Object { $_.TaskName -like "ProcessEd_*" } | Format-Table TaskName, State, @{
    Name="NextRun"
    Expression={ (Get-ScheduledTaskInfo $_.TaskName).NextRunTime }
} -AutoSize

Write-Host ""
Write-Host "Done. Pipeline will run at 06:00, 13:00 and 20:00 every day."
Write-Host "Logs will be written to: $LogDir"
Write-Host ""
Write-Host "To test immediately (without waiting): python run_pipeline.py"
