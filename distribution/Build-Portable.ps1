[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)] [string]$KnowledgeDb,
    [Parameter(Mandatory=$true)] [string]$LlamaBinDir,
    [Parameter(Mandatory=$true)] [string]$ModelFile,
    [Parameter(Mandatory=$true)] [string]$LlamaLicense,
    [Parameter(Mandatory=$true)] [string]$ModelLicense,
    [Parameter(Mandatory=$true)] [string]$PythonLicense,
    [Parameter(Mandatory=$true)] [string]$PyInstallerLicense,
    [Parameter(Mandatory=$true)] [string]$OutputDir,
    [string]$LlamaCommit = 'unknown',
    [string]$Python = 'python'
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$knowledge = (Resolve-Path -LiteralPath $KnowledgeDb).Path
$runtimeDir = (Resolve-Path -LiteralPath $LlamaBinDir).Path
$model = (Resolve-Path -LiteralPath $ModelFile).Path
$llamaLicensePath = (Resolve-Path -LiteralPath $LlamaLicense).Path
$modelLicensePath = (Resolve-Path -LiteralPath $ModelLicense).Path
$pythonLicensePath = (Resolve-Path -LiteralPath $PythonLicense).Path
$pyInstallerLicensePath = (Resolve-Path -LiteralPath $PyInstallerLicense).Path
$exe = Join-Path $runtimeDir 'llama-completion.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw 'Required CPU llama-completion.exe was not found in LlamaBinDir'
}
$requiredHash = 'd2387ca2dbfee2ffabce7120d3770dadca0b293052bc2f0e138fdc940d9bc7b5'
$actualHash = (Get-FileHash -LiteralPath $model -Algorithm SHA256).Hash.ToLowerInvariant()
if ($actualHash -ne $requiredHash) {
    throw 'Qwen3 1.7B Q4_K_M model SHA-256 does not match the T04 contract'
}
$output = [System.IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $output) {
    throw 'OutputDir must not exist; refusing to delete or overwrite an existing package'
}
New-Item -ItemType Directory -Path $output | Out-Null
$buildDir = Join-Path $output '_build'
$package = Join-Path $output 'DK-Knowledge-Engine-Win-x64'
foreach ($name in @('engine','runtime','models','knowledge','config','licenses')) {
    New-Item -ItemType Directory -Path (Join-Path $package $name) -Force | Out-Null
}
try {
    & $Python -m PyInstaller --noconfirm --clean --onedir --console --name 'DK-Knowledge-API' --paths $repoRoot --distpath (Join-Path $buildDir 'dist') --workpath (Join-Path $buildDir 'work') --specpath (Join-Path $buildDir 'spec') (Join-Path $repoRoot 'distribution\server_entry.py')
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed' }
    $engineDir = Join-Path $buildDir 'dist\DK-Knowledge-API'
    Copy-Item -Path (Join-Path $engineDir '*') -Destination (Join-Path $package 'engine') -Recurse -Force

    foreach ($file in (Get-ChildItem -LiteralPath $runtimeDir -File)) {
        if ($file.Extension -eq '.dll' -or $file.Name -eq 'llama-completion.exe') {
            Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $package 'runtime') -Force
        }
    }
    Copy-Item -LiteralPath $model -Destination (Join-Path $package 'models\Qwen3-1.7B-Q4_K_M.gguf')
    Copy-Item -LiteralPath $knowledge -Destination (Join-Path $package 'knowledge\knowledge.db')
    Copy-Item -LiteralPath $llamaLicensePath -Destination (Join-Path $package 'licenses\llama.cpp-LICENSE')
    Copy-Item -LiteralPath $modelLicensePath -Destination (Join-Path $package 'licenses\Qwen3-Apache-2.0-LICENSE')
    Copy-Item -LiteralPath $pythonLicensePath -Destination (Join-Path $package 'licenses\CPython-LICENSE')
    Copy-Item -LiteralPath $pyInstallerLicensePath -Destination (Join-Path $package 'licenses\PyInstaller-COPYING.txt')

    foreach ($name in @('Start-AIHelp.cmd','Update-Knowledge.ps1','Verify-AIHelp.ps1')) {
        Copy-Item -LiteralPath (Join-Path $repoRoot ('distribution\templates\' + $name)) -Destination (Join-Path $package $name)
    }
    $settings = [ordered]@{
        port = 8765
        allowed_origins = @()
        model = [ordered]@{
            file = 'models/Qwen3-1.7B-Q4_K_M.gguf'
            runtime = 'runtime/llama-completion.exe'
            threads = 4
            context_size = 4096
            max_tokens = 192
            timeout_seconds = 180
            gpu_layers = 0
            prompt_mode = 'raw_chatml'
        }
    }
    [System.IO.File]::WriteAllText((Join-Path $package 'config\settings.json'), ($settings | ConvertTo-Json -Depth 4), (New-Object System.Text.UTF8Encoding($false)))

    $engine = Join-Path $package 'engine\DK-Knowledge-API.exe'
    $db = Join-Path $package 'knowledge\knowledge.db'
    & $engine --verify-db $db
    if ($LASTEXITCODE -ne 0) { throw 'Bundled database did not pass validation' }
    (Get-FileHash -LiteralPath $db -Algorithm SHA256).Hash.ToLowerInvariant() | Set-Content -LiteralPath (Join-Path $package 'knowledge\knowledge.sha256') -Encoding Ascii

    $hashes = [ordered]@{}
    $files = Get-ChildItem -LiteralPath $package -Recurse -File | Sort-Object FullName
    foreach ($file in $files) {
        $relative = $file.FullName.Substring($package.Length + 1).Replace('\', '/')
        if ($relative.StartsWith('knowledge/') -or $relative.StartsWith('config/') -or $relative -eq 'manifest.json') {
            continue
        }
        $hashes[$relative] = (Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $manifest = [ordered]@{
        package_format = 1
        schema_version = '1'
        model = 'ggml-org/Qwen3-1.7B-GGUF/Qwen3-1.7B-Q4_K_M.gguf'
        model_sha256 = $requiredHash
        runtime_source = 'ggml-org/llama.cpp v0.8.0'
        runtime_commit = $LlamaCommit
        immutable_files = $hashes
    }
    [System.IO.File]::WriteAllText((Join-Path $package 'manifest.json'), ($manifest | ConvertTo-Json -Depth 10), (New-Object System.Text.UTF8Encoding($false)))

    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $package 'Verify-AIHelp.ps1')
    if ($LASTEXITCODE -ne 0) { throw 'Portable package verification failed' }

    $zip = Join-Path $output 'DK-Knowledge-Engine-Win-x64.zip'
    Compress-Archive -Path $package -DestinationPath $zip -CompressionLevel Fastest -Force
    Write-Output ('PORTABLE_PACKAGE_READY ' + $zip)
}
finally {
    if (Test-Path -LiteralPath $buildDir) {
        Remove-Item -LiteralPath $buildDir -Recurse -Force
    }
}
