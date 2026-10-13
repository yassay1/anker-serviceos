from logging.config import fileConfig

from alembic import context

from serviceos_api.persistence.database import build_engine, configured_database_url
from serviceos_api.persistence.models import BUSINESS_SCHEMA, Base

config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)


def include_name(name, type_, parent_names):
    if type_ == "schema":
        return name == BUSINESS_SCHEMA
    return True


options = dict(
    target_metadata=Base.metadata,
    include_schemas=True,
    include_name=include_name,
    compare_type=True,
    compare_server_default=True,
    version_table="serviceos_alembic_version",
)

if context.is_offline_mode():
    context.configure(
        url=config.attributes.get("database_url") or configured_database_url(),
        literal_binds=True, dialect_opts={"paramstyle": "named"}, **options,
    )
    with context.begin_transaction():
        context.run_migrations()
else:
    connection = config.attributes.get("connection")
    if connection is not None:
        context.configure(connection=connection, **options)
        with context.begin_transaction():
            context.run_migrations()
    else:
        engine = build_engine(config.attributes.get("database_url"))
        try:
            with engine.connect() as connection:
                context.configure(connection=connection, **options)
                with context.begin_transaction():
                    context.run_migrations()
        finally:
            engine.dispose()
