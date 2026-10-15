param([string]$Python = 'python', [switch]$InitializeAdmin)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
& (Join-Path $PSScriptRoot 'verify_package.ps1') -Root $root
& $Python -c 'import sys,struct; assert sys.version_info[:2]==(3,11) and struct.calcsize("P")==8'
if ($LASTEXITCODE -ne 0) { throw '先安装 Python 3.11 x64（不能使用 Python 3.12）' }
if (Test-Path (Join-Path $root '.venv')) { throw '需要全新安装目录，拒绝覆盖既有虚拟环境' }
& $Python -m venv (Join-Path $root '.venv')
if ($LASTEXITCODE -ne 0) { throw '创建虚拟环境失败' }
$venvPython = Join-Path $root '.venv\Scripts\python.exe'
& $venvPython -m pip install --no-index --find-links (Join-Path $root 'wheelhouse') -r (Join-Path $root 'requirements.lock')
if ($LASTEXITCODE -ne 0) { throw '离线依赖安装失败' }
Push-Location $root
try {
    & $venvPython -m flask --app wsgi:application migrate
    if ($LASTEXITCODE -ne 0) { throw '迁移失败' }
    if ($InitializeAdmin) {
        & $venvPython -m flask --app wsgi:application init-admin
        if ($LASTEXITCODE -ne 0) { throw '初始化账号失败' }
    }
} finally { Pop-Location }
Write-Output '离线安装完成；配置受保护 config.local.json、初始化管理员，然后启动 Web 与 Worker。'
