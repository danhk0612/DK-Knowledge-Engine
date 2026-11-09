using System.IO;
using System.Text.RegularExpressions;

namespace DKKnowledgeAdmin;

// Files in the authoring tree are never embedded in the end-user package.
public static class DocumentLibrary
{
    private static readonly HashSet<string> Extensions =
        new(StringComparer.OrdinalIgnoreCase) { ".pdf", ".docx", ".txt", ".md" };

    private static readonly Regex ProductName =
        new("^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$", RegexOptions.CultureInvariant);

    private static void CheckProduct(string productId)
    {
        if (!ProductName.IsMatch(productId) || productId is "." or "..")
            throw new ArgumentException("제품 ID는 영문·숫자로 시작하고 영문·숫자·._-만 사용할 수 있습니다.");
    }

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
        var parts = relativePath.Replace('/', Path.DirectorySeparatorChar)
            .Split(Path.DirectorySeparatorChar, StringSplitOptions.RemoveEmptyEntries);
        if (parts.Length < 3 || parts[1] != "manuals" ||
            parts.Any(p => p is "." or ".." || p.Contains(':')))
            throw new ArgumentException("제품 ID/manuals/문서 경로만 관리할 수 있습니다.");
        CheckProduct(parts[0]);
        var root = Path.GetFullPath(sourceRoot);
        var full = Path.GetFullPath(Path.Combine(root, Path.Combine(parts)));
        var rootPrefix = Path.EndsInDirectorySeparator(root)
            ? root : root + Path.DirectorySeparatorChar;
        if (!full.StartsWith(rootPrefix,
                StringComparison.OrdinalIgnoreCase) ||
            !Extensions.Contains(Path.GetExtension(full)))
            throw new ArgumentException("허용되지 않은 문서 경로 또는 확장자입니다.");
        CheckExistingAncestors(root, full);
        return full;
    }

    public static IReadOnlyList<string> List(string sourceRoot)
    {
        var root = Path.GetFullPath(sourceRoot);
        if (!Directory.Exists(root)) return [];
        if (IsLink(root)) throw new InvalidOperationException("심볼릭 링크 루트는 사용할 수 없습니다.");
        var result = new List<string>();
        foreach (var productDir in Directory.EnumerateDirectories(root))
        {
            if (IsLink(productDir))
                throw new InvalidOperationException("제품별 폴더가 심볼릭 링크입니다.");
            var manuals = Path.Combine(productDir, "manuals");
            if (!Directory.Exists(manuals)) continue;
            if (IsLink(manuals))
                throw new InvalidOperationException("문서 폴더가 심볼릭 링크입니다.");
            foreach (var file in Directory.EnumerateFiles(manuals, "*", SearchOption.AllDirectories))
            {
                if (!Extensions.Contains(Path.GetExtension(file))) continue;
                var relative = Path.GetRelativePath(root, file).Replace('\\', '/');
                ResolveDocument(root, relative);
                result.Add(relative);
            }
        }
        result.Sort(StringComparer.OrdinalIgnoreCase);
        return result;
    }

    public static string Add(string sourceRoot, string productId, string original)
    {
        CheckProduct(productId);
        if (!File.Exists(original) || !Extensions.Contains(Path.GetExtension(original)))
            throw new ArgumentException("PDF, DOCX, TXT 또는 MD 원본 파일을 선택하세요.");
        var root = Path.GetFullPath(sourceRoot);
        var folder = Path.Combine(root, productId, "manuals");
        var target = Path.Combine(folder, Path.GetFileName(original));
        CheckExistingAncestors(root, target);
        if (File.Exists(target))
            throw new IOException("동일한 파일 이름이 존재합니다. 교체 기능을 사용하세요.");
        Directory.CreateDirectory(folder);
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
