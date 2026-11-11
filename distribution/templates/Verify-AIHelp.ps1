[CmdletBinding()]
param(
    [string]$Root
)

$ErrorActionPreference = 'Stop'
function Get-Sha256([string]$FilePath) {
    $stream = [System.IO.File]::OpenRead($FilePath)
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    try {
        return [System.BitConverter]::ToString($hasher.ComputeHash($stream)).Replace('-', '').ToLowerInvariant()
    }
    finally {
        $stream.Dispose()
        $hasher.Dispose()
    }
}

if ([string]::IsNullOrWhiteSpace($Root)) { $Root = $PSScriptRoot }
$Root = (Resolve-Path -LiteralPath $Root).Path
$manifestPath = Join-Path $Root 'manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "Missing package manifest: $manifestPath"
}
$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
if ($manifest.package_format -ne 1 -or $manifest.schema_version -ne '1') {
    throw 'Unsupported package manifest or DB schema version'
}
foreach ($entry in $manifest.immutable_files.PSObject.Properties) {
    $relative = $entry.Name
    if ($relative.StartsWith('/') -or $relative.StartsWith('\') -or $relative.Contains('..') -or [System.IO.Path]::IsPathRooted($relative)) {
        throw "Invalid manifest path: $relative"
    }
    $path = Join-Path $Root ($relative.Replace('/', [IO.Path]::DirectorySeparatorChar))
    if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
        throw "Missing package file: $relative"
    }
    $actual = (Get-Sha256 $path)
    if ($actual -ne [string]$entry.Value) {
        throw "Package SHA-256 mismatch: $relative"
    }
}

# An interrupted database replacement must be reconciled before acceptance.
$pending = Join-Path $Root 'knowledge\knowledge.pending.json'
if (Test-Path -LiteralPath $pending -PathType Leaf) {
    throw 'Interrupted knowledge update detected: run Update-Knowledge.ps1 -Recover'
}

$db = Join-Path $Root 'knowledge\knowledge.db'
$expectedPath = Join-Path $Root 'knowledge\knowledge.sha256'
if (-not (Test-Path -LiteralPath $db -PathType Leaf) -or -not (Test-Path -LiteralPath $expectedPath -PathType Leaf)) {
    throw 'Knowledge DB or knowledge.sha256 is missing'
}
$expected = (Get-Content -LiteralPath $expectedPath -Raw).Trim().ToLowerInvariant()
$actual = (Get-Sha256 $db)
if ($expected -notmatch '^[0-9a-f]{64}$' -or $actual -ne $expected) {
    throw 'Knowledge database SHA-256 mismatch'
}

$engine = Join-Path $Root 'engine\DK-Knowledge-API.exe'
$productInfoPath = Join-Path $Root 'package-info.json'
if (Test-Path -LiteralPath $productInfoPath -PathType Leaf) {
    if (-not $manifest.immutable_files.PSObject.Properties['package-info.json']) {
        throw 'Client package information is not covered by the manifest'
    }
    $product = Get-Content -LiteralPath $productInfoPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($product.icon_file -ne 'assets/app.ico' -or
        -not $manifest.immutable_files.PSObject.Properties['assets/app.ico']) {
        throw 'Client icon path is missing or not protected by the manifest'
    }
    # New v0.2 Client packages are self-contained *multi-file* WPF apps.
    # Every required runtime dependency must also be in immutable_files.
    foreach ($clientFile in @('DK-Knowledge-Client.exe',
        'DK-Knowledge-Client.deps.json','DK-Knowledge-Client.runtimeconfig.json',
        'coreclr.dll','hostfxr.dll','PresentationFramework.dll')) {
        if (-not $manifest.immutable_files.PSObject.Properties[$clientFile] -or
            -not (Test-Path -LiteralPath (Join-Path $Root $clientFile) -PathType Leaf)) {
            throw "Self-contained Client dependency is missing or not verified: $clientFile"
        }
    }
    if ([string]$product.product_id -cnotmatch '^[a-z0-9][a-z0-9._-]{0,79}$' -or
        [string]$product.product_version -cnotmatch '^\d+(\.\d+)+$' -or
        [string]::IsNullOrWhiteSpace([string]$product.product_name)) {
        throw 'Invalid Client product metadata'
    }
    & $engine --verify-db $db --verify-product-id $product.product_id
} else {
    & $engine --verify-db $db
}
if ($LASTEXITCODE -ne 0) {
    throw 'Knowledge DB schema / SQLite integrity verification failed'
}
Write-Output 'PACKAGE_VERIFY_OK'
