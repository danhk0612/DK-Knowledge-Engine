[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)] [string]$ClientRoot
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $ClientRoot -ErrorAction Stop).Path
$settingsFile = Join-Path $root 'config\settings.json'
$apiExe = Join-Path $root 'engine\DK-Knowledge-API.exe'
foreach ($required in @($settingsFile,$apiExe,(Join-Path $root 'knowledge\knowledge.db'))) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) {
        throw "Offline Client search test prerequisite missing: $required"
    }
}

# Check the product-scoped offline Client made by the standalone Admin.
$cases = @(
    @{ query='Manual';        source='manual-test/manuals/guide.md';    evidence='Manual' },
    @{ query='Configuration'; source='manual-test/manuals/notes.txt';   evidence='Configuration help' },
    @{ query='DOCX';          source='manual-test/manuals/setup.docx';  evidence='DOCX setup instruction' },
    @{ query='PDF';           source='manual-test/manuals/setup.pdf';   evidence='PDF setup instruction' }
)
$original = [IO.File]::ReadAllBytes($settingsFile)
$listener = [Net.Sockets.TcpListener]::new([Net.IPAddress]::Loopback, 0)
$listener.Start()
$port = ([Net.IPEndPoint]$listener.LocalEndpoint).Port
$listener.Stop()
$process = $null
try {
    $settings = Get-Content -LiteralPath $settingsFile -Raw -Encoding UTF8 | ConvertFrom-Json
    $settings.port = $port
    [IO.File]::WriteAllText($settingsFile, ($settings | ConvertTo-Json -Depth 40),
        (New-Object System.Text.UTF8Encoding($false)))
    $process = Start-Process -FilePath $apiExe -WorkingDirectory $root -PassThru

    $deadline = [DateTime]::UtcNow.AddSeconds(50)
    $ready = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($process.HasExited) {
            throw "Offline Client API process exited: $($process.ExitCode)"
        }
        try {
            $health = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:$port/health" -TimeoutSec 2
            if ($health.status -eq 'ready') { $ready = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 300
    }
    if (-not $ready) { throw 'Offline Client API did not become ready' }

    foreach ($case in $cases) {
        $body = @{ product_id='manual-test'; version='1.0.0'; query=$case.query } |
            ConvertTo-Json -Compress
        $data = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$port/search" -ContentType 'application/json; charset=utf-8' -Body $body -TimeoutSec 30
        $matching = @($data.results | Where-Object {
            $_.source_path -eq $case.source -and
            [string]$_.excerpt -like ('*' + $case.evidence + '*')
        })
        if ($matching.Count -lt 1) {
            throw "Indexed document not found in product-scoped offline Client search: $($case.source)"
        }
        Write-Output "V020_MULTIFORMAT_SEARCH_OK source=$($case.source)"
    }
    Write-Output 'V020_MULTIFORMAT_PDF_DOCX_TXT_MD_SEARCH_OK'
}
finally {
    if ($null -ne $process) {
        if (-not $process.HasExited) {
            Stop-Process -Id $process.Id -Force
            $process.WaitForExit()
        }
        $process.Dispose()
    }
    [IO.File]::WriteAllBytes($settingsFile, $original)
}
