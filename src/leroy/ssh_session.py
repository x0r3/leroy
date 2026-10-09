"""One pinned SSH connection per action, with no silent reconnect or command replay."""

import subprocess
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def shared_ssh(args):
    """Keep the master alive for upstream cancellation and close it on every normal exit.

    Each context has a private socket; credentials and connections are never shared
    between jobs. A missing master fails through ProxyCommand rather than opening
    another TCP connection. Commands with unknown remote effects are never retried.
    """
    with tempfile.TemporaryDirectory(prefix="leroy-ssh-") as folder:
        socket = str(Path(folder) / "control")
        base = [*args[:-1], "-S", socket]
        host = args[-1]
        # Cancellation runs in a separate session upstream. Keep its transport
        # alive during the worker's initial process-group SIGTERM; the job
        # container still bounds the master's lifetime after a forced kill.
        master = subprocess.Popen(
            [*base, "-o", "ControlMaster=yes", "-o", "ControlPersist=no", "-N", host],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            deadline = time.monotonic() + 20
            while True:
                if master.poll() is not None:
                    raise RuntimeError("SSH connection could not be established; no commands replayed")
                ready = subprocess.run(
                    [*base, "-O", "check", host], capture_output=True, timeout=2, check=False
                )
                if ready.returncode == 0:
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError("SSH connection did not become ready within 20 seconds")
                time.sleep(0.1)
            yield [*base, "-o", "ControlMaster=no", "-o", "ProxyCommand=false", host]
        finally:
            if master.poll() is None:
                master.terminate()
                try:
                    master.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    master.kill()
                    master.wait(timeout=3)
