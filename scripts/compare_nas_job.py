"""Execute an explicitly prepared NAS comparison and collect its evidence."""

import argparse
import hashlib
import json
import os
import sys
from contextlib import closing
from pathlib import Path, PurePosixPath

from compare_nas_antares import client, jenkins
from nas_candidate_paths import comparison_source
from nas_measurement_guard import begin, finish


def collect_artifacts(api, run, folder):
    archive = folder / "leroy-artifacts"
    for item in run["artifacts"]:
        name = PurePosixPath(item["name"])
        step = PurePosixPath(item["step_id"])
        assert len(step.parts) == 1 and step.name not in (".", "..")
        assert not name.is_absolute() and ".." not in name.parts
        destination = archive.joinpath(step.name, *name.parts)
        assert destination.resolve().is_relative_to(archive.resolve())
        # Playwright trace resource names can exceed Win32's legacy path limit.
        # Validate the ordinary path before using the extended filesystem form.
        if os.name == "nt":
            resolved = str(destination.resolve())
            destination = Path(
                "\\\\?\\UNC\\" + resolved[2:] if resolved.startswith("\\\\") else "\\\\?\\" + resolved
            )
        if destination.is_file() and destination.stat().st_size == item["size"]:
            with destination.open("rb") as stream:
                if hashlib.file_digest(stream, "sha256").hexdigest() == item["sha256"]:
                    continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        partial = destination.with_name(destination.name + ".partial")
        digest, size = hashlib.sha256(), 0
        with api.stream("GET", "/api/artifacts/" + item["id"]) as response:
            response.raise_for_status()
            with partial.open("wb") as stream:
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    assert size <= item["size"], "Artifact exceeded its recorded size"
                    stream.write(chunk)
                    digest.update(chunk)
        assert size == item["size"] and digest.hexdigest() == item["sha256"]
        partial.replace(destination)


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pipeline")
    parser.add_argument(
        "phase", choices=["start-jenkins", "retry-jenkins", "jenkins", "start-leroy", "leroy"]
    )
    parser.add_argument("--reason", help="Required explanation for an explicit setup retry")
    parser.add_argument(
        "--candidate", help="Staged Graphato commit, recorded separately from the original baseline"
    )
    args = parser.parse_args()
    source, folder = comparison_source(args.pipeline, args.candidate)
    prepared = json.loads((folder / "prepared.json").read_text())
    parameters = prepared["parameters"]
    path = folder / "pair.json"
    state = (
        json.loads(path.read_text())
        if path.exists()
        else {
            "pipeline": args.pipeline,
            "commit": source["commit"],
            "parameters": parameters,
            "application_patches_applied": source.get("application_patches_applied", False),
            "complete": False,
        }
    )
    if args.phase in ("start-jenkins", "retry-jenkins"):
        retry = args.phase == "retry-jenkins"
        if retry:
            if not args.reason or state.get("leroy_run"):
                raise ValueError("A setup retry needs a reason and must precede the Leroy comparison")
            result = jenkins("status", args.pipeline)
            assert not result["build"]["building"] and result["build"]["result"]
            (folder / f"jenkins-{result['build']['number']}-console.log").write_text(
                result["console"], encoding="utf-8"
            )
            state.setdefault("setup_attempts", []).append(
                {"build": result["build"], "retry_reason": args.reason,
                 "production_guard_before": state.get("production_guard_before_jenkins"),
                 "production_guard_phase": state.get("production_guard_phase_jenkins")}
            )
            state.pop("jenkins", None)
        elif state.get("jenkins_start"):
            raise ValueError("Comparison already started; no implicit rerun")
        phase = 'jenkins-attempt-' + str(len(state.get('setup_attempts', [])) + 1)
        state['production_guard_before_jenkins'] = begin(folder, phase)
        state['production_guard_phase_jenkins'] = phase
        state["jenkins_start"] = jenkins(
            "retry" if retry or args.candidate else "start",
            args.pipeline,
            {
                key: str(value).lower() if isinstance(value, bool) else value
                for key, value in parameters.items()
            },
        )
    elif args.phase == "jenkins":
        result = jenkins("status", args.pipeline)
        (folder / "jenkins-console.log").write_text(result["console"], encoding="utf-8")
        (folder / f"jenkins-{result['build']['number']}-console.log").write_text(
            result["console"], encoding="utf-8"
        )
        state["jenkins"] = result["build"]
        if not result['build']['building'] and result['build']['result']:
            finish(folder, state.get('production_guard_phase_jenkins', 'jenkins'),
                   state.get('production_guard_before_jenkins'))
        print(json.dumps({k: result["build"][k] for k in ("number", "result", "building", "duration")}))
        print(result["console"][-900:])
    elif args.phase == "start-leroy":
        if state.get("leroy_run"):
            raise ValueError("Comparison already started; no implicit rerun")
        if not state.get("jenkins", {}).get("result") or state["jenkins"].get("building"):
            raise ValueError("Jenkins baseline must be completed first")
        state['production_guard_before_leroy'] = begin(folder, 'leroy')
        frozen_master = False
        if args.pipeline == "graphato-ci" and args.candidate:
            staged = json.loads((folder.parent / "staged.json").read_text())
            frozen_master = staged.get("source_kind") == "frozen_master_revision"
            if frozen_master:
                from nas_master_build_slot import wait_for_nas_build_slot

                wait_for_nas_build_slot(args.candidate)
        if args.pipeline == "graphato-ci" and (
            frozen_master or args.candidate == "ed21c2e6346aab6f71494765a37ba91e0d4559b7"
        ):
            from capture_leroy_current_graphato_budget import record_start_budget

            state["resource_policy_evidence"] = record_start_budget(folder / "leroy-start-resource-policy.json")
        with closing(client()) as api:
            pipelines = api.get("/api/pipelines").json()
            assert not any(p["enabled"] for p in pipelines)
            spec = next(p["spec"] for p in pipelines if p["id"] == args.pipeline)
            definitions = {p["name"]: p for p in spec["parameters"]}
            values = {key: value for key, value in parameters.items() if key in definitions}
            for key, value in values.items():
                if definitions[key]["kind"] == "integer" and isinstance(value, str):
                    values[key] = int(value)
            payload = {"parameters": values}
            if source["commit"]:
                payload["commit"] = source["commit"]
            response = api.post("/api/pipelines/" + args.pipeline + "/runs", json=payload)
            response.raise_for_status()
            state["leroy_run"] = response.json()["id"]
            print("Leroy run", state["leroy_run"])
    else:
        with closing(client()) as api:
            response = api.get("/api/runs/" + state["leroy_run"])
            response.raise_for_status()
            run = response.json()
            (folder / "leroy-run.json").write_text(json.dumps(run, indent=2), encoding="utf-8")
            collect_artifacts(api, run, folder)
            for step in run["steps"]:
                offset = 0
                with (folder / ("leroy-" + step["id"] + ".log")).open("w", encoding="utf-8") as stream:
                    while offset < step["log_bytes"]:
                        response = api.get(
                            f"/api/runs/{run['id']}/logs/{step['id']}", params={"offset": offset}
                        )
                        response.raise_for_status()
                        log = response.json()
                        stream.write(log.get("text", ""))
                        if log.get("next_offset", offset) <= offset:
                            break
                        offset = log["next_offset"]
            state["leroy_status"] = run["status"]
            if run['status'] not in {'queued', 'running', 'waiting'}:
                finish(folder, 'leroy', state.get('production_guard_before_leroy'))
            print(
                json.dumps(
                    {
                        "id": run["id"],
                        "status": run["status"],
                        "steps": [(s["id"], s["status"]) for s in run["steps"]],
                    },
                    indent=2,
                )
            )
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
