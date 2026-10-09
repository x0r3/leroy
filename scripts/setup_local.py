"""Generate local credentials and development profiles; never overwrite existing secrets."""

import secrets
from pathlib import Path

root = Path(".local")
root.mkdir(exist_ok=True)


def write_config(name, value):
    path = root / name
    if not path.exists():
        path.write_text(value, encoding="utf-8")


for name in ("admin_password", "db_password", "runner_token"):
    path = root / name
    if not path.exists():
        path.write_text(secrets.token_urlsafe(36))
password = (root / "db_password").read_text().strip()
write_config(
    "controller.env",
    f"LEROY_DATABASE_URL=postgresql+psycopg://leroy:{password}@postgres/leroy\nLEROY_ORIGIN=http://127.0.0.1:8088\nLEROY_COOKIE_SECURE=false\n",
)
config = "demo = true\n"
for name, repo in [
    ("home-lab-ci", "home-lab-service-collection"),
    ("nikicas-hub-ci", "nikicas-hub"),
    ("antares-ci", "antares"),
    ("graphato-ci", "graphato"),
    ("graphato-release-acceptance", "graphato"),
    ("graphato-postdeploy-web", "graphato"),
    ("graphato-postdeploy-quality", "graphato"),
    ("graphato-bootstrap-host", "home-lab-service-collection"),
    ("nikicas-hub-bootstrap-host", "home-lab-service-collection"),
    ("nikicas-hub-deploy", "nikicas-hub"),
    ("paperless-ngx-bootstrap-rules", "home-lab-service-collection"),
    ("music-library-sync-smartphone", "home-lab-service-collection"),
]:
    config += f'\n[pipelines."{name}"]\nrepository = "/sources/{repo}"\nenabled = false\n'
write_config("leroy.toml", config)
write_config(
    "runner.toml",
    'capacity = 2\n[profiles.default]\nimage = "leroy-job:local"\nnetwork = "leroy-jobs"\nmemory = "4g"\ncpus = 2\ndocker = false\n',
)
write_config("runner.test.toml", Path("examples/runner.test.toml").read_text(encoding="utf-8"))
(root / "test-secrets").mkdir(exist_ok=True)
(root / "music").mkdir(exist_ok=True)
(root / "music" / "sample.txt").write_text("Leroy isolated music synchronization fixture\n")
print("Local configuration generated. Administrator password: .local/admin_password (not printed).")
