"""Durable filesystem cleanup after retention commits."""

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "CREATE TABLE file_deletions (kind VARCHAR(16) NOT NULL, id VARCHAR(32) NOT NULL, PRIMARY KEY (kind, id))"
    )


def downgrade():
    op.execute("DROP TABLE file_deletions")
