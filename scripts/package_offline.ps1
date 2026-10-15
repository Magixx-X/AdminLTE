param([string]$Python = '', [string]$Output = '', [switch]$SkipDownloads)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
if (!$Python) { $Python = Join-Path $root '.venv\Scripts\python.exe' }
if (!$Output) { $Output = Join-Path $root ('release\InformationQuerySystem-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
$outputPath = [IO.Path]::GetFullPath($Output)
$releaseRoot = [IO.Path]::GetFullPath((Join-Path $root 'release'))
if (!$outputPath.StartsWith($releaseRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Output 必须位于项目 release 子目录' }
if (Test-Path -LiteralPath $outputPath) { throw '发布目录已存在，拒绝覆盖' }
$version = & $Python -c 'import sys,struct; assert sys.version_info[:2]==(3,11) and struct.calcsize("P")==8; print(sys.version.split()[0])'
if ($LASTEXITCODE -ne 0) { throw '必须使用 Python 3.11 x64' }
New-Item -ItemType Directory -Path $outputPath | Out-Null
foreach ($name in @('app','migrations','scripts','docs','tests','01_init_admin.cmd','02_start_system.cmd','wsgi.py','worker.py','alembic.ini','requirements.in','requirements.dev.in','requirements.lock','pytest.ini','config.example.json','.env.example','README.md','PROJECT_REQUIREMENTS.md','PROJECT_STATUS.md','VERSION')) {
    Copy-Item -LiteralPath (Join-Path $root $name) -Destination $outputPath -Recurse
}
Get-ChildItem -LiteralPath $outputPath -Recurse -Directory -Filter '__pycache__' | ForEach-Object {
    $resolved = [IO.Path]::GetFullPath($_.FullName)
    if (!$resolved.StartsWith($outputPath + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw '路径越界' }
    Remove-Item -LiteralPath $resolved -Recurse -Force
}
$wheelhouse = Join-Path $outputPath 'wheelhouse'
New-Item -ItemType Directory $wheelhouse | Out-Null
if ($SkipDownloads) {
    Copy-Item -Path (Join-Path $root '.runtime\wheelhouse\*.whl') -Destination $wheelhouse
} else {
    & $Python -m pip download --index-url https://pypi.org/simple --only-binary=:all: --no-deps --platform win_amd64 --python-version 311 --implementation cp --abi cp311 -r (Join-Path $root 'requirements.lock') -d $wheelhouse
    if ($LASTEXITCODE -ne 0) { throw 'wheel 下载失败，禁止发布不完整离线包' }
}
$installerDir = Join-Path $outputPath 'installers'
New-Item -ItemType Directory $installerDir | Out-Null
$pythonInstaller = Join-Path $root '.runtime\python-installer.exe'
if (!(Test-Path $pythonInstaller)) {
    if ($SkipDownloads) { throw '缺少 Python 官方安装程序' }
    Invoke-WebRequest 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile $pythonInstaller
}
Copy-Item $pythonInstaller (Join-Path $installerDir 'python-3.11.9-amd64.exe')
$wrapper = Join-Path $root '.runtime\WinSW-x64.exe'
if (!(Test-Path $wrapper)) {
    if ($SkipDownloads) { throw '缺少 WinSW 服务包装器' }
    Invoke-WebRequest 'https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe' -OutFile $wrapper
}
Copy-Item $wrapper (Join-Path $installerDir 'WinSW-x64.exe')
@{version=(Get-Content (Join-Path $root 'VERSION')).Trim(); python=$version; platform='win_amd64'; data_source='no-runtime-data'; oracle_client='separately-provided'; built_at=(Get-Date).ToUniversalTime().ToString('o')} | ConvertTo-Json | Set-Content (Join-Path $outputPath 'BUILD.json') -Encoding UTF8
$hashes = Get-ChildItem -LiteralPath $outputPath -Recurse -File | Sort-Object FullName | ForEach-Object {
    @{path=$_.FullName.Substring($outputPath.Length+1).Replace('\','/'); sha256=(Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
}
ConvertTo-Json -InputObject @($hashes) -Depth 3 | Set-Content (Join-Path $outputPath 'SHA256.json') -Encoding UTF8
Compress-Archive -Path (Join-Path $outputPath '*') -DestinationPath ($outputPath + '.zip')
(Get-FileHash -LiteralPath ($outputPath + '.zip') -Algorithm SHA256).Hash | Set-Content ($outputPath + '.zip.sha256') -Encoding ASCII
Write-Output "离线发布完成：$outputPath.zip"
