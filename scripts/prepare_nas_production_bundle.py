"""Prepare a disabled NAS production proposal without installing credentials or deploying."""

import copy
import hashlib
import json
import re
import tomllib
from contextlib import closing
from datetime import datetime, timezone

from compare_nas_antares import client
from nas_ssh import ROOT

from leroy.catalog import catalog
from leroy.schema import Pipeline

EVIDENCE = ROOT / 'test-results/nas-parity/followup/cutover-preparation'
DESTINATION = ROOT / 'infra/nas/production'
NAS = '192.168.178.97'
ROOT_ON_NAS = '/volume1/docker/leroy-production'


def read(name):
    return json.loads((EVIDENCE / name).read_text())


def inline_defaults(name, native):
    """Read literal defaults from the two unused native inline jobs.

    Their config.xml does not yet have ParametersDefinitionProperty. Verify the
    retained script against the current native hash before reading its literals.
    """
    assert name in {'gitea-bootstrap-repo', 'paperless-ngx-bootstrap-rules'}
    source = (ROOT / '.sources/jenkins' / (name + '.Jenkinsfile')).read_text(encoding='utf-8')
    assert hashlib.sha256(source.encode()).hexdigest() == native['inline_script_sha256']
    block = source.split('  parameters {', 1)[1].split('\n  }', 1)[0]
    rows = {}
    for line in block.splitlines():
        if not line.strip():
            continue
        match = re.match(r"\s*(string|booleanParam)\(name: '([^']+)', defaultValue: ('[^']*'|true|false), description:", line)
        assert match, 'Review a nonliteral inline parameter before generating production defaults'
        kind, key, literal = match.groups()
        assert key not in rows
        rows[key] = literal[1:-1] if kind == 'string' else literal
    assert len(rows) == (10 if name == 'gitea-bootstrap-repo' else 5)
    return rows


def toml_value(value):
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, list):
        return '[' + ', '.join(toml_value(item) for item in value) + ']'
    raise TypeError('Unsupported proposal configuration value: ' + type(value).__name__)


def toml_document(value):
    rows = []

    def emit(table, prefix=()):
        if prefix:
            rows.append('[' + '.'.join(json.dumps(part) for part in prefix) + ']')
        for name, item in table.items():
            if not isinstance(item, dict):
                rows.append(json.dumps(name) + ' = ' + toml_value(item))
        rows.append('')
        for name, item in table.items():
            if isinstance(item, dict):
                emit(item, (*prefix, name))

    emit(value)
    text = '\n'.join(rows)
    assert tomllib.loads(text) == value
    return text


def main():
    assert not DESTINATION.exists(), 'Retain the reviewed proposal; do not implicitly replace it'
    config_proof = read('production-configuration-proposal.json')
    native = {row['pipeline']: row for row in read(config_proof['native_mapping_evidence'])['pipelines']}
    expected = {row['pipeline'] for row in config_proof['pipelines']}
    assert len(expected) == 12 and 'antares-ci' not in expected
    canonical = {row.id: row for row in catalog()}
    with closing(client()) as api:
        response = api.get('/api/pipelines')
        response.raise_for_status()
        tested = {row['id']: Pipeline.model_validate(row['spec']) for row in response.json()}
    assert not any(row.enabled for row in tested.values())
    overrides = {'pipelines': {}}
    pipelines, activations = [], []
    for row in config_proof['pipelines']:
        name = row['pipeline']
        proposal = tested[name].model_copy(deep=True)
        original = canonical[name]
        assert proposal.steps == original.steps, 'Review any test-only step alteration before preparing production'
        repository = original.repository.replace('http://gitea:3000/', 'http://' + NAS + ':3000/')
        native_urls = native[name]['repositories']
        if native_urls:
            assert len(set(native_urls)) == 1
            assert repository == native_urls[0].replace('http://gitea:3000/', 'http://' + NAS + ':3000/')
        production_defaults = copy.deepcopy(row['production_defaults'])
        if name in {'gitea-bootstrap-repo', 'paperless-ngx-bootstrap-rules'}:
            production_defaults.update(inline_defaults(name, native[name]))
        for param in proposal.parameters:
            if param.name in production_defaults:
                value = production_defaults[param.name]
                if param.kind == 'boolean':
                    assert value in ('true', 'false')
                    value = value == 'true'
                elif param.kind == 'integer':
                    value = int(value)
                if param.name in {'GIT_URL', 'GITEA_URL'}:
                    value = value.replace('http://gitea:3000', 'http://' + NAS + ':3000')
                param.default = param.validate_value(value)
            else:
                prior = next(item for item in original.parameters if item.name == param.name)
                param.default = prior.default
            # Verification must receive the actual deployed revision explicitly.
            # Never leave the test's frozen release as a production default.
            if param.name == 'RELEASE_COMMIT':
                param.default = None
                param.required = True
        proposal.repository = repository
        proposal.ref = original.ref
        proposal.enabled = False
        proposal.poll_seconds = 0
        proposal.schedule = None
        proposal = Pipeline.model_validate(proposal.model_dump())
        pipelines.append(proposal.model_dump())
        defaults = {param.name: param.default for param in proposal.parameters if param.default is not None}
        overrides['pipelines'][name] = {'enabled': False, 'profile': proposal.profile,
                                        'repository': repository, 'ref': proposal.ref,
                                        'poll_seconds': 0, 'schedule': '', 'defaults': defaults}
        activations.append({'pipeline': name, 'enabled': False,
                            'intended_poll_seconds': original.poll_seconds,
                            'intended_schedule': original.schedule,
                            'original_native_triggers': native[name]['triggers']})
    overrides['pipelines']['antares-ci'] = {'enabled': False, 'profile': 'unconfigured', 'poll_seconds': 0}
    # Validate the controller's startup catalog with exactly these overrides too.
    startup = list(catalog(overrides))
    assert len(startup) == 13 and not any(row.enabled or row.poll_seconds or row.schedule for row in startup)
    runner = read('current-test-runner-public-configuration.json')
    profiles = copy.deepcopy(runner['profiles'])
    assert set(profiles) == {'image-builds', 'gitea', 'graphato', 'operations'}
    # The test daemon uses OCI indexes; the NAS classic store resolves the same
    # archived Linux image by its configuration blob digest.
    identities = read('native-job-image-identity-mapping.json')['images']
    for profile in profiles.values():
        identity = identities[profile['image']]
        assert identity['platform'] == 'linux/amd64'
        assert identity['image_configuration_blob_hash_matches_native_id']
        assert identity['native_rootfs_layers_match_archived_configuration']
        profile['image'] = identity['native_classic_image_id']
    # Anonymous fixture services did not need these groups. Production retains
    # the original Jenkins credential references even when a public read works.
    additional = {'git': ('GIT_USER', 'GIT_PASSWORD'), 'registry': ('REGISTRY_USER', 'REGISTRY_PASSWORD')}
    for pipeline in pipelines:
        fields = profiles[pipeline['profile']].setdefault('secrets', {})
        needed = {secret for step in pipeline['steps'] for secret in step['secrets']}
        for secret in needed - fields.keys():
            assert secret in additional, 'Review missing production secret group: ' + secret
            fields[secret] = {key: '/production-secrets/' + secret + '/' + key for key in additional[secret]}
    secret_paths = {}
    for profile in profiles.values():
        profile['network'] = 'home-lab-stack_default'
        profile.pop('host_mappings', None)
        profile['mounts'] = []
        env = profile.setdefault('environment', {})
        if 'CI_REGISTRY_URL' in env:
            env['CI_REGISTRY_URL'] = '127.0.0.1:5005'
        for group, fields in profile.get('secrets', {}).items():
            for key in fields:
                fields[key] = '/production-secrets/' + group + '/' + key
                secret_paths.setdefault(group, {})[key] = fields[key]
    graph = profiles['graphato']
    # The original native BuildKit uses host networking and the NAS loopback registry.
    # This trusted Graphato profile preserves that context without daemon changes.
    graph['network'] = 'host'
    graph['environment'].update(GRAPHATO_REGISTRY_PUSH='127.0.0.1:5005',
                                GRAPHATO_REGISTRY_API='http://127.0.0.1:5005')
    graph['mounts'] = ['type=bind,source=' + ROOT_ON_NAS + '/tools/docker,target=/usr/local/bin/docker,readonly',
                       'type=bind,source=' + ROOT_ON_NAS + '/tools/cli-plugins,target=/usr/local/lib/docker/cli-plugins,readonly']
    graph['graphato'].update(builder_name='leroy-graphato-production',
                             repository='http://' + NAS + ':3000/gitea-admin/graphato.git',
                             host='87.106.133.233', port=22,
                             desktop_releases='/volume1/Releases/graphato-desktop')
    music = read('production-execution-requirements.json')['music_source_mounts']
    profiles['operations']['mounts'] = ['type=bind,source=' + item['host_source'] + ',target=' +
                                       item['container_destination'] + ',readonly' for item in music]
    assert all(row['image'].startswith('sha256:') for row in profiles.values())
    runner_config = {'capacity': runner['capacity'], 'profiles': profiles}
    controls = {row['service']: row['image_id'] for row in read('production-control-images-desktop-destination.json')['services']}
    compose = '''name: leroy-production
x-logging: &logs
  driver: json-file
  options: {max-size: "10m", max-file: "3"}
services:
  postgres:
    image: POSTGRES_IMAGE
    pull_policy: never
    logging: *logs
    mem_limit: 256m
    memswap_limit: 256m
    mem_reservation: 128m
    cpus: 0.5
    environment:
      POSTGRES_DB: leroy
      POSTGRES_USER: leroy
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets: [db_password]
    volumes: [database:/var/lib/postgresql]
    healthcheck:
      test: [CMD-SHELL, "pg_isready -U leroy -d leroy"]
      interval: 3s
      retries: 30
    restart: unless-stopped
  controller:
    image: CONTROLLER_IMAGE
    pull_policy: never
    logging: *logs
    mem_limit: 256m
    memswap_limit: 256m
    mem_reservation: 128m
    cpus: 1
    env_file: config/controller.env
    environment:
      LEROY_ADMIN_PASSWORD_FILE: /run/secrets/admin_password
      LEROY_RUNNER_TOKEN_FILE: /run/secrets/runner_token
      LEROY_ORIGIN: http://192.168.178.97:8089
      LEROY_COOKIE_SECURE: "false"
    secrets: [admin_password, runner_token]
    ports: ["192.168.178.97:8089:8088"]
    volumes: [data:/data, "./config/leroy.toml:/config/leroy.toml:ro"]
    depends_on:
      postgres: {condition: service_healthy}
    healthcheck:
      test: [CMD, python, -c, "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8088/health/ready')"]
      interval: 5s
      retries: 30
    restart: unless-stopped
  runner:
    image: RUNNER_IMAGE
    pull_policy: never
    logging: *logs
    mem_limit: 192m
    memswap_limit: 192m
    mem_reservation: 64m
    cpus: 0.5
    environment:
      LEROY_CONTROLLER: http://192.168.178.97:8089
      LEROY_RUNNER_TOKEN_FILE: /run/secrets/runner_token
      LEROY_RUNNER_ID: runner-nas-production
    secrets: [runner_token]
    volumes:
      - ./config/runner.toml:/config/runner.toml:ro
      - ./config/production-secrets:/production-secrets:ro
      - /var/run/docker.sock:/var/run/docker.sock
    depends_on:
      controller: {condition: service_healthy}
    restart: unless-stopped
volumes:
  database:
  data:
secrets:
  db_password: {file: config/db_password}
  admin_password: {file: config/admin_password}
  runner_token: {file: config/runner_token}
'''
    for service in ('postgres', 'controller', 'runner'):
        compose = compose.replace(service.upper() + '_IMAGE', controls[service])
    for pipeline in pipelines:
        needed = {secret for step in pipeline['steps'] for secret in step['secrets']}
        assert needed <= profiles[pipeline['profile']].get('secrets', {}).keys()
    DESTINATION.mkdir()
    (DESTINATION / 'config').mkdir()
    (DESTINATION / 'compose.yaml').write_text(compose)
    (DESTINATION / 'config/leroy.toml').write_text(toml_document(overrides), encoding='utf-8')
    (DESTINATION / 'config/runner.toml').write_text(toml_document(runner_config), encoding='utf-8')
    (DESTINATION / 'config/controller.env.example').write_text(
        'LEROY_DATABASE_URL=postgresql+psycopg://leroy:REPLACE_WITH_URL_ENCODED_DB_PASSWORD@postgres/leroy\n')
    (DESTINATION / 'pipelines.json').write_text(json.dumps(pipelines, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (DESTINATION / 'activation-plan.json').write_text(json.dumps(activations, indent=2) + '\n')
    (DESTINATION / 'secret-file-mapping.json').write_text(json.dumps(secret_paths, indent=2) + '\n')
    phone = EVIDENCE / 'smartphone-known-hosts'
    if phone.is_file():
        (DESTINATION / 'smartphone-known-hosts').write_bytes(phone.read_bytes())
    body = '\n'.join((DESTINATION / 'config' / name).read_text() for name in ('leroy.toml', 'runner.toml'))
    assert not any(item in body for item in ('/test-secrets', '/fixtures/', '/sources/', 'graphato-vm', 'parity-vm', 'registry:5000'))
    assert all(not row['enabled'] and not row['poll_seconds'] and row['schedule'] is None for row in pipelines)
    files = {str(path.relative_to(DESTINATION)): hashlib.sha256(path.read_bytes()).hexdigest()
             for path in DESTINATION.rglob('*') if path.is_file()}
    report = {'at': datetime.now(timezone.utc).isoformat(), 'files': files,
              'pipelines': len(pipelines), 'profiles': len(profiles), 'all_pipeline_steps_match_tested_and_canonical': True,
              'all_automatic_triggers_disabled': True, 'test_endpoints_and_mounts_removed': True,
              'native_daemon_and_original_loopback_registry_context_retained': True,
              'credentials_installed': False, 'tools_installed': False, 'deployed': False,
              'actual_credential_permissions_validated': False, 'production_replacement_ready': False}
    (EVIDENCE / 'production-bundle-preparation.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('pipelines', 'profiles', 'all_automatic_triggers_disabled', 'deployed', 'production_replacement_ready')}), flush=True)


if __name__ == '__main__':
    main()
