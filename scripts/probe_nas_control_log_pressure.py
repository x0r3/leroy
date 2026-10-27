"""Run the bounded separate-controller diagnostic; retain both modes' evidence."""

import argparse
import ast
import inspect
import json
import re
from datetime import datetime, timezone

import nas_release_vm as vm
from diagnose_nas_control_latency import FOLDER
from nas_followup_support import production_jobs
from nas_gitea_target import idle
from nas_measurement_guard import begin, finish
from nas_ssh import ROOT, run_script


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["blocking", "non-blocking"])
    parser.add_argument(
        "--attempt", default="", help="Explicit new diagnostic namespace; prior evidence stays retained"
    )
    parser.add_argument("--expect-buffered-worker", action="store_true")
    args = parser.parse_args()
    assert not args.attempt or re.fullmatch(r"[a-z0-9]{1,12}", args.attempt)
    idle()
    assert not vm.state()["State"]["Running"]
    output = FOLDER / (args.mode + ("-" + args.attempt if args.attempt else ""))
    output.mkdir(parents=True, exist_ok=True)
    assert not (output / "started.json").exists(), "Inspect an uncertain diagnostic before retrying"
    before = begin(output, "control-log-pressure")
    tree = ast.parse(inspect.getsource(production_jobs))
    production_program = next(
        ast.literal_eval(row.value)
        for row in tree.body[0].body
        if isinstance(row, ast.Assign)
        and any(isinstance(name, ast.Name) and name.id == "program" for name in row.targets)
    )
    source = ROOT / "scripts/diagnostics/nas-control-log-pressure.py"
    program = (
        "MODE="
        + repr(args.mode)
        + "\nATTEMPT="
        + repr(args.attempt)
        + "\nEXPECT_BUFFERED_WORKER="
        + repr(args.expect_buffered_worker)
        + "\nPRODUCTION_PROGRAM="
        + repr(production_program)
        + "\n"
        + source.read_text(encoding="utf-8")
    )
    (output / "started.json").write_text(
        json.dumps(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "mode": args.mode,
                "production_guard_before": before,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "program.py").write_text(program, encoding="utf-8")
    result = run_script(
        "python3 - <<'PY'\n" + program + "\nPY\n", ROOT / ".local/nas-ssh.json", sudo=True, timeout=420
    )
    (output / "stdout.log").write_text(result.stdout, encoding="utf-8")
    (output / "stderr.log").write_text(result.stderr, encoding="utf-8")
    finish(output, "control-log-pressure", before)
    if result.returncode:
        print(json.dumps({"diagnostic_exit_code": result.returncode, "retained_folder": str(output)}))
        raise RuntimeError("Diagnostic failed; inspect retained sanitized evidence")
    value = json.loads(result.stdout.splitlines()[-1])
    (output / "result.json").write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "mode": args.mode,
                "status": value["run"]["status"],
                "reason": value["run"]["reason"],
                "api_timeout_samples": sum(not row["api_live"]["ok"] for row in value["samples"]),
                "direct_sql_failures": sum(not row["direct_sql"]["ok"] for row in value["samples"]),
                "verified_artifacts": value["verified_artifacts"],
                "graphato_tests_changed": False,
            }
        )
    )


if __name__ == "__main__":
    main()
