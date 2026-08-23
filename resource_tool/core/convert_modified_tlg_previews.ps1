param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot,
    [string]$ToolRoot,
    [Parameter(Mandatory = $true)]
    [string]$OutputRoot,
    [Parameter(Mandatory = $true)]
    [string]$ReportPath
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

if ([string]::IsNullOrWhiteSpace($ToolRoot)) {
    $ToolRoot = Join-Path $ProjectRoot 'tools'
}
$tlgLibrary = Join-Path $ToolRoot 'FreeMote-v4.7.0\lib\TlgLib.dll'
if (-not (Test-Path -LiteralPath $tlgLibrary)) {
    throw "TlgLib.dll was not found: $tlgLibrary"
}
[void][Reflection.Assembly]::LoadFrom($tlgLibrary)

$previewRoot = Join-Path $ProjectRoot 'extracted\_tlg_png'
$extractedRoot = Join-Path $ProjectRoot 'extracted'
if (-not (Test-Path -LiteralPath $previewRoot)) {
    throw "TLG preview directory was not found: $previewRoot"
}
[IO.Directory]::CreateDirectory($OutputRoot) | Out-Null

function Get-PixelHash([Drawing.Bitmap]$Image) {
    $copy = New-Object Drawing.Bitmap(
        $Image.Width,
        $Image.Height,
        [Drawing.Imaging.PixelFormat]::Format32bppArgb
    )
    $graphics = [Drawing.Graphics]::FromImage($copy)
    try {
        $graphics.DrawImageUnscaled($Image, 0, 0)
    } finally {
        $graphics.Dispose()
    }

    $rectangle = New-Object Drawing.Rectangle(0, 0, $copy.Width, $copy.Height)
    $bitmapData = $copy.LockBits(
        $rectangle,
        [Drawing.Imaging.ImageLockMode]::ReadOnly,
        [Drawing.Imaging.PixelFormat]::Format32bppArgb
    )
    try {
        $bytes = New-Object byte[] ([Math]::Abs($bitmapData.Stride) * $bitmapData.Height)
        [Runtime.InteropServices.Marshal]::Copy(
            $bitmapData.Scan0,
            $bytes,
            0,
            $bytes.Length
        )
    } finally {
        $copy.UnlockBits($bitmapData)
        $copy.Dispose()
    }

    $sha256 = [Security.Cryptography.SHA256]::Create()
    try {
        return [Convert]::ToBase64String($sha256.ComputeHash($bytes))
    } finally {
        $sha256.Dispose()
    }
}

function Convert-ToRawTlg([Drawing.Bitmap]$Image, [int]$Version) {
    if ($Version -eq 5) {
        [byte[]]$encoded = [FreeMote.Tlg.TlgNative]::ToTlg5($Image)
    } elseif ($Version -eq 6) {
        [byte[]]$encoded = [FreeMote.Tlg.TlgNative]::ToTlg6($Image)
    } else {
        throw "Unsupported TLG version: $Version"
    }

    $isWrapper = (
        $encoded.Length -ge 15 -and
        [Text.Encoding]::ASCII.GetString($encoded, 0, 10) -eq "TLG0.0`0sds" -and
        $encoded[10] -eq 0x1a
    )
    if ($isWrapper) {
        $rawSize = [BitConverter]::ToInt32($encoded, 11)
        if ($rawSize -le 0 -or (15 + $rawSize) -gt $encoded.Length) {
            throw 'Invalid TLG0 wrapper returned by TlgLib.'
        }
        $raw = New-Object byte[] $rawSize
        [Array]::Copy($encoded, 15, $raw, 0, $rawSize)
        return $raw
    }
    return $encoded
}

$entries = New-Object System.Collections.Generic.List[object]
$previews = @(Get-ChildItem -LiteralPath $previewRoot -Recurse -Filter '*.png' -File)
foreach ($preview in $previews) {
    $relativePng = $preview.FullName.Substring($previewRoot.Length + 1)
    $relativeTlg = [IO.Path]::ChangeExtension($relativePng, '.tlg')
    $originalTlg = Join-Path $extractedRoot $relativeTlg
    if (-not (Test-Path -LiteralPath $originalTlg)) {
        throw "Original TLG for preview was not found: $relativePng"
    }

    $loader = $null
    $edited = $null
    try {
        $loader = New-Object FreeMote.Tlg.TlgLoader -ArgumentList (
            , [IO.File]::ReadAllBytes($originalTlg)
        )
        $edited = [Drawing.Bitmap]::new($preview.FullName)
        if ($loader.Width -ne $edited.Width -or $loader.Height -ne $edited.Height) {
            throw (
                "TLG preview dimensions changed: $relativePng " +
                "($($edited.Width)x$($edited.Height), expected $($loader.Width)x$($loader.Height))"
            )
        }

        if ((Get-PixelHash $loader.Bitmap) -eq (Get-PixelHash $edited)) {
            continue
        }

        $outputPath = Join-Path $OutputRoot $relativeTlg
        [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($outputPath)) | Out-Null
        [byte[]]$converted = Convert-ToRawTlg $edited $loader.Version
        [IO.File]::WriteAllBytes($outputPath, $converted)

        $verifyLoader = $null
        try {
            $verifyLoader = New-Object FreeMote.Tlg.TlgLoader -ArgumentList (, $converted)
            if ((Get-PixelHash $verifyLoader.Bitmap) -ne (Get-PixelHash $edited)) {
                throw "Converted TLG pixel verification failed: $relativePng"
            }
        } finally {
            if ($null -ne $verifyLoader) {
                $verifyLoader.Dispose()
            }
        }

        $entries.Add([ordered]@{
            archive_name = $relativeTlg.Replace('\', '/')
            preview_path = $preview.FullName
            output_path = $outputPath
            tlg_version = $loader.Version
            width = $loader.Width
            height = $loader.Height
        })
    } finally {
        if ($null -ne $edited) {
            $edited.Dispose()
        }
        if ($null -ne $loader) {
            $loader.Dispose()
        }
    }
}

$report = [ordered]@{
    scanned = $previews.Count
    changed = $entries.Count
    entries = @($entries | ForEach-Object { $_ })
}
$json = $report | ConvertTo-Json -Depth 5
$utf8WithoutBom = New-Object Text.UTF8Encoding($false)
[IO.File]::WriteAllText($ReportPath, $json + "`n", $utf8WithoutBom)
Write-Output "TLG previews scanned: $($previews.Count); modified: $($entries.Count)"
