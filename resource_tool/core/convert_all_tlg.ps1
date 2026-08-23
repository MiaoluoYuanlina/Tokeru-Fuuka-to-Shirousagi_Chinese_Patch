param(
    [Parameter(Mandatory=$true)][string]$Extracted,
    [Parameter(Mandatory=$true)][string]$TlgLibrary
)
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
[void][Reflection.Assembly]::LoadFrom($TlgLibrary)
$root = (Resolve-Path -LiteralPath $Extracted).Path
$preview = Join-Path $root '_tlg_png'
$files = @(Get-ChildItem -LiteralPath $root -Recurse -Filter '*.tlg' -File | Where-Object { $_.FullName -notlike "$preview*" })
foreach ($source in $files) {
    $relative = $source.FullName.Substring($root.Length + 1)
    $destination = Join-Path $preview ([IO.Path]::ChangeExtension($relative, '.png'))
    [IO.Directory]::CreateDirectory([IO.Path]::GetDirectoryName($destination)) | Out-Null
    $loader = New-Object FreeMote.Tlg.TlgLoader -ArgumentList (, [IO.File]::ReadAllBytes($source.FullName))
    try { $loader.Bitmap.Save($destination, [Drawing.Imaging.ImageFormat]::Png) }
    finally { $loader.Dispose() }
}
Write-Host "TLG previews: $($files.Count)"

