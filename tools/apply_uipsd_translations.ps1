param(
    [string]$WorkbookPath,
    [switch]$NoDialog
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$buildDir = Join-Path $projectRoot 'build\uipsd_localize'
$baselineDir = Join-Path $projectRoot 'localization\uipsd_source_png'
$candidateDir = Join-Path $buildDir 'candidate_png'
$targetDir = Join-Path $projectRoot 'extracted\_tlg_png\uipsd'

if ([string]::IsNullOrWhiteSpace($WorkbookPath)) {
    Add-Type -AssemblyName System.Windows.Forms
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = 'Select the completed UI translation workbook'
    $dialog.InitialDirectory = Join-Path $projectRoot 'localization'
    $dialog.Filter = 'Excel workbook (*.xlsx)|*.xlsx|All files (*.*)|*.*'
    $dialog.FileName = 'uipsd_image_text_scan.xlsx'
    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        Write-Host 'Cancelled.'
        exit 0
    }
    $WorkbookPath = $dialog.FileName
}
try {
    $WorkbookPath = (Resolve-Path -LiteralPath $WorkbookPath -ErrorAction Stop).Path
} catch {
    throw "Excel translation workbook not found: $WorkbookPath"
}

$runtimeRoot = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies'
$python = Join-Path $runtimeRoot 'python\python.exe'
$node = Join-Path $runtimeRoot 'node\bin\node.exe'
foreach ($required in @($python, $node)) {
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

$runningGame = Get-Process -Name 'kazeshiro_demo' -ErrorAction SilentlyContinue
if ($runningGame) {
    throw 'Close kazeshiro_demo before writing localized images.'
}

Invoke-Step 'Prepare clean source image baseline' $python @(
    (Join-Path $PSScriptRoot 'prepare_uipsd_source_baseline.py'),
    '--project-root', $projectRoot,
    '--baseline-dir', $baselineDir
)
Invoke-Step 'Read and validate Excel translations' $node @(
    (Join-Path $PSScriptRoot 'spreadsheet_work\uipsd_scan\extract_completed_translations.mjs'),
    '--project-root', $projectRoot,
    '--workbook', $WorkbookPath,
    '--output-dir', $buildDir
)

$rectangles = Join-Path $buildDir 'pbd_state_rectangles.json'
if (-not (Test-Path -LiteralPath $rectangles)) {
    Invoke-Step 'Extract UI atlas rectangles' $python @((Join-Path $PSScriptRoot 'extract_uipsd_pbd_rects.py'))
}
$rectangleOcr = Join-Path $buildDir 'pbd_rectangle_ocr.json'
if (-not (Test-Path -LiteralPath $rectangleOcr)) {
    Invoke-Step 'OCR UI atlas states' $python @(
        (Join-Path $PSScriptRoot 'scan_pbd_state_text.py'),
        '--source-dir', $baselineDir,
        '--build-dir', $buildDir
    )
}

Invoke-Step 'Match translations to atlas rectangles' $python @((Join-Path $PSScriptRoot 'map_pbd_text_to_translations.py'))
Invoke-Step 'Render localized images with automatic fitting' $python @(
    (Join-Path $PSScriptRoot 'render_uipsd_localization.py'),
    '--source-dir', $baselineDir,
    '--build-dir', $buildDir,
    '--output-dir', $candidateDir,
    '--translations', (Join-Path $buildDir 'translations_from_excel.json')
)
Invoke-Step 'Verify image dimensions and text bounds' $python @(
    (Join-Path $PSScriptRoot 'verify_uipsd_render.py'),
    '--source-dir', $baselineDir,
    '--candidate-dir', $candidateDir,
    '--manifest', (Join-Path $buildDir 'render_manifest.json'),
    '--report', (Join-Path $buildDir 'render_verification.json')
)
Invoke-Step 'Create visual QA contact sheets' $python @((Join-Path $PSScriptRoot 'create_uipsd_candidate_contact_sheets.py'))
Invoke-Step 'Back up and apply localized images' $python @(
    (Join-Path $PSScriptRoot 'apply_uipsd_localization.py'),
    '--project-root', $projectRoot,
    '--source-dir', $candidateDir,
    '--target-dir', $targetDir
)

Write-Host "`nImage processing complete." -ForegroundColor Green
Write-Host "Visual QA sheets: $(Join-Path $buildDir 'qa_contact_sheets')"
Write-Host 'Run build_patch.bat and select the scenario TSV to update patch.xp3.'
