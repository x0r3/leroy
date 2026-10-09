"""Check equivalent music-sync destinations in the isolated Linux VM."""

import argparse
import json

from nas_ssh import ROOT
from prepare_nas_vm import guest

OUTPUT = ROOT / "test-results/nas-parity/aligned/music-library-sync-smartphone"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase", choices=["prepare", "capture"])
    parser.add_argument("engine", choices=["jenkins", "leroy"])
    args = parser.parse_args()
    if args.phase == "prepare":
        program = """from pathlib import Path
root=Path('/var/tmp/leroy-parity-music')
assert not root.is_symlink()
"""
        if args.engine == "leroy":
            assert (OUTPUT / "jenkins-target-state.json").exists()
            pair = json.loads((OUTPUT / "pair.json").read_text())
            assert pair["jenkins"]["result"] and not pair["jenkins"]["building"]
            program += "archive=Path('/var/tmp/leroy-parity-music-jenkins')\nassert root.is_dir() and not archive.exists()\nroot.rename(archive)\n"
        else:
            program += "assert not root.exists()\n"
        guest("sudo python3 -", program)
        print("Empty music-sync destination verified for", args.engine)
        return
    program = """import hashlib,json,pathlib,stat
root=pathlib.Path('/var/tmp/leroy-parity-music/Music')
assert root.is_dir() and not root.is_symlink()
files=[]
for path in sorted(root.rglob('*')):
 assert not path.is_symlink()
 if path.is_file():
  info=path.stat()
  files.append({'path':str(path.relative_to(root)),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'mode':oct(stat.S_IMODE(info.st_mode)),'uid':info.st_uid,'gid':info.st_gid,'size':info.st_size})
assert len(files)==2 and all(f['path'].endswith('.wav') for f in files)
print(json.dumps(files))
"""
    files = json.loads(guest("sudo python3 -", program))
    (OUTPUT / (args.engine + "-target-state.json")).write_text(
        json.dumps(files, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print("Verified two audio files; temporary and metadata files excluded.")
    if args.engine == "leroy":
        assert files == json.loads((OUTPUT / "jenkins-target-state.json").read_text(encoding="utf-8"))
        print("Paths, content, modes and ownership match the Jenkins result.")


if __name__ == "__main__":
    main()
