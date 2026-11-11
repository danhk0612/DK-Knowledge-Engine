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
    & dotnet publish (Join-Path $repo 'apps\Client\DKKnowledgeClient.csproj') -c Release -r win-x64 --self-contained true -p:PublishSingleFile=false -o $clientPublish
    if ($LASTEXITCODE -ne 0) { throw 'Client WPF publish failed' }

    $adminGui = Join-Path $adminPublish 'DK-Knowledge-Admin.exe'
    $clientGui = Join-Path $clientPublish 'DK-Knowledge-Client.exe'
    foreach ($exe in @($adminGui, $clientGui)) {
        if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
            throw "Published GUI missing: $exe"
        }
    }
    Copy-Item -LiteralPath $adminGui -Destination (Join-Path $package 'DK-Knowledge-Admin.exe')
    # Portable Admin must carry ALL Client runtime dependencies. The target
    # authoring PC has neither .NET SDK nor a separate .NET runtime.
    foreach ($required in @('DK-Knowledge-Client.deps.json',
        'DK-Knowledge-Client.runtimeconfig.json','coreclr.dll',
        'hostfxr.dll','PresentationFramework.dll')) {
        if (-not (Test-Path -LiteralPath (Join-Path $clientPublish $required) -PathType Leaf)) {
            throw "Client runtime dependency missing from publish: $required"
        }
    }
    foreach ($file in @(Get-ChildItem -LiteralPath $clientPublish -File -Recurse)) {
        $relative = $file.FullName.Substring($clientPublish.Length).TrimStart('\','/').Replace('\','/')
        if ($file.Extension -ine '.dll' -and
            $relative -cnotin @('DK-Knowledge-Client.exe','DK-Knowledge-Client.deps.json',
                'DK-Knowledge-Client.runtimeconfig.json')) {
            continue
        }
        if ($relative -match '(?i)(^|/)(DK-Knowledge-Admin|DK-Knowledge-Builder)') {
            throw "Unrelated executable or assembly in Client GUI publish: $relative"
        }
        $target = Join-Path $package ('client\' + $relative.Replace('/', [IO.Path]::DirectorySeparatorChar))
        New-Item -ItemType Directory -Path (Split-Path -Parent $target) -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $target -Force
    }

    # PyInstaller embeds CPython and the Builder's PDF/DOCX dependencies.
    & $Python -m PyInstaller --noconfirm --clean --onedir --console --name DK-Knowledge-Builder --paths $repo --collect-all pypdf --collect-all docx --distpath $builderDist --workpath (Join-Path $work 'py-work') --specpath (Join-Path $work 'py-spec') (Join-Path $repo 'distribution\builder_entry.py')
    if ($LASTEXITCODE -ne 0) { throw 'Standalone Builder executable compilation failed' }
    $builderFolder = Join-Path $builderDist 'DK-Knowledge-Builder'
    if (-not (Test-Path -LiteralPath (Join-Path $builderFolder 'DK-Knowledge-Builder.exe'))) {
        throw 'Frozen standalone Builder EXE is missing'
    }
    Copy-Item -LiteralPath $builderFolder -Destination (Join-Path $package 'tools\builder') -Recurse
    Copy-Item -LiteralPath (Join-Path $repo 'distribution\Build-Client-Package.ps1') -Destination (Join-Path $package 'tools\Build-Client-Package.ps1')
    Copy-Item -LiteralPath (Join-Path $repo 'distribution\Set-Exe-Icon.ps1') -Destination (Join-Path $package 'tools\Set-Exe-Icon.ps1')
    Copy-Item -LiteralPath (Join-Path $repo 'assets\Generate-Icon.ps1') -Destination (Join-Path $package 'tools\Generate-Icon.ps1')
    New-Item -ItemType Directory -Path (Join-Path $package 'assets') -Force | Out-Null
    foreach ($kind in @('admin','client')) {
        $defaultIcon = Join-Path $repo ('assets\generated\' + $kind + '.ico')
        if (-not (Test-Path -LiteralPath $defaultIcon -PathType Leaf)) {
            throw "Missing build-time default icon: $defaultIcon"
        }
        Copy-Item -LiteralPath $defaultIcon -Destination (Join-Path $package ('assets\' + $kind + '.ico'))
    }

    Copy-Item -LiteralPath (Join-Path $repo 'distribution\Copy-DotNet-Notices.ps1') -Destination (Join-Path $package 'tools\Copy-DotNet-Notices.ps1')

    # Bundle publisher instructions and project notices for the author PC.
    Copy-Item -LiteralPath (Join-Path $repo 'LICENSE') -Destination (Join-Path $package 'LICENSE')
    Copy-Item -LiteralPath (Join-Path $repo 'THIRD_PARTY_NOTICES.md') -Destination (Join-Path $package 'THIRD_PARTY_NOTICES.md')
    # Capture Microsoft Windows terms during the online build. Portable Admin
    # will carry these files and generate offline Client packages from them.
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $repo 'distribution\Copy-DotNet-Notices.ps1') -SourceDir (Join-Path $repo 'distribution\notices\dotnet') -OutputDir (Join-Path $package 'licenses\dotnet') -DownloadOfficialTerms
    if ($LASTEXITCODE -ne 0) { throw 'Windows .NET redistribution notice collection failed' }
    # Copy actual redistribution license texts from the installed Builder wheels.
    & $Python (Join-Path $repo 'distribution\collect-builder-licenses.py') --output (Join-Path $package 'licenses\builder')
    if ($LASTEXITCODE -ne 0) { throw 'Builder dependency license collection failed' }
    Copy-Item -LiteralPath (Join-Path $repo 'docs\ADMIN_QUICKSTART.md') -Destination (Join-Path $package 'README.md')
    New-Item -ItemType Directory -Path (Join-Path $package 'docs') -Force | Out-Null
    Copy-Item -LiteralPath (Join-Path $repo 'docs\CLIENT_QUICKSTART.md') -Destination (Join-Path $package 'docs\CLIENT_QUICKSTART.md')

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
