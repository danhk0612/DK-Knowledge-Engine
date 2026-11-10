[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)] [string]$SourceDir,
    [Parameter(Mandatory=$true)] [string]$OutputDir,
    [switch]$DownloadOfficialTerms
)
$ErrorActionPreference = 'Stop'
$source = (Resolve-Path -LiteralPath $SourceDir).Path
$output = [IO.Path]::GetFullPath($OutputDir)
if ($source.TrimEnd('\') -eq $output.TrimEnd('\')) {
    throw 'Notice source and output must differ'
}
New-Item -ItemType Directory -Path $output -Force | Out-Null

$required = @(
    'NET_RUNTIME_LICENSE.txt',
    'NET_RUNTIME_THIRD-PARTY-NOTICES.txt',
    'WPF_LICENSE.txt',
    'WPF_THIRD-PARTY-NOTICES.txt',
    'WINDOWS_LICENSE_INFORMATION.md'
)
foreach ($name in $required) {
    $file = Join-Path $source $name
    if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or (Get-Item $file).Length -lt 500) {
        throw "Missing or empty .NET legal notice: $file"
    }
    Copy-Item -LiteralPath $file -Destination (Join-Path $output $name) -Force
}

$terms = @(
    @('NET_LIBRARY_LICENSE.html', 'https://dotnet.microsoft.com/en-us/dotnet_library_license.htm', 'MICROSOFT'),
    @('WINDOWS_SDK_LICENSE.html', 'https://learn.microsoft.com/en-us/legal/windows-sdk/license', 'WINDOWS')
)
if ($DownloadOfficialTerms) {
    # This runs only while producing a new release/developer ZIP, never on
    # the end user's machine or from the portable offline Admin.
    foreach ($entry in $terms) {
        $destination = Join-Path $output $entry[0]
        Invoke-WebRequest -Uri $entry[1] -UseBasicParsing -TimeoutSec 60 -OutFile $destination
        $html = Get-Content -LiteralPath $destination -Raw -Encoding UTF8
        if ((Get-Item $destination).Length -lt 3000 -or
            $html.IndexOf($entry[2], [StringComparison]::OrdinalIgnoreCase) -lt 0 -or
            $html.IndexOf('LICENSE', [StringComparison]::OrdinalIgnoreCase) -lt 0) {
            throw "Official Microsoft legal page could not be verified: $($entry[1])"
        }
    }
    $runtimeVersions = @(& dotnet --list-runtimes)
    if ($LASTEXITCODE -ne 0 -or -not ($runtimeVersions -match 'Microsoft\.WindowsDesktop\.App\s+10\.')) {
        throw 'Windows Desktop .NET 10 runtime could not be identified'
    }
    $runtimeVersions | Set-Content -LiteralPath (Join-Path $output 'BUILD-DOTNET-RUNTIMES.txt') -Encoding UTF8
}
else {
    foreach ($entry in $terms) {
        $file = Join-Path $source $entry[0]
        if (-not (Test-Path -LiteralPath $file -PathType Leaf) -or (Get-Item $file).Length -lt 3000) {
            throw "Portable Admin does not contain required Microsoft legal terms: $file"
        }
        Copy-Item -LiteralPath $file -Destination (Join-Path $output $entry[0]) -Force
    }
    $versions = Join-Path $source 'BUILD-DOTNET-RUNTIMES.txt'
    if (Test-Path -LiteralPath $versions -PathType Leaf) {
        Copy-Item -LiteralPath $versions -Destination (Join-Path $output 'BUILD-DOTNET-RUNTIMES.txt') -Force
    }
}
Write-Output ('DOTNET_WINDOWS_NOTICES_INCLUDED ' + $output)
