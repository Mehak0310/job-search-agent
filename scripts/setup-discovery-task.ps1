[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$Register,
    [switch]$CatchUp,
    [ValidatePattern('^([01][0-9]|2[0-3]):[0-5][0-9]$')][string]$IndiaTime = '08:00',
    [string]$TaskName = 'AIJobSearchDiscovery2A'
)
$ErrorActionPreference = 'Stop'
$workspacePath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$pythonPath = Join-Path $workspacePath '.venv\Scripts\python.exe'
$configPath = Join-Path $workspacePath 'config\discovery.json'
$databasePath = Join-Path $workspacePath 'data\jobs.sqlite3'
if (-not (Test-Path -LiteralPath $pythonPath) -or -not (Test-Path -LiteralPath $configPath)) {
    throw 'Project Python or discovery configuration is missing.'
}
$taskDescription = "Public job discovery for $workspacePath (Milestone 2A)"
$arguments = "-m job_agent.discover --config `"$configPath`" --db `"$databasePath`""
# Default operation produces a reviewable plan, without registering any task.
[pscustomobject]@{
    TaskName = $TaskName
    Executable = $pythonPath
    Arguments = $arguments
    WorkingDirectory = $workspacePath
    DailyIndiaTime = $IndiaTime
    TimeZone = 'India Standard Time / Asia-Kolkata (UTC+05:30)'
    CatchUp = [bool]$CatchUp
    RequiresLoggedInUser = $true
    WillRegister = [bool]$Register
} | Format-List
if (-not $Register) { return }
$existingTask = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($existingTask -and $existingTask.Description -ne $taskDescription) {
    throw 'An unrelated task already uses this name. Choose another TaskName.'
}
$indiaZone = [TimeZoneInfo]::FindSystemTimeZoneById('India Standard Time')
$todayIndia = [TimeZoneInfo]::ConvertTimeFromUtc([DateTime]::UtcNow, $indiaZone)
$nextIndia = [DateTime]::ParseExact(($todayIndia.ToString('yyyy-MM-dd') + ' ' + $IndiaTime), 'yyyy-MM-dd HH:mm', [Globalization.CultureInfo]::InvariantCulture)
if ($nextIndia -le $todayIndia) { $nextIndia = $nextIndia.AddDays(1) }
$trigger = New-ScheduledTaskTrigger -Daily -At $nextIndia
# An explicit offset retains the intended India instant even on a different Windows timezone.
$trigger.StartBoundary = $nextIndia.ToString("yyyy-MM-dd'T'HH:mm:ss") + '+05:30'
$action = New-ScheduledTaskAction -Execute $pythonPath -Argument $arguments -WorkingDirectory $workspacePath
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable:$CatchUp -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
if ($PSCmdlet.ShouldProcess($TaskName, 'Register/update the daily public discovery task')) {
    Register-ScheduledTask -TaskName $TaskName -Description $taskDescription -Trigger $trigger -Action $action -Settings $settings -Principal $principal -Force | Select-Object TaskName, State
}
