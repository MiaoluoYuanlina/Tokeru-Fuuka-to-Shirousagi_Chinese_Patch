param(
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$scanDir = Join-Path $projectRoot 'build\uipsd_scan'
$baselineDir = Join-Path $projectRoot 'localization\uipsd_source_png'
if ([string]::IsNullOrWhiteSpace($OutputPath)) {
    $OutputPath = Join-Path $projectRoot 'localization\uipsd_image_text_scan.xlsx'
}
$OutputPath = [IO.Path]::GetFullPath($OutputPath)

$runtimeRoot = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies'
$python = Join-Path $runtimeRoot 'python\python.exe'
$node = Join-Path $runtimeRoot 'node\bin\node.exe'
$nodeModules = Join-Path $runtimeRoot 'node\node_modules'
foreach ($required in @($python, $node, $nodeModules)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required workspace runtime is missing: $required"
    }
}

function Invoke-Step([string]$Title, [string]$Executable, [string[]]$Arguments) {
    Write-Host "`n== $Title ==" -ForegroundColor Cyan
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$Title failed with exit code $LASTEXITCODE"
    }
}

$moduleLink = Join-Path $PSScriptRoot 'spreadsheet_work\uipsd_scan\node_modules'
if (-not (Test-Path -LiteralPath $moduleLink)) {
    New-Item -ItemType Junction -Path $moduleLink -Target $nodeModules | Out-Null
}

Invoke-Step 'Prepare clean source image baseline' $python @(
    (Join-Path $PSScriptRoot 'prepare_uipsd_source_baseline.py'),
    '--project-root', $projectRoot,
    '--baseline-dir', $baselineDir
)
Invoke-Step 'Create image manifest and contact sheets' $python @(
    (Join-Path $PSScriptRoot 'create_uipsd_scan_workspace.py'),
    $projectRoot,
    $scanDir,
    $baselineDir
)
Invoke-Step 'Scan UI image text with OCR' $python @(
    (Join-Path $PSScriptRoot 'scan_uipsd_text.py'),
    '--source-dir', $baselineDir,
    '--output-dir', $scanDir
)
Invoke-Step 'Prepare translation records' $python @(
    (Join-Path $PSScriptRoot 'prepare_uipsd_scan_data.py')
)

if (Test-Path -LiteralPath $OutputPath) {
    $timestamp = Get-Date -Format 'yyyyMMdd_HHmmss'
    $backupDir = Join-Path $projectRoot 'backups\spreadsheets'
    [IO.Directory]::CreateDirectory($backupDir) | Out-Null
    $backupPath = Join-Path $backupDir ("uipsd_image_text_scan_$timestamp.xlsx")
    Copy-Item -LiteralPath $OutputPath -Destination $backupPath
    Write-Host "Previous workbook backup: $backupPath" -ForegroundColor Yellow
}

Invoke-Step 'Create Excel translation workbook' $node @(
    (Join-Path $PSScriptRoot 'spreadsheet_work\uipsd_scan\build_uipsd_workbook.mjs'),
    '--project-root', $projectRoot,
    '--data', (Join-Path $scanDir 'workbook_data.json'),
    '--output', $OutputPath,
    '--preview-dir', (Join-Path $scanDir 'workbook_previews')
)

Write-Host "`nExport complete: $OutputPath" -ForegroundColor Green
Write-Host 'Fill the Chinese Translation column, then run apply_uipsd_translations.bat.'
