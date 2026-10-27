"""Opt-in, numeric transport diagnostics; request data is never retained."""

import json
import os
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

try:
    import resource
except ImportError:  # The worker runs on Linux; local development may use Windows.
    resource = None


PHASES = {
    'connection.connect_tcp': 'connect',
    'connection.connect_unix_socket': 'connect_unix',
    'connection.start_tls': 'tls',
    'http11.send_request_headers': 'send_headers',
    'http11.send_request_body': 'send_body',
    'http11.receive_response_headers': 'receive_headers',
    'http11.receive_response_body': 'receive_body',
    'http11.response_closed': 'close',
}


def emit(value):
    try:
        print('Leroy lease transport: ' + json.dumps(value, separators=(',', ':')),
              file=sys.stderr, flush=True)
    except (OSError, ValueError):
        # Diagnostics must not turn a successful renewal into a failed request.
        pass


def thread_usage():
    if resource is None or not hasattr(resource, 'RUSAGE_THREAD'):
        return None
    try:
        value = resource.getrusage(resource.RUSAGE_THREAD)
        return {name: int(getattr(value, 'ru_' + name)) for name in
                ('majflt', 'minflt', 'inblock', 'nvcsw', 'nivcsw')}
    except (AttributeError, OSError):
        return None


def announce_thread(base_url=None):
    mapping = None
    if base_url:
        try:
            host = urlsplit(base_url).hostname
            mapping = any(host in line.split('#', 1)[0].split()[1:]
                          for line in Path('/etc/hosts').read_text().splitlines())
        except (OSError, ValueError):
            pass
    emit({'event': 'thread', 'at_epoch': time.time(), 'pid': os.getpid(),
          'thread_id': threading.get_native_id(), 'controller_file_mapping_present': mapping,
          'proxy_environment_present': any(os.environ.get(key) for key in
              ('HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'http_proxy', 'https_proxy', 'all_proxy'))})


class LeaseTransportTrace:
    """Observe one request through HTTPCore's trace extension, ignoring all info."""

    def __init__(self, *, threshold_seconds=3):
        self.threshold = threshold_seconds
        self.started = time.monotonic()
        self.cpu_started = time.thread_time()
        self.usage_started = thread_usage()
        self.starts = {}
        self.durations = {}
        self.last_event = None

    def __call__(self, name, info):
        # `info` can hold authorization headers, bodies, URLs and exceptions.
        # Only a fixed list of event names crosses this diagnostic boundary.
        phase, separator, event = name.rpartition('.')
        if not separator or phase not in PHASES or event not in {'started', 'complete', 'failed'}:
            return
        at = time.monotonic()
        self.last_event = PHASES[phase] + '.' + event
        if event == 'started':
            self.starts[phase] = at
        elif phase in self.starts:
            label = PHASES[phase]
            self.durations[label] = self.durations.get(label, 0) + max(0, at - self.starts.pop(phase))

    def __enter__(self):
        return self

    def __exit__(self, error_type, error, traceback):
        wall = max(0, time.monotonic() - self.started)
        if wall >= self.threshold or error_type is not None:
            usage = thread_usage()
            delta = ({key: max(0, usage[key] - self.usage_started[key]) for key in usage}
                     if usage is not None and self.usage_started is not None else None)
            emit({'event': 'request', 'at_epoch': time.time(), 'wall_seconds': round(wall, 6),
                  'thread_cpu_seconds': round(max(0, time.thread_time() - self.cpu_started), 6),
                  'thread_usage_delta': delta, 'last_event': self.last_event,
                  'phases_seconds': {key: round(value, 6) for key, value in self.durations.items()},
                  'request_failed': error_type is not None})
        return False
