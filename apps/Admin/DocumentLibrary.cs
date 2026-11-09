using System.IO;

namespace DKKnowledgeAdmin;

// The authoring source folder is the document library; Client packages never include it.
public static class DocumentLibrary
{
    private static readonly HashSet<string> Extensions =
        new(StringComparer.OrdinalIgnoreCase) { ".pdf", ".docx", ".txt", ".md" };

    private static bool IsLink(string path) =>
        (File.GetAttributes(path) & FileAttributes.ReparsePoint) != 0;

    private static void CheckExistingAncestors(string root, string destination)
    {
        var current = Path.GetFullPath(root);
        if (Directory.Exists(current) && IsLink(current))
            throw new InvalidOperationException("연결된 폴더(심볼릭 링크)는 사용할 수 없습니다.");
        var relative = Path.GetRelativePath(current, destination);
        foreach (var part in relative.Split(Path.DirectorySeparatorChar))
        {
            current = Path.Combine(current, part);
            if ((File.Exists(current) || Directory.Exists(current)) && IsLink(current))
                throw new InvalidOperationException("심볼릭 링크인 문서 또는 폴더는 변경할 수 없습니다.");
        }
    }

    private static string ResolveDocument(string sourceRoot, string relativePath)
    {
        if (string.IsNullOrWhiteSpace(relativePath) || Path.IsPathRooted(relativePath))
            throw new ArgumentException("원본 폴더 내부의 상대 문서 경로를 선택하세요.");
        var parts = relativePath.Replace('/', Path.DirectorySeparatorChar)
            .Split(Path.DirectorySeparatorChar, StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length == 0 || parts.Any(p => p is "." or ".." || p.Contains(':')))
            throw new ArgumentException("원본 폴더 외부 경로는 사용할 수 없습니다.");

        var root = Path.GetFullPath(sourceRoot);
        var full = Path.GetFullPath(Path.Combine(root, Path.Combine(parts)));
        var rootPrefix = Path.EndsInDirectorySeparator(root)
            ? root : root + Path.DirectorySeparatorChar;
        if (!full.StartsWith(rootPrefix, StringComparison.OrdinalIgnoreCase) ||
            !Extensions.Contains(Path.GetExtension(full)))
            throw new ArgumentException("원본 폴더 외부 경로 또는 지원하지 않는 확장자입니다.");
        CheckExistingAncestors(root, full);
        return full;
    }

    public static IReadOnlyList<string> List(string sourceRoot)
    {
        var root = Path.GetFullPath(sourceRoot);
        if (!Directory.Exists(root)) return [];
        if (IsLink(root)) throw new InvalidOperationException("심볼릭 링크 루트는 사용할 수 없습니다.");

        var result = new List<string>();
        var pending = new Stack<string>();
        pending.Push(root);
        while (pending.Count > 0)
        {
            var folder = pending.Pop();
            foreach (var entry in Directory.EnumerateFileSystemEntries(folder))
            {
                if (IsLink(entry))
                    throw new InvalidOperationException("문서 루트 내부에 심볼릭 링크가 있습니다: " + entry);
                if (Directory.Exists(entry))
                {
                    pending.Push(entry);
                }
                else if (File.Exists(entry) && Extensions.Contains(Path.GetExtension(entry)))
                {
                    var relative = Path.GetRelativePath(root, entry).Replace('\\', '/');
                    ResolveDocument(root, relative);
                    result.Add(relative);
                }
            }
        }
        result.Sort(StringComparer.OrdinalIgnoreCase);
        return result;
    }

    public static string Add(string sourceRoot, string original)
    {
        if (!File.Exists(original) || !Extensions.Contains(Path.GetExtension(original)))
            throw new ArgumentException("PDF, DOCX, TXT 또는 MD 원본 파일을 선택하세요.");
        var root = Path.GetFullPath(sourceRoot);
        var target = ResolveDocument(root, Path.GetFileName(original));
        if (File.Exists(target))
            throw new IOException("동일한 파일 이름이 존재합니다. 교체 기능을 사용하세요.");
        Directory.CreateDirectory(root);
        File.Copy(original, target, overwrite: false);
        return Path.GetRelativePath(root, target).Replace('\\', '/');
    }

    public static void Replace(string sourceRoot, string relativePath, string replacement)
    {
        var target = ResolveDocument(sourceRoot, relativePath);
        if (!File.Exists(target))
            throw new FileNotFoundException("교체할 기존 문서를 찾을 수 없습니다.", target);
        if (!File.Exists(replacement) ||
            !string.Equals(Path.GetExtension(target), Path.GetExtension(replacement),
                StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("교체 파일은 기존 문서와 확장자가 같아야 합니다.");
        var temporary = Path.Combine(Path.GetDirectoryName(target)!,
            ".dk-replace-" + Guid.NewGuid().ToString("N") + Path.GetExtension(target));
        try
        {
            File.Copy(replacement, temporary);
            File.Move(temporary, target, overwrite: true);
        }
        finally
        {
            if (File.Exists(temporary)) File.Delete(temporary);
        }
    }

    public static void Delete(string sourceRoot, string relativePath)
    {
        var target = ResolveDocument(sourceRoot, relativePath);
        if (!File.Exists(target))
            throw new FileNotFoundException("삭제할 문서를 찾을 수 없습니다.", target);
        var metadata = target + ".meta.json";
        if (File.Exists(metadata) && IsLink(metadata))
            throw new InvalidOperationException("메타데이터가 심볼릭 링크입니다.");
        File.Delete(target);
        if (File.Exists(metadata)) File.Delete(metadata);
    }
}
