[CmdletBinding(DefaultParameterSetName='Update')]
param(
    [Parameter(ParameterSetName='Update', Mandatory=$true)] [string]$SourceDb,
    [Parameter(ParameterSetName='Update', Mandatory=$true)] [string]$ExpectedSha256,
    [Parameter(ParameterSetName='Rollback', Mandatory=$true)] [switch]$Rollback,
    [Parameter(ParameterSetName='Recover', Mandatory=$true)] [switch]$Recover
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

function Read-Hash([string]$FilePath) {
    if (-not (Test-Path -LiteralPath $FilePath -PathType Leaf)) {
        throw "Missing SHA-256 record: $FilePath"
    }
    $value = (Get-Content -LiteralPath $FilePath -Raw).Trim().ToLowerInvariant()
    if ($value -notmatch '^[0-9a-f]{64}$') {
        throw "Invalid SHA-256 record: $FilePath"
    }
    return $value
}

function Write-HashAtomic([string]$FilePath, [string]$Value) {
    $tempHash = Join-Path (Split-Path -Parent $FilePath) ('.knowledge-hash-' + [guid]::NewGuid().ToString('N'))
    try {
        [System.IO.File]::WriteAllText($tempHash, $Value + [Environment]::NewLine, (New-Object System.Text.UTF8Encoding($false)))
        if (Test-Path -LiteralPath $FilePath -PathType Leaf) {
            [System.IO.File]::Replace($tempHash, $FilePath, $null, $true)
        } else {
            [System.IO.File]::Move($tempHash, $FilePath)
        }
    }
    finally {
        if (Test-Path -LiteralPath $tempHash) {
            Remove-Item -LiteralPath $tempHash -Force
        }
    }
}

$root = $PSScriptRoot
$dataDir = Join-Path $root 'knowledge'
$current = Join-Path $dataDir 'knowledge.db'
$backup = Join-Path $dataDir 'knowledge.previous.db'
$hashFile = Join-Path $dataDir 'knowledge.sha256'
$backupHashFile = Join-Path $dataDir 'knowledge.previous.sha256'
$pending = Join-Path $dataDir 'knowledge.pending.json'
$engine = Join-Path $root 'engine\DK-Knowledge-API.exe'

function Assert-Db([string]$DbPath) {
    & $engine --verify-db $DbPath
    if ($LASTEXITCODE -ne 0) {
        throw "Knowledge database schema / integrity verification failed: $DbPath"
    }
}

if (Get-Process -Name 'DK-Knowledge-API' -ErrorAction SilentlyContinue) {
    throw 'Stop all DK-Knowledge-API processes before replacing or recovering the knowledge DB'
}
if (-not (Test-Path -LiteralPath $current -PathType Leaf)) {
    throw 'Current knowledge database does not exist'
}
if (-not (Test-Path -LiteralPath $engine -PathType Leaf)) {
    throw 'Bundled API executable is missing'
}

if ($Recover) {
    if (-not (Test-Path -LiteralPath $pending -PathType Leaf)) {
        throw 'No interrupted knowledge update journal exists'
    }
    $record = Get-Content -LiteralPath $pending -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($record.format -ne 1 -or
        [string]$record.old_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        [string]$record.new_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
        $record.old_sha256 -ceq $record.new_sha256) {
        throw 'Invalid interrupted update journal; do not overwrite the databases'
    }
    $actualCurrent = Get-Sha256 $current
    if ($actualCurrent -eq $record.new_sha256) {
        if (-not (Test-Path -LiteralPath $backup -PathType Leaf) -or
            (Get-Sha256 $backup) -ne $record.old_sha256) {
            throw 'Incomplete update backup mismatch; manual inspection required'
        }
        Assert-Db $current
        Assert-Db $backup
        Write-HashAtomic $hashFile $record.new_sha256
        Write-HashAtomic $backupHashFile $record.old_sha256
        Remove-Item -LiteralPath $pending -Force
        Write-Output ('KNOWLEDGE_RECOVERED SHA256=' + $record.new_sha256)
        return
    }
    if ($actualCurrent -eq $record.old_sha256) {
        if ((Read-Hash $hashFile) -ne $record.old_sha256) {
            throw 'Pre-replacement hash record mismatch; manual inspection required'
        }
        Assert-Db $current
        Remove-Item -LiteralPath $pending -Force
        Write-Output ('KNOWLEDGE_RECOVERY_NOT_NEEDED SHA256=' + $record.old_sha256)
        return
    }
    throw 'Neither expected database matches the interrupted update journal; manual inspection required'
}

if (Test-Path -LiteralPath $pending -PathType Leaf) {
    throw 'Interrupted knowledge update: run Update-Knowledge.ps1 -Recover before any new update or rollback'
}

$oldHash = Get-Sha256 $current
if ((Read-Hash $hashFile) -ne $oldHash) {
    throw 'Current knowledge DB hash mismatch; refusing to overwrite'
}
Assert-Db $current

$temporary = Join-Path $dataDir ('.knowledge-' + [guid]::NewGuid().ToString('N') + '.db')
try {
    if ($Rollback) {
        if (-not (Test-Path -LiteralPath $backup -PathType Leaf)) {
            throw 'No previous knowledge database is available'
        }
        $ExpectedSha256 = Read-Hash $backupHashFile
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
    $actual = Get-Sha256 $temporary
    if ($actual -ne $ExpectedSha256) {
        throw 'Incoming knowledge database SHA-256 mismatch'
    }
    Assert-Db $temporary
    if ($actual -eq $oldHash) {
        throw 'Incoming DB is identical to the current DB; no replacement is needed'
    }

    # Publish the tiny journal before the atomic database replacement.
    $journalTemp = Join-Path $dataDir ('.knowledge-journal-' + [guid]::NewGuid().ToString('N'))
    try {
        $record = [ordered]@{ format = 1; old_sha256 = $oldHash; new_sha256 = $actual }
        [System.IO.File]::WriteAllText($journalTemp, ($record | ConvertTo-Json -Compress), (New-Object System.Text.UTF8Encoding($false)))
        [System.IO.File]::Move($journalTemp, $pending)
    }
    finally {
        if (Test-Path -LiteralPath $journalTemp) {
            Remove-Item -LiteralPath $journalTemp -Force
        }
    }

    # Keep the journal when interrupted between File.Replace and hash writes.
    [System.IO.File]::Replace($temporary, $current, $backup, $true)
    Write-HashAtomic $hashFile $actual
    Write-HashAtomic $backupHashFile $oldHash
    Remove-Item -LiteralPath $pending -Force
    Write-Output ('KNOWLEDGE_UPDATE_OK SHA256=' + $actual)
}
finally {
    if (Test-Path -LiteralPath $temporary) {
        Remove-Item -LiteralPath $temporary -Force
    }
}
