param(
    [Parameter(ValueFromRemainingArguments=$true)]
    [string[]]$PhoneArguments
)
$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskConfig = Get-Content -LiteralPath (Join-Path $taskRoot '.phone-worker-local.json') -Raw | ConvertFrom-Json
foreach ($taskProperty in $taskConfig.environment.PSObject.Properties) {
    [Environment]::SetEnvironmentVariable($taskProperty.Name, [string]$taskProperty.Value, 'Process')
}
$taskPython = Join-Path $taskRoot '.venv-central/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { $taskPython = Join-Path $taskRoot 'venv/Scripts/python.exe' }
Push-Location $taskRoot
try { & $taskPython phone_worker_admin.py @PhoneArguments; if ($LASTEXITCODE -ne 0) { throw 'Phone worker command failed' } }
finally { Pop-Location }
