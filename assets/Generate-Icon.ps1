[CmdletBinding()]
param(
    [Parameter(Mandatory=$true)] [string]$Output,
    [ValidateSet('admin','client','png','ico')] [string]$Kind = 'client',
    [string]$SourcePng,
    [string]$SourceIco
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
if ($Kind -eq 'png' -and (-not $SourcePng -or
    -not (Test-Path -LiteralPath $SourcePng -PathType Leaf))) {
    throw 'Choose an existing PNG file for a custom icon'
}
$directory = [IO.Path]::GetDirectoryName([IO.Path]::GetFullPath($Output))
[IO.Directory]::CreateDirectory($directory) | Out-Null
# Preserve already compliant multi-resolution ICOs byte-for-byte. If an
# otherwise valid user ICO lacks one of the four EXE sizes, render its best
# available frame into a standard Windows ICO instead of rejecting it.
$sourceIcon = $null
$sourceImage = $null
if ($Kind -eq 'ico') {
    if (-not $SourceIco -or -not (Test-Path -LiteralPath $SourceIco -PathType Leaf)) {
        throw 'Choose an existing ICO file for a custom icon'
    }
    $sourcePath = (Resolve-Path -LiteralPath $SourceIco).Path
    $bytes = [IO.File]::ReadAllBytes($sourcePath)
    if ($bytes.Length -lt 6 -or [BitConverter]::ToUInt16($bytes,0) -ne 0 -or
        [BitConverter]::ToUInt16($bytes,2) -ne 1) {
        throw 'Not a valid Windows ICO file'
    }
    $count = [int][BitConverter]::ToUInt16($bytes,4)
    if ($count -lt 1 -or $count -gt 64 -or $bytes.Length -lt 6 + 16 * $count) {
        throw 'Invalid Windows ICO directory'
    }
    $present = [System.Collections.Generic.HashSet[int]]::new()
    for ($i=0; $i -lt $count; $i++) {
        $entry = 6 + 16 * $i
        $width = if ($bytes[$entry] -eq 0) {256} else {[int]$bytes[$entry]}
        $height = if ($bytes[$entry+1] -eq 0) {256} else {[int]$bytes[$entry+1]}
        $length = [uint64][BitConverter]::ToUInt32($bytes,$entry+8)
        $offset = [uint64][BitConverter]::ToUInt32($bytes,$entry+12)
        if ($length -eq 0 -or $length -gt 16MB -or $offset + $length -gt $bytes.Length) {
            throw 'Invalid Windows ICO image entry'
        }
        if ($width -eq $height) { [void]$present.Add($width) }
    }
    $requiredSizes = @(16,32,48,256)
    if (@($requiredSizes | Where-Object { -not $present.Contains($_) }).Count -eq 0) {
        Copy-Item -LiteralPath $sourcePath -Destination ([IO.Path]::GetFullPath($Output)) -Force
        Write-Output ('ICON_READY ' + [IO.Path]::GetFullPath($Output))
        return
    }
    $sourceIcon = [System.Drawing.Icon]::new($sourcePath, [System.Drawing.Size]::new(256,256))
    $sourceImage = $sourceIcon.ToBitmap()
}
$images = [System.Collections.Generic.List[byte[]]]::new()
$sizes = @(16,32,48,256)
foreach ($n in $sizes) {
    $bitmap = [System.Drawing.Bitmap]::new($n,$n)
    $g = [System.Drawing.Graphics]::FromImage($bitmap)
    try {
        $g.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
        $g.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
        if ($Kind -eq 'png') {
            $source = [System.Drawing.Image]::FromFile((Resolve-Path -LiteralPath $SourcePng).Path)
            try { $g.DrawImage($source,0,0,$n,$n) }
            finally { $source.Dispose() }
        } elseif ($Kind -eq 'ico') {
            $g.DrawImage($sourceImage,0,0,$n,$n)
        } else {
            $scale = $n / 256.0
            $g.ScaleTransform([float]$scale,[float]$scale)
            $outer = [System.Drawing.SolidBrush]::new(
                [System.Drawing.ColorTranslator]::FromHtml($(if ($Kind -eq 'admin') {'#334155'} else {'#176B75'})))
            $paper = [System.Drawing.SolidBrush]::new([System.Drawing.Color]::White)
            $accent = [System.Drawing.SolidBrush]::new(
                [System.Drawing.ColorTranslator]::FromHtml($(if ($Kind -eq 'admin') {'#58B4E7'} else {'#B8F3DF'})))
            try {
                # Transparent corners and a large high-contrast symbol survive 16x16 scaling.
                $g.FillEllipse($outer, 12,12,232,232)
                if ($Kind -eq 'admin') {
                    # Database stacked disks and document page.
                    $g.FillRectangle($paper,62,72,119,116)
                    $g.FillEllipse($accent,62,61,119,42)
                    $g.FillEllipse($accent,62,151,119,42)
                    $g.FillRectangle($paper,150,118,56,77)
                    $g.FillRectangle($outer,163,138,29,7)
                    $g.FillRectangle($outer,163,156,29,7)
                } else {
                    # Open book and speech mark.
                    $g.FillRectangle($paper,47,96,78,106)
                    $g.FillRectangle($paper,131,96,78,106)
                    $g.FillRectangle($accent,119,97,18,111)
                    $g.FillEllipse($accent,92,47,110,75)
                    $g.FillRectangle($accent,142,100,20,36)
                }
            } finally { $outer.Dispose();$paper.Dispose();$accent.Dispose() }
        }
        $ms = [IO.MemoryStream]::new()
        try {
            $bitmap.Save($ms,[System.Drawing.Imaging.ImageFormat]::Png)
            $images.Add($ms.ToArray())
        } finally { $ms.Dispose() }
    } finally { $g.Dispose();$bitmap.Dispose() }
}
$file = [IO.File]::Create([IO.Path]::GetFullPath($Output))
$writer = [IO.BinaryWriter]::new($file)
try {
    $writer.Write([uint16]0)
    $writer.Write([uint16]1)
    $writer.Write([uint16]$images.Count)
    $offset = 6 + 16 * $images.Count
    for ($i=0;$i -lt $images.Count;$i++) {
        $size = $sizes[$i]
        $writer.Write([byte]$(if ($size -eq 256) {0} else {$size}))
        $writer.Write([byte]$(if ($size -eq 256) {0} else {$size}))
        $writer.Write([byte]0)
        $writer.Write([byte]0)
        $writer.Write([uint16]1)
        $writer.Write([uint16]32)
        $writer.Write([uint32]$images[$i].Length)
        $writer.Write([uint32]$offset)
        $offset += $images[$i].Length
    }
    foreach ($png in $images) { $writer.Write($png) }
} finally {
    $writer.Dispose()
    if ($null -ne $sourceImage) { $sourceImage.Dispose() }
    if ($null -ne $sourceIcon) { $sourceIcon.Dispose() }
}
Write-Output ('ICON_READY ' + [IO.Path]::GetFullPath($Output))
