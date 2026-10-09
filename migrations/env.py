import os

from alembic import context
from sqlalchemy import create_engine

from leroy.db import Base

engine = create_engine(os.environ["LEROY_DATABASE_URL"])
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata)
    with context.begin_transaction():
        context.run_migrations()
