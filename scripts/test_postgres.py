"""Run database tests only against the dedicated local test-stack port."""

import os
import subprocess
import sys
from pathlib import Path

password = Path(".local/db_password").read_text().strip()
environment = {
    **os.environ,
    "LEROY_TEST_DATABASE_URL": f"postgresql+psycopg://leroy:{password}@127.0.0.1:55439/leroy",
}
raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "tests", "-q"], env=environment))
