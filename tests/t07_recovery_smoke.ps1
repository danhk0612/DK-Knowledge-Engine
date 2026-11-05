[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)] [string]$PackageRoot,
    [Parameter(Mandatory=$true)] [string]$SourceDb
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $PackageRoot).Path
$source = (Resolve-Path -LiteralPath $SourceDb).Path
$current = Join-Path $root 'knowledge\knowledge.db'
$backup = Join-Path $root 'knowledge\knowledge.previous.db'
$pending = Join-Path $root 'knowledge\knowledge.pending.json'
$hashFile = Join-Path $root 'knowledge\knowledge.sha256'
$backupHashFile = Join-Path $root 'knowledge\knowledge.previous.sha256'
$update = Join-Path $root 'Update-Knowledge.ps1'
$verify = Join-Path $root 'Verify-AIHelp.ps1'
$ps51 = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'

function Hash([string]$p) {
    return (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash.ToLowerInvariant()
}
function Journal([string]$before, [string]$after) {
    $data = [ordered]@{ format = 1; old_sha256 = $before; new_sha256 = $after }
    [System.IO.File]::WriteAllText($pending, ($data | ConvertTo-Json -Compress), (New-Object System.Text.UTF8Encoding($false)))
}
function Expect-Failure([string]$script, [string[]]$options) {
    & $ps51 -NoProfile -ExecutionPolicy Bypass -File $script @options *> $null
    if ($LASTEXITCODE -eq 0) { throw "Expected script to reject an incomplete state: $script" }
}
function Assert-Hashes([string]$expectedCurrent, [string]$expectedBackup) {
    if ((Hash $current) -ne $expectedCurrent -or (Hash $backup) -ne $expectedBackup) {
        throw 'Database bytes differ from expected atomic replacement'
    }
    if ((Get-Content -LiteralPath $hashFile -Raw).Trim() -ne $expectedCurrent -or
        (Get-Content -LiteralPath $backupHashFile -Raw).Trim() -ne $expectedBackup) {
        throw 'Recovered SHA-256 records differ from database bytes'
    }
    if (Test-Path -LiteralPath $pending) { throw 'Recovery journal was not removed' }
    & $verify | Out-Null
}

$old = Hash $current
$new = Hash $source
if ($old -eq $new) { throw 'Test fixture must use different DB bytes' }

# 1. Hard stop after atomic DB replacement, before either hash record is rewritten.
$staged = Join-Path $root 'knowledge\.test-interrupted.db'
Copy-Item -LiteralPath $source -Destination $staged
Journal $old $new
[System.IO.File]::Replace($staged, $current, $backup, $true)
Expect-Failure $verify @()
Expect-Failure $update @('-Rollback')
& $update -Recover | Out-Null
Assert-Hashes $new $old

# 2. Hard stop after the first hash record but before the backup hash.
$staged = Join-Path $root 'knowledge\.test-interrupted-again.db'
Copy-Item -LiteralPath $backup -Destination $staged
Journal $new $old
[System.IO.File]::Replace($staged, $current, $backup, $true)
[System.IO.File]::WriteAllText($hashFile, $old + [Environment]::NewLine)
Expect-Failure $verify @()
& $update -Recover | Out-Null
Assert-Hashes $old $new

# 3. Stop after journaling, before File.Replace: original DB stays intact.
Journal $old $new
& $update -Recover | Out-Null
Assert-Hashes $old $new

# 4. Tampered journal cannot be used to rewrite hash records or database bytes.
Journal ('a' * 64) ('b' * 64)
Expect-Failure $update @('-Recover')
if ((Hash $current) -ne $old -or (Get-Content -LiteralPath $hashFile -Raw).Trim() -ne $old) {
    throw 'Rejected journal unexpectedly modified current data or SHA'
}
Remove-Item -LiteralPath $pending -Force
Assert-Hashes $old $new
Write-Output 'T07_INTERRUPTED_UPDATE_RECOVERY_OK'
