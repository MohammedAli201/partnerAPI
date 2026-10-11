$ErrorActionPreference = 'Stop'
Set-Content -LiteralPath (Join-Path $PSScriptRoot '.phone-worker-stop') -Value 'stop'
Write-Output 'Stop requested for the local phone host and its supervised server.'
