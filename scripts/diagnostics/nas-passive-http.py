"""Record bounded HTTP metadata at an isolated server interface; never retain packets."""

import argparse
import collections
import ctypes
import hashlib
import hmac
import json
import os
import re
import signal
import socket
import struct
import time


class HttpStream:
    def __init__(self, request, emit, pending, allocate, identities=None):
        self.request, self.emit, self.pending, self.allocate = request, emit, pending, allocate
        self.identities = identities
        self.buffer = bytearray()
        self.message = None
        self.remaining = 0
        self.chunked = False
        self.chunk_remaining = None
        self.body = bytearray()
        self.chunk_trailers = False

    def finish(self, now):
        row = self.message
        if self.identities:
            self.identities.complete(self.request, row, self.body, self.emit)
        if self.request:
            if row['route'] == '/api/v1/commands' and self.body:
                try:
                    command = json.loads(self.body).get('command')
                except (ValueError, AttributeError):
                    command = None
                if isinstance(command, str) and re.fullmatch('[A-Za-z][A-Za-z0-9]{0,100}', command):
                    row['command'] = command
            row['request_id'] = self.allocate()
            self.pending.append(row)
            self.emit({'kind': 'request', **row, 'body_received_ns': now})
        self.message = None
        self.body.clear()
        self.chunk_remaining = None
        self.chunk_trailers = False

    def consume(self, count):
        if (self.request and self.message['route'] == '/api/v1/commands') or (
                self.identities and self.message.get('route') == '/api/v1/auth/login') or (
                self.request and self.identities and self.message.get('route') == '/api/v1/browser/session'):
            if len(self.body) + count > 1024**2:
                raise ValueError('Request body exceeds observation bound')
            self.body.extend(self.buffer[:count])
        del self.buffer[:count]

    def feed(self, data, now):
        self.buffer.extend(data)
        if len(self.buffer) > 2 * 1024**2:
            raise ValueError('Stream exceeds observation bound')
        while self.buffer:
            if self.message is None:
                end = self.buffer.find(b'\r\n\r\n')
                if end < 0:
                    if len(self.buffer) > 65536:
                        raise ValueError('Header exceeds observation bound')
                    return
                lines = bytes(self.buffer[:end]).split(b'\r\n')
                del self.buffer[:end + 4]
                headers = {}
                for line in lines[1:]:
                    name, separator, value = line.partition(b':')
                    if separator and name.lower() in {b'content-length', b'transfer-encoding', b'retry-after'}:
                        headers[name.lower()] = value.strip()
                if self.request:
                    method, target, protocol = lines[0].split(b' ', 2)
                    if not protocol.startswith(b'HTTP/1.'):
                        raise ValueError('Unexpected request protocol')
                    route = target.split(b'?', 1)[0].decode('ascii')
                    allowed = {'/api/v1/commands', '/api/v1/events', '/api/v1/info', '/api/v1/health'}
                    if self.identities:
                        allowed.add('/api/v1/auth/login')
                        allowed.add('/api/v1/browser/session')
                    if route not in allowed:
                        route = 'other-api'
                    self.message = {'method': method.decode('ascii'), 'route': route,
                                    'headers_received_ns': now, 'command': None}
                    if self.identities:
                        self.identities.headers(self.message, lines[1:])
                else:
                    protocol, status, *_ = lines[0].split(b' ')
                    if not protocol.startswith(b'HTTP/1.'):
                        raise ValueError('Unexpected response protocol')
                    self.message = {'status': int(status), 'response_headers_ns': now}
                    retry = headers.get(b'retry-after', b'')
                    if retry.isdigit() and len(retry) < 5:
                        self.message['retry_after_seconds'] = int(retry)
                    request = self.pending.popleft() if self.pending and int(status) >= 200 else {}
                    self.message = {**request, **self.message}
                    if self.identities:
                        self.identities.response_headers(self.message, lines[1:], self.emit)
                    if int(status) >= 200:
                        # Status is already authoritative at the header boundary.
                        # Long-lived event bodies must not hide their HTTP status.
                        self.emit({'kind': 'response', **self.message})
                self.chunked = b'chunked' in headers.get(b'transfer-encoding', b'').lower()
                self.remaining = int(headers.get(b'content-length', b'0'))
                if self.remaining < 0 or self.remaining > 64 * 1024**2:
                    raise ValueError('Message exceeds observation bound')
                if not self.chunked and self.remaining == 0:
                    self.finish(now)
                    continue
            if not self.chunked:
                count = min(self.remaining, len(self.buffer))
                self.consume(count)
                self.remaining -= count
                if self.remaining:
                    return
                self.finish(now)
                continue
            if self.chunk_trailers:
                if self.buffer.startswith(b'\r\n'):
                    del self.buffer[:2]
                    self.finish(now)
                    continue
                end = self.buffer.find(b'\r\n\r\n')
                if end < 0:
                    return
                del self.buffer[:end + 4]
                self.finish(now)
                continue
            if self.chunk_remaining is None:
                end = self.buffer.find(b'\r\n')
                if end < 0:
                    return
                self.chunk_remaining = int(self.buffer[:end].split(b';', 1)[0], 16)
                del self.buffer[:end + 2]
                if self.chunk_remaining == 0:
                    self.chunk_trailers = True
                    continue
                if self.chunk_remaining > 64 * 1024**2:
                    raise ValueError('Chunk exceeds observation bound')
            if len(self.buffer) < self.chunk_remaining + 2:
                return
            self.consume(self.chunk_remaining)
            if self.buffer[:2] != b'\r\n':
                raise ValueError('Unexpected chunk terminator')
            del self.buffer[:2]
            self.chunk_remaining = None


class ClientIdentities:
    """Correlate accounts and tokens only through per-observer HMAC pseudonyms.

    The random key, credentials, usernames and request bodies are never emitted.
    Pseudonyms cannot be compared across runs. This does not observe browser DOM.
    """

    def __init__(self, key=None):
        self.key = os.urandom(32) if key is None else key
        assert len(self.key) == 32

    def digest(self, value):
        return hmac.new(self.key, value.encode(), hashlib.sha256).hexdigest()

    def headers(self, row, lines):
        for line in lines:
            name, separator, value = line.partition(b':')
            if separator and name.lower() == b'authorization':
                token = value.strip().decode('ascii', errors='replace')
                if token.lower().startswith('bearer ') and len(token) <= 8192:
                    row['principal'] = self.digest(token[7:])
            if separator and name.lower() == b'cookie':
                for pair in value.decode('ascii', errors='replace').split(';'):
                    cookie, _, token = pair.strip().partition('=')
                    if cookie in {'__Host-graphato-session', 'graphato-dev-session'} and 0 < len(token) <= 8192:
                        row['browser_principal'] = self.digest(token)

    def response_headers(self, row, lines, emit):
        for line in lines:
            name, separator, value = line.partition(b':')
            if not separator or name.lower() != b'set-cookie':
                continue
            cookie, _, token = value.decode('ascii', errors='replace').split(';', 1)[0].strip().partition('=')
            if cookie in {'__Host-graphato-session', 'graphato-dev-session'} and 0 < len(token) <= 8192:
                row['browser_principal'] = self.digest(token)
                if row.get('account'):
                    emit({'kind': 'browser-session-binding', 'account': row['account'],
                          'browser_principal': row['browser_principal'], 'request_id': row.get('request_id')})

    def complete(self, request, row, body, emit):
        if not body:
            return
        try:
            data = json.loads(body)
        except (ValueError, UnicodeError):
            return
        if not isinstance(data, dict):
            return
        if row.get('route') == '/api/v1/commands' and request:
            client = data.get('clientId')
            if isinstance(client, str) and 0 < len(client) <= 512:
                row['client'] = self.digest(client)
                row['direct_test_client'] = client.startswith('demo-services-')
        elif row.get('route') in {'/api/v1/auth/login', '/api/v1/browser/session'}:
            if request and isinstance(data.get('username'), str):
                row['account'] = self.digest(data['username'])
            elif not request and isinstance(data.get('token'), str) and row.get('account'):
                emit({'kind': 'login-binding', 'account': row['account'],
                      'principal': self.digest(data['token']), 'request_id': row.get('request_id')})


class TcpStream:
    def __init__(self, http):
        self.http = http
        self.next_sequence = None
        self.waiting = {}

    def feed(self, sequence, payload, now, syn=False):
        if syn:
            sequence += 1
        if self.next_sequence is not None:
            # TCP's wire sequence wraps at 32 bits; retain an unwrapped stream.
            sequence += ((self.next_sequence - sequence + 2**31) // 2**32) * 2**32
        if self.next_sequence is None:
            self.next_sequence = sequence
        if not payload:
            return
        if sequence < self.next_sequence:
            payload = payload[self.next_sequence - sequence:]
            sequence = self.next_sequence
        if not payload:
            return
        if sequence > self.next_sequence:
            self.waiting[sequence] = (payload, now)
            if len(self.waiting) > 64 or sum(len(v[0]) for v in self.waiting.values()) > 1024**2:
                raise ValueError('Reassembly exceeds observation bound')
            return
        self.http.feed(payload, now)
        self.next_sequence += len(payload)
        while self.waiting and min(self.waiting) <= self.next_sequence:
            position = min(self.waiting)
            following, stamp = self.waiting.pop(position)
            following = following[self.next_sequence - position:]
            if not following:
                continue
            self.http.feed(following, stamp)
            self.next_sequence += len(following)


def filter_http(packet):
    """Filter IPv4 TCP/8042 in the kernel before copying traffic into Python."""
    class Filter(ctypes.Structure):
        _fields_ = [('code', ctypes.c_ushort), ('jt', ctypes.c_ubyte),
                    ('jf', ctypes.c_ubyte), ('k', ctypes.c_uint)]

    class Program(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ushort), ('instructions', ctypes.POINTER(Filter))]

    instructions = [
        (0x28, 0, 0, 12),       # Ethernet type.
        (0x15, 0, 9, 0x0800),   # IPv4 only.
        (0x30, 0, 0, 23),       # IP protocol.
        (0x15, 0, 7, 6),        # TCP only.
        (0x28, 0, 0, 20),       # IP fragment flags and offset.
        (0x45, 5, 0, 0x3fff),   # Do not parse fragments as TCP headers.
        (0xb1, 0, 0, 14),       # X = IPv4 header length.
        (0x48, 0, 0, 14),       # TCP source port.
        (0x15, 3, 0, 8042),
        (0x48, 0, 0, 16),       # TCP destination port.
        (0x15, 1, 0, 8042),
        (0x06, 0, 0, 0),        # Reject.
        (0x06, 0, 0, 65535),    # Capture.
    ]
    filters = (Filter * len(instructions))(*(Filter(*row) for row in instructions))
    program = Program(len(filters), filters)
    packet.setsockopt(socket.SOL_SOCKET, 26, bytes(program))  # SO_ATTACH_FILTER.


def join_fixture_network(pid, *, keep_namespace_caps=False):
    """Join only the inspected fixture namespace; retain solely NET_RAW after it.

    Docker must not register a network-mode dependency on the server: that would
    prevent the original fixture cleanup from removing its container.
    """
    assert pid > 1
    libc = ctypes.CDLL(None, use_errno=True)
    descriptor = os.open('/proc/' + str(pid) + '/ns/net', os.O_RDONLY)
    try:
        if libc.setns(descriptor, 0x40000000) != 0:  # CLONE_NEWNET.
            raise OSError(ctypes.get_errno(), 'Cannot join inspected fixture network')
    finally:
        os.close(descriptor)

    if not keep_namespace_caps:
        drop_namespace_caps()


def drop_namespace_caps():
    """Retain only packet reception after namespace entry and socket setup."""
    libc = ctypes.CDLL(None, use_errno=True)

    class Header(ctypes.Structure):
        _fields_ = [('version', ctypes.c_uint32), ('pid', ctypes.c_int)]

    class Capabilities(ctypes.Structure):
        _fields_ = [('effective', ctypes.c_uint32), ('permitted', ctypes.c_uint32), ('inheritable', ctypes.c_uint32)]

    header = Header(0x20080522, 0)
    caps = (Capabilities * 2)(Capabilities(1 << 13, 1 << 13, 0), Capabilities(0, 0, 0))
    if libc.capset(ctypes.byref(header), caps) != 0:
        raise OSError(ctypes.get_errno(), 'Cannot drop namespace-entry capability')


def self_check():
    rows, pending = [], collections.deque()
    counter = iter(range(1, 100))
    request = HttpStream(True, rows.append, pending, lambda: next(counter))
    response = HttpStream(False, rows.append, pending, lambda: next(counter))
    body = b'{"command":"sendSessionPrompt","args":{"password":"PRIVATE_TEST_MARKER"}}'
    wire = b'POST /api/v1/commands HTTP/1.1\r\nAuthorization: Bearer PRIVATE_TEST_MARKER\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body
    tcp = TcpStream(request)
    tcp.feed(100, b'', 1, syn=True)
    tcp.feed(121, wire[20:], 3)
    tcp.feed(101, wire[:20], 2)
    tcp.feed(101, wire[:20], 4)
    response.feed(b'HTTP/1.1 429 Too Many Requests\r\nTransfer-Encoding: chunked\r\nRetry-After: 1\r\n\r\n3\r\nabc\r\n', 5)
    assert len(rows) == 2 and rows[1]['status'] == 429, 'Response headers must not wait for body completion'
    response.feed(b'0\r\n\r\n', 6)
    assert len(rows) == 2 and rows[0]['command'] == 'sendSessionPrompt'
    assert rows[1]['status'] == 429 and rows[1]['request_id'] == 1
    assert 'PRIVATE_TEST_MARKER' not in json.dumps(rows)
    assert not pending
    wrapped_rows = []
    wrapped = TcpStream(HttpStream(True, wrapped_rows.append, collections.deque(), lambda: 99))
    start = 2**32 - 20
    wrapped.feed(start, wire[:30], 7)
    wrapped.feed((start + 30) % 2**32, wire[30:], 8)
    assert len(wrapped_rows) == 1 and wrapped_rows[0]['request_id'] == 99
    print(json.dumps({'metadata_parser_checks_passed': True, 'credentials_not_emitted': True}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output')
    parser.add_argument('--network-namespace-pid', type=int)
    parser.add_argument('--self-check', action='store_true')
    parser.add_argument('--pseudonymous-clients', action='store_true')
    parser.add_argument('--identity-key-file')
    parser.add_argument('--packet-buffer-bytes', type=int, default=0)
    args = parser.parse_args()
    if args.self_check:
        self_check()
        return
    assert args.output and os.path.isabs(args.output)
    assert args.packet_buffer_bytes in (0, 8*1024**2)
    if args.network_namespace_pid:
        join_fixture_network(args.network_namespace_pid, keep_namespace_caps=bool(args.packet_buffer_bytes))
    fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    rows = 0
    counts = collections.Counter()
    stopped = False
    connections = {}
    request_id = 0
    assert not args.identity_key_file or args.pseudonymous_clients
    key = None
    if args.identity_key_file:
        with open(args.identity_key_file, 'rb') as stream:
            key = stream.read(33)
        assert len(key) == 32
    identities = ClientIdentities(key) if args.pseudonymous_clients else None

    def allocate():
        nonlocal request_id
        request_id += 1
        return request_id

    with os.fdopen(fd, 'w') as output:
        def emit(row):
            nonlocal rows
            if rows >= 250000:
                raise ValueError('Metadata exceeds observation bound')
            output.write(json.dumps(row, separators=(',', ':')) + '\n')
            rows += 1

        def stop(*_):
            nonlocal stopped
            stopped = True

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        # ETH_P_ALL registers the outgoing tap as well as incoming traffic.
        # ETH_P_IP misses server egress on bridge interfaces (loopback disguises
        # that error). The kernel BPF filter still selects only IPv4 TCP/8042.
        # Linux net/core/dev.c: dev_queue_xmit_nit walks only ptype_all lists.
        packet = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(0x0003))
        if args.packet_buffer_bytes:
            # SO_RCVBUFFORCE changes only this diagnostic socket, without
            # modifying the guest/server network sysctls. NET_ADMIN is dropped
            # immediately afterwards; it is never retained while capturing.
            packet.setsockopt(socket.SOL_SOCKET, 33, args.packet_buffer_bytes)
            drop_namespace_caps()
        receive_buffer = packet.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
        # Compose can attach the application and database networks in either
        # interface order. Capture only TCP/8042 across this private namespace.
        filter_http(packet)
        packet.setsockopt(socket.SOL_SOCKET, 35, 1)  # Linux SO_TIMESTAMPNS (64-bit timespec).
        packet.settimeout(0.5)
        emit({'kind': 'observer-start', 'at_ns': time.time_ns(), 'raw_packets_persisted': False,
              'metadata_schema_version': 2, 'packet_socket_protocol': 'ETH_P_ALL',
              'timestamp_source': 'kernel_packet_realtime_ns',
              'docker_server_removal_dependency_created': False,
              'pseudonymous_client_metadata': bool(identities), 'browser_dom_observed': False,
              'receive_buffer_bytes': receive_buffer,
              'namespace_entry_capability_dropped': bool(args.network_namespace_pid)})
        output.flush()
        print('Passive metadata observer ready', flush=True)
        deadline = time.monotonic() + 3600
        while not stopped and time.monotonic() < deadline:
            try:
                frame, ancillary, flags, _ = packet.recvmsg(65535, 128)
            except socket.timeout:
                continue
            timestamps = [data for level, kind, data in ancillary if level == socket.SOL_SOCKET and kind == 35]
            if timestamps:
                seconds, nanos = struct.unpack('@qq', timestamps[0][:16])
                now = seconds * 10**9 + nanos
            else:
                counts['kernel_timestamp_missing'] += 1
                now = time.time_ns()
            if flags & socket.MSG_TRUNC:
                counts['truncated_packets'] += 1
                continue
            if len(frame) < 54 or frame[12:14] != b'\x08\x00':
                continue
            ip = 14
            header = (frame[ip] & 15) * 4
            total = struct.unpack_from('!H', frame, ip + 2)[0]
            if frame[ip + 9] != 6 or header < 20:
                continue
            if total > len(frame) - 14:
                counts['truncated_packets'] += 1
                continue
            tcp = ip + header
            source_port, target_port, sequence = struct.unpack_from('!HHI', frame, tcp)
            if 8042 not in (source_port, target_port):
                continue
            tcp_header = (frame[tcp + 12] >> 4) * 4
            flags = frame[tcp + 13]
            payload = frame[tcp + tcp_header:ip + total]
            request = target_port == 8042
            counts['request_direction_packets' if request else 'response_direction_packets'] += 1
            peer = (frame[ip + 12:ip + 16], source_port) if request else (frame[ip + 16:ip + 20], target_port)
            if peer not in connections:
                if len(connections) >= 512:
                    counts['connection_bound_exceeded'] += 1
                    continue
                pending = collections.deque()
                connections[peer] = {True: TcpStream(HttpStream(True, emit, pending, allocate, identities)),
                                     False: TcpStream(HttpStream(False, emit, pending, allocate, identities))}
            counts['selected_packets'] += 1
            try:
                connections[peer][request].feed(sequence, payload, now, bool(flags & 2))
            except (ValueError, UnicodeError, IndexError, TypeError):
                counts['unparsed_streams'] += 1
                del connections[peer]
            if flags & 5:
                if any(s.waiting for s in connections.get(peer, {}).values()):
                    counts['incomplete_tcp_streams'] += 1
                connections.pop(peer, None)
        received, dropped = struct.unpack('II', packet.getsockopt(263, 6, 8))  # SOL_PACKET, PACKET_STATISTICS.
        counts.update(kernel_packets_received=received, kernel_packets_dropped=dropped)
        packet.close()
        counts['incomplete_tcp_streams'] += sum(bool(s.waiting) for c in connections.values() for s in c.values())
        emit({'kind': 'observer-end', 'at_ns': time.time_ns(), 'counts': dict(counts),
              'raw_packets_persisted': False, 'metadata_rows': rows})
        output.flush()


if __name__ == '__main__':
    main()
