import argparse
import getpass
import importlib.util
import json
import os
from pathlib import Path

import httpx

from .schema import Pipeline


def main():
    parser = argparse.ArgumentParser(description="Leroy pipelines and local account administration")
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("validate", "publish"):
        definition = commands.add_parser(command)
        definition.add_argument("file", type=Path)
        definition.add_argument("--url", default="http://127.0.0.1:8088")
    users = commands.add_parser("user", help="Run inside the controller as a trusted host administrator")
    users.add_argument("action", choices=["list", "add", "password", "role", "delete"])
    users.add_argument("name", nargs="?")
    users.add_argument("--role", choices=["viewer", "operator", "admin"])
    args = parser.parse_args()
    if args.command == "user":
        from sqlalchemy import select

        from .accounts import manage_account
        from .config import Settings
        from .db import User, connect

        engine, sessions = connect(Settings.load().database_url)
        try:
            if args.action == "list":
                with sessions() as db:
                    for name, role in db.execute(select(User.name, User.role).order_by(User.name)):
                        print(name, role, sep="\t")
            else:
                password = None
                if args.action in ("add", "password"):
                    password = getpass.getpass("New password (minimum 16 characters): ")
                    if password != getpass.getpass("Repeat password: "):
                        parser.error("Passwords do not match")
                manage_account(sessions, args.action, args.name, role=args.role, password=password)
                print("Account updated; existing sessions revoked where applicable")
        except ValueError as exc:
            parser.error(str(exc))
        finally:
            engine.dispose()
        return
    spec = importlib.util.spec_from_file_location("local_pipeline", args.file)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    pipeline = Pipeline.model_validate(module.pipeline)
    if args.command == "validate":
        print(json.dumps(pipeline.model_dump(), indent=2))
        return
    with httpx.Client(base_url=args.url, headers={"X-Leroy-Request": "1"}) as client:
        response = client.post(
            "/api/auth/login",
            json={"username": os.getenv("LEROY_USER", "admin"), "password": os.environ["LEROY_PASSWORD"]},
        )
        response.raise_for_status()
        response = client.put("/api/pipelines/" + pipeline.id, json=pipeline.model_dump())
        response.raise_for_status()
        print("Published", pipeline.id)
