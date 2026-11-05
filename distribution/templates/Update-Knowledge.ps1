[CmdletBinding(DefaultParameterSetName='Update')]
param(
    [Parameter(ParameterSetName='Update', Mandatory=$true)]
    [string]$SourceDb,

    [Parameter(ParameterSetName='Update', Mandatory=$true)]
    [string]$ExpectedSha256,

    [Parameter(ParameterSetName='Rollback', Mandatory=$true)]
    [switch]$Rollback,

    [Parameter(ParameterSetName='Recover', Mandatory=$true)]
    [switch]$Recover
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
$journal = Join-Path $dataDir 'knowledge.pending.json'
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


# The SQLite replacement itself is atomic, but the two sidecar hashes are not.
# The journal is written BEFORE File.Replace and retained until BOTH hashes
# match their respective files, allowing recovery after an abrupt interruption.
function Complete-Journal([string]$NewHash, [string]$OldHash) {
    if ((Get-Sha256 $current) -ne $NewHash) {
        throw 'Pending update: current database does not match intended hash'
    }
    if (-not (Test-Path -LiteralPath $backup -PathType Leaf) -or
        (Get-Sha256 $backup) -ne $OldHash) {
        throw 'Pending update: previous database is missing or mismatched'
    }
    [System.IO.File]::WriteAllText($hashFile, $NewHash + [Environment]::NewLine)
    [System.IO.File]::WriteAllText($backupHashFile, $OldHash + [Environment]::NewLine)
}

if ($Recover) {
    if (-not (Test-Path -LiteralPath $journal -PathType Leaf)) {
        if (-not (Test-Path -LiteralPath $hashFile -PathType Leaf) -or
            (Get-Sha256 $current) -ne (Get-Content -LiteralPath $hashFile -Raw).Trim().ToLowerInvariant()) {
            throw 'No pending journal but database hash does not match; manual investigation required'
        }
        Write-Output 'KNOWLEDGE_RECOVERY_NOT_REQUIRED'
        return
    }
    $entry = Get-Content -LiteralPath $journal -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($entry.format -ne 1 -or
        [string]$entry.old_sha256 -cnotmatch '^[0-9a-f]{64}
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
    if (-not (Test-Path -LiteralPath $hashFile -PathType Leaf) -or
        (Get-Content -LiteralPath $hashFile -Raw).Trim().ToLowerInvariant() -ne $oldHash) {
        throw 'Current database checksum mismatch; refusing to replace unverified state'
    }

    $transaction = @{ format = 1; old_sha256 = $oldHash; new_sha256 = $actual } |
        ConvertTo-Json -Compress
    $journalTemp = Join-Path $dataDir ('.pending-' + [guid]::NewGuid().ToString('N') + '.json')
    try {
        [System.IO.File]::WriteAllText($journalTemp, $transaction,
            (New-Object System.Text.UTF8Encoding($false)))
        [System.IO.File]::Move($journalTemp, $journal)
    }
    finally {
        if (Test-Path -LiteralPath $journalTemp) { Remove-Item -LiteralPath $journalTemp -Force }
    }

    # File.Replace is atomic on the same volume; metadata reconciliation is
    # explicitly recoverable via -Recover if interrupted after this point.
    [System.IO.File]::Replace($temporary, $current, $backup, $true)
    Complete-Journal $actual $oldHash
    Remove-Item -LiteralPath $journal -Force
    Write-Output ('KNOWLEDGE_UPDATE_OK SHA256=' + $actual)
}
finally {
    if (Test-Path -LiteralPath $temporary) {
        Remove-Item -LiteralPath $temporary -Force
    }
}
 -or
        [string]$entry.new_sha256 -cnotmatch '^[0-9a-f]{64}
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
) {
        throw 'Invalid pending update journal; manual investigation required'
    }
    $old = [string]$entry.old_sha256
    $new = [string]$entry.new_sha256
    $currentHash = Get-Sha256 $current

    # File.Replace had not happened. The original database and hash remain.
    if ($currentHash -eq $old -and $old -ne $new) {
        if (-not (Test-Path -LiteralPath $hashFile -PathType Leaf) -or
            (Get-Content -LiteralPath $hashFile -Raw).Trim().ToLowerInvariant() -ne $old) {
            throw 'Pre-replacement current checksum mismatch; manual investigation required'
        }
        if (Test-Path -LiteralPath $backup -PathType Leaf) {
            if (-not (Test-Path -LiteralPath $backupHashFile -PathType Leaf) -or
                (Get-Sha256 $backup) -ne (Get-Content -LiteralPath $backupHashFile -Raw).Trim().ToLowerInvariant()) {
                throw 'Pre-replacement backup checksum mismatch; manual investigation required'
            }
        }
        Remove-Item -LiteralPath $journal -Force
        Write-Output 'KNOWLEDGE_RECOVERY_ABORTED_BEFORE_REPLACE'
        return
    }

    # File.Replace succeeded, possibly followed by only one checksum write.
    if ($currentHash -eq $new) {
        Complete-Journal $new $old
        Remove-Item -LiteralPath $journal -Force
        Write-Output ('KNOWLEDGE_RECOVERY_OK SHA256=' + $new)
        return
    }
    throw 'Pending journal does not describe current database; manual investigation required'
}
if (Test-Path -LiteralPath $journal -PathType Leaf) {
    throw 'An interrupted update exists. Run Update-Knowledge.ps1 -Recover before retrying'
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
