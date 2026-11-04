using System.Net.Http;
using System.Net.Http.Json;
using System.Text.Json;

namespace KnowledgeHelpDemo;

/// <summary>Small native Windows HTTP integration for the four T05 endpoints.</summary>
public sealed class KnowledgeHelpClient : IDisposable
{
    private readonly HttpClient _http;

    public KnowledgeHelpClient(string baseAddress = "http://127.0.0.1:8765/")
    {
        _http = new HttpClient { BaseAddress = new Uri(baseAddress) };
    }

    private async Task<JsonElement> PostAsync(string path, object body)
    {
        using var response = await _http.PostAsJsonAsync(path, body);
        response.EnsureSuccessStatusCode();
        using var json = await JsonDocument.ParseAsync(
            await response.Content.ReadAsStreamAsync());
        return json.RootElement.Clone();
    }

    public async Task<JsonElement> HealthAsync()
    {
        using var response = await _http.GetAsync("health");
        response.EnsureSuccessStatusCode();
        using var json = await JsonDocument.ParseAsync(
            await response.Content.ReadAsStreamAsync());
        return json.RootElement.Clone();
    }

    public Task<JsonElement> SearchAsync(string productId, string? version, string query) =>
        PostAsync("search", new { product_id = productId, version, query });

    public Task<JsonElement> ChatAsync(string productId, string? version, string question) =>
        PostAsync("chat", new { product_id = productId, version, question });

    public Task<JsonElement> EventAsync(
        string productId, string? version, string? eventId, string? errorCode, string? screenId) =>
        PostAsync("event", new {
            product_id = productId, version,
            event_id = eventId, error_code = errorCode, screen_id = screenId
        });

    public void Dispose() => _http.Dispose();
}
