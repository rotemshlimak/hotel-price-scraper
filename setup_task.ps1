# Creates a Windows Scheduled Task for daily price checks.
# Run once in PowerShell (as your user):
#   .\setup_task.ps1
#   .\setup_task.ps1 -StartTime "08:00"
#   .\setup_task.ps1 -IntervalHours 6   # optional: repeat every N hours instead of daily

param(
    [string]$StartTime = "08:00",
    [int]$IntervalHours = 0
)

$ErrorActionPreference = "Stop"
$TaskName = "HotelPriceScraper"
$RepoRoot = $PSScriptRoot
$BatchFile = Join-Path $RepoRoot "run_api.bat"

if (-not (Test-Path $BatchFile)) {
    throw "run_api.bat not found at $BatchFile"
}

$action = New-ScheduledTaskAction -Execute $BatchFile -WorkingDirectory $RepoRoot

if ($IntervalHours -gt 0) {
    $trigger = New-ScheduledTaskTrigger -Once -At $StartTime `
        -RepetitionInterval (New-TimeSpan -Hours $IntervalHours) `
        -RepetitionDuration ([TimeSpan]::MaxValue)
    $scheduleDesc = "every $IntervalHours hours (first at $StartTime)"
} else {
    $trigger = New-ScheduledTaskTrigger -Daily -At $StartTime
    $scheduleDesc = "daily at $StartTime"
}

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

Register-ScheduledTask `
    -TaskName $TaskName `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Description "Daily Marriott price check; emails only when price drops" `
    -Force

Write-Host "Scheduled task '$TaskName' created."
Write-Host "  Runs: $scheduleDesc"
Write-Host "  Command: $BatchFile"
Write-Host ""
Write-Host "Before the first run:"
Write-Host "  1. Fill in .env (STAYAPI_API_KEY, GMAIL_APP_PASSWORD)"
Write-Host "  2. Test email:  python emailer.py"
Write-Host "  3. Test run:    python run_api.py  (first run saves baseline, no email)"
Write-Host ""
Write-Host "Manage in Task Scheduler (taskschd.msc) or:"
Write-Host "  Start now:  Start-ScheduledTask -TaskName $TaskName"
Write-Host "  Remove:     Unregister-ScheduledTask -TaskName $TaskName -Confirm:`$false"
