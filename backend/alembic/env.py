from logging.config import fileConfig

from sqlalchemy import create_engine, pool

from alembic import context
from database.connection import DATABASE_URL, Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Make the models importable so metadata is complete for autogenerate.
import models  # noqa: F401

config.set_main_option("sqlalchemy.url", DATABASE_URL)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # sqlite only: use the stdlib sqlite3 driver (the app's async engine can't be
    # driven by alembic's sync interface).
    url = DATABASE_URL.replace("+aiosqlite", "")
    connectable = create_engine(url, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
