"""Exercise real authenticated Git against the private repository on test Gitea."""

import subprocess

from test_support import DIN

program = r"""
import base64,json,pathlib,subprocess,tempfile,urllib.request
from leroy.git_auth import git_environment
user=pathlib.Path('/test-secrets/gitea-user').read_text().strip()
password=pathlib.Path('/test-secrets/gitea-password').read_text().strip()
base='http://gitea-test:3000'
repo=user+'/leroy-migrated'
headers={'Authorization':'Basic '+base64.b64encode((user+':'+password).encode()).decode(),'Content-Type':'application/json'}
request=urllib.request.Request(base+'/api/v1/repos/'+repo,headers=headers)
with urllib.request.urlopen(request) as response: info=json.load(response)
assert info['private'] is True
if info['empty']:
 data={'content':base64.b64encode(b'Leroy private SCM acceptance\n').decode(),'message':'Isolated test fixture','branch':'main'}
 request=urllib.request.Request(base+'/api/v1/repos/'+repo+'/contents/README.md',data=json.dumps(data).encode(),headers=headers,method='POST')
 with urllib.request.urlopen(request) as response: assert response.status==201
url=base+'/'+repo+'.git'
with git_environment({'GIT_USER':user,'GIT_PASSWORD':password}) as env:
 result=subprocess.run(['git','ls-remote',url,'refs/heads/main'],env=env,text=True,capture_output=True)
 assert result.returncode==0 and len(result.stdout.split()[0])==40
 with tempfile.TemporaryDirectory() as directory:
  result=subprocess.run(['git','clone','--depth','1','--branch','main',url,directory],env=env,text=True,capture_output=True)
  assert result.returncode==0 and pathlib.Path(directory,'README.md').is_file()
with git_environment({'GIT_USER':'invalid','GIT_PASSWORD':'invalid'}) as env:
 result=subprocess.run(['git','ls-remote',url],env=env,text=True,capture_output=True)
 assert result.returncode!=0
print('Private Git: authenticated ls-remote and clone passed; invalid credentials rejected')
"""
result = subprocess.run(
    [
        "docker",
        "exec",
        "-i",
        DIN,
        "docker",
        "run",
        "--rm",
        "-i",
        "--network",
        "leroy-jobs",
        "--mount",
        "type=bind,source=/test-secrets,target=/test-secrets,readonly",
        "--entrypoint",
        "python",
        "leroy-job:local",
        "-",
    ],
    input=program,
    text=True,
    capture_output=True,
)
if result.returncode:
    raise SystemExit("Private Git acceptance failed; inspect the isolated test setup")
print(result.stdout.strip())
