$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
& (Join-Path $root '.venv\Scripts\waitress-serve.exe') --listen=127.0.0.1:8080 --threads=8 wsgi:application
exit $LASTEXITCODE
