using System.Diagnostics;
using System.Text.Json;
using System.Windows;
using DKKnowledgeShared;
using Microsoft.Win32;

namespace DKKnowledgeAdmin;

public partial class MainWindow : Window
{
    public MainWindow()
    {
        InitializeComponent();
        // Developer launch path: apps/Admin/bin/{configuration}/net10.0-windows/.
        var candidate = Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", ".."));
        if (File.Exists(Path.Combine(candidate, "builder", "knowledge_builder.py")))
            RepoBox.Text = candidate;
    }

    private static string? Version(string value) =>
        string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private async Task ExecuteAsync(Func<Task> action)
    {
        try { await action(); }
        catch (Exception error) { StatusText.Text = "작업 실패: " + error.Message; }
    }

    private void ChooseSourceClick(object sender, RoutedEventArgs e)
    {
        var picker = new OpenFolderDialog { Title = "원본 문서 루트 선택" };
        if (picker.ShowDialog(this) == true) SourceBox.Text = picker.FolderName;
    }

    private void ChooseEngineClick(object sender, RoutedEventArgs e)
    {
        var picker = new OpenFolderDialog { Title = "검증된 엔진 패키지 폴더 선택" };
        if (picker.ShowDialog(this) == true) EngineBox.Text = picker.FolderName;
    }

    private void ChooseDbClick(object sender, RoutedEventArgs e)
    {
        var picker = new SaveFileDialog
        {
            FileName = "knowledge.db", Filter = "SQLite DB (*.db)|*.db",
            OverwritePrompt = true
        };
        if (picker.ShowDialog(this) == true) DbBox.Text = picker.FileName;
    }

    private static async Task<string> RunToolAsync(
        string program, string workingDirectory, params string[] arguments)
    {
        var info = new ProcessStartInfo(program)
        {
            WorkingDirectory = workingDirectory,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        foreach (var argument in arguments) info.ArgumentList.Add(argument);
        using var process = Process.Start(info) ?? throw new InvalidOperationException("도구 실행 실패");
        var outputTask = process.StandardOutput.ReadToEndAsync();
        var errorTask = process.StandardError.ReadToEndAsync();
        await process.WaitForExitAsync();
        var output = await outputTask;
        var error = await errorTask;
        if (process.ExitCode != 0)
            throw new InvalidOperationException(error.Trim() + "\n" + output.Trim());
        return output.Trim();
    }

    private void ValidateRepository()
    {
        if (!File.Exists(Path.Combine(RepoBox.Text.Trim(), "builder", "knowledge_builder.py")))
            throw new InvalidOperationException("올바른 저장소 루트 경로를 입력하세요.");
    }

    private async void BuildDbClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(async () =>
        {
            ValidateRepository();
            if (!Directory.Exists(SourceBox.Text.Trim()))
                throw new DirectoryNotFoundException("원본 문서 폴더를 찾을 수 없습니다.");
            if (string.IsNullOrWhiteSpace(DbBox.Text) || string.IsNullOrWhiteSpace(PythonBox.Text))
                throw new ArgumentException("DB 경로와 Python 실행 명령을 입력하세요.");
            StatusText.Text = "지식 DB 재생성 중...";
            BuildLog.Text = await RunToolAsync(
                PythonBox.Text.Trim(), RepoBox.Text.Trim(), "-m", "builder.knowledge_builder",
                "--source", SourceBox.Text.Trim(), "--database", DbBox.Text.Trim(), "--rebuild");
            StatusText.Text = "DB 생성 완료";
        });

    private async Task TestAsync(bool chat)
    {
        if (!int.TryParse(PortBox.Text, out var port) || port is < 1 or > 65535)
            throw new ArgumentException("올바른 API 포트를 입력하세요.");
        var product = ProductBox.Text.Trim();
        var question = QuestionBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(product) || string.IsNullOrWhiteSpace(question))
            throw new ArgumentException("제품 ID와 질문을 입력하세요.");
        using var api = new LocalApiClient(port);
        StatusText.Text = chat ? "AI 답변 생성 중..." : "검색 중...";
        var result = chat
            ? await api.ChatAsync(product, Version(VersionBox.Text), question)
            : await api.SearchAsync(product, Version(VersionBox.Text), question);
        if (chat)
        {
            var sources = result.GetProperty("sources").EnumerateArray()
                .Select(s => s.GetProperty("source_path").GetString() +
                    (s.TryGetProperty("page_from", out var p) && p.ValueKind == JsonValueKind.Number
                        ? $" (p.{p.GetInt32()})" : "")).ToArray();
            TestLog.Text = (result.GetProperty("grounded").GetBoolean() ? "" : "[근거 부족]\n") +
                result.GetProperty("answer").GetString() +
                (sources.Length > 0 ? "\n\n출처:\n" + string.Join("\n", sources) : "");
        }
        else
        {
            var lines = result.GetProperty("results").EnumerateArray()
                .Select(s => s.GetProperty("title").GetString() + "\n" +
                    s.GetProperty("source_path").GetString() +
                    (s.TryGetProperty("page_from", out var p) && p.ValueKind == JsonValueKind.Number
                        ? $" (p.{p.GetInt32()})" : "")).ToArray();
            TestLog.Text = lines.Length == 0 ? "검색 결과 없음" : string.Join("\n\n", lines);
        }
        StatusText.Text = "시험 완료";
    }

    private async void TestChatClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(() => TestAsync(true));

    private async void TestSearchClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(() => TestAsync(false));

    private async void PackageClick(object sender, RoutedEventArgs e) =>
        await ExecuteAsync(async () =>
        {
            ValidateRepository();
            if (!Directory.Exists(EngineBox.Text.Trim()))
                throw new DirectoryNotFoundException("기본 엔진 패키지 폴더를 찾을 수 없습니다.");
            if (!File.Exists(DbBox.Text.Trim()))
                throw new FileNotFoundException("생성한 knowledge.db 파일을 선택하세요.");
            if (string.IsNullOrWhiteSpace(PackageOutputBox.Text))
                throw new ArgumentException("새 사용자 패키지 출력 폴더를 지정하세요.");
            var script = Path.Combine(RepoBox.Text.Trim(), "distribution", "Build-Client-Package.ps1");
            StatusText.Text = "사용자 전용 패키지 제작 중...";
            BuildLog.Text = await RunToolAsync(
                "powershell.exe", RepoBox.Text.Trim(),
                "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
                "-EnginePackage", EngineBox.Text.Trim(),
                "-KnowledgeDb", DbBox.Text.Trim(),
                "-OutputDir", PackageOutputBox.Text.Trim());
            StatusText.Text = "사용자 패키지 제작 완료";
        });
}
