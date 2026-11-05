// T06: direct C# integration with the T05 loopback API. No NuGet packages.
using System.Net.Http.Json;
using System.Text.Json;

if (args.Length < 4 || !int.TryParse(args[0], out var port) || port is < 1 or > 65535)
{
    Console.Error.WriteLine("Usage: <port> <product_id> <version|-> <health|search|chat|event> [query|error_code] [event_id|-] [screen_id|-]");
    return 2;
}

var productId = args[1];
var version = args[2] == "-" ? null : args[2];
var command = args[3];
var payload = new Dictionary<string, object?>
{
    ["product_id"] = productId,
};
if (version is not null)
{
    payload["version"] = version;
}

string path;
switch (command)
{
    case "health":
        path = "health";
        break;
    case "search":
        if (args.Length < 5) return Usage();
        path = "search";
        payload["query"] = args[4];
        break;
    case "chat":
        if (args.Length < 5) return Usage();
        path = "chat";
        payload["question"] = args[4];
        break;
    case "event":
        if (args.Length < 5) return Usage();
        path = "event";
        if (args[4] != "-") payload["error_code"] = args[4];
        if (args.Length >= 6 && args[5] != "-") payload["event_id"] = args[5];
        if (args.Length >= 7 && args[6] != "-") payload["screen_id"] = args[6];
        break;
    default:
        return Usage();
}

try
{
    using var http = new HttpClient
    {
        BaseAddress = new Uri($"http://127.0.0.1:{port}/"),
        Timeout = TimeSpan.FromSeconds(200),
    };
    // The native C# client does not send a browser Origin header.
    using var response = command == "health"
        ? await http.GetAsync(path)
        : await http.PostAsJsonAsync(path, payload);
    var content = await response.Content.ReadAsStringAsync();
    using var json = JsonDocument.Parse(content);
    Console.WriteLine(JsonSerializer.Serialize(
        json.RootElement, new JsonSerializerOptions { WriteIndented = true }));
    // API JSON already contains document_id, source_path and page_from;
    // do not fabricate clickable URLs for source documents.
    return response.IsSuccessStatusCode ? 0 : 1;
}
catch (HttpRequestException error)
{
    Console.Error.WriteLine($"Local API connection error: {error.Message}");
    return 1;
}
catch (TaskCanceledException)
{
    Console.Error.WriteLine("Local API request timed out");
    return 1;
}

static int Usage()
{
    Console.Error.WriteLine("Expected: <port> <product_id> <version|-> <health|search|chat|event> [query|error_code] [event_id|-] [screen_id|-]");
    return 2;
}
