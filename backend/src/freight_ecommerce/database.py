from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from freight_ecommerce.config import Settings


def build_engine(settings: Settings | None = None) -> Engine:
    settings = settings if settings is not None else Settings()
    url = make_url(settings.database_url.get_secret_value())
    if url.get_backend_name() != "postgresql":
        raise ValueError("This project requires PostgreSQL")
    return create_engine(url, pool_pre_ping=True, connect_args={"options": "-c timezone=UTC"})


@contextmanager
def transaction(engine: Engine) -> Iterator[Session]:
    """Commit atomically or roll back; no schema creation and no implicit external calls."""
    with Session(engine, expire_on_commit=False) as session, session.begin():
        yield session
