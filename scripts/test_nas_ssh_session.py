"""Exercise real SSH reuse, exit status, master loss and cleanup on the isolated VM."""

from nas_diagnostic import execute
from nas_ssh import ROOT

PROGRAM = r"""
import json,os,pathlib,signal,subprocess,time
from leroy.actions import ssh_args
scope={}
exec(SOURCE,scope)
shared_ssh=scope['shared_ssh']
args=ssh_args('graphato-vm','root',12225,os.environ['DEPLOY_KEY'],os.environ['KNOWN_HOSTS'])
expected='48b741264f3b8353400649f6b05abf6a9c129233'
with shared_ssh(args) as transport:
 socket=pathlib.Path(transport[transport.index('-S')+1]);folder=socket.parent
 assert folder.stat().st_mode & 0o777==0o700
 start=time.monotonic()
 for i in range(16):
  response=subprocess.run([*transport,'status'],capture_output=True,text=True,timeout=15)
  assert response.returncode==0,response.stderr
  value=json.loads(response.stdout)
  assert value['commit']==expected and value['postdeployProtocol']==2 and value['runtimeImageId'].startswith('sha256:')
 duration=time.monotonic()-start
 rejected=subprocess.run([*transport,'leroy-unsupported-diagnostic'],capture_output=True,text=True,timeout=10)
 assert rejected.returncode!=0
 response=subprocess.run([*transport,'status'],capture_output=True,text=True,timeout=10,check=True)
 assert json.loads(response.stdout)['commit']==expected
 control=[*args[:-1],'-S',str(socket),'-O','exit',args[-1]]
 subprocess.run(control,check=True,capture_output=True,timeout=5)
 for _ in range(100):
  if not socket.exists():break
  time.sleep(.05)
 assert not socket.exists()
 start=time.monotonic()
 failed=[subprocess.run([*transport,'status'],capture_output=True,text=True,timeout=5).returncode for _ in range(10)]
 assert all(code!=0 for code in failed)
 failure_seconds=time.monotonic()-start
assert not folder.exists()
class Expected(Exception):pass
try:
 with shared_ssh(args) as second:
  second_socket=pathlib.Path(second[second.index('-S')+1])
  assert second_socket!=socket
  raise Expected()
except Expected:pass
assert not second_socket.parent.exists()
report={'requests_on_one_connection':18,'successful_status_requests':17,'original_failure_exit_preserved':True,
 'reuse_seconds':duration,'master_loss_failures':len(failed),'master_loss_seconds':failure_seconds,
 'private_socket':True,'per_context_isolation':True,'exception_cleanup':True,'remote_mutations':False}
pathlib.Path('ssh-session.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
"""


if __name__ == "__main__":
    source = (ROOT / "src/leroy/ssh_session.py").read_text()
    execute(
        "ssh-session-v3",
        "SOURCE=" + repr(source) + "\n" + PROGRAM,
        secrets=["graphato-deploy"],
        artifacts=["ssh-session.json"],
    )
