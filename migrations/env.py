"""
Alembic environment configuration.

Connects Alembic to the application's SQLAlchemy models and settings,
enabling autogenerate support for `alembic revision --autogenerate`.

All model modules MUST be imported here so that Alembic can discover
the table definitions registered on Base.metadata.
"""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# Import application settings
from app.core.config import settings

# Import Base (contains all model metadata)
from app.core.database import Base

# Import ALL models so Alembic can discover their tables
# (Do NOT remove any import — each one registers tables on Base.metadata)
import app.modules.users.models      # noqa: F401 — Role, User
import app.modules.auth.models       # noqa: F401 — RefreshToken, AuditLog
import app.modules.patients.models   # noqa: F401 — Patient
import app.modules.sessions.models   # noqa: F401 — Session
import app.modules.biometric.models  # noqa: F401 — EmotionalSnapshot, MicroexpressionEvent, BiometricAnalysisJob
import app.modules.alerts.models     # noqa: F401 — Alert

# ---------------------------------------------------------------------------
# Alembic Config object
# ---------------------------------------------------------------------------
config = context.config

# Inject the SYNC database URL from application settings (psycopg2 driver)
config.set_main_option("sqlalchemy.url", settings.SYNC_DATABASE_URL)

# Configure Python logging from alembic.ini if present
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Target metadata for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in offline mode (no live DB connection required).

    This configures the context with just a URL, without creating an engine.
    Useful for generating SQL scripts to review before applying.
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in online mode (establishes a real DB connection).

    Creates a synchronous engine and connection, then executes pending
    migration scripts against the database.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
