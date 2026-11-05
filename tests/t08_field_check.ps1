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
$cases = @(Get-Content -LiteralPath $CasesPath -Encoding UTF8 -Raw | ConvertFrom-Json)
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
    if ($case.kind -eq 'chat' -and @($case.expected_any).Count -eq 0) {
        throw 'Grounded chat must specify expected_any for an objective check'
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
$computer = Get-CimInstance Win32_ComputerSystem
$os = Get-CimInstance Win32_OperatingSystem
$cpu = @(Get-CimInstance Win32_Processor)
$ramGiB = [Math]::Round([double]$computer.TotalPhysicalMemory / 1GB,2)
$cards = @()
try { $cards = @(Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }) } catch {}
$adapters = @()
try {
    $adapters = @(Get-NetAdapter -Physical -ErrorAction Stop | ForEach-Object {
        [pscustomobject]@{name=$_.Name; status=[string]$_.Status}
    })
} catch {}
$hardware = [ordered]@{
    windows_caption = [string]$os.Caption
    windows_version = [string]$os.Version
    architecture = [string]$os.OSArchitecture
    cpu_name = ($cpu | ForEach-Object { $_.Name }) -join '; '
    physical_ram_gib = $ramGiB
    approximately_8gb_ram = ($ramGiB -ge 7.0 -and $ramGiB -le 9.0)
    graphics_devices = $cards
    physical_adapter_status = $adapters
}
$offline = [ordered]@{
    operator_attests_disconnected_network = [bool]$OfflineOperatorAttested
    independent_physical_offline_verification = $false
    note = 'No adapter is disabled by this script. Wi-Fi/Ethernet and other routes must be manually disconnected; a local OS check cannot independently prove an air gap.'
}
$logOut = Join-Path $OutputDir 'api-stdout.log'
$logErr = Join-Path $OutputDir 'api-stderr.log'
$process = $null
$job = $null
$flag = Join-Path $OutputDir '.rss-active'
$results = New-Object System.Collections.Generic.List[object]
$startup = $null
$memory = @()
try {
    $begin = [Diagnostics.Stopwatch]::StartNew()
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
    $begin.Stop()
    $startup = [Math]::Round($begin.Elapsed.TotalSeconds,3)

    # Sampling is a separate job to observe the short-lived llama-completion
    # child. No extra packages required; sample every ~100ms where scheduled.
    [System.IO.File]::WriteAllText($flag,'running')
    $job = Start-Job -ArgumentList $process.Id,$flag -ScriptBlock {
        param([int]$apiPid,[string]$flagPath)
        while (Test-Path -LiteralPath $flagPath) {
            $api = Get-Process -Id $apiPid -ErrorAction SilentlyContinue
            $models = @(Get-Process -Name 'llama-completion' -ErrorAction SilentlyContinue)
            $rss = [long]0
            if ($null -ne $api) { $rss += [long]$api.WorkingSet64 }
            foreach ($item in $models) { $rss += [long]$item.WorkingSet64 }
            [pscustomobject]@{
                rss_mb = [Math]::Round($rss / 1MB,1)
                model_process_count = $models.Count
                sampled_at_utc = [DateTime]::UtcNow.ToString('o')
            }
            Start-Sleep -Milliseconds 100
        }
    }

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
            $timer = [Diagnostics.Stopwatch]::StartNew()
            $errorText=$null
            $data=$null
            try { $data=Request-Json -Path $path -Body $body }
            catch { $errorText=$_.Exception.GetType().Name }
            $timer.Stop()
            $passed=$false
            $sources=@()
            if ($null -ne $data) {
                switch ([string]$case.kind) {
                    'search' {
                        $hits=@($data.results)
                        $passed=$hits.Count -gt 0
                        if ($null -ne $case.expect_results) { $passed=($hits.Count -gt 0) -eq [bool]$case.expect_results }
                        $sources=@($hits | ForEach-Object { $_.source_path })
                    }
                    'chat' {
                        $passed=([bool]$data.grounded)
                        $answer=[string]$data.answer
                        $matches= @($case.expected_any | Where-Object { $answer.IndexOf([string]$_,[StringComparison]::OrdinalIgnoreCase) -ge 0 })
                        $banned= @($case.forbidden_any | Where-Object { $answer.IndexOf([string]$_,[StringComparison]::OrdinalIgnoreCase) -ge 0 })
                        $passed=$passed -and $matches.Count -gt 0 -and $banned.Count -eq 0
                        $sources=@($data.sources | ForEach-Object { $_.source_path })
                    }
                    'chat_no_evidence' {
                        $passed= -not [bool]$data.grounded -and @($data.sources).Count -eq 0
                    }
                    'event' {
                        $expectedMatched= if ($null -ne $case.expect_matched) { [bool]$case.expect_matched } else { $true }
                        $passed=([bool]$data.matched) -eq $expectedMatched
                        if ($expectedMatched -and $null -ne $case.expected_rule_id) {
                            $passed=$passed -and $data.rule_id -ceq [string]$case.expected_rule_id
                        }
                        if ($data.source) { $sources=@([string]$data.source.source_path) }
                    }
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
                latency_seconds=[Math]::Round($timer.Elapsed.TotalSeconds,3)
                passed=[bool]$passed
                source_paths=@($sources)
                error_type=$errorText
            })
        }
    }
} finally {
    if (Test-Path -LiteralPath $flag) { Remove-Item -LiteralPath $flag -Force }
    if ($null -ne $job) {
        $null=Wait-Job -Job $job -Timeout 10
        $memory=@(Receive-Job -Job $job -ErrorAction SilentlyContinue)
        Remove-Job -Job $job -Force -ErrorAction SilentlyContinue
    }
    if ($null -ne $process -and -not $process.HasExited) {
        $process.Kill()
        $process.WaitForExit(15000) | Out-Null
    }
}
$peak=0
if ($memory.Count -gt 0) { $peak=($memory | Measure-Object -Property rss_mb -Maximum).Maximum }
$report=[ordered]@{
    schema_version=1
    collected_utc=[DateTime]::UtcNow.ToString('o')
    tested_package_manifest=(Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $PackageRoot 'manifest.json')).Hash.ToLowerInvariant()
    hardware=$hardware
    offline=$offline
    startup_seconds=$startup
    approximate_peak_process_tree_rss_mb=$peak
    memory_sample_count=$memory.Count
    memory_note='API WorkingSet + all processes named llama-completion; 100ms separate PowerShell job; shared pages and other llama processes can double count; no 8GB guarantee.'
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
