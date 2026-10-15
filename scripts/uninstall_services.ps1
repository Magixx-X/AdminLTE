$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
foreach ($name in @('web','worker')) {
    $exe = Join-Path $root ('services\' + $name + '.exe')
    if (!(Test-Path $exe)) { throw "缺少服务包装器 $name" }
    & $exe stop
    & $exe uninstall
    if ($LASTEXITCODE -ne 0) { throw "$name 服务卸载失败" }
}
