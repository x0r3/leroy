"""DNS configuration must be restricted to the known isolated guest link."""
import importlib
from pathlib import Path

import pytest


@pytest.fixture
def dns(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'scripts'))
    return importlib.import_module('nas_vm_dns')


@pytest.mark.parametrize('routes', [
    [], [{'dst': 'default', 'gateway': '192.168.178.1', 'dev': 'eth0'}],
    [{'dst': 'default', 'gateway': '10.90.0.2', 'dev': '--help'}],
    [{'dst': 'default', 'gateway': '10.90.0.2', 'dev': 'eth0;touch /x'}],
    [{'dst': 'default', 'gateway': '10.90.0.2', 'dev': 'a' * 16}],
    [{'dst': 'default', 'gateway': '10.90.0.2', 'dev': 'eth0'}] * 2,
])
def test_other_routes_or_command_arguments_cannot_select_a_link(dns, routes):
    assert dns.default_link([{'dst': 'default', 'gateway': '10.90.0.2', 'dev': 'enp1s0'}]) == 'enp1s0'
    with pytest.raises(AssertionError):
        dns.default_link(routes)


def test_generated_resolver_file_is_parsed_without_using_comments_as_servers(dns):
    assert dns.resolver_addresses('# managed by resolved\nnameserver 8.8.8.8\nnameserver 1.1.1.1\nsearch .\n') == ['8.8.8.8', '1.1.1.1']


def test_malformed_resolver_is_rejected(dns):
    with pytest.raises(ValueError):
        dns.resolver_addresses('nameserver arbitrary-command\n')
