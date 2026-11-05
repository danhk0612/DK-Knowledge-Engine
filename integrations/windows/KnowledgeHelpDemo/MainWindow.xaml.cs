using System.Text;
using System.Text.Json;
using System.Windows;

namespace KnowledgeHelpDemo;

public partial class MainWindow : Window
{
    private readonly KnowledgeHelpClient _client = new();

    public MainWindow()
    {
        InitializeComponent();
        Closed += (_, _) => _client.Dispose();
    }

    private string? Version => string.IsNullOrWhiteSpace(ProductVersion.Text)
        ? null : ProductVersion.Text.Trim();

    private static string Sources(JsonElement items)
    {
        var lines = new List<string>();
        foreach (var source in items.EnumerateArray())
        {
            if (source.TryGetProperty("source_path", out var path))
            {
                var page = source.TryGetProperty("page_from", out var p) &&
                           p.ValueKind == JsonValueKind.Number
                    ? " (p." + p.GetInt32() + ")" : "";
                lines.Add(path.GetString() + page);
            }
        }
        return lines.Count == 0 ? "" : "\n\n출처:\n" + string.Join("\n", lines);
    }

    private static string FormatSearch(JsonElement data)
    {
        var results = data.GetProperty("results");
        if (results.GetArrayLength() == 0) return "일치하는 문서가 없습니다.";
        var lines = new List<string>();
        foreach (var item in results.EnumerateArray())
        {
            lines.Add(item.GetProperty("title").GetString() + "\n" +
                      item.GetProperty("excerpt").GetString());
        }
        return string.Join("\n\n", lines) + Sources(results);
    }

    private static string FormatChat(JsonElement data) =>
        data.GetProperty("answer").GetString() + Sources(data.GetProperty("sources"));

    private static string FormatEvent(JsonElement data)
    {
        if (!data.GetProperty("matched").GetBoolean())
            return data.TryGetProperty("reason", out var reason) &&
                   reason.GetString() == "ambiguous_rules"
                ? "중복 규칙이 있어 자동 안내할 수 없습니다."
                : "해당 오류 도움말이 없습니다.";

        var result = data.GetProperty("title").GetString() + "\n" +
                     data.GetProperty("content").GetString();
        if (data.TryGetProperty("source", out var source) &&
            source.TryGetProperty("source_path", out var path))
            result += "\n\n출처:\n" + path.GetString();
        return result;
    }

    private async Task ShowAsync(Func<Task<JsonElement>> call, Func<JsonElement, string> format)
    {
        Result.Text = "요청 중…";
        try
        {
            Result.Text = format(await call());
        }
        catch (Exception ex)
        {
            Result.Text = "요청 실패: " + ex.Message;
        }
    }

    private async void HealthClick(object sender, RoutedEventArgs e) =>
        await ShowAsync(
            () => _client.HealthAsync(),
            data => "엔진: " + data.GetProperty("status").GetString() +
                    " / LLM: " + (data.GetProperty("llm_ready").GetBoolean() ? "사용 가능" : "미설정"));

    private async void SearchClick(object sender, RoutedEventArgs e) =>
        await ShowAsync(
            () => _client.SearchAsync(ProductId.Text.Trim(), Version, Question.Text.Trim()),
            FormatSearch);

    private async void ChatClick(object sender, RoutedEventArgs e) =>
        await ShowAsync(
            () => _client.ChatAsync(ProductId.Text.Trim(), Version, Question.Text.Trim()),
            FormatChat);

    private async void EventClick(object sender, RoutedEventArgs e) =>
        await ShowAsync(
            () => _client.EventAsync(ProductId.Text.Trim(), Version,
                                    EmptyToNull(EventId.Text), EmptyToNull(ErrorCode.Text),
                                    EmptyToNull(ScreenId.Text)),
            FormatEvent);

    private static string? EmptyToNull(string text) =>
        string.IsNullOrWhiteSpace(text) ? null : text.Trim();
}
