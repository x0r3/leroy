"""Complete the prepared follow-up phases in order, stopping at any failed check."""

import json
import subprocess
import sys
import time

from nas_ssh import ROOT


def main():
    report = ROOT / "test-results/nas-parity/followup/home-lab-build/comparison.json"
    deadline = time.monotonic() + 3600
    while time.monotonic() < deadline:
        try:
            value = json.loads(report.read_text())
            if value.get("real_build_and_push_both"):
                break
        except (FileNotFoundError, json.JSONDecodeError):
            pass
        time.sleep(10)
    else:
        raise TimeoutError("Home-Lab evidence not yet complete")
    for script, args in [
        ("compare_nas_home_lab_contents.py", []),
        ("test_nas_stack_restart.py", []),
        ("test_nas_recovered_services.py", []),
        ("test_nas_parallel.py", []),
        ("summarize_nas_followup.py", []),
        ("compare_nas_antares_candidate.py", ["jenkins"]),
    ]:
        print("Follow-up phase:", script, *args, flush=True)
        subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args], cwd=ROOT, check=True)


if __name__ == "__main__":
    main()
