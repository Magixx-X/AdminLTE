param([string]$Root = (Split-Path $PSScriptRoot -Parent))
$ErrorActionPreference = 'Stop'
$base = [IO.Path]::GetFullPath($Root)
$manifest = Get-Content -Raw -LiteralPath (Join-Path $base 'SHA256.json') | ConvertFrom-Json
foreach ($entry in $manifest) {
    $file = [IO.Path]::GetFullPath((Join-Path $base $entry.path))
    if (!$file.StartsWith($base + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw '校验清单路径越界' }
    if (!(Test-Path -LiteralPath $file) -or (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) { throw "校验失败：$($entry.path)" }
}
Write-Output "SHA-256 校验通过：$($manifest.Count) 个文件"
