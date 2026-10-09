from alembic import context

from freight_ecommerce.config import Settings
from freight_ecommerce.database import build_engine
from freight_ecommerce.domain import models  # noqa: F401 - register all mapped entities
from freight_ecommerce.domain.base import Base, UTCDateTime

config = context.config


def render_item(type_, object_, autogen_context):
    if type_ == "type" and isinstance(object_, UTCDateTime):
        return "sa.DateTime(timezone=True)"
    return False


def run(connection=None):
    options = {
        "target_metadata": Base.metadata,
        "compare_type": True,
        "render_item": render_item,
        "include_object": lambda object_, name, type_, reflected, compare_to: (
            not (type_ == "table" and name == "alembic_version")
        ),
        "version_table_schema": config.attributes.get("version_table_schema"),
    }
    if context.is_offline_mode():
        context.configure(
            url=Settings().database_url.get_secret_value(),
            literal_binds=True,
            dialect_opts={"paramstyle": "named"},
            **options,
        )
    else:
        context.configure(connection=connection, **options)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run()
elif "connection" in config.attributes:
    run(config.attributes["connection"])
else:
    engine = build_engine()
    try:
        with engine.connect() as connection:
            run(connection)
    finally:
        engine.dispose()
