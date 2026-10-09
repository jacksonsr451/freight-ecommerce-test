import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from freight_ecommerce.catalog.seed import seed_demo_catalog
from freight_ecommerce.database import transaction
from freight_ecommerce.domain.models import CartItem, Inventory

ROOT = Path(__file__).resolve().parents[2]
pytestmark = [pytest.mark.postgres, pytest.mark.browser]


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for(url, processes):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if any(process.poll() is not None for process in processes):
            raise RuntimeError("Local browser test server exited")
        try:
            with urlopen(url, timeout=2):
                return
        except (URLError, TimeoutError):
            time.sleep(0.2)
    raise RuntimeError("Local browser test server did not become ready")


def test_store_journey_in_real_browser_uses_real_api_and_postgres(db_engine, tmp_path):
    node = shutil.which("node")
    edge = Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
    if (
        not node
        or not edge.is_file()
        or not (ROOT / "frontend/node_modules/@playwright/test").is_dir()
    ):
        pytest.skip("Live store test requires Node, frontend dependencies and local Edge")
    with transaction(db_engine) as session:
        seed_demo_catalog(session)
    with db_engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    api_port, ui_port = free_port(), free_port()
    while ui_port == api_port:
        ui_port = free_port()
    api_url = f"http://127.0.0.1:{api_port}"
    env = {
        **os.environ,
        "TEST_DATABASE_URL": db_engine.url.render_as_string(hide_password=False),
        "TEST_STORE_SCHEMA": schema,
        "APP_ENVIRONMENT": "test",
        "FREIGHT_MODE": "mock",
        "FREIGHT_BASE_URL": "https://store.mock.invalid",
        "FREIGHT_API_KEY": "synthetic-test-key",
        "FREIGHT_COMPANY_ID": "00000000-0000-4000-8000-000000000002",
        "VITE_PROXY_TARGET": api_url,
        "LIVE_STORE_URL": f"http://127.0.0.1:{ui_port}",
        "LIVE_STORE_SCREENSHOT": str(tmp_path / "cart-live-mobile.png"),
    }
    processes = []
    with (tmp_path / "servers.log").open("wb") as log:
        try:
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "live_store_app:create_app",
                        "--factory",
                        "--app-dir",
                        str(ROOT / "backend/tests"),
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(api_port),
                    ],
                    cwd=ROOT / "backend",
                    env=env,
                    stdout=log,
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
                        str(ui_port),
                        "--strictPort",
                    ],
                    cwd=ROOT / "frontend",
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                )
            )
            wait_for(f"{api_url}/api/health", processes)
            wait_for(env["LIVE_STORE_URL"], processes)
            result = subprocess.run(
                [node, str(ROOT / "frontend/tests/live-store.mjs")],
                cwd=ROOT / "frontend",
                env=env,
                capture_output=True,
                text=True,
                timeout=60,
            )
            assert result.returncode == 0, result.stdout + result.stderr
            assert "PASS" in result.stdout
            with Session(db_engine) as session:
                assert session.scalar(select(func.count()).select_from(CartItem)) == 0
                assert all(stock.reserved == 0 for stock in session.scalars(select(Inventory)))
        finally:
            for process in reversed(processes):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
