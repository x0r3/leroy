#!/usr/bin/env python3
"""Opt-in temporary storage for the owned NAS Antares comparison helpers.

Installed only in the isolated comparison Jenkins and Antares worker profile.
PostgreSQL keeps its disk volume: the complete suite exceeds 1 GiB of data/WAL.
The application checkout, Jenkinsfile and test commands remain untouched.
Other images/commands pass through to the real Docker CLI unchanged.
"""

import os
import re
import sys

POSTGRES = "postgres:18.4-alpine3.24"
BROWSER = "mcr.microsoft.com/playwright:v1.61.1-noble"


def option(args, name):
    for index, arg in enumerate(args):
        if arg == name:
            if index + 1 >= len(args):
                raise ValueError("Missing Docker option value")
            return args[index + 1]
        if arg.startswith(name + "="):
            return arg[len(name) + 1:]
    return None


def temporary_storage(args, enabled):
    if not enabled or not args or args[0] != "run":
        return args, None
    if BROWSER in args:
        position = args.index(BROWSER)
        flags = args[1:position]
        if args[position + 1:] != ["node", "node_modules/playwright/cli.js", "test"]:
            return args, None
        parent = option(flags, "--volumes-from") or ""
        label = option(flags, "--label") or ""
        owned_jenkins = parent == "29e75d9173c9" or parent == "29e75d9173c95db4f448ac038f2593e1f556e7eb2bf49bde68cba911526f3226"
        owned_leroy = re.fullmatch(r"io\.leroy\.run=[a-f0-9]{32}", label) and re.fullmatch(r"[a-f0-9]{12,64}", parent)
        if not (owned_jenkins or owned_leroy):
            return args, None
        mount = "/tmp:rw,nosuid,nodev,size=1g"
    else:
        return args, None
    if any(value == "--tmpfs" or value.startswith("--tmpfs=") for value in flags):
        raise ValueError("Temporary storage was already specified; inspect the comparison configuration")
    return ["run", "--tmpfs", mount, *args[1:]], mount


def main():
    mode = os.environ.get("LEROY_NAS_ANTARES_TMPFS", "")
    if mode not in ("", "1"):
        raise ValueError("Invalid isolated Antares temporary storage mode")
    args, mount = temporary_storage(sys.argv[1:], mode == "1")
    if mount:
        print("Isolated Antares temporary storage: " + mount, file=sys.stderr, flush=True)
    os.execv("/usr/bin/docker", ["/usr/bin/docker", *args])


if __name__ == "__main__":
    main()
