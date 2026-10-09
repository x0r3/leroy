"""Separate externally triggered production builds from mutations by the test harness."""

import json
from datetime import datetime, timezone

from compare_existing_host_nas_graphato import FOLDER
from nas_ssh import ROOT, run_script

PROGRAM = r'''
import hashlib,json,pathlib,subprocess,xml.etree.ElementTree as ET
info=json.loads(subprocess.check_output(['docker','inspect','jenkins'],text=True))[0]
home=pathlib.Path(next(m['Source'] for m in info['Mounts'] if m['Destination']=='/var/jenkins_home')).resolve(strict=True)
rows={};automatic=True;recognized=True
for name,after in AFTER.items():
 before=BEFORE[name]
 if before==after:continue
 assert after['number']>=before['number'] and after['number']-before['number']<=100
 folder=(home/'jobs'/name).resolve(strict=True);assert folder.is_relative_to(home)
 numbers=range(before['number']+1,after['number']+1) if after['number']>before['number'] else [after['number']]
 builds=[]
 for number in numbers:
  path=folder/'builds'/str(number)/'build.xml';assert path.resolve().is_relative_to(home)
  assert path.stat().st_size<16*1024**2
  with path.open('rb') as source:payload=source.read(16*1024**2+1)
  assert len(payload)<16*1024**2
  tree=ET.fromstring(payload);classes=sorted({entry.tag for entry in tree.iter() if 'Cause' in entry.tag})
  scm='hudson.triggers.SCMTrigger_-SCMTriggerCause' in classes
  timer='hudson.triggers.TimerTrigger_-TimerTriggerCause' in classes
  upstream=bool({'hudson.model.Cause_-UpstreamCause','org.jenkinsci.plugins.workflow.support.steps.build.BuildUpstreamCause'} & set(classes)) and tree.findtext('.//upstreamProject') in BEFORE
  manual='hudson.model.Cause_-UserIdCause' in classes
  auto=scm or timer or upstream;accepted=auto or manual
  automatic=automatic and auto;recognized=recognized and accepted
  builds.append({'number':number,'cause_classes':classes,'automatic_trigger_recognized':auto,
   'user_initiated_trigger_recorded':manual,'recognized_trigger_cause':accepted,
   'manual_actor_identity_proven':False,'xml_sha256':hashlib.sha256(payload).hexdigest()})
 rows[name]={'before':before,'after':after,'builds':builds}
print(json.dumps({'counter_changes':rows,'all_changed_builds_have_independent_automatic_causes':automatic,
 'all_changed_builds_have_recognized_trigger_causes':recognized,'read_only':True,
 'production_modified_by_agent':False,'production_builds_triggered_by_this_task':False,
 'manual_actor_identity_proven':False}))
'''


def collect_activity(before, after):
    """Keep the actual counter delta and verify its native Jenkins cause records."""
    assert before.keys() == after.keys()
    program = 'BEFORE=' + repr(before) + '\nAFTER=' + repr(after) + '\n' + PROGRAM
    result = run_script("python3 - <<'PY'\n" + program + '\nPY\n', ROOT / '.local/nas-ssh.json',
                        sudo=True, timeout=90)
    assert result.returncode == 0, result.stderr[-1000:]
    record = json.loads(result.stdout)
    record.update(at=datetime.now(timezone.utc).isoformat(), original_counters_unchanged=before == after,
                  equal_background_load_claimed=False, performance_comparison=False)
    return record


def main():
    before = json.loads((FOLDER / 'production-jobs-before.json').read_text())['jobs']
    after = json.loads((FOLDER / 'production-jobs-after.json').read_text())['jobs']
    record = collect_activity(before, after)
    (FOLDER / 'production-activity-audit.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'changed_jobs': list(record['counter_changes']), 'recognized_automatic_causes':
                      record['all_changed_builds_have_independent_automatic_causes'],
                      'recognized_trigger_causes': record['all_changed_builds_have_recognized_trigger_causes'],
                      'production_modified_by_agent': False}), flush=True)


if __name__ == '__main__':
    main()
