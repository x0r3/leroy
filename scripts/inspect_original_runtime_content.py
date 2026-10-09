"""Inspect immutable server sections and public UI assets without modifying images/tests."""

import json

from fetch_native_graphato_runtime import EVIDENCE
from prepare_nas_vm import guest

PROBE = r'''
import hashlib,json,pathlib,re,struct
server=pathlib.Path('/usr/local/bin/graphato-server')
with server.open('rb') as f:
 header=f.read(64);assert header[:6]==b'\x7fELF\x02\x01'
 fields=struct.unpack('<16sHHIQQQIHHHHHH',header);offset,entry,count,names=fields[6],fields[11],fields[12],fields[13]
 assert entry==64 and count<100
 f.seek(offset);sections=[struct.unpack('<IIQQQQIIQQ',f.read(entry)) for _ in range(count)]
 f.seek(sections[names][4]);strings=f.read(sections[names][5]);rows={}
 for row in sections:
  name=strings[row[0]:].split(b'\0',1)[0].decode();digest=None
  if row[1]!=8:
   f.seek(row[4]);remaining=row[5];h=hashlib.sha256()
   while remaining:
    chunk=f.read(min(remaining,1024**2));assert chunk;h.update(chunk);remaining-=len(chunk)
   digest=h.hexdigest()
  rows[name]={'type':row[1],'address':row[3],'size':row[5],'sha256':digest}
root=pathlib.Path('/usr/share/graphato-web');files={str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file() and not p.is_symlink()}
assert sum(map(len,files.values()))<8*1024**2
replacements={path:path for path in files}
for name in files:
 if match:=re.fullmatch(r'(.*)-([A-Za-z0-9_-]{8})\.(js|css)',name):
  replacements[name]=match[1]+'-<asset-hash>.'+match[3]
normalized={}
for name,data in files.items():
 if name=='web-build.json':continue
 try:text=data.decode()
 except UnicodeDecodeError:normalized.setdefault(replacements[name],[]).append(hashlib.sha256(data).hexdigest());continue
 for timestamp in ['20261006082324','20261006113757']:text=text.replace(timestamp,'<build-timestamp>')
 for old,new in sorted(replacements.items(),key=lambda row:len(row[0]),reverse=True):
  text=text.replace(pathlib.PurePosixPath(old).name,pathlib.PurePosixPath(new).name)
 normalized.setdefault(replacements[name],[]).append(hashlib.sha256(text.encode()).hexdigest())
print(json.dumps({'elf_sections':rows,'normalized_web_assets':{key:sorted(value) for key,value in normalized.items()},'normalization_rules':['two known build timestamp values','hashed JS/CSS filenames only'],'excluded_ui_metadata':['web-build.json'],'files_modified':False}))
'''


def main():
    target = EVIDENCE / 'runtime-content-comparison.json'
    assert not target.exists(), 'Retain the first immutable content comparison'
    loaded = json.loads((EVIDENCE / 'runtime-loaded-in-test-vm.json').read_text())
    ids = {'native': loaded['image_id'],
           'control': 'sha256:6251c60f499e41e706613f931bf281ce52312b957d5a6a123cf4e27dd3242585'}
    program = 'ids=' + repr(ids) + '\nprobe=' + repr(PROBE) + '\n'
    program += '''import json,subprocess
rows={}
for name,identity in ids.items():
 rows[name]=json.loads(subprocess.check_output(['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','256m','--memory-swap','256m','--pids-limit','32','--entrypoint','python3',identity,'-c',probe],text=True))
print(json.dumps(rows))
'''
    compile(PROBE, 'read-only immutable runtime probe', 'exec')
    values = json.loads(guest('sudo python3 -B -', program, timeout=90))
    left = values['native']['elf_sections']
    right = values['control']['elf_sections']
    shared = set(left) & set(right)
    mismatches = [key for key in sorted(shared) if left[key] != right[key]]
    value = {'observations': values, 'image_ids': ids, 'server_code_section_equal': left['.text'] == right['.text'],
             'differing_server_sections': mismatches, 'server_section_names_equal': set(left) == set(right),
             'normalized_public_ui_assets_equal': values['native']['normalized_web_assets'] == values['control']['normalized_web_assets'],
             'raw_image_and_file_bytes_equal': False, 'normalization_does_not_prove_all_import_graph_edges_equal': True,
             'test_files_modified': False, 'application_files_modified': False, 'production_modified': False,
             'cause_of_original_soak_difference_proven': False}
    target.write_text(json.dumps(value, indent=2) + '\n')
    print(json.dumps({key: value[key] for key in ['server_code_section_equal', 'differing_server_sections',
                                                 'normalized_public_ui_assets_equal', 'test_files_modified']}), flush=True)


if __name__ == '__main__':
    main()
