using System.ComponentModel;
using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.Http;
using System.Net.Sockets;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media.Imaging;
using DKKnowledgeShared;
using Microsoft.Win32;
using Forms = System.Windows.Forms;
using Drawing = System.Drawing;

namespace DKKnowledgeClient;

public partial class MainWindow : Window
{
    private readonly string _root = AppContext.BaseDirectory.TrimEnd(
        Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
    private LocalApiClient _api;
    private int _port;
    private readonly string _productId;
    private readonly string _productVersion;
    private readonly string _appName;
    private Process? _ownedEngine;
    private Forms.NotifyIcon? _tray;
    private Drawing.Icon? _trayIcon;
    private bool _exitRequested;

    public MainWindow()
    {
        InitializeComponent();
        var productFile = Path.Combine(_root, "package-info.json");
        if (!File.Exists(productFile))
            throw new FileNotFoundException("사용자 패키지의 제품 정보가 없습니다.", productFile);
        string productName;
        string iconFile;
        using (var doc = JsonDocument.Parse(File.ReadAllText(productFile)))
        {
            var info = doc.RootElement;
            _productId = info.GetProperty("product_id").GetString() ?? "";
            _productVersion = info.GetProperty("product_version").GetString() ?? "";
            _appName = info.GetProperty("app_name").GetString() ?? "";
            productName = info.GetProperty("product_name").GetString() ?? "";
            iconFile = info.GetProperty("icon_file").GetString() ?? "";
            if (string.IsNullOrWhiteSpace(_productId) ||
                string.IsNullOrWhiteSpace(_productVersion) ||
                string.IsNullOrWhiteSpace(_appName) ||
                string.IsNullOrWhiteSpace(productName) ||
                iconFile != "assets/app.ico")
                throw new InvalidDataException("사용자 패키지의 제품 정보가 올바르지 않습니다.");
        }

        Title = _appName;
        AppTitleText.Text = _appName;
        ProductInfoText.Text = productName + " · " + _productVersion;
        SettingsProductText.Text = productName + " (" + _productId + ") · " + _productVersion;

        var settingsPath = Path.Combine(_root, "config", "settings.json");
        using (var doc = JsonDocument.Parse(File.ReadAllText(settingsPath)))
            _port = doc.RootElement.GetProperty("port").GetInt32();
        _api = new LocalApiClient(_port);
        UpdatePortLabels();
        EngineStatusText.Text = "상태 확인을 눌러 엔진 연결 여부를 확인하세요.";

        var absoluteIcon = Path.Combine(_root, "assets", "app.ico");
        Icon = BitmapFrame.Create(
            new Uri(absoluteIcon), BitmapCreateOptions.None, BitmapCacheOption.OnLoad);
        HeaderAppIcon.Source = Icon;
        ConfigureTray(absoluteIcon);
        RefreshApiExample();
    }

    private void ConfigureTray(string iconFile)
    {
        _trayIcon = new Drawing.Icon(iconFile);
        _tray = new Forms.NotifyIcon
        {
            Icon = _trayIcon,
            Text = _appName.Length > 63 ? _appName[..63] : _appName,
            Visible = true
        };
        var menu = new Forms.ContextMenuStrip();
        menu.Items.Add("창 열기", null, (_, _) =>
            Dispatcher.Invoke(ShowClient));
        menu.Items.Add("AI 질문하기", null, (_, _) =>
            Dispatcher.Invoke(() => { ShowClient(); MainTabs.SelectedItem = QuestionTab; QuestionBox.Focus(); }));
        menu.Items.Add("엔진 시작", null, (_, _) =>
            Dispatcher.Invoke(() => { ShowClient(); MainTabs.SelectedItem = SettingsTab; StartEngineClick(this, new RoutedEventArgs()); }));
        menu.Items.Add("엔진 중지", null, (_, _) =>
            Dispatcher.Invoke(() => { ShowClient(); MainTabs.SelectedItem = SettingsTab; StopEngineClick(this, new RoutedEventArgs()); }));
        menu.Items.Add("지식 DB 관리", null, (_, _) =>
            Dispatcher.Invoke(() => { ShowClient(); MainTabs.SelectedItem = KnowledgeTab; }));
        menu.Items.Add("설정", null, (_, _) =>
            Dispatcher.Invoke(() => { ShowClient(); MainTabs.SelectedItem = SettingsTab; }));
        menu.Items.Add(new Forms.ToolStripSeparator());
        menu.Items.Add("종료", null, (_, _) =>
            Dispatcher.Invoke(() => { _exitRequested = true; Close(); }));
        _tray.ContextMenuStrip = menu;
        _tray.DoubleClick += (_, _) => Dispatcher.Invoke(ShowClient);
    }

    private void ShowClient()
    {
        Show();
        WindowState = WindowState.Normal;
        Activate();
    }

    private void WindowClosing(object sender, CancelEventArgs e)
    {
        if (_exitRequested) return;
        e.Cancel = true;
        Hide();
    }

    private void UpdatePortLabels()
    {
        SettingsPortBox.Text = _port.ToString();
        PortText.Text = $"http://127.0.0.1:{_port} (로컬 전용)";
        RefreshApiExample();
    }

    private void RefreshApiExample()
    {
        if (ApiRequestBox is null || string.IsNullOrWhiteSpace(_productId)) return;
        var endpoint = SelectedApiEndpoint();
        ApiUrlText.Text = $"http://127.0.0.1:{_port}/{endpoint}";
        ApiRequestBox.IsReadOnly = endpoint == "health";
        var template = endpoint switch
        {
            "search" => (object)new { product_id = _productId, version = _productVersion,
                                     query = "설치 확인 코드는?" },
            "chat" => new { product_id = _productId, version = _productVersion,
                            question = "설치 확인 코드는?" },
            "event" => new { product_id = _productId, version = _productVersion,
                             event_id = "connection_failed", error_code = "DB-1001",
                             screen_id = (string?)null },
            _ => null
        };
        ApiRequestBox.Text = template is null ? "" :
            JsonSerializer.Serialize(template, new JsonSerializerOptions { WriteIndented = true });
        ApiStatusText.Text = "";
    }

    private string SelectedApiEndpoint() =>
        (ApiEndpointBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? "health";

    private void ApiEndpointChanged(object sender, SelectionChangedEventArgs e) =>
        RefreshApiExample();

    private async Task ExecuteAsync(Func<Task> action)
    {
        try { await action(); }
        catch (Exception error) { StatusText.Text = "작업 실패: " + error.Message; }
    }

    private void ApiCopyClick(object sender, RoutedEventArgs e)
    {
        var endpoint = SelectedApiEndpoint();
        var request = (endpoint == "health" ? "GET " : "POST ") +
            ApiUrlText.Text + (endpoint == "health" ? "" :
            "\nContent-Type: application/json\n\n" + ApiRequestBox.Text);
        Clipboard.SetText(request);
        ApiStatusText.Text = "요청 복사 완료";
    }

    private async void ApiSendClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(async () =>
        {
            var endpoint = SelectedApiEndpoint();
            if (endpoint != "health")
            {
                using var _ = JsonDocument.Parse(ApiRequestBox.Text);
            }
            ApiStatusText.Text = "요청 중...";
            var response = await _api.SendJsonAsync(
                endpoint, endpoint == "health" ? null : ApiRequestBox.Text);
            ApiStatusText.Text = "HTTP " + response.StatusCode;
            try
            {
                using var data = JsonDocument.Parse(response.Body);
                ApiResultBox.Text = JsonSerializer.Serialize(
                    data.RootElement, new JsonSerializerOptions { WriteIndented = true });
            }
            catch (JsonException)
            {
                ApiResultBox.Text = response.Body;
            }
            StatusText.Text = "API 호출 완료";
        });

    private async void SavePortClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(async () =>
        {
            if (!int.TryParse(SettingsPortBox.Text.Trim(), out var next) || next is < 1 or > 65535)
                throw new ArgumentException("API 포트는 1~65535 범위여야 합니다.");
            if (next == _port) { StatusText.Text = "포트 변경 없음"; return; }
            if (_ownedEngine is { HasExited: false })
                throw new InvalidOperationException("이 프로그램이 시작한 엔진을 중지한 후 포트를 변경하세요.");
            try
            {
                var health = await _api.HealthAsync();
                if (health.GetProperty("status").GetString() == "ready")
                    throw new InvalidOperationException("현재 API 포트의 엔진을 중지한 뒤 저장하세요.");
            }
            catch (HttpRequestException) { }
            catch (TaskCanceledException) { }
            var path = Path.Combine(_root, "config", "settings.json");
            var settings = JsonNode.Parse(File.ReadAllText(path))?.AsObject()
                ?? throw new InvalidDataException("실행 설정 파일이 올바르지 않습니다.");
            settings["port"] = next;
            File.WriteAllText(path, settings.ToJsonString(
                new JsonSerializerOptions { WriteIndented = true }));
            _api.Dispose();
            _api = new LocalApiClient(next);
            _port = next;
            UpdatePortLabels();
            StatusText.Text = "포트 저장 완료 · 다음 엔진 시작부터 적용";
        });

    private async void HealthClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(async () =>
        {
            var data = await _api.HealthAsync();
            var ready = data.GetProperty("status").GetString() == "ready";
            EngineStatusText.Text = "엔진: " + data.GetProperty("status").GetString() +
                " / AI: " + (data.GetProperty("llm_ready").GetBoolean() ? "준비" : "사용 불가");
            HeaderEngineStatusText.Text = ready ? "엔진 실행 중" : "엔진 사용 불가";
            StatusText.Text = "연결 확인 완료";
        });

    private async Task StartOwnedEngineAsync()
    {
        try
        {
            var status = await _api.HealthAsync();
            if (status.GetProperty("status").GetString() == "ready")
            {
                EngineStatusText.Text = "이미 실행 중인 엔진이 있습니다. 외부 프로세스는 제어하지 않습니다.";
                HeaderEngineStatusText.Text = "엔진 실행 중";
                return;
            }
        }
        catch (HttpRequestException) { }
        catch (TaskCanceledException) { }

        // Detect another listener before attempting to start an engine.
        using (var probe = new TcpClient())
        {
            try
            {
                await probe.ConnectAsync(IPAddress.Loopback, _port);
                throw new InvalidOperationException($"포트 {_port}가 다른 프로그램에서 사용 중입니다.");
            }
            catch (SocketException) { /* No listener; the port is available. */ }
        }
        var exe = Path.Combine(_root, "engine", "DK-Knowledge-API.exe");
        if (!File.Exists(exe))
            throw new FileNotFoundException("엔진 실행 파일을 찾을 수 없습니다.", exe);
        _ownedEngine?.Dispose();
        _ownedEngine = Process.Start(new ProcessStartInfo(exe)
        {
            WorkingDirectory = _root, UseShellExecute = false, CreateNoWindow = true
        }) ?? throw new InvalidOperationException("엔진 실행 실패");
        for (var i = 0; i < 30; i++)
        {
            if (_ownedEngine.HasExited)
                throw new InvalidOperationException("엔진이 시작 직후 종료되었습니다.");
            try
            {
                var status = await _api.HealthAsync();
                if (status.GetProperty("status").GetString() == "ready")
                {
                    EngineStatusText.Text = "엔진 실행 중 (이 프로그램에서 시작함)";
                    HeaderEngineStatusText.Text = "엔진 실행 중";
                    StatusText.Text = "엔진 시작 완료";
                    return;
                }
            }
            catch (HttpRequestException) { }
            catch (TaskCanceledException) { }
            await Task.Delay(300);
        }
        throw new InvalidOperationException("엔진 응답을 확인하지 못했습니다.");
    }

    private async void StartEngineClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(StartOwnedEngineAsync);

    private async Task StopOwnedEngineAsync()
    {
        if (_ownedEngine is null || _ownedEngine.HasExited)
        {
            EngineStatusText.Text = "이 프로그램에서 시작한 엔진이 없습니다. 외부 엔진은 제어하지 않습니다.";
            return;
        }
        _ownedEngine.Kill(entireProcessTree: true);
        await _ownedEngine.WaitForExitAsync();
        _ownedEngine.Dispose();
        _ownedEngine = null;
        EngineStatusText.Text = "엔진 중지됨";
        HeaderEngineStatusText.Text = "엔진 중지";
        StatusText.Text = "엔진 중지 완료";
    }

    private async void StopEngineClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(StopOwnedEngineAsync);

    private async void AskClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(async () =>
        {
            var question = QuestionBox.Text.Trim();
            if (question.Length == 0) throw new ArgumentException("질문을 입력하세요.");
            StatusText.Text = "AI 답변 생성 중...";
            var answer = await _api.ChatAsync(_productId, _productVersion, question);
            var sources = answer.GetProperty("sources").EnumerateArray()
                .Select(p => p.GetProperty("source_path").GetString() +
                    (p.TryGetProperty("page_from", out var page) &&
                     page.ValueKind == JsonValueKind.Number ? $" (p.{page.GetInt32()})" : ""))
                .ToArray();
            AnswerBox.Text = (answer.GetProperty("grounded").GetBoolean() ? "" : "[근거 부족]\n") +
                answer.GetProperty("answer").GetString() +
                (sources.Length == 0 ? "" : "\n\n출처:\n" + string.Join("\n", sources));
            StatusText.Text = "AI 답변 완료";
        });

    private async void SearchClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(async () =>
        {
            var query = QuestionBox.Text.Trim();
            if (query.Length == 0) throw new ArgumentException("검색어를 입력하세요.");
            StatusText.Text = "검색 중...";
            var data = await _api.SearchAsync(_productId, _productVersion, query);
            var results = data.GetProperty("results").EnumerateArray()
                .Select(p => p.GetProperty("title").GetString() + "\n" +
                    p.GetProperty("excerpt").GetString() + "\n" +
                    p.GetProperty("source_path").GetString() +
                    (p.TryGetProperty("page_from", out var page) &&
                     page.ValueKind == JsonValueKind.Number ? $" (p.{page.GetInt32()})" : ""))
                .ToArray();
            AnswerBox.Text = results.Length == 0 ? "일치하는 문서가 없습니다." :
                string.Join("\n\n────────\n\n", results);
            StatusText.Text = "검색 완료";
        });

    private void ChooseDbClick(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Filter = "SQLite 지식 DB (*.db)|*.db|모든 파일 (*.*)|*.*",
            CheckFileExists = true
        };
        if (dialog.ShowDialog(this) == true) DbPathBox.Text = dialog.FileName;
    }

    private async Task RunScriptAsync(string name, params string[] parameters)
    {
        var script = Path.Combine(_root, name);
        if (!File.Exists(script))
            throw new FileNotFoundException("패키지 스크립트가 없습니다.", script);
        var psi = new ProcessStartInfo("powershell.exe")
        {
            WorkingDirectory = _root, UseShellExecute = false,
            RedirectStandardOutput = true, RedirectStandardError = true,
            CreateNoWindow = true
        };
        foreach (var arg in new[] { "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script }.Concat(parameters))
            psi.ArgumentList.Add(arg);
        using var proc = Process.Start(psi) ?? throw new InvalidOperationException("PowerShell 실행 실패");
        var stdout = proc.StandardOutput.ReadToEndAsync();
        var stderr = proc.StandardError.ReadToEndAsync();
        await proc.WaitForExitAsync();
        var output = await stdout;
        var errors = await stderr;
        if (proc.ExitCode != 0)
            throw new InvalidOperationException(errors.Trim() + "\n" + output.Trim());
        StatusText.Text = output.Trim();
    }

    private async Task MaintainKnowledgeAsync(params string[] args)
    {
        var hadOwnedEngine = _ownedEngine is { HasExited: false };
        if (hadOwnedEngine) await StopOwnedEngineAsync();
        await RunScriptAsync("Update-Knowledge.ps1", args);
        if (hadOwnedEngine) await StartOwnedEngineAsync();
    }

    private async void ApplyDbClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(async () =>
        {
            var file = DbPathBox.Text.Trim();
            if (!File.Exists(file))
                throw new FileNotFoundException("적용할 DB를 선택하세요.", file);
            using var stream = File.OpenRead(file);
            var hash = Convert.ToHexString(await SHA256.HashDataAsync(stream)).ToLowerInvariant();
            await MaintainKnowledgeAsync("-SourceDb", file, "-ExpectedSha256", hash);
        });

    private async void RollbackDbClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(() => MaintainKnowledgeAsync("-Rollback"));

    private async void VerifyClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(() => RunScriptAsync("Verify-AIHelp.ps1"));

    protected override void OnClosed(EventArgs e)
    {
        if (_ownedEngine is { HasExited: false })
            _ownedEngine.Kill(entireProcessTree: true);
        _ownedEngine?.Dispose();
        _tray?.Dispose();
        _trayIcon?.Dispose();
        _api.Dispose();
        base.OnClosed(e);
    }
}
