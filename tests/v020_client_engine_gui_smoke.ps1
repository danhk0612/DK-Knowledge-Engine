[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)] [string]$PackageRoot
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path -LiteralPath $PackageRoot -ErrorAction Stop).Path
$exe = Join-Path $root 'DK-Knowledge-Client.exe'
$apiExe = (Resolve-Path -LiteralPath (Join-Path $root 'engine\DK-Knowledge-API.exe')).Path
$settingsFile = Join-Path $root 'config\settings.json'
$knowledge = Join-Path $root 'knowledge\knowledge.db'
$backup = Join-Path $root 'knowledge\knowledge.previous.db'
$journal = Join-Path $root 'knowledge\knowledge.pending.json'
foreach ($required in @($exe,$settingsFile,$knowledge)) {
    if (-not (Test-Path -LiteralPath $required -PathType Leaf)) { throw "Client package file missing: $required" }
}
$originalSettings = [IO.File]::ReadAllBytes($settingsFile)
$originalDbHash = (Get-FileHash -LiteralPath $knowledge -Algorithm SHA256).Hash
$tempDb = Join-Path $env:RUNNER_TEMP ('v020-update-' + [guid]::NewGuid().ToString('N') + '.db')
Copy-Item -LiteralPath $knowledge -Destination $tempDb -Force
$port = 28769
$baseUrl = "http://127.0.0.1:$port"
$originalPort = (Get-Content -LiteralPath $settingsFile -Raw | ConvertFrom-Json).port
if (Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) {
    throw "Test port $port is occupied"
}
$settings = Get-Content -LiteralPath $settingsFile -Raw | ConvertFrom-Json
$settings.port = $port
[IO.File]::WriteAllText($settingsFile, ($settings | ConvertTo-Json -Depth 30),
    (New-Object System.Text.UTF8Encoding($false)))

Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
$client = $null
function Find-Element(
    [System.Windows.Automation.AutomationElement]$Parent,
    [string]$Id,
    [int]$Seconds = 20
) {
    $condition = [System.Windows.Automation.PropertyCondition]::new(
        [System.Windows.Automation.AutomationElement]::AutomationIdProperty, $Id)
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $element = $Parent.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
        if ($null -ne $element) { return $element }
        Start-Sleep -Milliseconds 250
    }
    throw "Client GUI control not found: $Id"
}
function Invoke-Button([System.Windows.Automation.AutomationElement]$Window, [string]$Id) {
    $item = Find-Element $Window $Id
    $item.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
}
function Select-Tab([System.Windows.Automation.AutomationElement]$Window, [string]$Id) {
    $item = Find-Element $Window $Id
    $item.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
}
function Wait-Health([bool]$Ready, [int]$Seconds = 35) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $ok = $false
        try {
            $json = Invoke-RestMethod -Uri "$baseUrl/health" -TimeoutSec 2
            $ok = $json.status -eq 'ready'
        } catch { }
        if ($ok -eq $Ready) { return }
        Start-Sleep -Milliseconds 350
    }
    throw "GUI-owned API readiness did not become $Ready on port $port"
}
function Get-LocalApiPid {
    $target = $apiExe.ToLowerInvariant()
    $processes = @(Get-CimInstance Win32_Process -Filter "Name='DK-Knowledge-API.exe'" -ErrorAction Stop)
    $owned = @($processes | Where-Object { $_.ExecutablePath -and $_.ExecutablePath.ToLowerInvariant() -eq $target })
    if ($owned.Count -gt 1) { throw 'More than one API process for this Client root' }
    if ($owned.Count -eq 0) { return 0 }
    return [int]$owned[0].ProcessId
}
function Wait-ApiPid([int]$Old, [int]$Seconds = 35) {
    $deadline = [DateTime]::UtcNow.AddSeconds($Seconds)
    while ([DateTime]::UtcNow -lt $deadline) {
        $pidValue = Get-LocalApiPid
        if ($pidValue -ne 0 -and $pidValue -ne $Old) { return $pidValue }
        Start-Sleep -Milliseconds 300
    }
    throw 'Client did not launch a new API process after DB maintenance'
}
try {
    $client = Start-Process -FilePath $exe -WorkingDirectory $root -PassThru
    $condition = [System.Windows.Automation.PropertyCondition]::new(
        [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $client.Id)
    $deadline = [DateTime]::UtcNow.AddSeconds(40)
    $window = $null
    while ([DateTime]::UtcNow -lt $deadline) {
        if ($client.HasExited) { throw "Client GUI exited before UI test: $($client.ExitCode)" }
        $window = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst(
            [System.Windows.Automation.TreeScope]::Children, $condition)
        if ($null -ne $window) { break }
        Start-Sleep -Milliseconds 350
    }
    if ($null -eq $window) { throw 'No Client WPF window found' }
    Select-Tab $window 'SettingsTab'
    Invoke-Button $window 'StartEngineButton'
    Wait-Health $true
    $firstPid = Wait-ApiPid 0
    Write-Output "V020_GUI_ENGINE_STARTED pid=$firstPid"

    Select-Tab $window 'KnowledgeTab'
    $dbPath = Find-Element $window 'DbPathBox'
    $dbPath.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue($tempDb)
    Invoke-Button $window 'ApplyDbButton'
    $deadline = [DateTime]::UtcNow.AddSeconds(65)
    $updated = 0
    while ([DateTime]::UtcNow -lt $deadline) {
        $candidate = Get-LocalApiPid
        if ($candidate -ne 0 -and $candidate -ne $firstPid -and
            (Test-Path -LiteralPath $backup -PathType Leaf) -and
            -not (Test-Path -LiteralPath $journal -PathType Leaf)) {
            try {
                $health = Invoke-RestMethod -Uri "$baseUrl/health" -TimeoutSec 2
                if ($health.status -eq 'ready') { $updated = $candidate; break }
            } catch { }
        }
        Start-Sleep -Milliseconds 400
    }
    if ($updated -eq 0) { throw 'GUI DB update did not stop/restart its own API and create a backup' }
    if ((Get-FileHash -LiteralPath $backup -Algorithm SHA256).Hash -ne $originalDbHash) {
        throw 'GUI DB update backup is not the original knowledge database'
    }
    Write-Output "V020_GUI_DB_APPLY_RESTART_OK pid=$updated"

    Invoke-Button $window 'RollbackDbButton'
    $rolledBack = Wait-ApiPid $updated 65
    Wait-Health $true
    if ((Get-FileHash -LiteralPath $knowledge -Algorithm SHA256).Hash -ne $originalDbHash) {
        throw 'GUI rollback failed to restore original database'
    }
    if (Test-Path -LiteralPath $journal -PathType Leaf) {
        throw 'GUI rollback left a pending recovery journal'
    }
    Write-Output "V020_GUI_DB_ROLLBACK_RESTART_OK pid=$rolledBack"

    Select-Tab $window 'SettingsTab'
    Invoke-Button $window 'StopEngineButton'
    Wait-Health $false
    $deadline = [DateTime]::UtcNow.AddSeconds(10)
    while ((Get-LocalApiPid) -ne 0 -and [DateTime]::UtcNow -lt $deadline) {
        Start-Sleep -Milliseconds 300
    }
    if ((Get-LocalApiPid) -ne 0) { throw 'GUI engine stop left its API running' }
    Write-Output 'V020_CLIENT_GUI_ENGINE_DB_UPDATE_ROLLBACK_OK'
}
finally {
    if ($null -ne $client) {
        if (-not $client.HasExited) { Stop-Process -Id $client.Id -Force }
        $client.Dispose()
    }
    # The script owns only API processes running from this disposable Client.
    $ownedApi = Get-LocalApiPid
    if ($ownedApi -ne 0) { Stop-Process -Id $ownedApi -Force }
    [IO.File]::WriteAllBytes($settingsFile, $originalSettings)
    if (Test-Path -LiteralPath $tempDb) { Remove-Item -LiteralPath $tempDb -Force }
}
