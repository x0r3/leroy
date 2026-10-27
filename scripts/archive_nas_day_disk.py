"""Archive only a closed disk registered in the current authorized day window."""

import json

import nas_release_vm as vm
from archive_nas_night_disk import PROGRAM
from nas_followup_support import production_jobs
from nas_gitea_target import idle


def archive(folder, approval, engine):
    from run_nas_day_window import validate_approval

    validate_approval(approval)
    assert folder.name == approval['window'] and engine == approval['engine']
    round_name, = approval['comparison_rounds']
    idle()
    before = production_jobs()
    assert not before['active_builds'] and before['older_concurrent_build_history_verified']
    marker = folder / 'closed-disk-archive.json'
    assert not marker.exists(), 'Retain the first archive outcome'
    constants = {'ROUND': round_name, 'ENGINE': engine, 'COMMIT': vm.COMMIT,
                 'WINDOW': folder.name, 'EXPECTED': before['jobs']}
    source = PROGRAM.replace('archived-night-20261014', 'archived-day-20261015')
    source = source.replace("assert not info['State']['Running'] and info['Config']['Labels']['io.leroy.nas-release-target']==COMMIT",
        "assert not info['State']['Running'] and info['Config']['Labels']['io.leroy.nas-release-target']==COMMIT\n assert info['Config']['Labels']['io.leroy.comparison']==ROUND and info['Config']['Labels']['io.leroy.engine']==ENGINE")
    program = ''.join(k + '=' + repr(v) + '\n' for k, v in constants.items()) + source
    proof = json.loads(vm.remote(program, sudo=True, timeout=2400))
    assert proof['source_removed'] and proof['copy_sha256'] == proof['sha256']
    marker.write_text(json.dumps(proof, indent=2) + '\n')
    return proof
