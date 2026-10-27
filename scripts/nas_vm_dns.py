"""Use verified public DNS only inside a freshly restored acceptance VM."""
import inspect
import ipaddress
import json
import re

import nas_release_vm as vm

UPSTREAMS = ('8.8.8.8', '1.1.1.1')
POLICY = {'scope': 'isolated_vm_link_only', 'upstreams': list(UPSTREAMS),
          'application_sources_tests_and_deadlines_changed': False,
          'nas_dns_firewall_or_routes_changed': False}


def reference_binding():
    base = vm.ROOT / 'test-results/nas-parity/followup'
    case = base / 'day-s-rust-leroy-20261015'
    window = base / 'resource-window-day-20261015-s-rust-leroy'
    receipt = json.loads((case / 'published-original-failure-summary.json').read_text())
    assert receipt['run_number'] == 180 and receipt['status'] == 'failed' and receipt['commit'] == vm.COMMIT
    assert receipt['receipt']['cleanupComplete'] is True and receipt['receipt']['cancelled'] is False
    assert receipt['dns_errors'] and all('EAI_AGAIN' in s or 'getaddrinfo' in s for s in receipt['dns_errors'])
    observations = [json.loads(line) for line in (case / 'dns-chain-observations.jsonl').read_text().splitlines()]
    failed = [r for r in observations if {q['server']: q.get('error_type') for q in r['dns_queries']}.get('10.90.0.3') == 'TimeoutError']
    assert failed and any(q['server'] == '8.8.8.8' and q.get('rcode') == 0 and q.get('answers', 0) > 0
                          for q in failed[-1]['dns_queries'])
    closed = json.loads((window / 'window-result.json').read_text())
    assert all(closed[k] is True for k in ('all_seven_original_services_restored_healthy', 'healthy_before_deadline',
                                          'native_jenkins_quiet', 'infrastructure_unchanged'))
    archive = json.loads((window / 'closed-disk-archive.json').read_text())
    assert archive['source_removed'] and archive['sha256'] == archive['copy_sha256']
    files = [case / 'published-original-failure-summary.json', case / 'dns-chain-observations.jsonl',
             window / 'window-result.json', window / 'closed-disk-archive.json']
    return {'reference_failed_original_run': receipt['run_id'], 'exclusive_cause_proven': False,
            'source_evidence_sha256': {p.relative_to(base).as_posix(): vm.digest(p) for p in files}}


def default_link(routes):
    candidates = [r for r in routes if r.get('dst') == 'default']
    assert len(candidates) == 1 and candidates[0].get('gateway') == '10.90.0.2'
    name = candidates[0]['dev']
    assert isinstance(name, str) and re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.:-]{0,14}', name)
    return name


def resolver_addresses(raw):
    return [str(ipaddress.ip_address(words[1])) for line in raw.splitlines()
            if len(words := line.split()) >= 2 and words[0] == 'nameserver']


def apply(folder, engine):
    from nas_original_workload import approval_for

    _, approval = approval_for(folder, engine, current=True)
    assert approval['attempt'] in {'t', 'u', 'v', 'w', 'x', 'y'} and approval['guest_dns_policy'] == POLICY
    assert vm.ROUND == folder.name and vm._GUEST_PIN['labels'] == {
        'io.leroy.nas-release-target': vm.COMMIT, 'io.leroy.comparison': folder.name,
        'io.leroy.engine': engine}
    marker = folder / (engine + '-guest-dns.json')
    assert not marker.exists(), 'Do not silently reconfigure an existing guest'
    program = ('UPSTREAMS=' + repr(UPSTREAMS) + '\nPOLICY=' + repr(POLICY) + '\n' +
               'COMMIT=' + repr(vm.COMMIT) + '\n' +
               'import re,ipaddress\n' + inspect.getsource(default_link) + '\n' +
               inspect.getsource(resolver_addresses) + '\n' + PROGRAM)
    value = json.loads(vm.guest('sudo python3 -B -', program, timeout=90))
    assert value['policy'] == POLICY and value['all_dns_queries_succeeded'] is True
    assert value['stub_nameservers_before'] == value['stub_nameservers_after'] == ['127.0.0.53']
    assert value['docker_host_upstream_nameservers'] == list(UPSTREAMS)
    with marker.open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')
    return value


def observe():
    program = 'UPSTREAMS=' + repr(UPSTREAMS) + '\n' + r'''
import json,pathlib
raw=pathlib.Path('/run/systemd/resolve/resolv.conf').read_text()
servers=[line.split()[1] for line in raw.splitlines() if line.startswith('nameserver ')]
assert servers==list(UPSTREAMS),'Retain a changed DNS environment as an unqualified comparison'
print(json.dumps({'upstreams':servers,'qemu_dns_proxy_bypassed':True,'host_configuration_changed':False}))
'''
    return json.loads(vm.guest('python3 -B -', program, timeout=45))


PROGRAM = r'''
import json,pathlib,secrets,socket,struct,subprocess,time
def call(args):return subprocess.check_output(args,text=True,timeout=10)
assert pathlib.Path('/var/lib/leroy-vm/ready').is_file()
assert call(['systemd-detect-virt']).strip()=='kvm'
active=pathlib.Path('/opt/graphato/current').resolve(strict=True)
assert active.is_relative_to('/opt/graphato/releases')
assert json.loads((active/'manifest.json').read_text())['commit']==COMMIT
routes_before=json.loads(call(['ip','-j','route','show','default']))
link=default_link(routes_before)
stub=pathlib.Path('/etc/resolv.conf');stub_before=resolver_addresses(stub.read_text())
assert stub_before==['127.0.0.53']
upstream=pathlib.Path('/run/systemd/resolve/resolv.conf')
before=resolver_addresses(upstream.read_text())
assert before==['10.90.0.3'],'Fresh original network baseline required'
assert call(['systemctl','is-active','systemd-resolved']).strip()=='active'
call(['resolvectl','dns',link,*UPSTREAMS])
call(['resolvectl','domain',link,'~.'])
call(['resolvectl','flush-caches'])
after=resolver_addresses(upstream.read_text());assert after==list(UPSTREAMS)
assert json.loads(call(['ip','-j','route','show','default']))==routes_before
assert resolver_addresses(stub.read_text())==stub_before
def query(server):
 at=time.monotonic();ident=secrets.randbelow(65536)
 name=b''.join(bytes([len(p)])+p.encode() for p in 'registry.npmjs.org'.split('.'))+b'\0'
 request=struct.pack('!HHHHHH',ident,0x100,1,0,0,0)+name+struct.pack('!HH',1,1)
 with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
  sock.settimeout(3);sock.connect((server,53));sock.send(request);raw=sock.recv(65535)
 header=struct.unpack('!HHHHHH',raw[:12]);assert header[0]==ident and header[1]&15==0 and header[3]>0
 return {'server':server,'rcode':header[1]&15,'answers':header[3],'seconds':time.monotonic()-at}
queries=[query(s) for s in (*UPSTREAMS,'127.0.0.53')]
answers=socket.getaddrinfo('registry.npmjs.org',443,type=socket.SOCK_STREAM)
assert answers
print(json.dumps({'at_epoch':time.time(),'policy':POLICY,'link':link,'source_commit':COMMIT,
 'stub_nameservers_before':stub_before,'stub_nameservers_after':resolver_addresses(stub.read_text()),
 'original_upstream_nameservers':before,'docker_host_upstream_nameservers':after,
 'dns_queries':queries,'libc_address_families':sorted(set(a[0] for a in answers)),
 'all_dns_queries_succeeded':True,'default_route_unchanged':True,'original_ci_dispatched':False}))
'''
