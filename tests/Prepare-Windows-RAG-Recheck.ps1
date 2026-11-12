[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)] [long]$RunId,
    [Parameter(Mandatory=$true)] [string]$ExpectedCommit,
    [Parameter(Mandatory=$true)] [string]$KnowledgeDb,
    [Parameter(Mandatory=$true)] [string]$ProductId,
    [Parameter(Mandatory=$true)] [string]$ProductName,
    [Parameter(Mandatory=$true)] [string]$ProductVersion,
    [string]$AppName = 'DK Knowledge Client',
    [string]$IconFile,
    [string]$OutputDir = '.\DK-Knowledge-Engine-v020-RAG-Recheck'
)
$ErrorActionPreference = 'Stop'
$repository = 'danhk0612/DK-Knowledge-Engine'

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    throw 'GitHub CLI (gh) is required for the one-time Admin artifact download'
}
$db = (Resolve-Path -LiteralPath $KnowledgeDb -ErrorAction Stop).Path
$output = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $output) {
    throw "Existing QA output is never overwritten: $output"
}
$beforeHash = (Get-FileHash -LiteralPath $db -Algorithm SHA256).Hash
$runJson = & gh run view $RunId -R $repository --json headSha,status,conclusion
if ($LASTEXITCODE -ne 0) { throw 'Cannot look up the specified T12 run' }
$run = ($runJson | Out-String | ConvertFrom-Json)
if ($run.status -ne 'completed' -or $run.conclusion -ne 'success') {
    throw "T12 run is not successful: $RunId"
}
if ($run.headSha -ine $ExpectedCommit) {
    throw "Unexpected run commit: $($run.headSha), wanted $ExpectedCommit"
}

$download = Join-Path $output 'admin-download'
$unpacked = Join-Path $output 'Admin'
New-Item -ItemType Directory -Path $download,$unpacked -Force | Out-Null
& gh run download $RunId -R $repository -n 'DK-Knowledge-Engine-Admin-Win-x64-T13' -D $download
if ($LASTEXITCODE -ne 0) { throw 'Admin download failed or the artifact has expired' }
$zip = Join-Path $download 'DK-Knowledge-Engine-Admin-Win-x64.zip'
if (-not (Test-Path -LiteralPath $zip -PathType Leaf)) {
    throw 'Downloaded Admin ZIP was not found'
}
Expand-Archive -LiteralPath $zip -DestinationPath $unpacked
$admin = Join-Path $unpacked 'DK-Knowledge-Engine-Admin'
$engine = Join-Path $admin 'engine-template'
$clientExe = Join-Path $admin 'client\DK-Knowledge-Client.exe'
$packageScript = Join-Path $admin 'tools\Build-Client-Package.ps1'
foreach ($required in @(
    (Join-Path $admin 'DK-Knowledge-Admin.exe'),
    (Join-Path $engine 'Verify-AIHelp.ps1'),
    (Join-Path $engine 'engine\DK-Knowledge-API.exe'),
    $clientExe, $packageScript
)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Admin package prerequisite missing: $required"
    }
}
& powershell.exe -NoProfile -File (Join-Path $engine 'Verify-AIHelp.ps1') -Root $engine
if ($LASTEXITCODE -ne 0) { throw 'Bundled engine SHA-256 verification failed' }
& (Join-Path $engine 'engine\DK-Knowledge-API.exe') --verify-db $db --verify-product-id $ProductId
if ($LASTEXITCODE -ne 0) {
    throw 'Existing knowledge DB did not pass validation for the selected product'
}

$packageArgs = @(
    '-NoProfile', '-File', $packageScript,
    '-EnginePackage', $engine,
    '-KnowledgeDb', $db,
    '-ClientExe', $clientExe,
    '-OutputDir', (Join-Path $output 'generated'),
    '-ProductId', $ProductId,
    '-ProductName', $ProductName,
    '-ProductVersion', $ProductVersion,
    '-AppName', $AppName,
    '-PromptMode', 'raw_chatml'
)
if (-not [string]::IsNullOrWhiteSpace($IconFile)) {
    $chosenIcon = (Resolve-Path -LiteralPath $IconFile -ErrorAction Stop).Path
    $packageArgs += @('-IconFile', $chosenIcon)
}
& powershell.exe @packageArgs
if ($LASTEXITCODE -ne 0) { throw 'Client package creation failed' }

$client = Join-Path $output 'generated\DK-Knowledge-Engine-Client'
$verification = Join-Path $client 'Verify-AIHelp.ps1'
& powershell.exe -NoProfile -File $verification -Root $client
if ($LASTEXITCODE -ne 0) { throw 'Generated Client SHA-256 verification failed' }
$packageInfo = Get-Content -LiteralPath (Join-Path $client 'package-info.json') -Raw -Encoding UTF8 | ConvertFrom-Json
if ($packageInfo.product_id -cne $ProductId -or $packageInfo.product_version -cne $ProductVersion -or
    $packageInfo.app_name -cne $AppName) {
    throw 'Generated Client metadata does not match the requested product'
}
$afterHash = (Get-FileHash -LiteralPath $db -Algorithm SHA256).Hash
if ($beforeHash -ne $afterHash) {
    throw 'Original authoring knowledge database was unexpectedly modified'
}

$report = @"
# v0.2.0 RAG recheck preparation
- T12 run: $RunId
- Source commit: $($run.headSha)
- Original DB SHA-256 (unchanged): $afterHash
- Selected product: $ProductId
- Client: $client
- Generated Client integrity: passed
- Real manual question accuracy: not checked

Check the same previous questions in the newly generated Client GUI.
Verify both the answer text and the relevant manual pages.
This preparation step never runs inference or edits the authoring DB.
"@
[IO.File]::WriteAllText(
    (Join-Path $output 'RECHECK_RESULT.md'),
    $report,
    (New-Object System.Text.UTF8Encoding($false))
)
Write-Output "V020_RAG_RECHECK_READY commit=$($run.headSha)"
Write-Output "CLIENT_EXE=$(Join-Path $client 'DK-Knowledge-Client.exe')"
Write-Output "QA_REPORT=$(Join-Path $output 'RECHECK_RESULT.md')"
