"""Copy only the production Graphato executable tools into the comparison stack."""

import json

from compare_nas_antares import jenkins_python
from deploy_nas_parity import CREDENTIALS, LOCAL, REMOTE, remote
from nas_ssh import ROOT, upload_file


def main():
    exporter = LOCAL / "export-graphato-tools.py"
    exporter.write_text(
        """import pathlib,sys,tarfile
root=pathlib.Path('/var/jenkins_home/tools/graphato')
names=['bin/docker','docker-config/cli-plugins/docker-buildx','docker-config/cli-plugins/docker-compose']
with tarfile.open(fileobj=sys.stdout.buffer,mode='w|') as archive:
 for name in names:
  path=root/name
  if not path.is_file() or path.is_symlink():raise ValueError('Expected a regular tool executable')
  archive.add(path,arcname=name,recursive=False)
""",
        encoding="utf-8",
    )
    upload_file(exporter, REMOTE + "/export-graphato-tools.py", CREDENTIALS)
    remote(
        f"""cd {REMOTE}
docker exec -i jenkins python3 - < export-graphato-tools.py > graphato-tools.tar
mkdir -p fixtures/graphato-tools
tar -xf graphato-tools.tar -C fixtures/graphato-tools
chmod -R a+rX fixtures/graphato-tools
docker exec leroy-nas-parity-docker-1 docker exec jenkins-parity mkdir -p /var/jenkins_home/tools/graphato
docker exec -i leroy-nas-parity-docker-1 docker exec -i jenkins-parity tar --no-same-owner -xf - -C /var/jenkins_home/tools/graphato < graphato-tools.tar
""",
        timeout=180,
    )
    result = jenkins_python("""import hashlib,json,os,pathlib,subprocess
root=pathlib.Path('/var/jenkins_home/tools/graphato')
env={**os.environ,'DOCKER_CONFIG':str(root/'docker-config')}
tools={n:hashlib.sha256((root/n).read_bytes()).hexdigest() for n in ['bin/docker','docker-config/cli-plugins/docker-buildx','docker-config/cli-plugins/docker-compose']}
versions={name:subprocess.check_output([str(root/'bin/docker'),*args],env=env,text=True).strip() for name,args in {'docker':['--version'],'buildx':['buildx','version'],'compose':['compose','version']}.items()}
print(json.dumps({'sha256':tools,'versions':versions,'copied_credentials':False}))
""")
    evidence = json.loads(result)
    (ROOT / "test-results/nas-parity/graphato-tools.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence["versions"], indent=2))


if __name__ == "__main__":
    main()
