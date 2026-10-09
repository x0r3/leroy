"""Verify the actual test gates of a successful candidate in both CI engines."""

import argparse
import json
import re
import subprocess

from nas_ssh import ROOT


def plain(value):
    value = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", value)
    return re.sub(r"^\[[0-9T:.Z-]+\] ?", "", value, flags=re.MULTILINE)


def test_counts(log):
    rows = re.findall(r"^\s*Tests\s+(\d+) passed\s+\((\d+)\)\s*$", log, re.MULTILINE)
    assert len(rows) == 2 and all(passed == total for passed, total in rows), rows
    unit, integration = [int(total) for _, total in rows]
    assert unit >= 635 and integration >= 101, (unit, integration)
    return {"unit": unit, "integration": integration}


def browser_counts(log):
    rows = re.findall(r"^\s*(\d+) (passed|skipped|flaky|failed)\b", log, re.MULTILINE)
    result = {name: 0 for name in ("passed", "skipped", "flaky", "failed")}
    for count, name in rows:
        assert result[name] == 0, "Inspect duplicate browser result summaries"
        result[name] = int(count)
    assert result["failed"] == 0 and result["skipped"] == 3, result
    assert result["passed"] + result["flaky"] >= 26, result
    projects = {
        "game-chromium",
        "game-mobile",
        "game-firefox",
        "game-webkit",
        "admin-chromium",
        "admin-surface-low-dpr",
        "admin-surface-firefox",
        "admin-surface-webkit",
    }
    assert all("[" + project + "]" in log for project in projects), "Browser project missing"
    return {**result, "projects": sorted(projects)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", required=True)
    commit = parser.parse_args().candidate
    assert re.fullmatch("[a-f0-9]{40}", commit)
    folder = ROOT / "test-results/nas-parity/followup/candidates/antares" / commit
    state = json.loads((folder / "comparison.json").read_text())
    run = json.loads((folder / "leroy-run.json").read_text())
    assert state["jenkins"]["result"] == "SUCCESS" and state["jenkins"]["building"] is False
    assert run["status"] == "succeeded" and run["commit"] == state["commit"] == commit
    assert all(step["status"] == "succeeded" for step in run["steps"])
    assert {step["id"] for step in run["steps"]} == {
        "checkout",
        "toolchain",
        "postgres",
        "dependencies",
        "static",
        "tests",
        "build",
        "browsers",
        "cleanup",
    }
    checkout = ROOT / ".sources/antares-nas-validation"
    original = state["original_commit"]
    assert subprocess.check_output(
        ["git", "-C", str(checkout), "show", original + ":Jenkinsfile"]
    ) == subprocess.check_output(["git", "-C", str(checkout), "show", commit + ":Jenkinsfile"])
    jenkins = plain((folder / "jenkins-console.log").read_text(encoding="utf-8"))
    leroy_tests = plain((folder / "leroy-tests.log").read_text(encoding="utf-8"))
    leroy_browsers = plain((folder / "leroy-browsers.log").read_text(encoding="utf-8"))
    counts = {"jenkins": test_counts(jenkins), "leroy": test_counts(leroy_tests)}
    assert counts["jenkins"] == counts["leroy"]
    candidate_files = subprocess.check_output(
        ["git", "-C", str(checkout), "ls-tree", "-r", "--name-only", commit], text=True
    ).splitlines()
    if "tests/integration/maintenance-readers.test.ts" in candidate_files:
        assert counts["jenkins"]["integration"] >= 102
        assert all("maintenance-readers.test.ts" in log for log in (jenkins, leroy_tests)), (
            "Reader-disconnect regression missing from a complete candidate run"
        )
    if "apps/game/__tests__/social-overlay-accessibility.test.tsx" in candidate_files:
        assert counts["jenkins"]["unit"] >= 636
        assert all("social-overlay-accessibility.test.tsx" in log for log in (jenkins, leroy_tests)), (
            "Pending and loaded reputation-list regression missing from a complete candidate run"
        )
    if "apps/game/__tests__/confirmation-dialog-lifecycle.test.tsx" in candidate_files:
        assert counts["jenkins"]["unit"] >= 637
        assert all("confirmation-dialog-lifecycle.test.tsx" in log for log in (jenkins, leroy_tests)), (
            "Confirmation lifecycle regression missing from a complete candidate run"
        )
    browsers = {"jenkins": browser_counts(jenkins), "leroy": browser_counts(leroy_browsers)}
    assert sum(browsers["jenkins"][key] for key in ("passed", "flaky")) == sum(
        browsers["leroy"][key] for key in ("passed", "flaky")
    )
    state.update(
        complete_matching_gates=True,
        workload_success_both=True,
        tests=counts,
        browsers=browsers,
        production_image_built_both=True,
        jenkinsfile_unchanged=True,
        application_patches_applied=True,
        retries_reported_separately=True,
    )
    (folder / "comparison.json").write_text(json.dumps(state, indent=2) + "\n")
    print(json.dumps({"commit": commit, "tests": counts, "browsers": browsers, "passed": True}))


if __name__ == "__main__":
    main()
