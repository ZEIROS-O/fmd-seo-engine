# Registers (or updates) the Windows Task Scheduler entry for the FMD SEO
# engine's daily brain tick. Idempotent: -Force replaces an existing task.
# Mirrors ZEIROS register_ingest_task.ps1.
#
# Run once from WSL (unelevated is fine):
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "\\wsl.localhost\Ubuntu-22.04\home\lucascoh\fmd-seo-engine\bin\register-fmd-seo-task.ps1"
#
# The engine lives on WSL ext4 (~/fmd-seo-engine). The launcher VBS is deployed
# to a Windows-local path so the 04:00 cold-start never depends on WSL serving
# a UNC file to wscript before WSL is running — the VBS itself starts WSL via
# wsl.exe. This script self-deploys the canonical repo copy on every run.
#
# Schedule: daily 04:00 local — deliberately AFTER the 03:30 ZEIROS ingest, so
# the two overnight WSL jobs don't collide on shared subscription auth. The tick
# is cheap (a few Semrush API calls + assess) and idempotent (checks are
# cadence-gated), so a double-fire or a missed day is harmless.
# StartWhenAvailable runs a missed trigger when the machine is next awake.
# WakeToRun stays off — an SEO check can wait a day; waking the machine cannot.
#
# The task runs sync + assess only. It NEVER publishes, deploys, or sends
# (CONTRACT.md). A non-zero exit means assess found a critical finding or gate
# drift worth a session run — surfaced in the log, not acted on automatically.

$deployDir = 'C:\Users\lucas\Scripts'
$deployedVbs = Join-Path $deployDir 'run-fmd-seo-cron-hidden.vbs'
New-Item -ItemType Directory -Force -Path $deployDir | Out-Null
Copy-Item -Force (Join-Path $PSScriptRoot 'run-fmd-seo-cron-hidden.vbs') $deployedVbs

$action = New-ScheduledTaskAction -Execute 'wscript.exe' `
    -Argument ('"' + $deployedVbs + '"')

$trigger = New-ScheduledTaskTrigger -Daily -At 4:00AM

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -MultipleInstances IgnoreNew `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

Register-ScheduledTask `
    -TaskName 'FMD-SEO-Daily' `
    -Description 'FMD SEO engine daily brain tick (WSL, hidden via run-fmd-seo-cron-hidden.vbs): headless Semrush sync + threshold assess. Never publishes/deploys/sends. Logs to fmd-seo-engine/.run/cron/.' `
    -Action $action `
    -Trigger $trigger `
    -Settings $settings `
    -Force

Get-ScheduledTask -TaskName 'FMD-SEO-Daily' | Format-List TaskName, State
(Get-ScheduledTaskInfo -TaskName 'FMD-SEO-Daily').NextRunTime
