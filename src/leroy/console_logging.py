"""Best-effort console output must never stop the control plane's request loop.

Docker's non-blocking driver cannot help when its reader of the container pipe
itself stalls. Format and write records in a bounded daemon, without holding a
logging-handler or Python TextIO lock across the potentially blocked write.
Pipeline logs and audit events use their existing durable stores.
"""

import copy
import logging
import os
import queue
import sys
import threading


class NonBlockingStreamHandler(logging.Handler):
    def __init__(self, stream=None, capacity=128, max_bytes=16384):
        super().__init__()
        if type(capacity) is not int or capacity < 1 or type(max_bytes) is not int or max_bytes < 128:
            raise ValueError("Console bounds must be positive (message bound at least 128 bytes)")
        self.stream = stream if stream is not None else sys.stderr
        self.records = queue.Queue(maxsize=capacity)
        self.max_bytes = max_bytes
        self.dropped_records = 0
        self.write_errors = 0
        self._closing = False
        self._reported_drops = 0
        try:
            self._fd = os.dup(self.stream.fileno())
        except (AttributeError, OSError, ValueError):
            self._fd = None
        self.writer = threading.Thread(target=self._drain, name="leroy-console", daemon=True)
        self.writer.start()

    def emit(self, record):
        if self._closing:
            return
        try:
            self.records.put_nowait(copy.copy(record))
        except queue.Full:
            self.dropped_records += 1

    def _write(self, data):
        if self._fd is None:
            self.stream.write(data.decode("utf-8", errors="replace"))
            self.stream.flush()
            return
        remaining = memoryview(data)
        while remaining:
            written = os.write(self._fd, remaining)
            if written <= 0:
                raise OSError("Console write made no progress")
            remaining = remaining[written:]

    def _drain(self):
        try:
            while True:
                record = self.records.get()
                if record is None or self._closing:
                    return
                try:
                    data = (self.format(record) + "\n").encode("utf-8", errors="backslashreplace")
                    if len(data) > self.max_bytes:
                        data = data[: self.max_bytes - 20].decode("utf-8", errors="ignore").encode()
                        data += b"...[truncated]\n"
                    self._write(data)
                    dropped = self.dropped_records
                    if dropped > self._reported_drops:
                        self._write(f"Leroy console: {dropped} records dropped under output backpressure\n".encode())
                        self._reported_drops = dropped
                except Exception:
                    # Logging errors must not recurse into the same blocked sink.
                    self.write_errors += 1
        finally:
            if self._fd is not None:
                os.close(self._fd)

    def flush(self):
        # logging.shutdown() also runs in the caller. Never wait there for a
        # blocked sink; raw fd writes avoid holding sys.stderr's TextIO lock.
        pass

    def close(self):
        self._closing = True
        try:
            self.records.put_nowait(None)
        except queue.Full:
            pass
        super().close()


def logging_config():
    from uvicorn.config import LOGGING_CONFIG

    config = copy.deepcopy(LOGGING_CONFIG)
    for handler in config["handlers"].values():
        if handler.get("class") == "logging.StreamHandler":
            handler["class"] = "leroy.console_logging.NonBlockingStreamHandler"
    config["root"] = {"handlers": ["default"], "level": "INFO"}
    return config
