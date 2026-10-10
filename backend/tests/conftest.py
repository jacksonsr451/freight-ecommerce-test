import inspect
import os
import socket
import subprocess
from pathlib import Path
from uuid import uuid4

import testrunner
from _testrunner_support import async_test_loop  # noqa: F401 - registers shared loop fixture
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

BACKEND = Path(__file__).resolve().parents[1]


@testrunner.fixture(autouse=True)
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


@testrunner.fixture(scope="session")
def postgres_url(tmp_path_factory):
    configured = os.environ.get("TEST_DATABASE_URL")
    if configured:
        url = make_url(configured)
        allowed_hosts = {
            "127.0.0.1",
            "localhost",
            "::1",
        }
        if os.environ.get("TESTRUNNER_DOCKER") == "1":
            allowed_hosts.add("db")
        if url.get_backend_name() != "postgresql" or url.host not in allowed_hosts:
            testrunner.fail("Persistence tests require an explicit loopback PostgreSQL URL")
        yield url
        return
    binary_dir = os.environ.get("TEST_POSTGRES_BIN")
    if not binary_dir:
        testrunner.skip("PostgreSQL integration requires TEST_DATABASE_URL or TEST_POSTGRES_BIN")
    binary = Path(binary_dir)
    suffix = ".exe" if os.name == "nt" else ""
    initdb = binary / f"initdb{suffix}"
    pg_ctl = binary / f"pg_ctl{suffix}"
    if not initdb.is_file() or not pg_ctl.is_file():
        testrunner.fail("TEST_POSTGRES_BIN must contain initdb and pg_ctl")
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


@testrunner.fixture
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


@testrunner.fixture
def session(db_engine):
    with Session(db_engine, expire_on_commit=False) as session:
        yield session


@testrunner.fixture
def alembic_config():
    return migration_config


@testrunner.hookimpl(tryfirst=True)
def testrunner_pyfunc_call(pyfuncitem):
    """Run coroutine tests on the same loop used by adapted async fixtures."""
    function = pyfuncitem.obj
    if not inspect.iscoroutinefunction(function):
        return None
    loop = pyfuncitem.funcargs["async_test_loop"]
    arguments = {
        name: pyfuncitem.funcargs[name]
        for name in inspect.signature(function).parameters
        if name in pyfuncitem.funcargs
    }
    loop.run_until_complete(function(**arguments))
    return True
