"""Read-only NAS/Jenkins inventory. Never include container environments or credentials."""

import json
from datetime import datetime, timezone

from nas_ssh import ROOT, run_script

JENKINS = r"""
import base64, json, os, urllib.request
auth = base64.b64encode((os.environ['JENKINS_ADMIN_ID'] + ':' + os.environ['JENKINS_ADMIN_PASSWORD']).encode()).decode()
def get(path):
    request = urllib.request.Request('http://127.0.0.1:8080' + path, headers={'Authorization': 'Basic ' + auth})
    with urllib.request.urlopen(request, timeout=20) as response:
        return response.read()
tree = 'jobs[name,color,lastBuild[number,result,building,timestamp,url,actions[lastBuiltRevision[SHA1]]]]'
jobs = json.loads(get('/api/json?tree=' + tree))['jobs']
configs = {}
for job in jobs:
    if job['name'] in JOB_NAMES:
        configs[job['name']] = get('/job/' + job['name'] + '/config.xml').decode()
print(json.dumps({'jobs': jobs, 'configs': configs, 'queue': json.loads(get('/queue/api/json?tree=items[id,task[name],why]'))}))
"""

REMOTE = r"""
import json, os, platform, subprocess
def command(*args):
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=40)
    except subprocess.TimeoutExpired:
        return {'exit_code': 124, 'stdout': '', 'stderr': 'Read-only query exceeded 40 seconds'}
    return {'exit_code': p.returncode, 'stdout': p.stdout.strip(), 'stderr': p.stderr.strip()}
def docker_json(*args):
    return json.loads(subprocess.check_output(['docker', *args], text=True, timeout=40))
containers = []
for name in ['jenkins', 'portainer', 'registry']:
    c = docker_json('inspect', name)[0]
    h = c['HostConfig']
    containers.append({'name': name, 'image_id': c['Image'], 'image_tag': c['Config']['Image'],
        'user': c['Config']['User'], 'running': c['State']['Running'],
        'memory': h['Memory'], 'memory_swap': h['MemorySwap'], 'nano_cpus': h['NanoCpus'],
        'cpu_quota': h['CpuQuota'], 'cpu_period': h['CpuPeriod'],
        'mounts': [{k: m[k] for k in ['Type', 'Source', 'Destination', 'RW']} for m in c['Mounts']],
        'networks': list(c['NetworkSettings']['Networks']),
        'ports': c['NetworkSettings']['Ports']})
versions = {}
for key, argv in {
    'node': ['node', '--version'], 'npm': ['npm', '--version'], 'python': ['python3', '--version'],
    'docker': ['docker', 'version', '--format', '{{json .}}'], 'compose': ['docker', 'compose', 'version'],
    'graphato_docker': ['/var/jenkins_home/tools/graphato/bin/docker', 'version', '--format', '{{json .}}'],
    'graphato_compose': ['/var/jenkins_home/tools/graphato/bin/docker', '--config', '/var/jenkins_home/tools/graphato/docker-config', 'compose', 'version'],
    'identity': ['id'],
}.items():
    versions[key] = command('docker', 'exec', 'jenkins', *argv)
result = {'host': platform.node(), 'kernel': platform.release(), 'architecture': platform.machine(),
    'cpu_count': os.cpu_count(), 'memory': command('free', '-m'), 'disk': command('df', '-h', '/volume1'),
    'engine': docker_json('version', '--format', '{{json .}}'),
    'security_options': docker_json('info', '--format', '{{json .SecurityOptions}}'),
    'containers': containers, 'jenkins_toolchain': versions,
    'networks': command('docker', 'network', 'ls', '--format', '{{.Name}}'),
    'disk_usage': {'skipped': 'Expensive image accounting exceeded the initial timeout'},
    'container_usage': command('docker', 'stats', '--no-stream', '--format', '{{.Name}} {{.CPUPerc}} {{.MemUsage}}')}
inspection = command('docker', 'exec', 'jenkins', 'python3', '-c', JENKINS_SCRIPT)
if inspection['exit_code']:
    raise RuntimeError('Authenticated read-only Jenkins inventory failed')
result['jenkins'] = json.loads(inspection['stdout'])
print(json.dumps(result))
"""


def main():
    inventory = json.loads((ROOT / "docs/jenkins-inventory.json").read_text())
    names = [job["name"] for job in inventory["jobs"]]
    jenkins = "JOB_NAMES = " + repr(names) + "\n" + JENKINS
    remote = "JENKINS_SCRIPT = " + repr(jenkins) + "\n" + REMOTE
    result = run_script("python3 - <<'PY'\n" + remote + "\nPY\n", ROOT / ".local/nas-ssh.json", timeout=150)
    if result.returncode:
        raise SystemExit("NAS inventory failed: " + result.stderr)
    report = json.loads(result.stdout)
    report["captured_at"] = datetime.now(timezone.utc).isoformat()
    output = ROOT / "test-results/nas-parity"
    output.mkdir(parents=True, exist_ok=True)
    configs = report["jenkins"].pop("configs")
    directory = output / "jenkins-configs"
    directory.mkdir(exist_ok=True)
    for name, xml in configs.items():
        (directory / (name + ".xml")).write_text(xml, encoding="utf-8")
    (output / "nas-inventory.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "host": report["host"],
                "cpu_count": report["cpu_count"],
                "jenkins_toolchain": report["jenkins_toolchain"],
                "jobs": report["jenkins"]["jobs"],
                "queue": report["jenkins"]["queue"],
                "container_usage": report["container_usage"],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
