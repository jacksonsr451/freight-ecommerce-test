#!/usr/bin/env python3
"""Cross-platform project tasks. All child processes use argv lists and explicit cwd paths."""

from __future__ import annotations

import argparse
import ipaddress
import os
import platform
import shutil
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import unquote, urlsplit
from uuid import UUID

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
ENV_EXAMPLE = ROOT / ".env.example"
ENV_FILE = ROOT / ".env"
os.environ.setdefault("POETRY_VIRTUALENVS_IN_PROJECT", "true")

ALIASES = {
    "install": "setup",
    "backendcheck": "backend-check",
    "frontendcheck": "frontend-check",
    "persistencecheck": "persistence-check",
    "layoutcheck": "layout",
}


def normalized_task(value: str) -> str:
    value = value.strip().lower().replace("_", "-")
    return ALIASES.get(value.replace("-", ""), value)


def run(
    argv: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess:
    print(f"[{cwd.relative_to(ROOT)}] {' '.join(argv)}", flush=True)
    try:
        result = subprocess.run(argv, cwd=cwd, env=env, shell=False, check=False)
    except FileNotFoundError as error:
        raise RuntimeError(f"Required executable not found: {argv[0]}") from error
    if check and result.returncode:
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {argv[0]}")
    return result


def require_tool(name: str) -> str:
    executable = shutil.which(name)
    if executable is None:
        raise RuntimeError(f"Required tool '{name}' was not found on PATH")
    return executable


def poetry(*args: str) -> list[str]:
    return [require_tool("poetry"), *args]


def npm(*args: str) -> list[str]:
    return [require_tool("npm"), *args]


def docker(*args: str) -> list[str]:
    return [require_tool("docker"), *args]


def compose(*args: str) -> list[str]:
    return docker("compose", *args)


def ensure_env_file() -> None:
    if not ENV_FILE.exists():
        if not ENV_EXAMPLE.is_file():
            raise RuntimeError("Root .env.example is missing")
        shutil.copyfile(ENV_EXAMPLE, ENV_FILE)
        print("Created root .env from .env.example; existing .env files are never overwritten.")


def test_database_configured() -> None:
    if not os.environ.get("TEST_DATABASE_URL") and not os.environ.get("TEST_POSTGRES_BIN"):
        raise RuntimeError(
            "Full backend tests require TEST_DATABASE_URL (loopback PostgreSQL) or "
            "TEST_POSTGRES_BIN (initdb/pg_ctl). See docs/setup-windows.md or docs/setup-linux.md."
        )


def _dotenv_values() -> dict[str, str]:
    values: dict[str, str] = {}
    if not ENV_FILE.is_file():
        return values
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[key.strip()] = value
    return values


def _setting(values: dict[str, str], name: str, default: str = "") -> str:
    return os.environ.get(name) or values.get(name) or default


def assert_local_database() -> None:
    try:
        values = _dotenv_values()
        environment = _setting(values, "APP_ENVIRONMENT", "development")
        database_url = _setting(
            values,
            "DATABASE_URL",
            "postgresql+psycopg://freight_local:local_demo_only@127.0.0.1:5432/freight_local",
        )
        parsed = urlsplit(database_url)
    except Exception:
        raise RuntimeError("DATABASE_URL is invalid; database operation was not started.") from None
    if (
        environment == "production"
        or parsed.scheme not in {"postgresql", "postgresql+psycopg"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1", "db"}
    ):
        raise RuntimeError(
            "Refusing migration/seed: configure an owned loopback PostgreSQL database."
        )


def env_check() -> None:
    values = _dotenv_values()
    environment = _setting(values, "APP_ENVIRONMENT", "development")
    if environment not in {"development", "test", "production"}:
        raise RuntimeError("APP_ENVIRONMENT must be development, test or production.")
    local_admin = _setting(values, "LOCAL_ADMIN_KEY")
    if local_admin and len(local_admin) < 32:
        raise RuntimeError("LOCAL_ADMIN_KEY must be empty or at least 32 characters.")
    mode = _setting(values, "FREIGHT_MODE", "mock")
    if mode not in {"mock", "real"}:
        raise RuntimeError("FREIGHT_MODE must be mock or real.")
    base_url = _setting(values, "FREIGHT_BASE_URL")
    api_key = _setting(values, "FREIGHT_API_KEY")
    company = _setting(values, "FREIGHT_COMPANY_ID")
    location = _setting(values, "FREIGHT_LOCATION_ID")
    connection = _setting(values, "FREIGHT_DISPATCH_CONNECTION_ID")
    database_url = _setting(
        values,
        "DATABASE_URL",
        "postgresql+psycopg://freight_local:local_demo_only@127.0.0.1:5432/freight_local",
    )
    try:
        database = urlsplit(database_url)
        _ = database.port
        if database.scheme not in {"postgresql", "postgresql+psycopg"} or database.hostname not in {
            "127.0.0.1",
            "localhost",
            "::1",
            "db",
        }:
            raise ValueError
        for configured_uuid in (company, location, connection):
            if configured_uuid:
                UUID(configured_uuid)
    except ValueError:
        raise RuntimeError(
            "Database URL or freight context is invalid; values were not printed."
        ) from None
    if mode == "real":
        if not base_url or not api_key or not company:
            raise RuntimeError(
                "Real mode requires FREIGHT_BASE_URL, FREIGHT_API_KEY and FREIGHT_COMPANY_ID."
            )
        try:
            parsed = urlsplit(base_url)
            host = parsed.hostname or ""
            _ = parsed.port
            try:
                is_loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
            except ValueError:
                is_loopback = host == "localhost"
            UUID(company)
            if location:
                UUID(location)
            if connection:
                UUID(connection)
            if (
                parsed.scheme not in {"https", "http"}
                or (parsed.scheme == "http" and not is_loopback)
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
                or "/api/v1/freight" in unquote(parsed.path)
                or api_key in unquote(base_url)
                or any(character.isspace() for character in base_url)
            ):
                raise ValueError
        except ValueError:
            raise RuntimeError(
                "Real freight URL/context is invalid; values were not printed."
            ) from None
    webhook_secret = _setting(values, "PACKSENVIOS_WEBHOOK_SECRET")
    webhook_format = _setting(values, "PACKSENVIOS_WEBHOOK_TIMESTAMP_FORMAT")
    if webhook_format and webhook_format != "unix_seconds":
        raise RuntimeError(
            "Unsupported local webhook timestamp parser; no provider format is inferred."
        )
    if webhook_secret and webhook_secret == api_key:
        raise RuntimeError("Webhook signing secret must be separate from FREIGHT_API_KEY.")
    if webhook_secret and not company:
        raise RuntimeError("A configured webhook receiver requires FREIGHT_COMPANY_ID.")
    sensitive_names = ("API_KEY", "BEARER", "TOKEN", "WEBHOOK_SECRET", "PASSWORD")
    exposed = [
        key
        for key in set(values) | set(os.environ)
        if key.startswith("VITE_")
        and any(sensitive in key.upper() for sensitive in sensitive_names)
    ]
    if exposed:
        raise RuntimeError(
            "Sensitive-looking VITE_* setting(s) are forbidden: " + ", ".join(sorted(exposed))
        )
    if environment == "production" and local_admin:
        print("WARNING: local admin endpoints are disabled in production regardless of the key.")
    if mode == "real":
        print("Real freight configuration is present; no credential values were printed or tested.")
    else:
        print("PASS: freight mode is mock; provider adapter is synthetic/offline.")
    if webhook_secret and not webhook_format:
        print("WARNING: webhook receiver remains disabled until timestamp format is confirmed.")
    print("PASS: application environment parsed; secrets and values were not printed.")


def backend_check() -> None:
    test_database_configured()
    run(poetry("check", "--lock"), cwd=BACKEND)
    run(poetry("run", "ruff", "check", "."), cwd=BACKEND)
    run(poetry("run", "ruff", "format", "--check", "."), cwd=BACKEND)
    run(poetry("run", "ruff", "check", str(ROOT / "tests")), cwd=BACKEND)
    run(poetry("run", "ruff", "format", "--check", str(ROOT / "tests")), cwd=BACKEND)
    run(poetry("run", "testrunner"), cwd=BACKEND)
    run(poetry("run", "python", str(ROOT / "tests" / "validate_contract_matrix.py")), cwd=BACKEND)


def frontend_check() -> None:
    for script in ("lint", "format:check", "test", "build"):
        run(npm("run", script), cwd=FRONTEND)


def full_check() -> None:
    env_check()
    backend_check()
    frontend_check()


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def browser_environment() -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault(
        "PLAYWRIGHT_BROWSER_CHANNEL", "msedge" if sys.platform == "win32" else "chromium"
    )
    return env


def smoke() -> None:
    run(poetry("run", "python", str(ROOT / "tests" / "smoke_local.py")), cwd=BACKEND)


def http_get(url: str, *, timeout: float = 3.0) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return response.status, response.read()
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(f"Local smoke endpoint failed: {urlparse_safe(url)}") from error


def urlparse_safe(url: str) -> str:
    # Smoke URLs contain only loopback hosts and ephemeral ports; omit query/userinfo regardless.
    from urllib.parse import urlsplit

    parsed = urlsplit(url)
    return f"{parsed.scheme}://{parsed.hostname}:{parsed.port}{parsed.path}"


def compose_smoke() -> None:
    project = f"freight-smoke-{os.getpid()}".lower()
    env = os.environ.copy()
    env["COMPOSE_PROJECT_NAME"] = project
    env["POSTGRES_PORT"] = str(free_port())
    env["BACKEND_PORT"] = str(free_port())
    env["FRONTEND_PORT"] = str(free_port())
    while len({env["POSTGRES_PORT"], env["BACKEND_PORT"], env["FRONTEND_PORT"]}) != 3:
        env["FRONTEND_PORT"] = str(free_port())
    backend_port = env["BACKEND_PORT"]
    frontend_port = env["FRONTEND_PORT"]
    try:
        run(compose("up", "--build", "--detach", "--wait"), env=env)
        api = f"http://127.0.0.1:{backend_port}"
        front = f"http://127.0.0.1:{frontend_port}"
        status, _ = http_get(f"{api}/api/health")
        if status != 200:
            raise RuntimeError("Compose backend health endpoint did not return 200")
        status, body = http_get(f"{front}/api/diagnostics")
        if status != 200 or b'"postgresql"' not in body:
            raise RuntimeError("Compose frontend proxy/diagnostics check failed")
        print(
            """PASS: isolated Compose DB/backend/frontend, health and proxy; 
            external API not queried."""
        )
    finally:
        # This project name is unique to this invocation; its named volume is owned by this smoke.
        run(compose("down", "--volumes", "--remove-orphans"), env=env, check=False)


def compose_test() -> None:
    env = os.environ.copy()
    env["COMPOSE_PROJECT_NAME"] = f"freight-tests-{os.getpid()}".lower()
    env["POSTGRES_PORT"] = str(free_port())
    try:
        run(
            compose(
                "--profile",
                "test",
                "up",
                "--build",
                "--abort-on-container-exit",
                "--exit-code-from",
                "backend-test",
                "backend-test",
            ),
            env=env,
        )
    finally:
        run(
            compose("--profile", "test", "down", "--volumes", "--remove-orphans"),
            env=env,
            check=False,
        )


def doctor() -> None:
    print(f"Project root: {ROOT}")
    print(f"Operating system: {platform.platform()}")
    versions = {
        "python": [sys.executable, "--version"],
        "poetry": ["poetry", "--version"],
        "jsr-testrunner": ["poetry", "run", "testrunner", "--version"],
        "node": ["node", "--version"],
        "npm": ["npm", "--version"],
        "docker": ["docker", "--version"],
        "docker-compose": ["docker", "compose", "version"],
    }
    for name, command in versions.items():
        executable = command[0] if Path(command[0]).is_file() else shutil.which(command[0])
        if executable is None:
            print(f"{name}: missing")
            continue
        try:
            result = subprocess.run(
                [executable, *command[1:]],
                cwd=BACKEND if name == "jsr-testrunner" else ROOT,
                shell=False,
                capture_output=True,
                text=True,
                check=False,
            )
            output = (result.stdout or result.stderr).strip().splitlines()
            print(f"{name}: {output[0] if output else 'unavailable'}")
        except (OSError, IndexError):
            print(f"{name}: unavailable")
    if shutil.which("docker"):
        result = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            cwd=ROOT,
            shell=False,
            capture_output=True,
            text=True,
            check=False,
        )
        print(f"Docker daemon: {'available' if result.returncode == 0 else 'unavailable'}")


def clean() -> None:
    generated = (
        BACKEND / ".testrunner_cache",
        BACKEND / ".ruff_cache",
        ROOT / ".testrunner_cache",
        ROOT / ".ruff_cache",
        FRONTEND / "dist",
        FRONTEND / "coverage",
        FRONTEND / "test-results",
        FRONTEND / "playwright-report",
    )
    for path in generated:
        if path.is_symlink():
            path.unlink()
            print(f"Removed generated symlink: {path.relative_to(ROOT)}")
        elif path.is_dir():
            shutil.rmtree(path)
            print(f"Removed generated artifact: {path.relative_to(ROOT)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "task", help="setup, up, down, migrate, seed, test, lint, build, smoke, check, …"
    )
    args = parser.parse_args()
    task = normalized_task(args.task)
    tasks = {
        "setup": lambda: (
            ensure_env_file(),
            run(poetry("sync"), cwd=BACKEND),
            run(npm("ci"), cwd=FRONTEND),
            env_check(),
        ),
        "env-check": env_check,
        "doctor": doctor,
        "up": lambda: run(compose("up", "--build", "--detach", "--wait")),
        "down": lambda: run(compose("down")),
        "compose-check": lambda: run(compose("config", "--quiet")),
        "compose-build": lambda: run(compose("build")),
        "compose-smoke": compose_smoke,
        "compose-test": compose_test,
        "migrate": lambda: (
            assert_local_database(),
            run(poetry("run", "alembic", "upgrade", "head"), cwd=BACKEND),
        ),
        "migration-current": lambda: (
            assert_local_database(),
            run(poetry("run", "alembic", "current"), cwd=BACKEND),
        ),
        "migration-check": lambda: (
            assert_local_database(),
            run(poetry("run", "alembic", "check"), cwd=BACKEND),
        ),
        "seed": lambda: (
            assert_local_database(),
            run(poetry("run", "python", "-m", "freight_ecommerce.catalog.seed"), cwd=BACKEND),
        ),
        "backend": lambda: run(
            poetry(
                "run",
                "python",
                "-m",
                "uvicorn",
                "freight_ecommerce.main:create_app",
                "--factory",
                "--reload",
                "--host",
                "127.0.0.1",
                "--port",
                "8000",
            ),
            cwd=BACKEND,
        ),
        "frontend": lambda: run(npm("run", "dev"), cwd=FRONTEND),
        "backend-test": lambda: (
            test_database_configured(),
            run(poetry("run", "testrunner"), cwd=BACKEND),
        ),
        "frontend-test": lambda: run(npm("run", "test"), cwd=FRONTEND),
        "test": lambda: (
            test_database_configured(),
            run(poetry("run", "testrunner"), cwd=BACKEND),
            run(npm("run", "test"), cwd=FRONTEND),
        ),
        "backend-check": backend_check,
        "frontend-check": frontend_check,
        "lint": lambda: (
            run(poetry("run", "ruff", "check", "."), cwd=BACKEND),
            run(npm("run", "lint"), cwd=FRONTEND),
        ),
        "format": lambda: (
            run(poetry("run", "ruff", "format", "."), cwd=BACKEND),
            run(npm("run", "format"), cwd=FRONTEND),
        ),
        "build": lambda: run(npm("run", "build"), cwd=FRONTEND),
        "smoke": smoke,
        "layout": lambda: run(npm("run", "test:layout"), cwd=FRONTEND, env=browser_environment()),
        "persistence-check": lambda: (
            test_database_configured(),
            run(poetry("run", "testrunner", "-m", "postgres"), cwd=BACKEND),
        ),
        "contract": lambda: run(
            [sys.executable, str(ROOT / "tests" / "validate_contract_matrix.py")]
        ),
        "check": full_check,
        "clean": clean,
    }
    if task not in tasks:
        parser.error(f"Unknown task: {args.task}")
    try:
        result = tasks[task]()
        return int(result) if isinstance(result, int) else 0
    except RuntimeError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
