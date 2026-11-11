[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)] [string]$PublishedClient,
    [string]$OutputPath = (Join-Path $env:TEMP 'dk-v020-gui-smoke')
)
$ErrorActionPreference = 'Stop'
$publish = (Resolve-Path -LiteralPath $PublishedClient -ErrorAction Stop).Path
foreach ($required in @('DK-Knowledge-Client.exe', 'hostfxr.dll', 'coreclr.dll',
    'PresentationFramework.dll', 'DK-Knowledge-Client.deps.json',
    'DK-Knowledge-Client.runtimeconfig.json')) {
    if (-not (Test-Path -LiteralPath (Join-Path $publish $required) -PathType Leaf)) {
        throw "Published multi-file Client dependency is missing: $required"
    }
}
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class DKWindowSmoke {
    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);
}
'@
$root = Join-Path $OutputPath ('sample-client-' + [Guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $root -Force | Out-Null
$client = $null
try {
    Copy-Item -Path (Join-Path $publish '*') -Destination $root -Recurse -Force
    New-Item -ItemType Directory -Path (Join-Path $root 'assets'),(Join-Path $root 'config') -Force | Out-Null
    $icon = Join-Path $publish 'assets/client.ico'
    if (-not (Test-Path -LiteralPath $icon -PathType Leaf)) {
        $icon = Join-Path (Split-Path -Parent $PSScriptRoot) 'assets/generated/client.ico'
    }
    if (-not (Test-Path -LiteralPath $icon -PathType Leaf)) {
        throw 'Default Client icon is unavailable'
    }
    Copy-Item -LiteralPath $icon -Destination (Join-Path $root 'assets/app.ico') -Force
    [IO.File]::WriteAllText((Join-Path $root 'package-info.json'),
        '{"product_id":"gui-smoke","product_name":"GUI Smoke Product","product_version":"1.2.3","app_name":"GUI Smoke Client","icon_file":"assets/app.ico"}')
    [IO.File]::WriteAllText((Join-Path $root 'config/settings.json'), '{"port":28765,"allowed_origins":[]}')
    $client = Start-Process -FilePath (Join-Path $root 'DK-Knowledge-Client.exe') -WorkingDirectory $root -PassThru

    function Wait-ForWindow([int]$ProcessId) {
        $condition = [System.Windows.Automation.PropertyCondition]::new(
            [System.Windows.Automation.AutomationElement]::ProcessIdProperty, $ProcessId)
        $deadline = [DateTime]::UtcNow.AddSeconds(35)
        while ([DateTime]::UtcNow -lt $deadline) {
            if ($client.HasExited) { throw "Client stopped before opening window: $($client.ExitCode)" }
            $item = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst(
                [System.Windows.Automation.TreeScope]::Children, $condition)
            if ($null -ne $item) { return $item }
            Start-Sleep -Milliseconds 350
        }
        throw 'WPF MainWindow not visible to Windows UI Automation'
    }
    function Wait-ForElement(
        [System.Windows.Automation.AutomationElement]$Parent,
        [System.Windows.Automation.AutomationProperty]$Property,
        [string]$Value
    ) {
        $condition = [System.Windows.Automation.PropertyCondition]::new($Property, $Value)
        $deadline = [DateTime]::UtcNow.AddSeconds(15)
        while ([DateTime]::UtcNow -lt $deadline) {
            $element = $Parent.FindFirst([System.Windows.Automation.TreeScope]::Descendants, $condition)
            if ($null -ne $element) { return $element }
            Start-Sleep -Milliseconds 200
        }
        throw "UI Automation element not found: $Value"
    }

    $window = Wait-ForWindow $client.Id
    if ($window.Current.Name -ne 'GUI Smoke Client') {
        throw "Admin-selected Client title is missing: $($window.Current.Name)"
    }
    $windowHandle = [IntPtr]$window.Current.NativeWindowHandle
    if ($windowHandle -eq [IntPtr]::Zero -or -not [DKWindowSmoke]::IsWindowVisible($windowHandle)) {
        throw 'Client did not open a visible main window'
    }
    $settingsTab = Wait-ForElement $window ([System.Windows.Automation.AutomationElement]::AutomationIdProperty) 'SettingsTab'
    $settingsTab.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
    $portInput = Wait-ForElement $window ([System.Windows.Automation.AutomationElement]::AutomationIdProperty) 'SettingsPortBox'
    $portInput.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue('28766')
    $save = Wait-ForElement $window ([System.Windows.Automation.AutomationElement]::NameProperty) '포트 저장'
    $save.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()

    $settingsFile = Join-Path $root 'config/settings.json'
    $saved = $false
    $deadline = [DateTime]::UtcNow.AddSeconds(15)
    while ([DateTime]::UtcNow -lt $deadline) {
        if ((Get-Content -LiteralPath $settingsFile -Raw | ConvertFrom-Json).port -eq 28766) {
            $saved = $true
            break
        }
        Start-Sleep -Milliseconds 250
    }
    if (-not $saved) { throw 'GUI port save did not update settings.json' }
    $apiTab = Wait-ForElement $window ([System.Windows.Automation.AutomationElement]::AutomationIdProperty) 'ApiTab'
    $apiTab.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
    $apiUrl = Wait-ForElement $window ([System.Windows.Automation.AutomationElement]::AutomationIdProperty) 'ApiUrlText'
    if ($apiUrl.Current.Name -ne 'http://127.0.0.1:28766/health') {
        throw "API tool did not follow saved port: $($apiUrl.Current.Name)"
    }

    $window.GetCurrentPattern([System.Windows.Automation.WindowPattern]::Pattern).Close()
    Start-Sleep -Seconds 2
    if ($client.HasExited) { throw 'Client exited instead of hiding to tray' }
    if ([DKWindowSmoke]::IsWindowVisible($windowHandle)) {
        throw 'Client window stayed visible after close-to-tray'
    }
    Write-Output 'V020_CLIENT_UI_TITLE_PORT_API_TRAY_HIDE_OK'
}
finally {
    if ($null -ne $client) {
        if (-not $client.HasExited) {
            Stop-Process -Id $client.Id -Force
            $client.WaitForExit()
        }
        $client.Dispose()
    }
    if (Test-Path -LiteralPath $root) {
        Remove-Item -LiteralPath $root -Recurse -Force
    }
}
