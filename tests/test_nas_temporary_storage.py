"""Constrain the optional NAS test policy to actual disposable Antares helpers."""

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "antares_docker", Path(__file__).resolve().parents[1] / "infra/nas/antares-docker.py"
)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)


@pytest.mark.parametrize("name", ["antares-ci-postgres-12", "leroy-antares-" + "a" * 32])
def test_complete_suite_database_keeps_disk_storage(name):
    args = ["run", "--rm", "--name", name, policy.POSTGRES]
    assert policy.temporary_storage(args, True) == (args, None)


@pytest.mark.parametrize("flags", [
    ["--volumes-from", "29e75d9173c9"],
    ["--volumes-from", "b" * 12, "--label", "io.leroy.run=" + "a" * 32],
])
def test_original_browser_command_gets_only_temporary_profiles(flags):
    args = ["run", "--rm", *flags, policy.BROWSER, "node", "node_modules/playwright/cli.js", "test"]
    configured, mount = policy.temporary_storage(args, True)
    assert mount == "/tmp:rw,nosuid,nodev,size=1g"
    assert configured[3:] == args[1:]


@pytest.mark.parametrize("args", [
    ["run", "--name", "production-postgres", policy.POSTGRES],
    ["run", "--name", "leroy-antares-invalid", policy.POSTGRES],
    ["run", "--volumes-from", "foreign", policy.BROWSER, "node", "node_modules/playwright/cli.js", "test"],
    ["run", "--volumes-from", "29e75d9173c9", policy.BROWSER, "sh", "-c", "other command"],
    ["run", "--name", "antares-ci-postgres-12", "other-image"],
    ["build", "--tag", "antares:ci-12", "."],
    ["compose", "config", "--quiet"],
    ["exec", "antares-ci-postgres-12", "pg_isready"],
])
def test_foreign_images_commands_and_helpers_are_unchanged(args):
    assert policy.temporary_storage(args, True) == (args, None)


def test_policy_is_opt_in_and_duplicate_storage_is_rejected():
    args = ["run", "--volumes-from", "29e75d9173c9", "--tmpfs", "/tmp:rw,size=1g",
            policy.BROWSER, "node", "node_modules/playwright/cli.js", "test"]
    assert policy.temporary_storage(args, False) == (args, None)
    with pytest.raises(ValueError, match="already specified"):
        policy.temporary_storage(args, True)
