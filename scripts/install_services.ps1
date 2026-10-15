param([Parameter(Mandatory=$true)][string]$ServiceAccount)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$serviceDir = Join-Path $root 'services'
New-Item -ItemType Directory -Force $serviceDir | Out-Null
foreach ($name in @('web','worker')) {
    $exe = Join-Path $serviceDir ($name + '.exe')
    Copy-Item (Join-Path $root 'installers\WinSW-x64.exe') $exe
    Copy-Item (Join-Path $PSScriptRoot ('services\' + $name + '.xml')) (Join-Path $serviceDir ($name + '.xml'))
    & $exe install
    if ($LASTEXITCODE -ne 0) { throw "$name 服务安装失败" }
}
# Install initially disabled: hospital operator supplies a protected password in services.msc.
foreach ($id in @('HospitalQueryWeb','HospitalQueryWorker')) { Set-Service -Name $id -StartupType Disabled }
Write-Output "服务已注册并禁用。请在 services.msc 将登录账号设为 $ServiceAccount（低权限），输入密码、配置目录 ACL，再设为自动并启动。禁止以默认 LocalSystem 上线。"
