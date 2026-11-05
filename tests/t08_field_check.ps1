# Windows PowerShell 5.1, no modules, Python, Docker or network required on target PC.
# Runs the EXISTING T07 portable package, never rewrites its config or knowledge DB.
[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)][string]$PackageRoot,
    [Parameter(Mandatory=$true)][string]$CasesPath,
    [Parameter(Mandatory=$true)][string]$OutputDir,
    [ValidateRange(1,10)][int]$RunsPerChat = 3,
    [switch]$OfflineOperatorAttested
)

$ErrorActionPreference = 'Stop'
$PackageRoot = (Resolve-Path -LiteralPath $PackageRoot).Path
$CasesPath = (Resolve-Path -LiteralPath $CasesPath).Path
$OutputDir = [System.IO.Path]::GetFullPath($OutputDir)
if (Test-Path -LiteralPath $OutputDir) {
    throw 'OutputDir must be a new path to avoid overwriting prior evidence'
}
$exe = Join-Path $PackageRoot 'engine\DK-Knowledge-API.exe'
$settingsPath = Join-Path $PackageRoot 'config\settings.json'
$verifyScript = Join-Path $PackageRoot 'Verify-AIHelp.ps1'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf) -or
    -not (Test-Path -LiteralPath $settingsPath -PathType Leaf) -or
    -not (Test-Path -LiteralPath $verifyScript -PathType Leaf)) {
    throw 'Not a valid T07 portable package'
}

# Validate input contracts BEFORE launching executable or creating report files.
$parsedCases = Get-Content -LiteralPath $CasesPath -Encoding UTF8 -Raw | ConvertFrom-Json
# Windows PowerShell 5.1 can return a whole top-level JSON array as ONE
# pipeline item; expanding it explicitly prevents evaluating all cases as one.
$cases = if ($parsedCases -is [System.Array]) { @($parsedCases) } else { @($parsedCases) }
if ($cases.Count -eq 0) { throw 'Cases file must contain at least one case' }
$caseNames = @{}
foreach ($case in $cases) {
    if ($case -isnot [pscustomobject]) { throw 'Every case must be a JSON object' }
    if ([string]::IsNullOrWhiteSpace([string]$case.id) -or
        [string]::IsNullOrWhiteSpace([string]$case.product_id)) {
        throw 'Every case must have id and product_id'
    }
    if ($caseNames.ContainsKey([string]$case.id)) { throw 'Duplicate case id' }
    $caseNames[[string]$case.id] = $true
    if (@('search','chat','event','chat_no_evidence') -cnotcontains [string]$case.kind) {
        throw "Unsupported case kind: $($case.kind)"
    }
    if ($case.kind -eq 'search' -and [string]::IsNullOrWhiteSpace([string]$case.query)) {
        throw 'Search requires query'
    }
    if (($case.kind -eq 'chat' -or $case.kind -eq 'chat_no_evidence') -and
        [string]::IsNullOrWhiteSpace([string]$case.question)) {
        throw 'Chat requires question'
    }
    if ($case.kind -eq 'event' -and
        [string]::IsNullOrWhiteSpace([string]$case.event_id) -and
        [string]::IsNullOrWhiteSpace([string]$case.error_code)) {
        throw 'Event requires event_id or error_code'
    }
    if ($case.kind -eq 'chat') {
        $keywords = @($case.expected_any | Where-Object { -not [string]::IsNullOrWhiteSpace([string]$_) })
        if ($null -eq $case.expected_any -or
            $keywords.Count -eq 0 -or
            $keywords.Count -ne @($case.expected_any).Count) {
            throw 'Grounded chat must specify non-empty expected_any keywords'
        }
    }
}
$settings = Get-Content -LiteralPath $settingsPath -Raw -Encoding UTF8 | ConvertFrom-Json
$port = [int]$settings.port
if ($port -lt 1 -or $port -gt 65535) { throw 'Invalid portable API port' }
$base = "http://127.0.0.1:$port"

function Request-Json {
    param([string]$Path,[object]$Body=$null)
    $request = [System.Net.HttpWebRequest][System.Net.WebRequest]::Create($base + $Path)
    $request.Proxy = $null
    $request.Timeout = 180000
    $request.ReadWriteTimeout = 180000
    if ($null -ne $Body) {
        $request.Method = 'POST'
        $request.ContentType = 'application/json'
        $json = $Body | ConvertTo-Json -Depth 10 -Compress
        $raw = [System.Text.Encoding]::UTF8.GetBytes($json)
        $request.ContentLength = $raw.Length
        $stream = $request.GetRequestStream()
        try { $stream.Write($raw,0,$raw.Length) } finally { $stream.Dispose() }
    } else { $request.Method='GET' }
    $response = $request.GetResponse()
    try {
        $reader = New-Object System.IO.StreamReader($response.GetResponseStream(),[System.Text.Encoding]::UTF8)
        try { return ($reader.ReadToEnd() | ConvertFrom-Json) } finally { $reader.Dispose() }
    } finally { $response.Dispose() }
}

# Port collision must not silently evaluate another service at this address.
$socket = New-Object System.Net.Sockets.TcpClient
try {
    $connection = $socket.BeginConnect('127.0.0.1',$port,$null,$null)
    if ($connection.AsyncWaitHandle.WaitOne(400)) {
        try { $socket.EndConnect($connection); throw "Port $port is already in use; stop the other server first" }
        catch [System.Net.Sockets.SocketException] { }
    }
} finally { $socket.Dispose() }

& $verifyScript -Root $PackageRoot | Out-Null
if ($LASTEXITCODE -ne 0) { throw 'Package verification failed' }

New-Item -ItemType Directory -Path $OutputDir | Out-Null
$env:SystemRoot | Out-Null
$os = Get-CimInstance Win32_OperatingSystem
$platform = [ordered]@{
    windows_caption = [string]$os.Caption
    windows_version = [string]$os.Version
    architecture = [string]$os.OSArchitecture
}
$offline = [ordered]@{
    operator_attests_disconnected_network = [bool]$OfflineOperatorAttested
    independent_physical_offline_verification = $false
    note = 'No adapter is disabled by this script. Wi-Fi/Ethernet and other routes must be manually disconnected; a local OS check cannot independently prove an air gap.'
}
$logOut = Join-Path $OutputDir 'api-stdout.log'
$logErr = Join-Path $OutputDir 'api-stderr.log'
$process = $null
$results = New-Object System.Collections.Generic.List[object]
try {
    $process = Start-Process -FilePath $exe -WorkingDirectory $PackageRoot -PassThru -RedirectStandardOutput $logOut -RedirectStandardError $logErr
    $ready = $false
    for ($attempt=0;$attempt -lt 80;$attempt++) {
        if ($process.HasExited) { throw "Portable API exited with code $($process.ExitCode)" }
        try {
            $health=Request-Json -Path '/health'
            if ($health.status -eq 'ready' -and $health.llm_ready) { $ready=$true; break }
        } catch {}
        Start-Sleep -Milliseconds 250
    }
    if (-not $ready) { throw 'T07 portable API not ready after 20 seconds' }
    foreach ($case in $cases) {
        $count = if ($case.kind -eq 'chat') { $RunsPerChat } else { 1 }
        for ($repeat=1;$repeat -le $count;$repeat++) {
            $body = [ordered]@{
                product_id = [string]$case.product_id
                version = if ([string]::IsNullOrWhiteSpace([string]$case.version)) { $null } else { [string]$case.version }
            }
            $path = ''
            switch ([string]$case.kind) {
                'search' { $path='/search';$body.query=[string]$case.query }
                'chat' { $path='/chat';$body.question=[string]$case.question }
                'chat_no_evidence' { $path='/chat';$body.question=[string]$case.question }
                'event' {
                    $path='/event'
                    foreach ($key in @('event_id','error_code','screen_id')) {
                        $body[$key]=if ($null -eq $case.$key) { $null } else { [string]$case.$key }
                    }
                }
            }
            $errorText=$null
            $data=$null
            try { $data=Request-Json -Path $path -Body $body }
            catch { $errorText=$_.Exception.GetType().Name }
            $passed=$false
            $sources=@()
            if ($null -ne $data) {
                switch ([string]$case.kind) {
                    'search' {
                        # Windows PowerShell 5.1 may expose a single JSON
                        # result as an object rather than an Array. Keep the
                        # required results field, reject null/string payloads,
                        # and accept a single structured result with source_path.
                        $entries = @($data.results | Where-Object { $null -ne $_ })
                        $validResults = ($null -ne $data.PSObject.Properties['results']) -and
                            (($data.results -is [System.Array]) -or
                             ($entries.Count -eq 1 -and
                              $null -ne $entries[0].PSObject.Properties['source_path']))
                        $hits = if ($validResults) { $entries } else { @() }
                        $passed = $validResults -and $hits.Count -gt 0
                        if ($null -ne $case.expect_results) {
                            $passed = $validResults -and (($hits.Count -gt 0) -eq [bool]$case.expect_results)
                        }
                        $sources=@($hits | ForEach-Object { $_.source_path })
                    }
                    'chat' {
                        $validSources = $null -ne $data.PSObject.Properties['sources'] -and
                            $data.sources -is [System.Array]
                        $sources = if ($validSources) { @($data.sources | ForEach-Object { $_.source_path }) } else { @() }
                        $passed = ([bool]$data.grounded) -and $validSources -and $sources.Count -gt 0
                        $answer=[string]$data.answer
                        $matches= @($case.expected_any | Where-Object { $answer.IndexOf([string]$_,[StringComparison]::OrdinalIgnoreCase) -ge 0 })
                        $banned= @($case.forbidden_any | Where-Object { $answer.IndexOf([string]$_,[StringComparison]::OrdinalIgnoreCase) -ge 0 })
                        $passed=$passed -and $matches.Count -gt 0 -and $banned.Count -eq 0
                    }
                    'chat_no_evidence' {
                        $passed = ($null -ne $data.PSObject.Properties['grounded']) -and
                            ($data.grounded -eq $false) -and
                            ($null -ne $data.PSObject.Properties['sources']) -and
                            ($data.sources -is [System.Array]) -and
                            ($data.sources.Count -eq 0)
                    }
                    'event' {
                        $expectedMatched= if ($null -ne $case.expect_matched) { [bool]$case.expect_matched } else { $true }
                        $passed = ($null -ne $data.PSObject.Properties['matched']) -and
                            (([bool]$data.matched) -eq $expectedMatched)
                        if ($expectedMatched -and $null -ne $case.expected_rule_id) {
                            $passed=$passed -and $data.rule_id -ceq [string]$case.expected_rule_id
                        }
                        if ($data.source) { $sources=@([string]$data.source.source_path) }
                    }
                }
                if ($env:GITHUB_ACTIONS -eq 'true' -and $case.id -eq 'sample-search') {
                    Write-Output ("T08_DIAGNOSTIC sample-search before-source-check " +
                        "results_field=" + ($null -ne $data.PSObject.Properties['results']) +
                        " results_type=" + $data.results.GetType().FullName +
                        " valid_results=" + $validResults +
                        " hits=" + $hits.Count +
                        " expect_results=" + [bool]$case.expect_results +
                        " source_count=" + $sources.Count +
                        " source_matches=" + ($sources -ccontains [string]$case.expected_source) +
                        " passed=" + $passed)
                }
                if ($null -ne $case.expected_source) {
                    $passed=$passed -and ($sources -ccontains [string]$case.expected_source)
                }
            }
            # Results never store raw questions, retrieved excerpts or answers.
            $results.Add([pscustomobject]@{
                case_id=[string]$case.id
                kind=[string]$case.kind
                iteration=$repeat
                passed=[bool]$passed
                source_paths=@($sources)
                error_type=$errorText
            })
        }
    }
} finally {
    if ($null -ne $process -and -not $process.HasExited) {
        $process.Kill()
        $process.WaitForExit(15000) | Out-Null
    }
}
$report=[ordered]@{
    schema_version=1
    collected_utc=[DateTime]::UtcNow.ToString('o')
    tested_package_manifest=(Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $PackageRoot 'manifest.json')).Hash.ToLowerInvariant()
    platform=$platform
    offline=$offline
    tests=@($results.ToArray())
    passed_count=@($results | Where-Object { $_.passed }).Count
    total_count=$results.Count
    pending_manual_checks=@('actual_physical_airgap','browser_https_lna','smartscreen_code_signing','local_license_review','real_customer_manual_answer_review')
}
$json=$report | ConvertTo-Json -Depth 12
[IO.File]::WriteAllText((Join-Path $OutputDir 'field-validation.json'),$json,(New-Object System.Text.UTF8Encoding($false)))
if ($report.passed_count -eq $report.total_count) {
    Write-Output ('T08_FIELD_CHECK_OK passed=' + $report.passed_count + ' of ' + $report.total_count)
} else {
    Write-Output ('T08_FIELD_CHECK_FAILED passed=' + $report.passed_count + ' of ' + $report.total_count)
    exit 1
}
