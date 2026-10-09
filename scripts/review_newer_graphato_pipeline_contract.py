"""Read newer native Jenkins revisions without changing the frozen comparison."""

import json
from datetime import datetime, timezone

from nas_ssh import ROOT, run_script
from stage_nas_production_graphato import COMMIT

REVISIONS = (
    '82f52a6079b6fee4a1f18b3c93536cce7d942d78',
    'b88336f489537724d1dddd8ce27039a1df3a1bb3',
)

PROGRAM = r'''
import hashlib,json,subprocess
def git(*args):
 return subprocess.check_output(['docker','exec','jenkins','git','-c',
  'safe.directory=/var/jenkins_home/workspace/graphato-ci','-C',
  '/var/jenkins_home/workspace/graphato-ci',*args],timeout=20)
paths=['Jenkinsfile','Jenkinsfile.acceptance','Jenkinsfile.postdeploy-web',
 'Jenkinsfile.postdeploy-quality','deployments/linux/host/postdeploy.py',
 'deployments/linux/host/runtime_state.py','deployments/linux/host/bootstrap.py',
 'deployments/linux/host/deploy.py','deployments/linux/host/release.py',
 'deployments/linux/host/test_host.py','scripts/ci.py']
existing=set(git('ls-tree','-r','--name-only',BASE).decode().splitlines())
assert all(path in existing for path in paths[:4])
paths=[path for path in paths if path in existing]
rows=[]
for revision in REVISIONS:
 assert git('rev-parse',revision+'^{commit}').decode().strip()==revision
 files=[]
 for path in paths:
  old=git('show',BASE+':'+path);new=git('show',revision+':'+path)
  assert len(old)<=1024**2 and len(new)<=1024**2
  files.append({'path':path,'base_sha256':hashlib.sha256(old).hexdigest(),
   'revision_sha256':hashlib.sha256(new).hexdigest(),'identical':old==new})
 reviewed_diff=git('diff',BASE,revision,'--',*paths,
  'docs/qa/postdeploy-status-and-compose-2026-10-05.md',
  'docs/qa/merge-preflight-and-test-clones-2026-10-06.md').decode()
 assert len(reviewed_diff.encode())<=4*1024**2
 rows.append({'commit':revision,'subject':git('show','-s','--format=%s',revision).decode().strip(),
  'changed_paths':git('diff','--name-only',BASE,revision).decode().splitlines(),
  'pipeline_and_helper_diff':reviewed_diff,
  'reviewed_files':files,'jenkinsfiles_identical':all(f['identical'] for f in files if f['path'].startswith('Jenkinsfile')),
  'selected_host_helpers_identical':all(f['identical'] for f in files if not f['path'].startswith('Jenkinsfile'))})
print(json.dumps({'frozen_comparison_commit':BASE,'newer_revisions':rows,'read_only':True,
 'source_patches_applied':False,'frozen_comparison_changed':False,'newer_workload_parity_claimed':False}))
'''


def main():
    program = 'BASE=' + repr(COMMIT) + '\nREVISIONS=' + repr(REVISIONS) + '\n' + PROGRAM
    result = run_script("python3 - <<'PY'\n" + program + '\nPY\n',
                        ROOT / '.local/nas-ssh.json', sudo=True, timeout=150)
    assert result.returncode == 0, result.stderr[-1000:]
    record = json.loads(result.stdout)
    record['at'] = datetime.now(timezone.utc).isoformat()
    folder = ROOT / 'test-results/nas-parity/followup/production-source-review'
    (folder / 'newer-pipeline-contract.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'revisions': [{key: row[key] for key in
                      ('commit', 'jenkinsfiles_identical', 'selected_host_helpers_identical')}
                     for row in record['newer_revisions']], 'newer_workload_parity_claimed': False}))


if __name__ == '__main__':
    main()
