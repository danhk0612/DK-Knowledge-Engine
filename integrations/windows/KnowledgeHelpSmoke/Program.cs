// Headless Windows CI smoke: reuse the exact HttpClient code linked by the WPF example.
using KnowledgeHelpDemo;

using var client = new KnowledgeHelpClient(args.Length == 1
    ? args[0] : "http://127.0.0.1:8765/");

var health = await client.HealthAsync();
if (health.GetProperty("status").GetString() != "ready")
    throw new Exception("health not ready");

var search = await client.SearchAsync("example-program", "2.1.0", "연결 오류");
var hits = search.GetProperty("results");
if (hits.GetArrayLength() == 0 ||
    hits[0].GetProperty("source_path").GetString() != "example-program/manuals/setup.md")
    throw new Exception("document search or source path mismatch");

var evt = await client.EventAsync(
    "example-program", "2.1.0", "connection_failed", "DB-1001", "db_settings");
if (!evt.GetProperty("matched").GetBoolean() ||
    evt.GetProperty("rule_id").GetString() != "db-1001")
    throw new Exception("event rule mismatch");

var chat = await client.ChatAsync("example-program", "2.1.0", "연결 오류 포트");
if (chat.GetProperty("grounded").GetBoolean() != true ||
    !chat.GetProperty("answer").GetString()!.Contains("3308") ||
    chat.GetProperty("sources").GetArrayLength() == 0)
    throw new Exception("grounded answer/source mismatch");

Console.WriteLine("T06 C# HTTP client smoke OK: health/search/event/chat");
