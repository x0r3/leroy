import subprocess

source = subprocess.Popen(["docker", "save", "leroy-job:local"], stdout=subprocess.PIPE)
try:
    subprocess.run(
        ["docker", "exec", "-i", "leroy-test-docker-1", "docker", "load"], stdin=source.stdout, check=True
    )
finally:
    source.stdout.close()
if source.wait():
    raise SystemExit("Image export failed")
