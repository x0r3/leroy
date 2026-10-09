import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


def secret(name):
    filename = os.getenv(name + "_FILE")
    return Path(filename).read_text().strip() if filename else os.environ.get(name, "")


@dataclass
class Settings:
    database_url: str
    data: Path
    config: dict
    runner_token: str
    admin_password: str
    origin: str
    cookie_secure: bool

    @classmethod
    def load(cls):
        path = Path(os.environ.get("LEROY_CONFIG", "/config/leroy.toml"))
        config = tomllib.loads(path.read_text()) if path.exists() else {}
        return cls(
            os.environ["LEROY_DATABASE_URL"],
            Path(os.getenv("LEROY_DATA", "/data")),
            config,
            secret("LEROY_RUNNER_TOKEN"),
            secret("LEROY_ADMIN_PASSWORD"),
            os.getenv("LEROY_ORIGIN", "http://127.0.0.1:8088"),
            os.getenv("LEROY_COOKIE_SECURE", "true").lower() == "true",
        )
