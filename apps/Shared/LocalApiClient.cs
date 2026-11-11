using System.Net.Http;
using System.Text;
using System.Text.Json;

namespace DKKnowledgeShared;

// Shared API contract only. This file has no builder or administrator code.
public sealed class LocalApiClient : IDisposable
{
    private readonly HttpClient _http;

    public LocalApiClient(int port)
    {
        if (port is < 1 or > 65535)
            throw new ArgumentOutOfRangeException(nameof(port));
        _http = new HttpClient
        {
            BaseAddress = new Uri($"http://127.0.0.1:{port}/"),
            Timeout = TimeSpan.FromSeconds(240)
        };
    }

    private async Task<JsonElement> PostAsync(string endpoint, object payload)
    {
        using var content = new StringContent(
            JsonSerializer.Serialize(payload), Encoding.UTF8, "application/json");
        using var response = await _http.PostAsync(endpoint, content);
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

    // Used only by the explicit Client API test screen; preserves actual HTTP status.
    public async Task<(int StatusCode, string Body)> SendJsonAsync(
        string endpoint, string? jsonBody)
    {
        if (endpoint is not ("health" or "search" or "chat" or "event"))
            throw new ArgumentException("Unsupported API endpoint", nameof(endpoint));
        using var request = new HttpRequestMessage(
            endpoint == "health" ? HttpMethod.Get : HttpMethod.Post, endpoint);
        if (endpoint != "health")
            request.Content = new StringContent(jsonBody ?? "{}", Encoding.UTF8, "application/json");
        using var response = await _http.SendAsync(request);
        var body = await response.Content.ReadAsStringAsync();
        return ((int)response.StatusCode, body);
    }


    public void Dispose() => _http.Dispose();
}
