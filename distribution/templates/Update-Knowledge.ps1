[CmdletBinding(DefaultParameterSetName='Update')]
param(
    [Parameter(ParameterSetName='Update', Mandatory=$true)]
    [string]$SourceDb,

    [Parameter(ParameterSetName='Update', Mandatory=$true)]
    [string]$ExpectedSha256,

    [Parameter(ParameterSetName='Rollback', Mandatory=$true)]
    [switch]$Rollback
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

$root = $PSScriptRoot
$dataDir = Join-Path $root 'knowledge'
$current = Join-Path $dataDir 'knowledge.db'
$backup = Join-Path $dataDir 'knowledge.previous.db'
$hashFile = Join-Path $dataDir 'knowledge.sha256'
$backupHashFile = Join-Path $dataDir 'knowledge.previous.sha256'
$engine = Join-Path $root 'engine\DK-Knowledge-API.exe'

# A running API can have an open SQLite handle on Windows; require an offline
# maintenance window instead of silently updating a live database.
if (Get-Process -Name 'DK-Knowledge-API' -ErrorAction SilentlyContinue) {
    throw 'Stop all DK-Knowledge-API processes before replacing the knowledge DB'
}
if (-not (Test-Path -LiteralPath $current -PathType Leaf)) {
    throw 'Current knowledge database does not exist'
}
if (-not (Test-Path -LiteralPath $engine -PathType Leaf)) {
    throw 'Bundled API executable is missing'
}

$temporary = Join-Path $dataDir ('.knowledge-' + [guid]::NewGuid().ToString('N') + '.db')
try {
    if ($Rollback) {
        if (-not (Test-Path -LiteralPath $backup -PathType Leaf) -or
            -not (Test-Path -LiteralPath $backupHashFile -PathType Leaf)) {
            throw 'No previous knowledge database is available'
        }
        $ExpectedSha256 = (Get-Content -LiteralPath $backupHashFile -Raw).Trim()
        Copy-Item -LiteralPath $backup -Destination $temporary
    } else {
        if (-not (Test-Path -LiteralPath $SourceDb -PathType Leaf)) {
            throw "New knowledge database not found: $SourceDb"
        }
        Copy-Item -LiteralPath $SourceDb -Destination $temporary
    }

    $ExpectedSha256 = $ExpectedSha256.Trim().ToLowerInvariant()
    if ($ExpectedSha256 -notmatch '^[0-9a-f]{64}$') {
        throw 'ExpectedSha256 must contain exactly 64 hexadecimal characters'
    }
    $actual = (Get-Sha256 $temporary)
    if ($actual -ne $ExpectedSha256) {
        throw 'Incoming knowledge database SHA-256 mismatch'
    }
    & $engine --verify-db $temporary
    if ($LASTEXITCODE -ne 0) {
        throw 'Incoming knowledge database failed schema / integrity verification'
    }

    $oldHash = (Get-Sha256 $current)
    # File.Replace is an atomic same-volume replacement on Windows.
    # If it fails (for example because the database is open), current is intact.
    [System.IO.File]::Replace($temporary, $current, $backup, $true)
    [System.IO.File]::WriteAllText($hashFile, $actual + [Environment]::NewLine)
    [System.IO.File]::WriteAllText($backupHashFile, $oldHash + [Environment]::NewLine)
    Write-Output ('KNOWLEDGE_UPDATE_OK SHA256=' + $actual)
}
finally {
    if (Test-Path -LiteralPath $temporary) {
        Remove-Item -LiteralPath $temporary -Force
    }
}
