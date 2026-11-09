using DKKnowledgeAdmin;

static void Check(bool condition, string message)
{
    if (!condition) throw new Exception(message);
}

static void Reject(Action act, string message)
{
    try { act(); }
    catch (ArgumentException) { return; }
    catch (IOException) { return; }
    throw new Exception(message);
}

var root = Path.Combine(Path.GetTempPath(), "dk-admin-document-smoke-" + Guid.NewGuid().ToString("N"));
try
{
    var sources = Path.Combine(root, "sources");
    Directory.CreateDirectory(root);
    var first = Path.Combine(root, "manual.md");
    var second = Path.Combine(root, "updated.md");
    File.WriteAllText(first, "# 네트워크\n포트 3308");
    File.WriteAllText(second, "# 네트워크\n포트 3322");

    var doc = DocumentLibrary.Add(sources, "manual-test", first);
    Check(doc == "manual-test/manuals/manual.md", "Import path/product incorrect");
    Check(DocumentLibrary.List(sources).SequenceEqual([doc]), "Document list incorrect");
    Check(DocumentLibrary.List(sources + Path.DirectorySeparatorChar).SequenceEqual([doc]),
        "Trailing separator unexpectedly rejected the document list");

    Reject(() => DocumentLibrary.Add(sources, "manual-test", first),
        "Duplicate add overwrote an existing document");
    Reject(() => DocumentLibrary.Add(sources, "../outside", first),
        "Invalid product ID was accepted");
    Reject(() => DocumentLibrary.Delete(sources, "../outside/manuals/manual.md"),
        "Traversal was accepted");
    Reject(() => DocumentLibrary.Delete(sources, "manual-test/rules/rule.md"),
        "Non-manual path was accepted");

    var target = Path.Combine(sources, "manual-test", "manuals", "manual.md");
    File.WriteAllText(target + ".meta.json", "{\"document_id\":\"stable-id\"}");
    DocumentLibrary.Replace(sources, doc, second);
    Check(File.ReadAllText(target).Contains("3322"), "Document replace failed");
    Check(File.Exists(target + ".meta.json"), "Replace lost the metadata sidecar");

    var pdf = Path.Combine(root, "replace.pdf");
    File.WriteAllText(pdf, "placeholder");
    Reject(() => DocumentLibrary.Replace(sources, doc, pdf),
        "Cross-extension replace was accepted");

    DocumentLibrary.Delete(sources, doc);
    Check(!File.Exists(target) && !File.Exists(target + ".meta.json"),
        "Document or matching sidecar was not removed");
    Check(DocumentLibrary.List(sources).Count == 0, "Deleted document still listed");
    Check(!Directory.Exists(Path.Combine(sources, "..", "outside")),
        "Operation escaped its source root");
    Console.WriteLine("T13_ADMIN_DOCUMENT_CRUD_OK");
}
finally
{
    if (Directory.Exists(root)) Directory.Delete(root, recursive: true);
}
