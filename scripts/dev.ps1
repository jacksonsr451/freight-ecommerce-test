param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Install', 'Check', 'Format', 'Backend', 'Frontend', 'Smoke', 'Migrate', 'PersistenceCheck', 'Seed')]
    [string]$Task
)

$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$env:POETRY_VIRTUALENVS_IN_PROJECT = 'true'

function Invoke-Checked {
    param([string]$Executable, [string[]]$Arguments)
    & $Executable @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $Executable (exit $LASTEXITCODE)"
    }
}

switch ($Task) {
    'Install' {
        Invoke-Checked 'poetry' @('-C', $Backend, 'sync')
        Invoke-Checked 'npm.cmd' @('--prefix', $Frontend, 'ci')
    }
    'Check' {
        Invoke-Checked 'poetry' @('-C', $Backend, 'check', '--lock')
        Invoke-Checked 'poetry' @('-C', $Backend, 'run', 'ruff', 'check', '.')
        Invoke-Checked 'poetry' @('-C', $Backend, 'run', 'ruff', 'format', '--check', '.')
        Invoke-Checked 'poetry' @('-C', $Backend, 'run', 'ruff', 'check', (Join-Path $Root 'tests'))
        Invoke-Checked 'poetry' @('-C', $Backend, 'run', 'ruff', 'format', '--check', (Join-Path $Root 'tests'))
        Invoke-Checked 'poetry' @('-C', $Backend, 'run', 'pytest')
        foreach ($Script in @('lint', 'format:check', 'test', 'build')) {
            Invoke-Checked 'npm.cmd' @('--prefix', $Frontend, 'run', $Script)
        }
        Invoke-Checked 'poetry' @('-C', $Backend, 'run', 'python', (Join-Path $Root 'tests\validate_contract_matrix.py'))
    }
    'Format' {
        Invoke-Checked 'poetry' @('-C', $Backend, 'run', 'ruff', 'format', '.')
        Invoke-Checked 'poetry' @('-C', $Backend, 'run', 'ruff', 'format', (Join-Path $Root 'tests'))
        Invoke-Checked 'npm.cmd' @('--prefix', $Frontend, 'run', 'format')
    }
    'Backend' {
        Invoke-Checked 'poetry' @('-C', $Backend, 'run', 'python', '-m', 'uvicorn', 'freight_ecommerce.main:create_app', '--factory', '--reload', '--host', '127.0.0.1', '--port', '8000')
    }
    'Frontend' {
        Invoke-Checked 'npm.cmd' @('--prefix', $Frontend, 'run', 'dev')
    }
    'Smoke' {
        Invoke-Checked 'poetry' @('-C', $Backend, 'run', 'python', (Join-Path $Root 'tests\smoke_local.py'))
    }
    'Migrate' {
        Invoke-Checked 'poetry' @('-C', $Backend, 'run', 'alembic', 'upgrade', 'head')
    }
    'Seed' {
        Invoke-Checked 'poetry' @('-C', $Backend, 'run', 'python', '-m', 'freight_ecommerce.catalog.seed')
    }
    'PersistenceCheck' {
        if (-not $env:TEST_DATABASE_URL -and -not $env:TEST_POSTGRES_BIN) {
            throw 'Set TEST_DATABASE_URL (loopback PostgreSQL) or TEST_POSTGRES_BIN before PersistenceCheck.'
        }
        Invoke-Checked 'poetry' @('-C', $Backend, 'run', 'pytest', '-m', 'postgres')
    }
}
