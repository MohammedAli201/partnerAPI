$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskPython = Join-Path $taskRoot '.venv-central/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $taskPython)) { $taskPython = Join-Path $taskRoot 'venv/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath (Join-Path $taskRoot '.phone-worker-local.json'))) {
    throw 'Prepare .phone-worker-local.json with the local backend configuration; see docs/PAYOUTWORKER.rst.'
}
$taskListener = Get-NetTCPConnection -State Listen -LocalPort 8000 -ErrorAction SilentlyContinue
if ($taskListener) {
    Write-Output 'Port 8000 is already in use. Check the running host before starting another.'
    exit 0
}
$taskStop = Join-Path $taskRoot '.phone-worker-stop'
if (Test-Path -LiteralPath $taskStop) { Remove-Item -LiteralPath $taskStop }
$taskProcess = Start-Process -FilePath $taskPython -ArgumentList 'development_support/phone_worker_host.py' `
    -WorkingDirectory $taskRoot -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput (Join-Path $taskRoot '.phone-host.stdout.log') `
    -RedirectStandardError (Join-Path $taskRoot '.phone-host.stderr.log')
Write-Output "Local phone host started (PID $($taskProcess.Id)). Website: http://127.0.0.1:8000/"
