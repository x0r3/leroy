"""Installing diagnostic telemetry must preserve all unrelated NAS configuration."""

import sys
import tomllib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import deploy_nas_worker_transport as deploy  # noqa: E402


@pytest.mark.parametrize('environment', ['', 'environment = { GIT_CONFIG_COUNT = "4" }\n',
                                      '[profiles.graphato.environment]\nGIT_CONFIG_COUNT = "4"\n'])
def test_only_graphato_image_and_diagnostic_flag_change(environment):
    text = ('capacity = 2\n[profiles.graphato]\nimage = "' + deploy.OLD_IMAGE + '"\n'
            'memory = "2g"\n' + environment + '\n[profiles.other]\nimage = "' + deploy.OLD_IMAGE + '"\n')
    before = tomllib.loads(text)
    after = tomllib.loads(deploy.updated_config(text, 'sha256:' + 'a' * 64))
    assert after['profiles']['other'] == before['profiles']['other']
    assert after['profiles']['graphato']['memory'] == '2g'
    assert after['profiles']['graphato']['environment']['LEROY_LEASE_TRACE'] == '1'
    assert before['profiles']['graphato'].get('environment', {}).get('GIT_CONFIG_COUNT') == after['profiles']['graphato']['environment'].get('GIT_CONFIG_COUNT')


def test_unexpected_worker_or_existing_trace_flag_refuses_mutation():
    with pytest.raises(AssertionError):
        deploy.updated_config('[profiles.graphato]\nimage = "other"\n', 'candidate')
    with pytest.raises(AssertionError):
        deploy.updated_config('[profiles.graphato]\nimage = "' + deploy.OLD_IMAGE +
                              '"\nenvironment = { LEROY_LEASE_TRACE = "1" }\n', 'candidate')
