"""Run a validated plan inside an ephemeral job container; report durable evidence."""

import json
import os
import queue
import signal
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx

from .lease_trace import LeaseTransportTrace, announce_thread
from .schema import Pipeline


def signal_process_group(process, signum):
    # The leader may already have exited while descendants still hold stdout.
    # Such descendants still need TERM/KILL; poll() only observes the leader.
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass


class Redactor:
    """Hold only possible secret prefixes; ordinary progress must stream promptly."""

    def __init__(self, values):
        self.values = sorted({v.encode() for v in values if isinstance(v, str) and v}, key=len, reverse=True)
        self.pending = b""
        self.masked_prefix = 0
        self.redaction_open = False

    def feed(self, data, final=False):
        self.pending += data
        boundary = len(self.pending)
        matches = [(0, self.masked_prefix)] if self.masked_prefix else []
        for value in self.values:
            if not final:
                # Only a proper prefix at the end can become a secret on the
                # next read. Searching its first byte avoids scanning every
                # prefix length of long private keys on every output chunk.
                start = self.pending.find(value[:1], max(0, len(self.pending) - len(value) + 1))
                while start >= 0:
                    if value.startswith(self.pending[start:]):
                        boundary = min(boundary, start)
                        break
                    start = self.pending.find(value[:1], start + 1)
            start = self.pending.find(value)
            while start >= 0:
                matches.append((start, start + len(value)))
                start = self.pending.find(value, start + 1)
        # Carry masking across reads if a completed match overlaps a possible
        # prefix of another secret. Never retain an unbounded chain of overlaps.
        merged = []
        for start, end in sorted(matches):
            if merged and start <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
            else:
                merged.append((start, end))
        parts, cursor = [], 0
        for start, end in merged:
            if start >= boundary:
                break
            if start > cursor:
                parts.append(self.pending[cursor:start])
                self.redaction_open = False
            if not self.redaction_open:
                parts.append(b"[REDACTED]")
                self.redaction_open = True
            cursor = min(end, boundary)
        if cursor < boundary:
            parts.append(self.pending[cursor:boundary])
            self.redaction_open = False
        self.masked_prefix = max(
            (end - boundary for start, end in merged if start <= boundary < end), default=0
        )
        self.pending = self.pending[boundary:]
        return b"".join(parts)


class Reporter:
    def __init__(self, url, run, token):
        self.trace_lease = os.environ.get("LEROY_LEASE_TRACE") == "1"
        self.trace_announced = False
        self.base = url.rstrip("/") + "/internal/runs/" + run
        self.client = httpx.Client(headers={"Authorization": "Bearer " + token}, timeout=30)
        # Artifact uploads and log retries must not occupy the lease connection.
        self.heartbeat_client = httpx.Client(
            headers={"Authorization": "Bearer " + token},
            timeout=httpx.Timeout(5, connect=3, pool=1),
            limits=httpx.Limits(max_connections=1, max_keepalive_connections=1),
        )

    def heartbeat(self):
        # One attempt; tracing must not change retries, timeouts or lease clocks.
        if not self.trace_lease:
            return self._heartbeat()
        if not self.trace_announced:
            announce_thread(self.base)
            self.trace_announced = True
        with LeaseTransportTrace() as trace:
            return self._heartbeat(trace)

    def _heartbeat(self, trace=None):
        options = {} if trace is None else {"extensions": {"trace": trace}}
        response = self.heartbeat_client.post(self.base + "/heartbeat", **options)
        response.raise_for_status()
        return response.json()

    def send(self, path, *, body=None, content=None, params=None, method="POST"):
        for attempt in range(6):
            try:
                r = self.client.request(
                    method,
                    self.base + path,
                    json=body if content is None else None,
                    content=content,
                    params=params,
                )
                r.raise_for_status()
                return r.json()
            except (httpx.TransportError, httpx.HTTPStatusError) as exc:
                if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                    raise
                if attempt == 5:
                    raise
                time.sleep(min(2**attempt, 8))


def maintain_lease(send, stop, cancelled, reason):
    """Stop work before the 90s server lease expires when renewal is uncertain."""
    confirmed = time.monotonic()
    last_failure = None
    last_request_seconds = None
    previous_loop = confirmed
    loop_gap_seconds = 0

    def timing(event, **values):
        print('Leroy lease timing: ' + json.dumps({'event': event, **values}, separators=(',', ':')),
              file=sys.stderr, flush=True)

    def lose_lease():
        timing('local_deadline', unconfirmed_seconds=round(time.monotonic() - confirmed, 3),
               last_request_seconds=last_request_seconds, loop_gap_seconds=round(loop_gap_seconds, 3))
        reason[0] = "Controller lease could not be renewed"
        if last_failure:
            reason[0] += " (last failure: " + last_failure + ")"
        print("Leroy lease stopped: " + reason[0], file=sys.stderr, flush=True)
        cancelled.set()

    while not stop.is_set():
        started = time.monotonic()
        loop_gap_seconds = started - previous_loop
        previous_loop = started
        if started - confirmed >= 45:
            lose_lease()
            return
        try:
            data = send()
            last_request_seconds = round(time.monotonic() - started, 3)
            if last_request_seconds >= 3:
                timing('slow_confirmation', request_seconds=last_request_seconds,
                       previous_confirmation_age_seconds=round(started - confirmed, 3))
            if data["cancel"]:
                reason[0] = data.get("reason") or "Cancelled"
                cancelled.set()
                # Cancellation stops ordinary steps, not ownership. Artifact
                # uploads and always-run cleanup may outlast a server lease.
                # Keep renewing until main() finishes or this attempt is fenced.
            # Count request time conservatively; receiving a delayed response
            # does not mean the controller renewed the lease at receipt time.
            confirmed = started
            last_failure = None
        except httpx.HTTPStatusError as exc:
            last_request_seconds = round(time.monotonic() - started, 3)
            last_failure = "HTTP " + str(exc.response.status_code)
            print("Leroy lease renewal failed: " + last_failure, file=sys.stderr, flush=True)
            if exc.response.status_code in (401, 403, 409):
                reason[0] = "Controller rejected this runner attempt"
                cancelled.set()
                return
        except Exception as exc:
            last_request_seconds = round(time.monotonic() - started, 3)
            # URLs, response bodies and exception messages may contain secrets.
            # Retain only the type and timing needed to diagnose transport stalls.
            last_failure = type(exc).__name__
            print("Leroy lease renewal failed: " + last_failure
                  + "; seconds since confirmation: " + str(round(time.monotonic() - confirmed, 3)),
                  file=sys.stderr, flush=True)
        if time.monotonic() - confirmed >= 45:
            lose_lease()
            return
        # Keep the renewal cadence measured from request start. Sleeping another
        # interval after a slow success can consume the remaining 45s window.
        stop.wait(max(0, 3 - (time.monotonic() - started)))


def child_inputs(step, context):
    commit = context["values"].get("commit") or context["run"].get("commit")
    commit = commit or context["parameters"].get("RELEASE_COMMIT")
    parameters = dict(step.options.get("parameters", {}))
    for name, source in step.options.get("parameter_sources", {}).items():
        if source == "commit":
            parameters[name] = commit
        else:
            group, key = source.split(".", 1)
            parameters[name] = context[group][key]
    return {
        "step_id": step.id,
        "parameters": parameters,
        "commit": commit if step.options.get("inherit_commit", True) else None,
    }


def main():
    plan = json.loads(Path("/job/assignment.json").read_text())
    pipeline = Pipeline.model_validate(plan["snapshot"])
    profile = json.loads(Path("/job/profile.json").read_text())
    credentials = profile.get("secrets", {})
    reporter = Reporter(os.environ["LEROY_CONTROLLER"], plan["id"], os.environ["LEROY_ATTEMPT_TOKEN"])
    cancelled, heartbeat_stop = threading.Event(), threading.Event()
    all_secret_values = [v for fields in credentials.values() for v in fields.values() if isinstance(v, str)]
    all_secret_values += [
        p.read_text().strip() for p in Path("/job/credentials").glob("*") if "KNOWN_HOSTS" not in p.name
    ]
    all_secret_values += [os.environ["LEROY_ATTEMPT_TOKEN"]]
    cancellation_reason = ["Cancelled"]

    monitor = threading.Thread(
        target=maintain_lease,
        args=(reporter.heartbeat, heartbeat_stop, cancelled, cancellation_reason),
        daemon=True,
    )
    monitor.start()
    signal.signal(signal.SIGTERM, lambda *_: cancelled.set())
    signal.signal(signal.SIGINT, lambda *_: cancelled.set())
    root = Path("/work")
    root.mkdir(exist_ok=True)
    (root / "repo").mkdir(exist_ok=True)
    (root / "results").mkdir(exist_ok=True)
    context = {
        "run": {k: v for k, v in plan.items() if k != "token"},
        "parameters": plan["parameters"],
        "profile": {k: v for k, v in profile.items() if k != "secrets"},
        "repo": str(root / "repo"),
        "work": str(root),
        "results": str(root / "results"),
        "values": {},
    }
    statuses, reasons, blocked = {}, {}, set()
    tolerated = {step.id for step in pipeline.steps if step.continue_on_error}
    context_lock = threading.Lock()
    waiting_children = set()

    def scrub(value):
        if isinstance(value, dict):
            return {scrub(k): scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [scrub(v) for v in value]
        if isinstance(value, str):
            for secret in sorted(all_secret_values, key=len, reverse=True):
                value = value.replace(secret, "[REDACTED]")
        return value

    def artifacts(step):
        for pattern in step.artifacts:
            if pattern.startswith(".leroy-results/"):
                base, pattern = root / "results", pattern.removeprefix(".leroy-results/")
            else:
                base = root / "repo"
            for path in base.glob(pattern):
                if (
                    not path.is_file()
                    or path.is_symlink()
                    or not path.resolve().is_relative_to(base.resolve())
                ):
                    continue
                name = path.relative_to(base).as_posix()
                with path.open("rb") as handle:
                    response = reporter.client.post(
                        reporter.base + "/artifacts/" + step.id,
                        params={"name": name},
                        content=handle,
                        timeout=120,
                    )
                    response.raise_for_status()

    def execute(step):
        with context_lock:
            current = json.loads(json.dumps(context))
        if cancelled.is_set() and not step.always:
            status, reason = "cancelled", cancellation_reason[0]
            reporter.send("/steps/" + step.id, body={"status": status, "reason": reason})
            return status, {}, reason
        if step.condition and not current["values"].get(step.condition):
            reason = current["values"].get("skip_reason", f"Condition {step.condition} is false")
            reporter.send("/steps/" + step.id, body={"status": "skipped", "reason": reason})
            return "skipped", {}, reason
        reporter.send("/steps/" + step.id, body={"status": "running"})
        if step.action == "child":
            child = reporter.send(
                "/children/" + step.options["pipeline"],
                body=child_inputs(step, current),
            )
            if step.options.get("wait"):
                with context_lock:
                    waiting_children.add(step.id)
                deadline = time.monotonic() + step.timeout
                expired = False
                try:
                    while not cancelled.wait(1):
                        children = reporter.send("/children", method="GET")
                        child = next(c for c in children if c["id"] == child["id"])
                        if child["status"] not in ("queued", "running", "waiting"):
                            break
                        if time.monotonic() >= deadline:
                            expired = True
                            reporter.send("/children/" + child["id"] + "/cancel", body={})
                            break
                    status = (
                        "timed_out"
                        if expired
                        else "succeeded"
                        if child["status"] == "succeeded"
                        else "cancelled"
                        if cancelled.is_set()
                        else "failed"
                    )
                finally:
                    with context_lock:
                        waiting_children.discard(step.id)
            else:
                status = "succeeded"
            output = {step.id + "_child": child["id"], step.id + "_result": child["status"]}
            reason = (
                "" if status == "succeeded" else
                cancellation_reason[0] if status == "cancelled" else
                "Child pipeline timeout exceeded" if status == "timed_out" else
                "Child job did not succeed"
            )
            reporter.send(
                "/steps/" + step.id,
                body={
                    "status": status,
                    "outputs": output,
                    "reason": reason,
                },
            )
            return status, output, reason
        input_path = root / (step.id + "-input.json")
        output_path = root / (step.id + "-output.json")
        input_path.write_text(json.dumps(dict(current, step=step.model_dump(), output=str(output_path))))
        env = {k: v for k, v in os.environ.items() if not k.startswith("LEROY_")}
        env.update({str(k): str(v) for k, v in profile.get("environment", {}).items()})
        for name in step.secrets:
            if name in credentials:
                env.update(credentials[name])
        env.update({"PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1", "CI": "true"})
        process = subprocess.Popen(
            [sys.executable, "-m", "leroy.actions", str(input_path)],
            cwd=root / "repo",
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        pipe = queue.Queue(maxsize=64)

        def read_pipe():
            try:
                while data := os.read(process.stdout.fileno(), 8192):
                    pipe.put(data)
            finally:
                pipe.put(None)

        reader = threading.Thread(target=read_pipe, daemon=True)
        reader.start()
        redactor, offset, pending = Redactor(all_secret_values), 0, b""
        started, flushed, stopping = time.monotonic(), time.monotonic(), None
        state, reason, ended = "succeeded", "", False
        try:
            while not ended or process.poll() is None:
                elapsed = time.monotonic() - started
                if ((cancelled.is_set() and not step.always) or elapsed > step.timeout) and stopping is None:
                    state = "timed_out" if elapsed > step.timeout else "cancelled"
                    reason = "Step timeout exceeded" if state == "timed_out" else cancellation_reason[0]
                    signal_process_group(process, signal.SIGTERM)
                    stopping = time.monotonic()
                if stopping and time.monotonic() - stopping > 15:
                    signal_process_group(process, signal.SIGKILL)
                try:
                    data = pipe.get(timeout=0.1)
                    if data is None:
                        pending += redactor.feed(b"", final=True)
                        ended = True
                    else:
                        pending += redactor.feed(data)
                except queue.Empty:
                    pass
                if pending and (len(pending) >= 32768 or time.monotonic() - flushed > 0.5 or ended):
                    while pending:
                        chunk, pending = pending[:65536], pending[65536:]
                        response = reporter.send("/logs/" + step.id, content=chunk, params={"offset": offset})
                        offset = response["offset"]
                    flushed = time.monotonic()
            code = process.wait(timeout=20)
            if code and state == "succeeded":
                state, reason = "failed", f"Process exited with code {code}"
            output = json.loads(output_path.read_text()) if output_path.exists() else {}
            if state == "succeeded" and output.get("_skip"):
                state, reason = "skipped", output.pop("_skip")
            if output.get("commit"):
                reporter.send("/identity", body={"commit": output["commit"]})
            artifacts(step)
            reporter.send(
                "/steps/" + step.id,
                body={"status": state, "reason": reason, "exit_code": code, "outputs": scrub(output)},
            )
            return state, output, reason
        finally:
            if stopping is not None or not ended or process.poll() is None:
                signal_process_group(process, signal.SIGKILL)
            process.wait()

    started = time.monotonic()
    pipeline_timed_out = False
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            running = {}
            released_capacity = False
            while len(statuses) < len(pipeline.steps):
                if time.monotonic() - started > pipeline.timeout:
                    pipeline_timed_out = True
                    cancelled.set()
                    cancellation_reason[0] = "Pipeline timeout exceeded"
                with context_lock:
                    all_waiting = bool(running) and all(
                        id in waiting_children and not future.done() for id, future in running.items()
                    )
                if released_capacity:
                    if all_waiting or not reporter.send("/waiting", body={"waiting": False})["resumed"]:
                        time.sleep(0.1)
                        continue
                    released_capacity = False
                for step in pipeline.steps:
                    if (
                        step.id in statuses
                        or step.id in running
                        or len(running) >= 4
                        or not all(n in statuses for n in step.needs)
                    ):
                        continue
                    bad = [
                        n
                        for n in step.needs
                        if n in blocked
                        or (statuses[n] not in ("succeeded", "skipped") and n not in tolerated)
                    ]
                    if bad and not step.always:
                        reason = "Blocked by unsuccessful dependencies: " + ", ".join(bad)
                        statuses[step.id], reasons[step.id] = "skipped", reason
                        blocked.add(step.id)
                        reporter.send("/steps/" + step.id, body={"status": "skipped", "reason": reason})
                    else:
                        running[step.id] = pool.submit(execute, step)
                for id, future in list(running.items()):
                    if future.done():
                        try:
                            status, outputs, reason = future.result()
                        except Exception as exc:
                            status, outputs, reason = (
                                "failed",
                                {},
                                "Execution infrastructure error: " + type(exc).__name__,
                            )
                            if isinstance(exc, httpx.HTTPStatusError):
                                try:
                                    detail = exc.response.json().get("detail")
                                    if isinstance(detail, str):
                                        reason += ": " + scrub(detail)[:2000]
                                except (ValueError, AttributeError):
                                    pass
                            reporter.send("/steps/" + id, body={"status": status, "reason": reason})
                        statuses[id], reasons[id] = status, reason
                        with context_lock:
                            context["values"].update(outputs)
                        del running[id]
                with context_lock:
                    all_waiting = bool(running) and all(
                        id in waiting_children and not future.done() for id, future in running.items()
                    )
                if all_waiting:
                    reporter.send("/waiting", body={"waiting": True})
                    released_capacity = True
                time.sleep(0.1)
        failed = [s.id for s in pipeline.steps if statuses[s.id] in ("failed", "timed_out", "interrupted")]
        status = (
            "timed_out"
            if pipeline_timed_out
            else "cancelled"
            if cancelled.is_set()
            else "failed"
            if failed
            else "succeeded"
        )
        reason = (
            cancellation_reason[0] if cancelled.is_set() else "; ".join(f"{s}: {reasons[s]}" for s in failed)
        )
        reporter.send(
            "/complete", body={"status": status, "reason": reason, "outputs": scrub(context["values"])}
        )
    finally:
        heartbeat_stop.set()
        monitor.join(timeout=5)


if __name__ == "__main__":
    main()
