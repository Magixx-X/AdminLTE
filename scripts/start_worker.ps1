$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
& (Join-Path $root '.venv\Scripts\python.exe') worker.py
exit $LASTEXITCODE
