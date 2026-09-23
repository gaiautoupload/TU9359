$ErrorActionPreference = "Stop"

$taskName = "TU9359 Weekday 1730 Update"
$batchPath = Join-Path $PSScriptRoot "update_scheduled.bat"
$taskRun = '"' + $batchPath + '"'

if (-not (Test-Path -LiteralPath $batchPath)) {
    throw "Batch file not found: $batchPath"
}

& "$env:WINDIR\System32\schtasks.exe" /Create /TN $taskName /TR $taskRun /SC WEEKLY /D MON,TUE,WED,THU,FRI /ST 17:30 /F
if ($LASTEXITCODE -ne 0) {
    throw "Failed to create scheduled task: $taskName"
}

& "$env:WINDIR\System32\schtasks.exe" /Query /TN $taskName /FO LIST /V
if ($LASTEXITCODE -ne 0) {
    throw "Scheduled task was created but could not be queried: $taskName"
}
