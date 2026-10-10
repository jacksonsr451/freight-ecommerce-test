param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Task
)

$ErrorActionPreference = 'Stop'
$Script = Join-Path $PSScriptRoot 'dev.py'
$Python = Get-Command 'python' -ErrorAction SilentlyContinue
if ($null -eq $Python) {
    $Launcher = Get-Command 'py' -ErrorAction SilentlyContinue
    if ($null -eq $Launcher) {
        throw 'Python 3.11+ was not found. Install Python and Poetry, then retry.'
    }
    & $Launcher.Source '-3' $Script $Task
} else {
    & $Python.Source $Script $Task
}
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}
