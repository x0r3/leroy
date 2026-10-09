"""Frozen initial durable execution schema."""

from alembic import op

revision = "0001"
down_revision = None


def upgrade():
    op.execute("CREATE SEQUENCE run_number_seq")
    op.execute(
        "\nCREATE TABLE pipelines (\n\tid VARCHAR(100) NOT NULL, \n\tspec JSONB NOT NULL, \n\trevision INTEGER NOT NULL, \n\tenabled BOOLEAN NOT NULL, \n\tlast_revision VARCHAR(64), \n\tnext_trigger TIMESTAMP WITH TIME ZONE, \n\tupdated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE users (\n\tname VARCHAR(100) NOT NULL, \n\tpassword_hash TEXT NOT NULL, \n\trole VARCHAR(20) NOT NULL, \n\tPRIMARY KEY (name)\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE runners (\n\tid VARCHAR(100) NOT NULL, \n\tprofiles JSONB NOT NULL, \n\tlast_seen TIMESTAMP WITH TIME ZONE NOT NULL, \n\tcapacity INTEGER NOT NULL, \n\tPRIMARY KEY (id)\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE runs (\n\tid VARCHAR(32) NOT NULL, \n\tnumber BIGINT DEFAULT nextval('run_number_seq') NOT NULL, \n\tpipeline_id VARCHAR(100) NOT NULL, \n\tsnapshot JSONB NOT NULL, \n\tparameters JSONB NOT NULL, \n\tstatus VARCHAR(24) NOT NULL, \n\ttrigger VARCHAR(120) NOT NULL, \n\tactor VARCHAR(100) NOT NULL, \n\tparent_id VARCHAR(32), \n\tretry_of VARCHAR(32), \n\tcommit VARCHAR(64), \n\timage_digest VARCHAR(100), \n\trunner VARCHAR(100), \n\ttoken_hash VARCHAR(64), \n\tlease_until TIMESTAMP WITH TIME ZONE, \n\tcancel_requested BOOLEAN NOT NULL, \n\tresource VARCHAR(200), \n\treason TEXT NOT NULL, \n\toutputs JSONB NOT NULL, \n\tdedupe_key VARCHAR(200), \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tstarted_at TIMESTAMP WITH TIME ZONE, \n\tfinished_at TIMESTAMP WITH TIME ZONE, \n\tPRIMARY KEY (id), \n\tUNIQUE (number), \n\tFOREIGN KEY(pipeline_id) REFERENCES pipelines (id), \n\tFOREIGN KEY(parent_id) REFERENCES runs (id), \n\tFOREIGN KEY(retry_of) REFERENCES runs (id), \n\tUNIQUE (dedupe_key)\n)\n\n"
    )
    op.execute("CREATE INDEX ix_runs_created_at ON runs (created_at)")
    op.execute("CREATE INDEX ix_runs_lease_until ON runs (lease_until)")
    op.execute("CREATE INDEX ix_runs_status ON runs (status)")
    op.execute("CREATE INDEX ix_runs_parent_id ON runs (parent_id)")
    op.execute("CREATE INDEX ix_runs_pipeline_id ON runs (pipeline_id)")
    op.execute("CREATE INDEX ix_runs_resource ON runs (resource)")
    op.execute(
        '\nCREATE TABLE sessions (\n\tid VARCHAR(64) NOT NULL, \n\t"user" VARCHAR(100) NOT NULL, \n\texpires TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY("user") REFERENCES users (name)\n)\n\n'
    )
    op.execute(
        "\nCREATE TABLE steps (\n\trun_id VARCHAR(32) NOT NULL, \n\tid VARCHAR(100) NOT NULL, \n\tname VARCHAR(200) NOT NULL, \n\tposition INTEGER NOT NULL, \n\tneeds JSONB NOT NULL, \n\tstatus VARCHAR(24) NOT NULL, \n\treason TEXT NOT NULL, \n\texit_code INTEGER, \n\toutputs JSONB NOT NULL, \n\tstarted_at TIMESTAMP WITH TIME ZONE, \n\tfinished_at TIMESTAMP WITH TIME ZONE, \n\tlog_bytes BIGINT NOT NULL, \n\tPRIMARY KEY (run_id, id), \n\tFOREIGN KEY(run_id) REFERENCES runs (id) ON DELETE CASCADE\n)\n\n"
    )
    op.execute(
        "\nCREATE TABLE events (\n\tid BIGSERIAL NOT NULL, \n\trun_id VARCHAR(32), \n\tstep_id VARCHAR(100), \n\tkind VARCHAR(50) NOT NULL, \n\tdata JSONB NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(run_id) REFERENCES runs (id) ON DELETE CASCADE\n)\n\n"
    )
    op.execute("CREATE INDEX events_run_cursor ON events (run_id, id)")
    op.execute("CREATE INDEX ix_events_run_id ON events (run_id)")
    op.execute(
        "\nCREATE TABLE artifacts (\n\tid VARCHAR(32) NOT NULL, \n\trun_id VARCHAR(32) NOT NULL, \n\tstep_id VARCHAR(100) NOT NULL, \n\tname VARCHAR(400) NOT NULL, \n\tsha256 VARCHAR(64) NOT NULL, \n\tsize BIGINT NOT NULL, \n\tcreated_at TIMESTAMP WITH TIME ZONE NOT NULL, \n\tPRIMARY KEY (id), \n\tFOREIGN KEY(run_id) REFERENCES runs (id) ON DELETE CASCADE\n)\n\n"
    )
    op.execute("CREATE INDEX ix_artifacts_run_id ON artifacts (run_id)")


def downgrade():
    op.execute("DROP TABLE steps")
    op.execute("DROP TABLE events")
    op.execute("DROP TABLE artifacts")
    op.execute("DROP TABLE sessions")
    op.execute("DROP TABLE runs")
    op.execute("DROP TABLE users")
    op.execute("DROP TABLE runners")
    op.execute("DROP TABLE pipelines")
    op.execute("DROP SEQUENCE run_number_seq")
