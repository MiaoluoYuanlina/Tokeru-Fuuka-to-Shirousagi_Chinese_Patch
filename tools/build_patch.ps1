param(
    [string]$TsvPath,
    [switch]$NoDialog
)

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [Text.UTF8Encoding]::new()
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$buildDirectory = Join-Path $projectRoot 'build'
[IO.Directory]::CreateDirectory($buildDirectory) | Out-Null
$lockPath = Join-Path $buildDirectory '.patch_build.lock'
try {
    $buildLock = [IO.File]::Open(
        $lockPath,
        [IO.FileMode]::OpenOrCreate,
        [IO.FileAccess]::ReadWrite,
        [IO.FileShare]::None
    )
} catch {
    Write-Host 'Another patch build is already running. Please wait for it to finish.' -ForegroundColor Yellow
    exit 1
}

$runningGame = Get-Process -Name 'kazeshiro_demo' -ErrorAction SilentlyContinue
if ($runningGame) {
    Write-Host 'Please close kazeshiro_demo before building the patch.' -ForegroundColor Yellow
    if (-not $NoDialog) {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(
            'Please close kazeshiro_demo before building the patch.',
            'Game is running',
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning
        ) | Out-Null
    }
    exit 1
}

Add-Type -AssemblyName System.Windows.Forms
if ([string]::IsNullOrWhiteSpace($TsvPath)) {
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = 'Select the scenario translation TSV to package'
    $dialog.InitialDirectory = Join-Path $projectRoot 'localization'
    $dialog.Filter = 'TSV translation file (*.tsv)|*.tsv|All files (*.*)|*.*'
    $dialog.FileName = 'scenario_dialogue_zh_cn_from_excel.tsv'
    $dialog.CheckFileExists = $true
    $dialog.Multiselect = $false

    if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
        Write-Host 'Build cancelled.'
        exit 0
    }

    $selectedTsv = $dialog.FileName
} else {
    try {
        $selectedTsv = (Resolve-Path -LiteralPath $TsvPath -ErrorAction Stop).Path
    } catch {
        Write-Host "TSV file not found: $TsvPath" -ForegroundColor Red
        exit 1
    }
}

$bundledPython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$python = $null
$pythonPrefix = @()
if (Test-Path -LiteralPath $bundledPython) {
    $python = $bundledPython
} else {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $python = $pythonCommand.Source
    } else {
        $pyCommand = Get-Command py -ErrorAction SilentlyContinue
        if ($pyCommand) {
            $python = $pyCommand.Source
            $pythonPrefix = @('-3')
        }
    }
}
if (-not $python) {
    throw 'Python 3 was not found. Install Python or keep the bundled Codex runtime.'
}

$builder = Join-Path $PSScriptRoot 'build_patch.py'
$arguments = @($pythonPrefix) + @(
    $builder,
    '--project-root', $projectRoot,
    '--tsv', $selectedTsv
)

Write-Host "Selected TSV: $selectedTsv"
Write-Host ''
& $python @arguments
$exitCode = $LASTEXITCODE

if (($exitCode -eq 0) -and (-not $NoDialog)) {
    [System.Windows.Forms.MessageBox]::Show(
        "Patch built successfully:`n$projectRoot\patch.xp3",
        'Build complete',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Information
    ) | Out-Null
} elseif (-not $NoDialog) {
    [System.Windows.Forms.MessageBox]::Show(
        "Patch build failed with exit code $exitCode.`nSee the console for details.",
        'Build failed',
        [System.Windows.Forms.MessageBoxButtons]::OK,
        [System.Windows.Forms.MessageBoxIcon]::Error
    ) | Out-Null
}
$buildLock.Dispose()
exit $exitCode
