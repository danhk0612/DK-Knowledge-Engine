[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)] [string]$EnginePackage,
    [Parameter(Mandatory=$true)] [string]$OutputDir,
    [string]$Python = 'python'
)

$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$engine = (Resolve-Path -LiteralPath $EnginePackage).Path
$output = [IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $output) {
    throw 'OutputDir must not exist; refusing to overwrite an existing Admin package'
}
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $engine 'Verify-AIHelp.ps1') -Root $engine
if ($LASTEXITCODE -ne 0) { throw 'Source engine verification failed' }

$package = Join-Path $output 'DK-Knowledge-Engine-Admin'
$work = Join-Path $output '_admin-build'
$adminPublish = Join-Path $work 'admin'
$clientPublish = Join-Path $work 'client'
$builderDist = Join-Path $work 'dist'
New-Item -ItemType Directory -Path $package -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $package 'tools') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $package 'client') -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $package 'workspace\sources') -Force | Out-Null

try {
    & dotnet publish (Join-Path $repo 'apps\Admin\DKKnowledgeAdmin.csproj') -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o $adminPublish
    if ($LASTEXITCODE -ne 0) { throw 'Admin WPF publish failed' }
    & dotnet publish (Join-Path $repo 'apps\Client\DKKnowledgeClient.csproj') -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o $clientPublish
    if ($LASTEXITCODE -ne 0) { throw 'Client WPF publish failed' }

    $adminGui = Join-Path $adminPublish 'DK-Knowledge-Admin.exe'
    $clientGui = Join-Path $clientPublish 'DK-Knowledge-Client.exe'
    foreach ($exe in @($adminGui, $clientGui)) {
        if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
            throw "Published GUI missing: $exe"
        }
    }
    Copy-Item -LiteralPath $adminGui -Destination (Join-Path $package 'DK-Knowledge-Admin.exe')
    Copy-Item -LiteralPath $clientGui -Destination (Join-Path $package 'client\DK-Knowledge-Client.exe')

    # PyInstaller embeds CPython and the Builder's PDF/DOCX dependencies.
    & $Python -m PyInstaller --noconfirm --clean --onedir --console --name DK-Knowledge-Builder --paths $repo --collect-all pypdf --collect-all docx --distpath $builderDist --workpath (Join-Path $work 'py-work') --specpath (Join-Path $work 'py-spec') (Join-Path $repo 'distribution\builder_entry.py')
    if ($LASTEXITCODE -ne 0) { throw 'Standalone Builder executable compilation failed' }
    $builderFolder = Join-Path $builderDist 'DK-Knowledge-Builder'
    if (-not (Test-Path -LiteralPath (Join-Path $builderFolder 'DK-Knowledge-Builder.exe'))) {
        throw 'Frozen standalone Builder EXE is missing'
    }
    Copy-Item -LiteralPath $builderFolder -Destination (Join-Path $package 'tools\builder') -Recurse
    Copy-Item -LiteralPath (Join-Path $repo 'distribution\Build-Client-Package.ps1') -Destination (Join-Path $package 'tools\Build-Client-Package.ps1')

    # Ship the already verified template only to the authoring machine.
    # End users receive a SEPARATE Client-only ZIP with their selected DB.
    $engineDest = Join-Path $package 'engine-template'
    New-Item -ItemType Directory -Path $engineDest -Force | Out-Null
    foreach ($folder in @('engine','runtime','models','knowledge','config','licenses')) {
        $src = Join-Path $engine $folder
        if (-not (Test-Path -LiteralPath $src -PathType Container)) {
            throw "Source engine missing folder: $folder"
        }
        Copy-Item -LiteralPath $src -Destination (Join-Path $engineDest $folder) -Recurse
    }
    foreach ($file in @('Start-AIHelp.cmd','Update-Knowledge.ps1','Verify-AIHelp.ps1','manifest.json')) {
        $src = Join-Path $engine $file
        if (-not (Test-Path -LiteralPath $src -PathType Leaf)) {
            throw "Source engine missing file: $file"
        }
        Copy-Item -LiteralPath $src -Destination (Join-Path $engineDest $file)
    }
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $engineDest 'Verify-AIHelp.ps1') -Root $engineDest
    if ($LASTEXITCODE -ne 0) { throw 'Bundled engine template verification failed' }

    $zip = Join-Path $output 'DK-Knowledge-Engine-Admin-Win-x64.zip'
    Compress-Archive -LiteralPath $package -DestinationPath $zip -CompressionLevel Fastest
    Write-Output ('ADMIN_STANDALONE_PACKAGE_READY ' + $zip)
}
finally {
    if (Test-Path -LiteralPath $work) {
        Remove-Item -LiteralPath $work -Recurse -Force
    }
}
