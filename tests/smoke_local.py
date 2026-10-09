"""Starts owned local processes, checks HTTP + Vite proxy, then stops them."""

import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def get(url: str, processes: list[subprocess.Popen]) -> str:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if any(process.poll() is not None for process in processes):
            raise RuntimeError("A local service exited during startup")
        try:
            with urlopen(url, timeout=2) as response:
                return response.read().decode("utf-8")
        except (URLError, TimeoutError):
            time.sleep(0.2)
    raise RuntimeError(f"Local service did not become ready: {url}")


def main() -> None:
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node is required; run the Install task first")
    backend_port, frontend_port = free_port(), free_port()
    while frontend_port == backend_port:
        frontend_port = free_port()
    backend_url = f"http://127.0.0.1:{backend_port}"
    frontend_url = f"http://127.0.0.1:{frontend_port}"
    env = {
        **os.environ,
        "APP_ENVIRONMENT": "test",
        "VITE_PROXY_TARGET": backend_url,
        "FREIGHT_MODE": "mock",
        "FREIGHT_BASE_URL": "https://smoke.mock.invalid",
        "FREIGHT_API_KEY": "synthetic-smoke-key",
        "FREIGHT_COMPANY_ID": "00000000-0000-4000-8000-000000000002",
    }
    processes: list[subprocess.Popen] = []
    try:
        processes.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "freight_ecommerce.main:create_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(backend_port),
                ],
                cwd=ROOT / "backend",
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
        )
        processes.append(
            subprocess.Popen(
                [
                    node,
                    str(ROOT / "frontend/node_modules/vite/bin/vite.js"),
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(frontend_port),
                    "--strictPort",
                ],
                cwd=ROOT / "frontend",
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
            )
        )
        expected = {"status": "ok", "service": "freight-ecommerce-test"}
        assert json.loads(get(f"{backend_url}/api/health", processes)) == expected
        assert 'src="/src/main.tsx"' in get(frontend_url, processes)
        assert json.loads(get(f"{frontend_url}/api/health", processes)) == expected
        assert json.loads(get(f"{frontend_url}/api/runtime", processes)) == {
            "freight_mode": "mock",
            "purchases_simulated": True,
        }
        print("PASS: FastAPI HTTP, Vite HTML and local health/runtime proxy")
    finally:
        for process in reversed(processes):
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
