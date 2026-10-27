param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("morning", "evening")]
    [string]$Mode
)

$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Program = Join-Path $PSScriptRoot "daily_investment_automation.py"
$BundledPython = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"

if (Test-Path -LiteralPath $BundledPython) {
    $Python = $BundledPython
} else {
    $PythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if (-not $PythonCommand) {
        throw "Python was not found. Expected runtime: $BundledPython"
    }
    $Python = $PythonCommand.Source
}

Push-Location $ProjectRoot
try {
    & $Python $Program --mode $Mode
    exit $LASTEXITCODE
}
finally {
    Pop-Location
}
