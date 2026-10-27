"""The explicit open-ended grant permits new bounded windows, never old extensions."""
import hashlib
import json

from nas_ssh import ROOT

REQUEST = 'Das Wartungsfenster ist nun unbegrenzt offen. Fahre fort wie vorgeschlagen'
FILE = 'authorization-open-ended-20261017.json'
SERVICES = ['paperless', 'sonarr', 'radarr', 'sabnzbd', 'plex',
            'yt-downloader-service', 'mail-ingest-service']


def binding(*, maximum_window_seconds=14400):
    assert maximum_window_seconds in {14400, 43200}
    name = FILE if maximum_window_seconds == 14400 else 'authorization-full-release-open-ended-20261017.json'
    path = ROOT / 'test-results/nas-parity/followup' / name
    value = json.loads(path.read_text(encoding='utf-8'))
    assert value['explicit_user_request'] == REQUEST and value['user_approved'] is True
    assert value['open_ended'] is True and value['authorization_end_epoch'] is None
    assert value['services'] == SERVICES and value['source_commit'] == '0ad540dd578033d45e4d0c25d89fbe57b32102a4'
    assert value['maximum_separate_window_seconds'] == maximum_window_seconds and value['restore_margin_seconds'] == 900
    assert value['production_cutover'] is False and value['closed_windows_extended'] is False
    return {'authorization_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'open_ended': True, 'closed_windows_extended': False}
