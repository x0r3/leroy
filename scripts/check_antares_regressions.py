"""Exercise the upstream repair candidate against an owned disposable database."""

import subprocess
import sys
import time
import uuid

from test_support import DIN, ROOT, inner

sys.stdout.reconfigure(encoding="utf-8")
name = "leroy-antares-check-" + uuid.uuid4().hex[:8]
files = [
    "src/server/admin/routes.ts",
    "src/server/game/routes.ts",
    "apps/shared/CombatLiveArena.tsx",
    "apps/shared/__tests__/combat-live-arena.test.tsx",
    "tests/integration/maintenance-readers.test.ts",
]
try:
    inner(
        "run",
        "-d",
        "--name",
        name,
        "--network",
        "leroy-jobs",
        "-e",
        "POSTGRES_DB=antares_test",
        "-e",
        "POSTGRES_USER=antares",
        "-e",
        "POSTGRES_PASSWORD=antares-test-password",
        "postgres:17-alpine",
    )
    for _ in range(30):
        try:
            inner("exec", name, "pg_isready", "-U", "antares", "-d", "antares_test")
            break
        except RuntimeError:
            time.sleep(1)
    else:
        raise TimeoutError("Disposable PostgreSQL did not start")
    commands = [f"cp /validation/{path} {path}" for path in files]
    commands += [
        "npm run lint",
        "npm run typecheck",
        "node node_modules/vitest/vitest.mjs run apps/shared/__tests__/combat-live-arena.test.tsx",
        "node node_modules/vitest/vitest.mjs run --config vitest.integration.config.ts tests/integration/maintenance-readers.test.ts",
    ]
    if "--browsers" in sys.argv:
        commands += [
            "npm run build:game",
            "npm run build:admin",
            "node node_modules/playwright/cli.js test --project=admin-chromium tests/e2e/admin-access.spec.ts tests/e2e/admin-live-arena-visual.spec.ts",
        ]
    image = "mcr.microsoft.com/playwright:v1.61.1-noble" if "--browsers" in sys.argv else "leroy-job:local"
    with (ROOT / "test-results/antares-focused-check.log").open("w", encoding="utf-8") as stream:
        result = subprocess.run(
            [
                "docker",
                "exec",
                DIN,
                "docker",
                "run",
                "--rm",
                "--init",
                "--ipc=host",
                "--name",
                name + "-runner",
                "--network",
                "leroy-jobs",
                "-v",
                "leroy-antares-profile:/work",
                "-v",
                "/sources/antares-validation:/validation:ro",
                "-w",
                "/work/repo",
                "-e",
                "CI=true",
                "-e",
                "HOME=/tmp",
                "-e",
                f"TEST_DATABASE_URL=postgres://antares:antares-test-password@{name}:5432/antares_test",
                image,
                "sh",
                "-c",
                " && ".join(commands),
            ],
            stdout=stream,
            stderr=subprocess.STDOUT,
        )
    print("Focused Antares checks:", result.returncode, flush=True)
finally:
    inner("rm", "-f", name)
raise SystemExit(result.returncode)
