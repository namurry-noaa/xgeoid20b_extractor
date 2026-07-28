<#
.SYNOPSIS
    Launcher for the xGEOID20B Batch Extraction Tool.

.DESCRIPTION
    Selects the conda environment to run in (per the [runtime] section of
    config.ini), verifies conda + the environment + required packages, then
    runs xgeoid20b_extractor.py in that environment.

    Conda is the recommended package manager: netCDF4/numpy depend on
    compiled binaries (HDF5, netCDF-C) that conda resolves far more reliably
    than pip.

.NOTES
    Data-file / input / output problems are handled by the Python tool
    itself; this launcher only ensures a valid runtime, then hands off.
#>

$ErrorActionPreference = 'Stop'

# --- Locate ourselves ---
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ConfigPath = Join-Path $ScriptDir 'config.ini'
$PyScript   = Join-Path $ScriptDir 'xgeoid20b_extractor.py'
$EnvYml     = Join-Path $ScriptDir 'environment.yml'

function Fail {
    param([string]$Message)
    Write-Host ""
    Write-Host "ERROR: $Message" -ForegroundColor Red
    Write-Host ""
    # Hold the window open so the error is readable when launched by
    # double-click (where it would otherwise close instantly).
    Write-Host "Press any key to close..."
    [void][System.Console]::ReadKey($true)
    exit 1
}

# --- Read the [runtime] section of config.ini (simple INI parse) ---
function Get-RuntimeConfig {
    param([string]$Path)
    $result = @{ conda_root = ''; conda_env = '' }
    if (-not (Test-Path -LiteralPath $Path)) { return $result }

    $section = ''
    foreach ($line in Get-Content -LiteralPath $Path) {
        $trimmed = $line.Trim()
        if ($trimmed -eq '' -or $trimmed.StartsWith('#') -or $trimmed.StartsWith(';')) { continue }
        if ($trimmed -match '^\[(.+)\]$') { $section = $matches[1].Trim().ToLower(); continue }
        if ($section -eq 'runtime' -and $trimmed -match '^(.*?)=(.*)$') {
            $key = $matches[1].Trim().ToLower()
            $val = $matches[2].Trim()
            if ($result.ContainsKey($key)) { $result[$key] = $val }
        }
    }
    return $result
}

# --- Resolve the conda install root ---
function Resolve-CondaRoot {
    param([string]$Explicit)

    # 1. Explicit conda_root from config wins outright.
    if ($Explicit -ne '') {
        if (-not (Test-Path -LiteralPath $Explicit)) {
            Fail "config.ini [runtime] conda_root does not exist:`n    $Explicit"
        }
        return $Explicit
    }

    # 2. Autodetect: conda on PATH.
    $onPath = Get-Command conda -ErrorAction SilentlyContinue
    if ($onPath) {
        # conda is typically <root>\Scripts\conda.exe or <root>\condabin\conda.bat
        $condaDir = Split-Path -Parent $onPath.Source
        $root = Split-Path -Parent $condaDir
        if (Test-Path (Join-Path $root 'python.exe')) { return $root }
        if (Test-Path (Join-Path $root 'Scripts\conda.exe')) { return $root }
    }

    # 3. Autodetect: common install locations under the user profile.
    foreach ($name in @('Miniconda3', 'miniconda3', 'Anaconda3', 'anaconda3')) {
        $cand = Join-Path $env:USERPROFILE $name
        if (Test-Path (Join-Path $cand 'Scripts\conda.exe')) { return $cand }
    }

    Fail @"
Could not locate a conda installation.
       Install Miniconda, or set conda_root in config.ini [runtime] to your
       conda install directory (e.g. C:\Users\you\Miniconda3).
"@
}

# --- Locate the python.exe for the chosen environment ---
function Resolve-EnvPython {
    param([string]$Root, [string]$EnvName)

    if ($EnvName -eq '' -or $EnvName.ToLower() -eq 'base') {
        $py = Join-Path $Root 'python.exe'
        if (-not (Test-Path -LiteralPath $py)) {
            Fail "base environment python.exe not found under:`n    $Root"
        }
        return $py
    }

    $py = Join-Path $Root "envs\$EnvName\python.exe"
    if (-not (Test-Path -LiteralPath $py)) {
        Fail @"
conda environment '$EnvName' not found under:
    $Root\envs\$EnvName
       Create it with:
    conda env create -f "$EnvYml"
       or set conda_env in config.ini [runtime] to an existing environment.
"@
    }
    return $py
}

# =============================================================================
# Main
# =============================================================================
if (-not (Test-Path -LiteralPath $PyScript)) {
    Fail "Cannot find xgeoid20b_extractor.py next to run.ps1."
}

$rt = Get-RuntimeConfig -Path $ConfigPath
$condaRoot = Resolve-CondaRoot -Explicit $rt.conda_root
$envName   = $rt.conda_env
$envLabel  = if ($envName -eq '') { 'base' } else { $envName }
$python    = Resolve-EnvPython -Root $condaRoot -EnvName $envName

Write-Host "xGEOID20B launcher" -ForegroundColor Cyan
Write-Host "  conda root : $condaRoot"
Write-Host "  environment: $envLabel"
Write-Host "  python     : $python"

# --- Verify required packages import in the chosen environment ---
$check = & $python -c "import netCDF4, numpy" 2>&1
if ($LASTEXITCODE -ne 0) {
    Fail @"
Environment '$envLabel' is missing required packages (netCDF4 / numpy).
       Detail: $check
       Recommended (conda):
    conda env create -f "$EnvYml"        # creates the 'xgeoid' env
       or, into the current environment:
    conda install -c conda-forge netCDF4 numpy
"@
}

Write-Host "  packages   : netCDF4, numpy OK" -ForegroundColor Green
Write-Host ""

# --- Hand off to the Python tool (it handles data/file issues itself) ---
& $python $PyScript @args
$code = $LASTEXITCODE

# Keep the window readable when launched by double-click (where it would
# otherwise close instantly). On error: hold until a key is pressed so the
# message can be read. On success: a brief pause so the user can see the
# output/log location scroll by.
if ($code -ne 0) {
    Write-Host ""
    Write-Host "The tool exited with an error (code $code). Review the message above." -ForegroundColor Red
    Write-Host "Press any key to close..."
    [void][System.Console]::ReadKey($true)
} else {
    Write-Host ""
    Write-Host "Done. See the output/ and logs/ folders for results." -ForegroundColor Green
    Start-Sleep -Seconds 3
}

exit $code
