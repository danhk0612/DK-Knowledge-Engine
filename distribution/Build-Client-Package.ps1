[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)] [string]$EnginePackage,
    [Parameter(Mandatory=$true)] [string]$KnowledgeDb,
    [Parameter(Mandatory=$true)] [string]$OutputDir,
    [string]$ClientExe,
    [string]$ModelFile,
    [ValidateSet('raw_chatml','qwen3','jinja')] [string]$PromptMode = 'raw_chatml',
    [string]$EmbeddingModelFile,
    [ValidateRange(0.05,1.0)] [double]$EmbeddingMinSimilarity = 0.72
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$engineRoot = (Resolve-Path -LiteralPath $EnginePackage).Path
$db = (Resolve-Path -LiteralPath $KnowledgeDb).Path
$output = [System.IO.Path]::GetFullPath($OutputDir)
$clientProject = Join-Path $repo 'apps\Client\DKKnowledgeClient.csproj'
$finalPackage = Join-Path $output 'DK-Knowledge-Engine-Client'
$finalZip = Join-Path $output 'DK-Knowledge-Engine-Client-Win-x64.zip'

function Test-Within([string]$Candidate, [string]$Root) {
    $candidatePath = [IO.Path]::GetFullPath($Candidate).TrimEnd('\', '/')
    $rootPath = [IO.Path]::GetFullPath($Root).TrimEnd('\', '/')
    return ($candidatePath.Equals($rootPath, [StringComparison]::OrdinalIgnoreCase) -or
        $candidatePath.StartsWith($rootPath + [IO.Path]::DirectorySeparatorChar,
            [StringComparison]::OrdinalIgnoreCase))
}

if ([string]::IsNullOrWhiteSpace($ClientExe) -and
    -not (Test-Path -LiteralPath $clientProject -PathType Leaf)) {
    throw 'Client UI project not found; specify -ClientExe for standalone Admin packaging'
}
# An existing destination is fine; only overlap with input files is forbidden.
if ((Test-Within $output $engineRoot) -or
    (Test-Within $engineRoot $finalPackage) -or
    (Test-Within $db $finalPackage)) {
    throw 'Output package must not overlap the source engine or selected knowledge DB'
}

& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $engineRoot 'Verify-AIHelp.ps1') -Root $engineRoot
if ($LASTEXITCODE -ne 0) { throw 'Input engine package verification failed' }

New-Item -ItemType Directory -Path $output -Force | Out-Null
# Build and verify in a new isolated directory so old output remains untouched
# until the replacement package and ZIP are complete.
$stage = Join-Path $output ('_client-build-' + [guid]::NewGuid().ToString('N'))
$package = Join-Path $stage 'DK-Knowledge-Engine-Client'
$publish = Join-Path $stage '_client-publish'
New-Item -ItemType Directory -Path $package -Force | Out-Null

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

    # Select the user-facing GGUF independently from knowledge DB creation.
    # Custom GGUF files are bundled into this Client package, not referenced
    # by their original path on the authoring workstation.
    $modelHash = $null
    $modelRelative = $null
    if (-not [string]::IsNullOrWhiteSpace($ModelFile)) {
        $chosenModel = (Resolve-Path -LiteralPath $ModelFile -ErrorAction Stop).Path
        if (-not (Test-Path -LiteralPath $chosenModel -PathType Leaf) -or
            [IO.Path]::GetExtension($chosenModel) -ine '.gguf') {
            throw 'Selected AI model must be an existing .gguf file'
        }
        $modelName = [IO.Path]::GetFileName($chosenModel)
        $modelsRoot = Join-Path $package 'models'
        foreach ($oldModel in @(Get-ChildItem -LiteralPath $modelsRoot -File -Filter '*.gguf')) {
            Remove-Item -LiteralPath $oldModel.FullName -Force
        }
        $destinationModel = Join-Path $modelsRoot $modelName
        Copy-Item -LiteralPath $chosenModel -Destination $destinationModel -Force
        $modelHash = (Get-FileHash -LiteralPath $destinationModel -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($modelHash -ne (Get-FileHash -LiteralPath $chosenModel -Algorithm SHA256).Hash.ToLowerInvariant()) {
            throw 'Selected AI model SHA-256 mismatch after copying'
        }
        $modelRelative = 'models/' + $modelName
    }
    if ($modelRelative -or $PSBoundParameters.ContainsKey('PromptMode')) {
        $settingsPath = Join-Path $package 'config/settings.json'
        $settings = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $settings.model) {
            throw 'Input engine settings have no model configuration'
        }
        if ($modelRelative) { $settings.model.file = $modelRelative }
        if ($PSBoundParameters.ContainsKey('PromptMode')) { $settings.model.prompt_mode = $PromptMode }
        [IO.File]::WriteAllText($settingsPath,
            ($settings | ConvertTo-Json -Depth 20), (New-Object System.Text.UTF8Encoding($false)))
    }

    # Populate this isolated package, never an unrelated installed API.
    $dbHash = (Get-FileHash -LiteralPath $db -Algorithm SHA256).Hash.ToLowerInvariant()
    $packagedDb = Join-Path $package 'knowledge\knowledge.db'
    Copy-Item -LiteralPath $db -Destination $packagedDb -Force
    $packagedHash = (Get-FileHash -LiteralPath $packagedDb -Algorithm SHA256).Hash.ToLowerInvariant()
    if ($packagedHash -ne $dbHash) { throw 'Copied knowledge DB SHA-256 mismatch' }
    if ([string]::IsNullOrWhiteSpace($EmbeddingModelFile)) {
        # T19 vectors are unnecessary in the default FTS5 Client. Compact only
        # this isolated package copy; the selected source DB is never modified.
        & (Join-Path $package 'engine\DK-Knowledge-API.exe') --compact-no-embeddings
        if ($LASTEXITCODE -ne 0) { throw 'Client DB vector compaction failed' }
        $packagedHash = (Get-FileHash -LiteralPath $packagedDb -Algorithm SHA256).Hash.ToLowerInvariant()
    }
    $dbInfoText = & (Join-Path $package 'engine\DK-Knowledge-API.exe') --verify-db $packagedDb
    if ($LASTEXITCODE -ne 0) { throw 'Selected knowledge DB failed schema / integrity verification' }
    $dbInfo = $dbInfoText | ConvertFrom-Json
    $embeddingHash = $null
    $embeddingRelative = $null
    if (-not [string]::IsNullOrWhiteSpace($EmbeddingModelFile)) {
        if (-not $dbInfo.embedding -or -not $dbInfo.embedding.complete) {
            throw 'Selected DB has no complete semantic embedding index'
        }
        $selectedEncoder = (Resolve-Path -LiteralPath $EmbeddingModelFile -ErrorAction Stop).Path
        if (-not (Test-Path -LiteralPath $selectedEncoder -PathType Leaf) -or
            [IO.Path]::GetExtension($selectedEncoder) -ine '.gguf') {
            throw 'Embedding model must be an existing .gguf file'
        }
        $embeddingHash = (Get-FileHash -LiteralPath $selectedEncoder -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($embeddingHash -ne [string]$dbInfo.embedding.model_sha256) {
            throw 'Selected semantic GGUF does not match the author-built DB vectors'
        }
        if (-not (Test-Path -LiteralPath (Join-Path $package 'runtime/llama-embedding.exe') -PathType Leaf)) {
            throw 'Input portable engine has no compatible llama-embedding.exe'
        }
        $encoderName = [IO.Path]::GetFileName($selectedEncoder)
        $embeddingRelative = 'models/' + $encoderName
        $encoderDest = Join-Path $package ('models/' + $encoderName)
        if ((Test-Path -LiteralPath $encoderDest -PathType Leaf) -and
            (Get-FileHash -LiteralPath $encoderDest -Algorithm SHA256).Hash.ToLowerInvariant() -ne $embeddingHash) {
            throw 'Embedding GGUF filename collides with another selected model'
        }
        Copy-Item -LiteralPath $selectedEncoder -Destination $encoderDest -Force
        $settingsPath = Join-Path $package 'config/settings.json'
        $settings = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $settings | Add-Member -NotePropertyName embedding -NotePropertyValue ([pscustomobject]@{
            file = $embeddingRelative
            runtime = 'runtime/llama-embedding.exe'
            min_similarity = $EmbeddingMinSimilarity
        }) -Force
        [IO.File]::WriteAllText($settingsPath,
            ($settings | ConvertTo-Json -Depth 20), (New-Object System.Text.UTF8Encoding($false)))
    }
    else {
        # Default Client is genuinely light: it carries neither the optional
        # embedding GGUF nor its executable, only FTS5 + the user LLM.
        $embeddingExe = Join-Path $package 'runtime/llama-embedding.exe'
        if (Test-Path -LiteralPath $embeddingExe) {
            Remove-Item -LiteralPath $embeddingExe -Force
        }
    }
    [System.IO.File]::WriteAllText(
        (Join-Path $package 'knowledge\knowledge.sha256'),
        $packagedHash + [Environment]::NewLine,
        (New-Object System.Text.UTF8Encoding($false))
    )
    foreach ($name in @('knowledge.previous.db', 'knowledge.previous.sha256')) {
        $stale = Join-Path $package ('knowledge\' + $name)
        if (Test-Path -LiteralPath $stale) {
            Remove-Item -LiteralPath $stale -Force
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($ClientExe)) {
        $gui = (Resolve-Path -LiteralPath $ClientExe).Path
    }
    else {
        & dotnet publish $clientProject -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o $publish
        if ($LASTEXITCODE -ne 0) { throw 'Client UI publish failed' }
        $gui = Join-Path $publish 'DK-Knowledge-Client.exe'
    }
    if (-not (Test-Path -LiteralPath $gui -PathType Leaf) -or
        [IO.Path]::GetExtension($gui) -ne '.exe') {
        throw 'Client GUI executable not found'
    }
    Copy-Item -LiteralPath $gui -Destination (Join-Path $package 'DK-Knowledge-Client.exe')

    # In developer mode $repo is the source tree. In standalone Admin mode
    # it resolves to the authoring bundle, which carries the same notices.
    foreach ($entry in @(
        @('LICENSE', 'LICENSE'),
        @('THIRD_PARTY_NOTICES.md', 'THIRD_PARTY_NOTICES.md'),
        @('docs\CLIENT_QUICKSTART.md', 'README.md')
    )) {
        $src = Join-Path $repo $entry[0]
        if (-not (Test-Path -LiteralPath $src -PathType Leaf)) {
            throw "Missing Client distribution notice: $src"
        }
        Copy-Item -LiteralPath $src -Destination (Join-Path $package $entry[1]) -Force
    }

    # Client created by a portable Admin reuses its bundled legal texts;
    # developer/CI builds collect current Microsoft terms at build time.
    $noticeScript = Join-Path $PSScriptRoot 'Copy-DotNet-Notices.ps1'
    $repoNoticeSource = Join-Path $repo 'distribution\notices\dotnet'
    $destNotices = Join-Path $package 'licenses\dotnet'
    if (Test-Path -LiteralPath $repoNoticeSource -PathType Container) {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $noticeScript 
            -SourceDir $repoNoticeSource -OutputDir $destNotices -DownloadOfficialTerms
    }
    else {
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $noticeScript 
            -SourceDir (Join-Path $repo 'licenses\dotnet') -OutputDir $destNotices
    }
    if ($LASTEXITCODE -ne 0) { throw 'Client .NET redistribution notice collection failed' }

    $manifestPath = Join-Path $package 'manifest.json'
    $manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($modelRelative) {
        foreach ($property in @($manifest.immutable_files.PSObject.Properties)) {
            if ($property.Name.StartsWith('models/', [StringComparison]::OrdinalIgnoreCase)) {
                $manifest.immutable_files.PSObject.Properties.Remove($property.Name)
            }
        }
        $manifest.immutable_files | Add-Member -NotePropertyName $modelRelative -NotePropertyValue $modelHash -Force
        $manifest.model = 'selected-local-gguf/' + [IO.Path]::GetFileName($modelRelative)
        $manifest.model_sha256 = $modelHash
    }
    # Add the separate query encoder AFTER changing the generative GGUF
    # so its hash remains in the immutable file list.
    if (-not $embeddingRelative) {
        $manifest.immutable_files.PSObject.Properties.Remove('runtime/llama-embedding.exe')
    }
    else {
        $manifest.immutable_files | Add-Member -NotePropertyName $embeddingRelative -NotePropertyValue $embeddingHash -Force
        $manifest | Add-Member -NotePropertyName embedding_model_sha256 -NotePropertyValue $embeddingHash -Force
    }
    $guiHash = (Get-FileHash -LiteralPath (Join-Path $package 'DK-Knowledge-Client.exe') -Algorithm SHA256).Hash.ToLowerInvariant()
    $manifest.immutable_files | Add-Member -NotePropertyName 'DK-Knowledge-Client.exe' -NotePropertyValue $guiHash -Force
    foreach ($name in @('LICENSE', 'README.md', 'THIRD_PARTY_NOTICES.md')) {
        $noticeHash = (Get-FileHash -LiteralPath (Join-Path $package $name) -Algorithm SHA256).Hash.ToLowerInvariant()
        $manifest.immutable_files | Add-Member -NotePropertyName $name -NotePropertyValue $noticeHash -Force
    }
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

    $stageZip = Join-Path $stage 'DK-Knowledge-Engine-Client-Win-x64.zip'
    Compress-Archive -LiteralPath $package -DestinationPath $stageZip -CompressionLevel Fastest

    # Reuse the chosen output directory. Replace generated files by relative path
    # without deleting unrelated files that the author may keep in the directory.
    # Remove obsolete *previously generated* GGUFs only when the existing
    # model's hash still matches the old manifest (leave user-modified files alone).
    $previousManifestPath = Join-Path $finalPackage 'manifest.json'
    if (Test-Path -LiteralPath $previousManifestPath -PathType Leaf) {
        $oldManifest = Get-Content -LiteralPath $previousManifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $newManifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($entry in @($oldManifest.immutable_files.PSObject.Properties)) {
            $isManagedModel = $entry.Name -match '^models/[^/\\]+\.gguf$'
            $isManagedEmbeddingRuntime = $entry.Name -eq 'runtime/llama-embedding.exe'
            if ((-not $isManagedModel -and -not $isManagedEmbeddingRuntime) -or
                $newManifest.immutable_files.PSObject.Properties[$entry.Name]) {
                continue
            }
            $obsolete = Join-Path $finalPackage ($entry.Name.Replace('/', [IO.Path]::DirectorySeparatorChar))
            if (Test-Path -LiteralPath $obsolete -PathType Leaf) {
                $oldHash = (Get-FileHash -LiteralPath $obsolete -Algorithm SHA256).Hash.ToLowerInvariant()
                if ($oldHash -eq [string]$entry.Value) {
                    Remove-Item -LiteralPath $obsolete -Force
                }
            }
        }
    }
    New-Item -ItemType Directory -Path $finalPackage -Force | Out-Null
    foreach ($file in (Get-ChildItem -LiteralPath $package -File -Recurse)) {
        $relative = $file.FullName.Substring($package.Length).TrimStart('\', '/')
        $destination = Join-Path $finalPackage $relative
        New-Item -ItemType Directory -Path (Split-Path -Parent $destination) -Force | Out-Null
        Copy-Item -LiteralPath $file.FullName -Destination $destination -Force
    }
    # The ZIP is assembled from clean staging, never from the reused output folder.
    Copy-Item -LiteralPath $stageZip -Destination $finalZip -Force
    Write-Output ('CLIENT_ONLY_PACKAGE_READY ' + $finalZip)
}
finally {
    if (Test-Path -LiteralPath $stage) {
        Remove-Item -LiteralPath $stage -Recurse -Force
    }
}
