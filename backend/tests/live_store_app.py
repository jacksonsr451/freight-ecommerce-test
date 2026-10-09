"""Owned test-schema server entrypoint; never migrate or access a non-loopback database."""

import os
import re

from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from freight_ecommerce.config import Settings
from freight_ecommerce.main import create_app as create_store


def create_app():
    url = make_url(os.environ["TEST_DATABASE_URL"])
    schema = os.environ["TEST_STORE_SCHEMA"]
    if url.host not in {"127.0.0.1", "localhost", "::1"} or not re.fullmatch(
        r"freight_test_[0-9a-f]{32}", schema
    ):
        raise RuntimeError("Live browser server requires an owned local test schema")
    engine = create_engine(
        url, connect_args={"options": f"-c search_path={schema} -c timezone=UTC"}
    )
    return create_store(Settings(_env_file=None, environment="test"), engine=engine)
