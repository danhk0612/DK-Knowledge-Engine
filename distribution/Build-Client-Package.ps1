[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)] [string]$EnginePackage,
    [Parameter(Mandatory=$true)] [string]$KnowledgeDb,
    [Parameter(Mandatory=$true)] [string]$OutputDir
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$engineRoot = (Resolve-Path -LiteralPath $EnginePackage).Path
$db = (Resolve-Path -LiteralPath $KnowledgeDb).Path
$output = [System.IO.Path]::GetFullPath($OutputDir)
$clientProject = Join-Path $repo 'apps\Client\DKKnowledgeClient.csproj'

if (-not (Test-Path -LiteralPath $clientProject -PathType Leaf)) {
    throw 'Client UI project not found'
}
if ((Test-Path -LiteralPath $output) -or
    $output.StartsWith($engineRoot + [IO.Path]::DirectorySeparatorChar,
                       [StringComparison]::OrdinalIgnoreCase)) {
    throw 'OutputDir must be new and outside the source engine package'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $engineRoot 'Verify-AIHelp.ps1') -Root $engineRoot
if ($LASTEXITCODE -ne 0) { throw 'Input engine package verification failed' }

New-Item -ItemType Directory -Path $output | Out-Null
$package = Join-Path $output 'DK-Knowledge-Engine-Client'
$publish = Join-Path $output '_client-publish'
New-Item -ItemType Directory -Path $package | Out-Null

try {
    # Explicit allowlist: never copy unexpected admin tools or authoring data.
    foreach ($folder in @('engine', 'runtime', 'models', 'knowledge', 'config', 'licenses')) {
        $src = Join-Path $engineRoot $folder
        if (-not (Test-Path -LiteralPath $src -PathType Container)) {
            throw "Missing engine package folder: $folder"
        }
        Copy-Item -LiteralPath $src -Destination (Join-Path $package $folder) -Recurse -Force
    }
    foreach ($file in @('Start-AIHelp.cmd', 'Update-Knowledge.ps1', 'Verify-AIHelp.ps1', 'manifest.json')) {
        $src = Join-Path $engineRoot $file
        if (-not (Test-Path -LiteralPath $src -PathType Leaf)) {
            throw "Missing engine package file: $file"
        }
        Copy-Item -LiteralPath $src -Destination (Join-Path $package $file)
    }

    $dbHash = (Get-FileHash -LiteralPath $db -Algorithm SHA256).Hash.ToLowerInvariant()
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $package 'Update-Knowledge.ps1') -SourceDb $db -ExpectedSha256 $dbHash
    if ($LASTEXITCODE -ne 0) { throw 'User knowledge DB update failed' }
    # The base package's sample/previous DB must never be delivered to users.
    # A rollback backup will be created by the first subsequent user update.
    foreach ($name in @('knowledge.previous.db', 'knowledge.previous.sha256')) {
        $stale = Join-Path $package ('knowledge\\' + $name)
        if (Test-Path -LiteralPath $stale) {
            Remove-Item -LiteralPath $stale -Force
        }
    }

    & dotnet publish $clientProject -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o $publish
    if ($LASTEXITCODE -ne 0) { throw 'Client UI publish failed' }

    $gui = Join-Path $publish 'DK-Knowledge-Client.exe'
    if (-not (Test-Path -LiteralPath $gui -PathType Leaf)) {
        throw 'Published Client EXE not found'
    }
    Copy-Item -LiteralPath $gui -Destination (Join-Path $package 'DK-Knowledge-Client.exe')

    # The original manifest keeps engine/model/script hashes; extend it with
    # the only new immutable executable. Administrator binaries are never copied.
    $manifestPath = Join-Path $package 'manifest.json'
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $guiHash = (Get-FileHash -LiteralPath (Join-Path $package 'DK-Knowledge-Client.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
    $manifest.immutable_files | Add-Member -NotePropertyName 'DK-Knowledge-Client.exe' -NotePropertyValue $guiHash -Force
    [System.IO.File]::WriteAllText(
        $manifestPath,
        ($manifest | ConvertTo-Json -Depth 20),
        (New-Object System.Text.UTF8Encoding($false))
    )

    if (Test-Path -LiteralPath (Join-Path $package 'DK-Knowledge-Admin.exe')) {
        throw 'ADMIN_EXECUTABLE_MUST_NOT_SHIP'
    }
    if (Test-Path -LiteralPath (Join-Path $package 'builder')) {
        throw 'BUILDER_MUST_NOT_SHIP'
    }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $package 'Verify-AIHelp.ps1') -Root $package
    if ($LASTEXITCODE -ne 0) { throw 'Client-only package integrity check failed' }

    $zip = Join-Path $output 'DK-Knowledge-Engine-Client-Win-x64.zip'
    Compress-Archive -LiteralPath $package -DestinationPath $zip -CompressionLevel Fastest
    Write-Output ('CLIENT_ONLY_PACKAGE_READY ' + $zip)
}
finally {
    if (Test-Path -LiteralPath $publish) {
        Remove-Item -LiteralPath $publish -Recurse -Force
    }
}
