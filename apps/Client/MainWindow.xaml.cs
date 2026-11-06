using System.IO;
using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using System.Windows;
using DKKnowledgeShared;
using Microsoft.Win32;

namespace DKKnowledgeClient;

public partial class MainWindow : Window
{
    private readonly string _root = AppContext.BaseDirectory.TrimEnd(
        Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
    private readonly LocalApiClient _api;
    private Process? _ownedEngine;

    public MainWindow()
    {
        InitializeComponent();
        var settingsFile = Path.Combine(_root, "config", "settings.json");
        var port = 8765;
        if (File.Exists(settingsFile))
        {
            using var doc = JsonDocument.Parse(File.ReadAllText(settingsFile));
            port = doc.RootElement.GetProperty("port").GetInt32();
        }
        _api = new LocalApiClient(port);
        PortText.Text = $"API 주소: http://127.0.0.1:{port}";
        EngineStatusText.Text = "상태 확인을 눌러 엔진 연결 여부를 확인하세요.";
    }

    private static string? Version(string input) =>
        string.IsNullOrWhiteSpace(input) ? null : input.Trim();

    private async Task ExecuteAsync(Func<Task> action)
    {
        try { await action(); }
        catch (Exception error) { StatusText.Text = "작업 실패: " + error.Message; }
    }

    private void ChooseDbClick(object sender, RoutedEventArgs e)
    {
        var dialog = new OpenFileDialog
        {
            Filter = "SQLite 지식 DB (*.db)|*.db|모든 파일 (*.*)|*.*",
            CheckFileExists = true
        };
        if (dialog.ShowDialog(this) == true)
            DbPathBox.Text = dialog.FileName;
    }

    private async void HealthClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(async () =>
        {
            var data = await _api.HealthAsync();
            EngineStatusText.Text = "상태: " + data.GetProperty("status").GetString() +
                " / LLM: " + (data.GetProperty("llm_ready").GetBoolean() ? "준비" : "사용 불가");
            StatusText.Text = "연결 확인 완료";
        });

    private async void StartEngineClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(async () =>
        {
            try
            {
                var status = await _api.HealthAsync();
                if (status.GetProperty("status").GetString() == "ready")
                {
                    EngineStatusText.Text = "기존 엔진이 실행 중입니다. 외부 프로세스는 제어하지 않습니다.";
                    return;
                }
            }
            catch (HttpRequestException) { }
            catch (TaskCanceledException) { }

            var exe = Path.Combine(_root, "engine", "DK-Knowledge-API.exe");
            if (!File.Exists(exe))
                throw new FileNotFoundException("패키지의 엔진 실행 파일을 찾을 수 없습니다.", exe);
            _ownedEngine?.Dispose();
            _ownedEngine = Process.Start(new ProcessStartInfo(exe)
            {
                WorkingDirectory = _root,
                UseShellExecute = false,
                CreateNoWindow = true
            }) ?? throw new InvalidOperationException("엔진 실행 실패");

            for (var i = 0; i < 30; i++)
            {
                if (_ownedEngine.HasExited)
                    throw new InvalidOperationException("엔진이 시작 직후 종료됐습니다.");
                try
                {
                    var status = await _api.HealthAsync();
                    if (status.GetProperty("status").GetString() == "ready")
                    {
                        EngineStatusText.Text = "엔진 실행 중 (이 프로그램에서 시작함)";
                        StatusText.Text = "엔진 실행 완료";
                        return;
                    }
                }
                catch (HttpRequestException) { }
                catch (TaskCanceledException) { }
                await Task.Delay(300);
            }
            throw new InvalidOperationException("엔진 응답을 확인하지 못했습니다.");
        });

    private async void StopEngineClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(async () =>
        {
            if (_ownedEngine is null || _ownedEngine.HasExited)
            {
                EngineStatusText.Text = "이 프로그램에서 시작한 엔진이 없습니다. 다른 프로세스는 종료하지 않습니다.";
                return;
            }
            _ownedEngine.Kill(entireProcessTree: true);
            await _ownedEngine.WaitForExitAsync();
            _ownedEngine.Dispose();
            _ownedEngine = null;
            EngineStatusText.Text = "엔진 중지됨";
            StatusText.Text = "엔진 중지 완료";
        });

    private string[] InputValues() =>
        [ProductIdBox.Text.Trim(), QuestionBox.Text.Trim()];

    private async void AskClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(async () =>
        {
            var input = InputValues();
            if (input.Any(string.IsNullOrWhiteSpace))
                throw new ArgumentException("제품 ID와 질문을 입력하세요.");
            StatusText.Text = "AI 답변 생성 중...";
            var answer = await _api.ChatAsync(input[0], Version(VersionBox.Text), input[1]);
            var sources = answer.GetProperty("sources").EnumerateArray()
                .Select(s => s.GetProperty("source_path").GetString() +
                    (s.TryGetProperty("page_from", out var p) && p.ValueKind == JsonValueKind.Number
                        ? $" (p.{p.GetInt32()})" : "")).ToArray();
            AnswerBox.Text = (answer.GetProperty("grounded").GetBoolean() ? "" : "[근거 부족]\n") +
                answer.GetProperty("answer").GetString() +
                (sources.Length > 0 ? "\n\n출처:\n" + string.Join("\n", sources) : "");
            StatusText.Text = "AI 답변 완료";
        });

    private async void SearchClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(async () =>
        {
            var input = InputValues();
            if (input.Any(string.IsNullOrWhiteSpace))
                throw new ArgumentException("제품 ID와 검색어를 입력하세요.");
            StatusText.Text = "문서 검색 중...";
            var response = await _api.SearchAsync(input[0], Version(VersionBox.Text), input[1]);
            var lines = response.GetProperty("results").EnumerateArray()
                .Select(s => s.GetProperty("title").GetString() + "\n" +
                    s.GetProperty("excerpt").GetString() + "\n" +
                    s.GetProperty("source_path").GetString() +
                    (s.TryGetProperty("page_from", out var p) && p.ValueKind == JsonValueKind.Number
                        ? $" (p.{p.GetInt32()})" : "")).ToArray();
            AnswerBox.Text = lines.Length == 0 ? "일치하는 문서가 없습니다." :
                string.Join("\n\n────────\n\n", lines);
            StatusText.Text = "검색 완료";
        });

    private async Task RunScriptAsync(string name, params string[] parameters)
    {
        var script = Path.Combine(_root, name);
        if (!File.Exists(script))
            throw new FileNotFoundException("패키지에 필요한 스크립트가 없습니다.", script);
        var psi = new ProcessStartInfo("powershell.exe")
        {
            WorkingDirectory = _root, UseShellExecute = false,
            RedirectStandardOutput = true, RedirectStandardError = true,
            CreateNoWindow = true
        };
        foreach (var arg in new[] { "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script }.Concat(parameters))
            psi.ArgumentList.Add(arg);
        using var process = Process.Start(psi) ?? throw new InvalidOperationException("PowerShell 실행 실패");
        var outputTask = process.StandardOutput.ReadToEndAsync();
        var errorTask = process.StandardError.ReadToEndAsync();
        await process.WaitForExitAsync();
        var output = await outputTask;
        var error = await errorTask;
        if (process.ExitCode != 0)
            throw new InvalidOperationException(error.Trim() + "\n" + output.Trim());
        StatusText.Text = output.Trim();
    }

    private void RequireEngineStopped()
    {
        if (_ownedEngine is { HasExited: false })
            throw new InvalidOperationException("업데이트 전에 이 프로그램에서 실행한 엔진을 종료하세요.");
    }

    private async void ApplyDbClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(async () =>
        {
            RequireEngineStopped();
            var file = DbPathBox.Text.Trim();
            if (!File.Exists(file))
                throw new FileNotFoundException("적용할 DB를 선택하세요.", file);
            using var stream = File.OpenRead(file);
            var hash = Convert.ToHexString(await SHA256.HashDataAsync(stream)).ToLowerInvariant();
            await RunScriptAsync("Update-Knowledge.ps1", "-SourceDb", file, "-ExpectedSha256", hash);
        });

    private async void RollbackDbClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(async () =>
        {
            RequireEngineStopped();
            await RunScriptAsync("Update-Knowledge.ps1", "-Rollback");
        });

    private async void VerifyClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(() => RunScriptAsync("Verify-AIHelp.ps1"));

    protected override void OnClosed(EventArgs e)
    {
        if (_ownedEngine is { HasExited: false })
            _ownedEngine.Kill(entireProcessTree: true);
        _ownedEngine?.Dispose();
        _api.Dispose();
        base.OnClosed(e);
    }

}
