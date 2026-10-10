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
from freight_ecommerce.domain.models import (
    Cart,
    CartItem,
    CheckoutAttempt,
    FreightOptionSnapshot,
    FreightQuote,
    Fulfillment,
    Inventory,
    Order,
    PaymentSimulation,
    Product,
    StockReservation,
    TrackingEvent,
)
from freight_ecommerce.domain.states import (
    CartStatus,
    FulfillmentStatus,
    OrderStatus,
    PaymentStatus,
)

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


def browser_available(channel: str) -> bool:
    if channel == "msedge":
        if shutil.which("msedge") or shutil.which("msedge.exe"):
            return True
        for variable in ("PROGRAMFILES(X86)", "PROGRAMFILES"):
            root = os.environ.get(variable)
            if root and (Path(root) / "Microsoft/Edge/Application/msedge.exe").is_file():
                return True
        return False
    if channel != "chromium":
        return False
    configured = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if configured and configured != "0":
        roots = [Path(configured)]
    elif configured == "0":
        roots = [ROOT / "frontend/node_modules/playwright-core/.local-browsers"]
    elif os.name == "nt":
        roots = [Path.home() / "AppData/Local/ms-playwright"]
    else:
        roots = [Path.home() / ".cache/ms-playwright"]
    patterns = (
        "chromium-*/chrome-linux/chrome",
        "chromium-*/chrome-linux64/chrome",
        "chromium-*/chrome-win/chrome.exe",
    )
    return any(any(root.glob(pattern)) for root in roots for pattern in patterns)


def test_store_journey_in_real_browser_uses_real_api_and_postgres(db_engine, tmp_path):
    node = shutil.which("node")
    browser_channel = os.environ.get(
        "PLAYWRIGHT_BROWSER_CHANNEL", "msedge" if os.name == "nt" else "chromium"
    )
    if (
        not node
        or not browser_available(browser_channel)
        or not (ROOT / "frontend/node_modules/@playwright/test").is_dir()
    ):
        pytest.skip(
            "Live store requires Node, frontend dependencies and installed browser channel "
            f"{browser_channel}"
        )
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
        "LOCAL_ADMIN_KEY": "synthetic-local-admin-key-for-browser-tests-only",
        "PLAYWRIGHT_BROWSER_CHANNEL": browser_channel,
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
                assert session.scalar(select(func.count()).select_from(CartItem)) == 1
                cart = session.scalar(select(Cart))
                assert cart.buyer_details["email"] == "buyer@example.com"
                assert cart.delivery_address["postal_code"] == "01001000"
                quote = session.scalar(select(FreightQuote))
                assert quote is not None and quote.selected_option_snapshot_id is not None
                option = session.get(FreightOptionSnapshot, quote.selected_option_snapshot_id)
                assert option.manual_only is True and option.demonstration_only is True
                order = session.scalar(select(Order))
                assert order.status == OrderStatus.PAID_SIMULATED and order.simulation is True
                payment = session.scalar(
                    select(PaymentSimulation).where(PaymentSimulation.order_id == order.id)
                )
                assert payment.status == PaymentStatus.APPROVED and payment.simulation is True
                orders = session.scalars(select(Order).order_by(Order.created_at, Order.id)).all()
                assert len(orders) == 1
                fulfilled_order = orders[0]
                assert fulfilled_order.status == OrderStatus.PAID_SIMULATED
                assert all(item.simulation is True for item in orders)
                assert all(
                    session.get(
                        Cart, session.get(CheckoutAttempt, item.checkout_attempt_id).cart_id
                    ).status
                    == CartStatus.CHECKED_OUT
                    for item in orders
                )
                fulfilled_fulfillment = session.scalar(
                    select(Fulfillment).where(Fulfillment.order_id == fulfilled_order.id)
                )
                assert fulfilled_fulfillment.status == FulfillmentStatus.DELIVERED_SIMULATED
                reservations = session.scalars(
                    select(StockReservation).order_by(StockReservation.order_id)
                ).all()
                assert len(reservations) == 1
                assert reservations[0].active and reservations[0].quantity == 2
                assert session.scalar(select(func.count()).select_from(TrackingEvent)) == 7
                book_stock = session.scalar(
                    select(Inventory).join(Product).where(Product.sku == "DEMO-BOOK")
                )
                assert book_stock.reserved == 2
        finally:
            for process in reversed(processes):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
