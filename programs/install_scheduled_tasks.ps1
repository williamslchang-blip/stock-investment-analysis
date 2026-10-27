param(
    [string]$MorningTime = "08:30",
    [string]$EveningTime = "20:30"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Launcher = Join-Path $PSScriptRoot "run_daily_investment_automation.ps1"
$PowerShell = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe"
$Days = @("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
$UserId = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

if (-not (Test-Path -LiteralPath $Launcher)) {
    throw "Scheduled-task launcher was not found: $Launcher"
}

$Settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Hours 2) `
    -MultipleInstances IgnoreNew

$Principal = New-ScheduledTaskPrincipal `
    -UserId $UserId `
    -LogonType Interactive `
    -RunLevel Limited

$Definitions = @(
    @{
        Name = "AutomatedInvestment-MorningReport"
        Time = $MorningTime
        Mode = "morning"
        Description = "Generate the two daily investment PDF reports on weekdays."
    },
    @{
        Name = "AutomatedInvestment-EveningReview"
        Time = $EveningTime
        Mode = "evening"
        Description = "Review morning selections after the close without single-day automatic reweighting."
    }
)

foreach ($Definition in $Definitions) {
    $Action = New-ScheduledTaskAction `
        -Execute $PowerShell `
        -Argument "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$Launcher`" -Mode $($Definition.Mode)" `
        -WorkingDirectory $ProjectRoot
    $Trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek $Days -At $Definition.Time
    $Task = New-ScheduledTask `
        -Action $Action `
        -Trigger $Trigger `
        -Settings $Settings `
        -Principal $Principal `
        -Description $Definition.Description
    Register-ScheduledTask -TaskName $Definition.Name -InputObject $Task -Force | Out-Null
}

Get-ScheduledTask -TaskName "AutomatedInvestment-*" |
    ForEach-Object {
        $Info = Get-ScheduledTaskInfo -TaskName $_.TaskName
        [pscustomobject]@{
            TaskName = $_.TaskName
            State = $_.State
            NextRunTime = $Info.NextRunTime
            LastTaskResult = $Info.LastTaskResult
        }
    }
