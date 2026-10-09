"""Temporary Git authentication without credentials in URLs or process arguments."""

import os
import shlex
import tempfile
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def git_environment(values=None):
    values = values or os.environ
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    with tempfile.TemporaryDirectory(prefix="leroy-git-") as directory:
        if values.get("GIT_PASSWORD"):
            askpass = Path(directory) / "askpass"
            askpass.write_text(
                '#!/bin/sh\ncase "$1" in *sername*) printf "%s" "$GIT_USER";; *) printf "%s" "$GIT_PASSWORD";; esac\n',
                encoding="utf-8",
            )
            askpass.chmod(0o700)
            env.update(
                GIT_ASKPASS=str(askpass),
                GIT_USER=values.get("GIT_USER", "git"),
                GIT_PASSWORD=values["GIT_PASSWORD"],
            )
        if values.get("GIT_SSH_KEY_FILE"):
            known = values.get("GIT_KNOWN_HOSTS")
            if not known:
                raise ValueError("Git SSH authentication requires pinned known hosts")
            env["GIT_SSH_COMMAND"] = (
                "ssh -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile="
                + shlex.quote(known)
                + " -i "
                + shlex.quote(values["GIT_SSH_KEY_FILE"])
            )
        yield env
