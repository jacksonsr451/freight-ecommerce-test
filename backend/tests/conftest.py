import os
import socket
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolate_freight_test_environment(request, monkeypatch):
    if request.module.__name__.startswith("test_freight_"):
        for name in tuple(os.environ):
            if name.startswith("FREIGHT_"):
                monkeypatch.delenv(name)


def run_postgres_command(arguments, root):
    # File output prevents inherited child pipe handles from blocking communicate() on Windows.
    log = root / "controller.log"
    with log.open("ab") as output:
        try:
            subprocess.run(
                arguments, check=True, timeout=60, stdout=output, stderr=subprocess.STDOUT
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise RuntimeError(log.read_text(encoding="utf-8", errors="replace")) from error


def migration_config(connection=None, schema=None):
    config = Config(str(BACKEND / "alembic.ini"))
    if connection is not None:
        config.attributes["connection"] = connection
    if schema is not None:
        config.attributes["version_table_schema"] = schema
    return config


@pytest.fixture(scope="session")
def postgres_url(tmp_path_factory):
    configured = os.environ.get("TEST_DATABASE_URL")
    if configured:
        url = make_url(configured)
        if url.get_backend_name() != "postgresql" or url.host not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            pytest.fail("Persistence tests require an explicit loopback PostgreSQL URL")
        yield url
        return
    binary_dir = os.environ.get("TEST_POSTGRES_BIN")
    if not binary_dir:
        pytest.skip("PostgreSQL integration requires TEST_DATABASE_URL or TEST_POSTGRES_BIN")
    binary = Path(binary_dir)
    suffix = ".exe" if os.name == "nt" else ""
    initdb = binary / f"initdb{suffix}"
    pg_ctl = binary / f"pg_ctl{suffix}"
    if not initdb.is_file() or not pg_ctl.is_file():
        pytest.fail("TEST_POSTGRES_BIN must contain initdb and pg_ctl")
    root = tmp_path_factory.mktemp("private-postgres")
    data = root / "data"
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    run_postgres_command(
        [
            str(initdb),
            "-D",
            str(data),
            "-U",
            "postgres",
            "--auth=trust",
            "--encoding=UTF8",
            "--locale=C",
        ],
        root,
    )
    run_postgres_command(
        [
            str(pg_ctl),
            "-D",
            str(data),
            "-l",
            str(root / "postgres.log"),
            "-o",
            f"-p {port} -h 127.0.0.1 -c timezone=UTC",
            "-w",
            "start",
        ],
        root,
    )
    try:
        yield make_url(f"postgresql+psycopg://postgres@127.0.0.1:{port}/postgres")
    finally:
        run_postgres_command(
            [str(pg_ctl), "-D", str(data), "-m", "fast", "-w", "stop"],
            root,
        )


@pytest.fixture
def db_engine(postgres_url):
    """Only create/drop an owned random schema; never migrate public or another app's schema."""
    schema = f"freight_test_{uuid4().hex}"
    admin = create_engine(postgres_url)
    with admin.begin() as connection:
        connection.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
    engine = create_engine(
        postgres_url, connect_args={"options": f"-c search_path={schema} -c timezone=UTC"}
    )
    try:
        with engine.connect() as connection:
            command.upgrade(migration_config(connection, schema), "head")
            connection.commit()
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as connection:
            connection.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        admin.dispose()


@pytest.fixture
def session(db_engine):
    with Session(db_engine, expire_on_commit=False) as session:
        yield session


@pytest.fixture
def alembic_config():
    return migration_config
