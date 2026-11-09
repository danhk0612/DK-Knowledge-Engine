using System.IO;
using System.Diagnostics;
using System.Text.Json;
using System.Windows;
using DKKnowledgeShared;
using Microsoft.Win32;

namespace DKKnowledgeAdmin;

public partial class MainWindow : Window
{
    private readonly string _appRoot = AppContext.BaseDirectory;
    private readonly bool _bundled;

    public MainWindow()
    {
        InitializeComponent();
        _bundled = File.Exists(Path.Combine(_appRoot, "tools", "builder", "DK-Knowledge-Builder.exe"));
        // Keep editable documents and generated packages outside temporary ZIP extraction folders.
        var dataRoot = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "DK-Knowledge-Engine");
        SourceBox.Text = Path.Combine(dataRoot, "sources");
        DbBox.Text = Path.Combine(dataRoot, "knowledge.db");
        PackageOutputBox.Text = Path.Combine(dataRoot, "client-packages");
        Directory.CreateDirectory(SourceBox.Text);
        if (_bundled)
        {
            DeveloperRepoPanel.Visibility = Visibility.Collapsed;
            DeveloperPythonPanel.Visibility = Visibility.Collapsed;
            EngineBox.Text = Path.Combine(_appRoot, "engine-template");
            PackageRequirementsText.Text = "관리자 패키지에 포함된 도구를 사용합니다. Git·Python·.NET SDK가 필요하지 않습니다.";
        }
        else
        {
            // Developer launch path: apps/Admin/bin/{configuration}/net10.0-windows/.
            var candidate = Path.GetFullPath(Path.Combine(
                _appRoot, "..", "..", "..", "..", ".."));
            if (File.Exists(Path.Combine(candidate, "builder", "knowledge_builder.py")))
                RepoBox.Text = candidate;
            // Developer launches can reuse a previously extracted verified engine.
            foreach (var engineFolder in new[]
            {
                Path.Combine(_appRoot, "engine-template"),
                Path.Combine(candidate, "trial-extracted", "DK-Knowledge-Engine-Win-x64")
            })
            {
                if (!File.Exists(Path.Combine(engineFolder, "Verify-AIHelp.ps1"))) continue;
                EngineBox.Text = engineFolder;
                break;
            }
        }
        RefreshDocuments();
        Loaded += DetectPythonOnLoaded;
    }

    private async void DetectPythonOnLoaded(object sender, RoutedEventArgs e)
    {
        if (_bundled) return;
        var repo = RepoBox.Text.Trim();
        var workingDirectory = Directory.Exists(repo) ? repo : _appRoot;
        var candidates = new (string Program, string[] Prefix)[]
        {
            (Path.Combine(repo, ".venv", "Scripts", "python.exe"), []),
            (Path.Combine(repo, "venv", "Scripts", "python.exe"), []),
            ("python", []),
            ("py", ["-3"])
        };
        foreach (var (program, prefix) in candidates)
        {
            try
            {
                var args = prefix.Concat(new[] { "-c", "import sys, pypdf, docx; print(sys.executable)" }).ToArray();
                var result = await RunToolAsync(program, workingDirectory, args);
                var executable = result.Trim();
                if (!File.Exists(executable)) continue;
                PythonBox.Text = executable;
                StatusText.Text = "Python 및 문서 변환 라이브러리 자동 확인 완료";
                return;
            }
            catch (Exception)
            {
                // Try the next local interpreter; no packages are installed automatically.
            }
        }
        PythonBox.Text = "";
        StatusText.Text = "사용 가능한 Python(pypdf, python-docx 포함)을 찾지 못했습니다. 독립형 관리자 패키지는 Python 설치가 필요 없습니다.";
    }

    private static string? Version(string value) =>
        string.IsNullOrWhiteSpace(value) ? null : value.Trim();

    private async Task ExecuteAsync(Func<Task> action)
    {
        try { await action(); }
        catch (Exception error) { StatusText.Text = "작업 실패: " + error.Message; }
    }

    // A document selection is valid only for its original source root.
    private void SourceBoxTextChanged(object sender, System.Windows.Controls.TextChangedEventArgs e)
    {
        if (DocumentsList is not null)
        {
            DocumentsList.SelectedItem = null;
            DocumentsList.ItemsSource = Array.Empty<string>();
        }
    }

    private void RefreshDocuments()
    {
        DocumentsList.ItemsSource = string.IsNullOrWhiteSpace(SourceBox.Text)
            ? Array.Empty<string>()
            : DocumentLibrary.List(SourceBox.Text.Trim());
    }

    private void RunDocumentAction(Action action)
    {
        try { action(); }
        catch (Exception error) { StatusText.Text = "문서 작업 실패: " + error.Message; }
    }

    private void RefreshDocumentsClick(object sender, RoutedEventArgs e) =>
        RunDocumentAction(() =>
        {
            RefreshDocuments();
            StatusText.Text = "문서 목록 새로고침 완료";
        });

    private void AddDocumentClick(object sender, RoutedEventArgs e) =>
        RunDocumentAction(() =>
        {
            if (string.IsNullOrWhiteSpace(SourceBox.Text))
                throw new ArgumentException("원본 문서 루트 경로를 입력하세요.");
            var picker = new OpenFileDialog
            {
                Title = "등록할 원본 문서 선택",
                Filter = "지원 문서 (*.pdf;*.docx;*.txt;*.md)|*.pdf;*.docx;*.txt;*.md",
                CheckFileExists = true
            };
            if (picker.ShowDialog(this) != true) return;
            var relative = DocumentLibrary.Add(SourceBox.Text.Trim(), picker.FileName);
            RefreshDocuments();
            DocumentsList.SelectedItem = relative;
            StatusText.Text = "문서 등록: " + relative + " — DB 재생성 전";
        });

    private void ReplaceDocumentClick(object sender, RoutedEventArgs e) =>
        RunDocumentAction(() =>
        {
            var selected = DocumentsList.SelectedItem as string
                ?? throw new ArgumentException("교체할 문서를 목록에서 선택하세요.");
            var picker = new OpenFileDialog
            {
                Title = "선택 문서를 교체할 원본 파일 선택",
                Filter = "지원 문서 (*.pdf;*.docx;*.txt;*.md)|*.pdf;*.docx;*.txt;*.md",
                CheckFileExists = true
            };
            if (picker.ShowDialog(this) != true) return;
            DocumentLibrary.Replace(SourceBox.Text.Trim(), selected, picker.FileName);
            RefreshDocuments();
            DocumentsList.SelectedItem = selected;
            StatusText.Text = "문서 교체: " + selected + " — DB 재생성 전";
        });

    private void DeleteDocumentClick(object sender, RoutedEventArgs e) =>
        RunDocumentAction(() =>
        {
            var selected = DocumentsList.SelectedItem as string
                ?? throw new ArgumentException("삭제할 문서를 목록에서 선택하세요.");
            if (MessageBox.Show(this,
                selected + "\n\n원본 문서와 연결된 메타데이터를 삭제하시겠습니까?",
                "문서 삭제 확인", MessageBoxButton.YesNo, MessageBoxImage.Warning)
                != MessageBoxResult.Yes) return;
            DocumentLibrary.Delete(SourceBox.Text.Trim(), selected);
            RefreshDocuments();
            StatusText.Text = "문서 삭제: " + selected + " — DB 재생성 전";
        });

    private void OpenConfiguredFolder(string value, bool filePath = false, bool createIfMissing = false)
    {
        try
        {
            if (string.IsNullOrWhiteSpace(value))
                throw new ArgumentException("먼저 경로를 지정하세요.");
            var fullPath = Path.GetFullPath(value.Trim());
            var directory = filePath ? Path.GetDirectoryName(fullPath)! : fullPath;
            if (createIfMissing) Directory.CreateDirectory(directory);
            if (!Directory.Exists(directory))
                throw new DirectoryNotFoundException("폴더가 존재하지 않습니다: " + directory);

            var startInfo = new ProcessStartInfo("explorer.exe") { UseShellExecute = true };
            startInfo.ArgumentList.Add(directory);
            Process.Start(startInfo);
        }
        catch (Exception error)
        {
            StatusText.Text = "탐색기 열기 실패: " + error.Message;
        }
    }

    private void OpenRepoFolderClick(object sender, RoutedEventArgs e) =>
        OpenConfiguredFolder(RepoBox.Text);

    private void OpenSourceFolderClick(object sender, RoutedEventArgs e) =>
        OpenConfiguredFolder(SourceBox.Text, createIfMissing: true);

    private void OpenDbFolderClick(object sender, RoutedEventArgs e) =>
        OpenConfiguredFolder(DbBox.Text, filePath: true, createIfMissing: true);

    private void OpenEngineFolderClick(object sender, RoutedEventArgs e) =>
        OpenConfiguredFolder(EngineBox.Text);

    private void OpenPackageOutputFolderClick(object sender, RoutedEventArgs e) =>
        OpenConfiguredFolder(PackageOutputBox.Text, createIfMissing: true);

    private void ChooseSourceClick(object sender, RoutedEventArgs e)
    {
        var picker = new OpenFolderDialog { Title = "원본 문서 루트 선택" };
        if (picker.ShowDialog(this) == true)
        {
            SourceBox.Text = picker.FolderName;
            RunDocumentAction(RefreshDocuments);
        }
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
            if (!_bundled) ValidateRepository();
            if (!Directory.Exists(SourceBox.Text.Trim()))
                throw new DirectoryNotFoundException("원본 문서 폴더를 찾을 수 없습니다.");
            if (string.IsNullOrWhiteSpace(DbBox.Text))
                throw new ArgumentException("DB 경로를 입력하세요.");
            var defaultProductId = ManageProductBox.Text.Trim();
            if (string.IsNullOrWhiteSpace(defaultProductId))
                throw new ArgumentException("최상위·일반 폴더 문서에 적용할 제품 ID를 입력하세요.");
            StatusText.Text = "지식 DB 재생성 중...";
            if (_bundled)
                BuildLog.Text = await RunToolAsync(
                    Path.Combine(_appRoot, "tools", "builder", "DK-Knowledge-Builder.exe"),
                    _appRoot, "--source", SourceBox.Text.Trim(),
                    "--database", DbBox.Text.Trim(), "--default-product-id", defaultProductId, "--rebuild");
            else
            {
                if (string.IsNullOrWhiteSpace(PythonBox.Text))
                    throw new ArgumentException("Python 실행 명령을 입력하세요.");
                BuildLog.Text = await RunToolAsync(
                    PythonBox.Text.Trim(), RepoBox.Text.Trim(), "-m", "builder.knowledge_builder",
                    "--source", SourceBox.Text.Trim(), "--database", DbBox.Text.Trim(),
                    "--default-product-id", defaultProductId, "--rebuild");
            }
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
            if (!_bundled) ValidateRepository();
            if (!Directory.Exists(EngineBox.Text.Trim()))
                throw new DirectoryNotFoundException("기본 엔진 패키지 폴더를 찾을 수 없습니다.");
            if (!File.Exists(DbBox.Text.Trim()))
                throw new FileNotFoundException("생성한 knowledge.db 파일을 선택하세요.");
            if (string.IsNullOrWhiteSpace(PackageOutputBox.Text))
                PackageOutputBox.Text = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                    "DK-Knowledge-Engine", "client-packages");
            var script = _bundled
                ? Path.Combine(_appRoot, "tools", "Build-Client-Package.ps1")
                : Path.Combine(RepoBox.Text.Trim(), "distribution", "Build-Client-Package.ps1");
            StatusText.Text = "사용자 전용 패키지 제작 중...";
            var args = new List<string> {
                "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", script,
                "-EnginePackage", EngineBox.Text.Trim(),
                "-KnowledgeDb", DbBox.Text.Trim(),
                "-OutputDir", PackageOutputBox.Text.Trim()
            };
            if (_bundled)
            {
                args.Add("-ClientExe");
                args.Add(Path.Combine(_appRoot, "client", "DK-Knowledge-Client.exe"));
            }
            BuildLog.Text = await RunToolAsync(
                "powershell.exe", _bundled ? _appRoot : RepoBox.Text.Trim(), args.ToArray());
            StatusText.Text = "사용자 패키지 제작 완료";
        });
}
