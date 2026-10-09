"""Reclaim interrupted uploads after their attempt ends."""

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE file_deletions ADD COLUMN upload_run_id VARCHAR(32)")


def downgrade():
    op.execute("ALTER TABLE file_deletions DROP COLUMN upload_run_id")
