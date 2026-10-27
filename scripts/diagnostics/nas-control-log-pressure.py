"""Bounded stdout backpressure on a separate controller, database and real worker.

Executed only through the reviewed NAS SSH wrapper. Secrets never enter output.
The sink emulates stalled log delivery; it does not claim to reproduce HDD stalls.
"""

import hashlib
import http.cookiejar
import ipaddress
import json
import os
import pathlib
import socket
import subprocess
import threading
import time
import tomllib
import urllib.parse
import urllib.request

MODE = globals()["MODE"]
ATTEMPT = globals()["ATTEMPT"]
EXPECT_BUFFERED_WORKER = globals()["EXPECT_BUFFERED_WORKER"]
PRODUCTION_PROGRAM = globals()["PRODUCTION_PROGRAM"]
root = pathlib.Path("/volume1/docker/leroy-nas-parity")
assert root.resolve() == root and (root / ".leroy-owned").is_file()
assert MODE in ("blocking", "non-blocking")
phase = MODE.replace("-", "") + ATTEMPT
work = root / "control-latency-20261012" / phase
assert not work.exists(), "Retain uncertain probe outcomes before retrying"
work.mkdir(parents=True, mode=0o700)
prefix = "leroy-control-probe-" + phase
controller_name, runner_name = prefix + "-controller", prefix + "-runner"
runner_id = "control-probe-" + phase
database = "leroy_control_probe_" + phase + "_20261012"
owner = "io.leroy.control-probe=20261012-" + phase
stopping, read_allowed = threading.Event(), threading.Event()
receiver_stop = threading.Event()
read_allowed.set()
sink_bytes = [0]
sink_connections = [0]
warnings = []
containers = []
samples = []
probe_run = None
watcher = None
routing_rule = None


def call(args, *, payload=None, timeout=30):
    try:
        result = subprocess.run(args, input=payload, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError("Bounded operation timed out") from None
    if result.returncode:
        raise RuntimeError("Bounded operation failed with exit code " + str(result.returncode))
    return result.stdout.strip()


def inspect(name):
    return json.loads(call(["docker", "inspect", name]))[0]


actual = {
    name: inspect("leroy-nas-parity-" + name + "-1")
    for name in ("controller", "runner", "postgres", "docker")
}
assert all(
    c["Config"]["Labels"]["com.docker.compose.project"] == "leroy-nas-parity" and c["State"]["Running"]
    for c in actual.values()
)
assert not inspect("leroy-nas-release-target-vm")["State"]["Running"]
inner = ["docker", "exec", actual["docker"]["Id"], "docker"]
firewall = ["docker", "exec", actual["docker"]["Id"], "iptables"]
firewall_before = call(firewall + ["-S", "LEROY-PARITY-EGRESS"])
assert call(inner + ["inspect", "jenkins-parity", "--format", "{{.State.Running}}"]) == "false"
assert not call(inner + ["ps", "-q", "--filter", "label=io.leroy.runner=runner-nas-parity"])
network = next(
    name for name in actual["controller"]["NetworkSettings"]["Networks"] if name == "leroy-nas-parity_default"
)
source_config = tomllib.loads((root / "config/runner.toml").read_text())
job_image = source_config["profiles"]["graphato"]["image"]
assert job_image.startswith("sha256:")
assert json.loads(call(inner + ["image", "inspect", job_image]))[0]["Id"] == job_image
sink = socket.socket()
sink.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
sink.bind(("127.0.0.1", 0))
sink.listen(2)
sink.settimeout(0.5)
port = sink.getsockname()[1]


def receive_logs():
    while not receiver_stop.is_set():
        try:
            connection, _ = sink.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        connection.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
        sink_connections[0] += 1
        connection.settimeout(0.5)
        paused = False
        with connection:
            while not receiver_stop.is_set():
                if not read_allowed.wait(0.1):
                    paused = True
                    continue
                if paused:
                    connection.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 1024**2)
                    paused = False
                try:
                    data = connection.recv(65536)
                except socket.timeout:
                    continue
                if not data:
                    break
                sink_bytes[0] += len(data)


threading.Thread(target=receive_logs, daemon=True).start()
environment = {}
for item in actual["controller"]["Config"]["Env"]:
    key, _, value = item.partition("=")
    environment[key] = value
url = urllib.parse.urlsplit(environment["LEROY_DATABASE_URL"])
assert url.path == "/leroy" and url.hostname == "postgres"
environment["LEROY_DATABASE_URL"] = urllib.parse.urlunsplit(url._replace(path="/" + database))
environment["LEROY_CONFIG"] = "/config/leroy.toml"
(work / "leroy.toml").write_text("")
(work / "data").mkdir(mode=0o700)
os.chown(work / "data", 10001, 10001)
bootstrap = r"""
import json,pathlib,threading,time,uvicorn
def flood():
 root=pathlib.Path('/data')
 while not (root/'inject-logging.flag').exists():time.sleep(0.1)
 at=time.monotonic();value={'started':True,'error':None,'lines':0}
 (root/'flood-start.json').write_text(json.dumps(value))
 try:
  for i in range(2048):
   print('CONTROL_LOG_PRESSURE '+'x'*4000,flush=True);value['lines']+=1
 except Exception as e:value['error']=type(e).__name__
 value['duration_seconds']=time.monotonic()-at
 (root/'flood-result.json').write_text(json.dumps(value))
threading.Thread(target=flood,daemon=True).start()
uvicorn.run('leroy.api:create_app',factory=True,host='0.0.0.0',port=8088)
"""
(work / "bootstrap.py").write_text(bootstrap)
controller_args = [
    "docker",
    "run",
    "-d",
    "--name",
    controller_name,
    "--label",
    owner,
    "--network",
    network,
    "--memory",
    "256m",
    "--memory-swap",
    "256m",
    "--memory-reservation",
    "128m",
    "--cpus",
    "1",
    "--log-driver",
    "syslog",
    "--log-opt",
    "syslog-address=tcp://127.0.0.1:" + str(port),
    "--log-opt",
    "mode=" + MODE,
]
if MODE == "non-blocking":
    controller_args += ["--log-opt", "max-buffer-size=4m"]
for key, value in environment.items():
    controller_args += ["--env", key + "=" + value]
for mount in actual["controller"]["Mounts"]:
    if mount["Destination"].startswith("/run/secrets/"):
        controller_args += [
            "--mount",
            "type=bind,src=" + mount["Source"] + ",dst=" + mount["Destination"] + ",readonly",
        ]
controller_args += [
    "--mount",
    "type=bind,src=" + str(work / "bootstrap.py") + ",dst=/probe.py,readonly",
    "--mount",
    "type=bind,src=" + str(work / "leroy.toml") + ",dst=/config/leroy.toml,readonly",
    "--mount",
    "type=bind,src=" + str(work / "data") + ",dst=/data",
    actual["controller"]["Image"],
    "sh",
    "-c",
    "alembic upgrade head && python -u /probe.py",
]

cookies = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
address = None


def request(path, body=None, timeout=3):
    data = None if body is None else json.dumps(body).encode()
    headers = {"X-Leroy-Request": "1", "Content-Type": "application/json"}
    with opener.open(
        urllib.request.Request(address + path, data=data, headers=headers), timeout=timeout
    ) as response:
        return response.read()


def watch_safety():
    while not stopping.wait(5):
        memory = {
            line.split(":")[0]: int(line.split()[1])
            for line in pathlib.Path("/proc/meminfo").read_text().splitlines()
            if line.startswith(("MemAvailable:", "SwapFree:"))
        }
        if memory["MemAvailable"] < 512 * 1024 or memory["SwapFree"] < 3 * 1024**2:
            warnings.append("NAS reserves below the stricter diagnostic floor")
            read_allowed.set()
            stopping.set()
            return
        try:
            production = json.loads(
                call(["python3", "-c", "VERIFY_HISTORY=False\n" + PRODUCTION_PROGRAM], timeout=20)
            )
            if production["active_builds"]:
                warnings.append("Productive Jenkins build started during diagnostic")
                read_allowed.set()
                stopping.set()
                return
        except RuntimeError:
            warnings.append("Current productive Jenkins activity could not be verified")
            read_allowed.set()
            stopping.set()
            return


sql_probe = r"""
import json,time
from sqlalchemy import text
from leroy.config import Settings
from leroy.db import connect
engine,_=connect(Settings.load().database_url);at=time.perf_counter()
try:
 with engine.connect() as db:
  db.execute(text('SET TRANSACTION READ ONLY'));db.execute(text("SET LOCAL statement_timeout='2s'"));assert db.scalar(text('SELECT 1'))==1
 value={'seconds':time.perf_counter()-at,'ok':True}
except Exception as e:value={'seconds':time.perf_counter()-at,'ok':False,'error':type(e).__name__}
engine.dispose();print(json.dumps(value))
"""

try:
    assert not call(
        [
            "docker",
            "exec",
            actual["postgres"]["Id"],
            "psql",
            "-XqAt",
            "-U",
            "leroy",
            "-d",
            "postgres",
            "-c",
            "SELECT datname FROM pg_database WHERE datname='" + database + "'",
        ]
    )
    call(
        [
            "docker",
            "exec",
            actual["postgres"]["Id"],
            "psql",
            "-XqAt",
            "-U",
            "leroy",
            "-d",
            "postgres",
            "-c",
            "CREATE DATABASE " + database,
        ]
    )
    containers.append(controller_name)
    call(controller_args, timeout=90)
    c = inspect(controller_name)
    assert c["Config"]["Labels"]["io.leroy.control-probe"] == "20261012-" + phase
    address = "http://" + c["NetworkSettings"]["Networks"][network]["IPAddress"] + ":8088"
    deadline = time.monotonic() + 90
    while time.monotonic() < deadline:
        try:
            request("/health/ready")
            break
        except Exception:
            time.sleep(1)
    else:
        raise RuntimeError("Separate probe controller did not become ready")
    request(
        "/api/auth/login",
        {"username": "admin", "password": (root / "config/admin_password").read_text().strip()},
        timeout=15,
    )
    code = "import json,pathlib,time\nfor i in range(21):\n print('CONTROL PROBE TICK '+str(i),flush=True);time.sleep(5)\npathlib.Path('receipt.json').write_text(json.dumps({'ticks':21,'completed':True}))\n"
    pipeline = {
        "id": "control-lease-probe",
        "name": "Control lease probe",
        "group": "Diagnostics",
        "profile": "probe",
        "timeout": 240,
        "enabled": False,
        "steps": [
            {
                "id": "work",
                "name": "Run through logging pressure",
                "command": ["python", "-u", "-c", code],
                "timeout": 180,
                "artifacts": ["receipt.json"],
            }
        ],
    }
    put = urllib.request.Request(
        address + "/api/pipelines/control-lease-probe",
        data=json.dumps(pipeline).encode(),
        headers={"X-Leroy-Request": "1", "Content-Type": "application/json"},
        method="PUT",
    )
    with opener.open(put, timeout=5) as response:
        assert response.status == 200
    probe_run = json.loads(request("/api/pipelines/control-lease-probe/runs", {}, timeout=5))
    ip = c["NetworkSettings"]["Networks"][network]["IPAddress"]
    assert ipaddress.ip_address(ip) in ipaddress.ip_network("10.232.98.0/24")
    assert ip != actual["controller"]["NetworkSettings"]["Networks"][network]["IPAddress"]
    routing_rule = ["-d", ip, "-p", "tcp", "--dport", "8088", "-j", "RETURN"]
    call(firewall + ["-I", "LEROY-PARITY-EGRESS", "2", *routing_rule])
    profile = (
        'capacity=1\n[profiles.probe]\nimage="'
        + job_image
        + '"\nnetwork="leroy-jobs"\nmemory="128m"\nmemory_swap="128m"\ncpus=0.25\nhost_mappings={controller="'
        + ip
        + '"}\n'
    )
    (work / "runner.toml").write_text(profile)
    runner_args = [
        "docker",
        "run",
        "-d",
        "--name",
        runner_name,
        "--label",
        owner,
        "--network",
        network,
        "--add-host",
        "controller:" + ip,
        "--memory",
        "192m",
        "--memory-swap",
        "192m",
        "--cpus",
        "0.5",
        "--env",
        "DOCKER_HOST=tcp://docker:2375",
        "--env",
        "LEROY_CONTROLLER=http://controller:8088",
        "--env",
        "LEROY_RUNNER_ID=" + runner_id,
        "--env",
        "LEROY_RUNNER_TOKEN_FILE=/run/secrets/runner_token",
        "--mount",
        "type=bind,src=" + str(work / "runner.toml") + ",dst=/config/runner.toml,readonly",
        "--mount",
        "type=bind,src=" + str(root / "config/runner_token") + ",dst=/run/secrets/runner_token,readonly",
        actual["runner"]["Image"],
    ]
    containers.append(runner_name)
    call(runner_args, timeout=60)
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        run = json.loads(request("/api/runs/" + probe_run["id"]))
        if run["steps"][0]["status"] == "running":
            break
        time.sleep(1)
    else:
        raise RuntimeError("Actual worker did not start the diagnostic command")
    job_info = json.loads(call(inner + ["inspect", "leroy-" + probe_run["id"]]))[0]
    worker_logging = job_info["HostConfig"]["LogConfig"]
    if EXPECT_BUFFERED_WORKER:
        assert worker_logging["Config"]["mode"] == "non-blocking"
        assert worker_logging["Config"]["max-buffer-size"] == "4m"
    watcher = threading.Thread(target=watch_safety, daemon=True)
    watcher.start()
    started = time.monotonic()
    read_allowed.clear()
    print(
        json.dumps(
            {"phase": MODE, "fault_injected": True, "run_id": probe_run["id"], "worker_image": job_image}
        ),
        flush=True,
    )
    (work / "data/inject-logging.flag").write_text("trigger\n")
    while time.monotonic() - started < 70 and not stopping.is_set():
        row = {"elapsed": round(time.monotonic() - started, 3)}
        at = time.perf_counter()
        try:
            request("/health/live", timeout=2)
            row["api_live"] = {"ok": True, "seconds": time.perf_counter() - at}
        except Exception as e:
            row["api_live"] = {"ok": False, "seconds": time.perf_counter() - at, "error": type(e).__name__}
        try:
            row["direct_sql"] = json.loads(
                call(
                    ["docker", "exec", "-i", actual["controller"]["Id"], "python", "-"],
                    payload=sql_probe,
                    timeout=10,
                )
            )
        except RuntimeError:
            row["direct_sql"] = {"ok": False, "error": "ObservationTimeout"}
        samples.append(row)
        time.sleep(3)
    read_allowed.set()
    assert not warnings, "Diagnostic invalidated by safety observations"
    partial = {
        "mode": MODE,
        "run_id": probe_run["id"],
        "samples": samples,
        "sink_bytes": sink_bytes[0],
        "sink_connections": sink_connections[0],
        "flood_started": (work / "data/flood-start.json").exists(),
        "valid_terminal_result": False,
    }
    (work / "partial-result.json").write_text(json.dumps(partial, indent=2) + "\n")
    deadline = time.monotonic() + 60
    while not (work / "data/flood-result.json").exists() and time.monotonic() < deadline:
        time.sleep(0.2)
    flood_result = json.loads((work / "data/flood-result.json").read_text())
    assert flood_result["error"] is None and flood_result["lines"] == 2048, (
        "The injected logging writer failed; no backpressure claim"
    )
    deadline = time.monotonic() + 110
    while time.monotonic() < deadline:
        try:
            run = json.loads(request("/api/runs/" + probe_run["id"], timeout=5))
            if run["status"] not in ("queued", "running", "waiting"):
                break
        except Exception:
            pass
        time.sleep(2)
    else:
        raise RuntimeError("Diagnostic run did not become terminal within its bounded window")
    artifacts = []
    for artifact in run["artifacts"]:
        data = request("/api/artifacts/" + artifact["id"])
        assert len(data) == artifact["size"] and hashlib.sha256(data).hexdigest() == artifact["sha256"]
        artifacts.append({"name": artifact["name"], "sha256": artifact["sha256"], "size": len(data)})
        if artifact["name"] == "receipt.json":
            assert json.loads(data) == {"ticks": 21, "completed": True}
    log = json.loads(request("/api/runs/" + run["id"] + "/logs/work?offset=0"))
    assert log["next_offset"] == run["steps"][0]["log_bytes"]
    if run["status"] == "succeeded":
        assert (
            len([line for line in log["text"].splitlines() if line.startswith("CONTROL PROBE TICK ")]) == 21
        )
        assert artifacts
    result = {
        "mode": MODE,
        "original_controller_image": actual["controller"]["Image"],
        "runner_image": actual["runner"]["Image"],
        "worker_image": job_image,
        "actual_worker_diagnostic_logging": worker_logging,
        "pipeline_sha256": hashlib.sha256(json.dumps(pipeline, sort_keys=True).encode()).hexdigest(),
        "run": run,
        "samples": samples,
        "verified_artifacts": artifacts,
        "job_log": log,
        "sink_bytes": sink_bytes[0],
        "logging_writer": flood_result,
        "diagnostic_bootstrap_sha256": hashlib.sha256(bootstrap.encode()).hexdigest(),
        "logging_pressure_ended": True,
        "diagnostic_scope": "Synthetic log-delivery stall on a separate control database and real job; not historical HDD causality proof",
        "graphato_sources_or_tests_changed": False,
        "production_modified": False,
    }
    (work / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result), flush=True)
finally:
    read_allowed.set()
    stopping.set()
    if watcher:
        watcher.join(timeout=5)
    if runner_name in containers and call(["docker", "ps", "-aq", "--filter", "name=^" + runner_name + "$"]):
        assert inspect(runner_name)["Config"]["Labels"]["io.leroy.control-probe"] == "20261012-" + phase
        call(["docker", "stop", "--time", "5", runner_name])
    owned = call(inner + ["ps", "-aq", "--filter", "label=io.leroy.runner=" + runner_id]).split()
    for id in owned:
        item = json.loads(call(inner + ["inspect", id]))[0]
        assert item["Config"]["Labels"]["io.leroy.runner"] == runner_id
        call(inner + ["rm", "-f", "-v", id])
        volume = "leroy-" + item["Config"]["Labels"]["io.leroy.run"] + "-work"
        call(inner + ["volume", "rm", volume])
    for name in reversed(containers):
        if not call(["docker", "ps", "-aq", "--filter", "name=^" + name + "$"]):
            continue
        assert inspect(name)["Config"]["Labels"]["io.leroy.control-probe"] == "20261012-" + phase
        call(["docker", "rm", "-f", name])
    if routing_rule:
        call(firewall + ["-D", "LEROY-PARITY-EGRESS", *routing_rule])
    assert call(firewall + ["-S", "LEROY-PARITY-EGRESS"]) == firewall_before
    receiver_stop.set()
    sink.close()
    assert not call(inner + ["ps", "-q", "--filter", "label=io.leroy.runner=" + runner_id])
    (work / "cleanup.json").write_text(
        json.dumps(
            {
                "temporary_controllers_runners_and_jobs_removed": True,
                "probe_database_retained": database,
                "warnings": warnings,
                "productive_containers_modified": False,
                'temporary_network_rule_restored': True,
            }
        )
        + "\n"
    )
