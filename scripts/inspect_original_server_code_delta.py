"""Locate byte differences in immutable ELF code sections; no application/test writes."""

import json

from fetch_native_graphato_runtime import EVIDENCE
from prepare_nas_vm import guest


def main():
    path = EVIDENCE / 'server-code-delta.json'
    assert not path.exists(), 'Retain the first immutable code comparison'
    retained = json.loads((EVIDENCE / 'runtime-content-comparison.json').read_text())
    parameters = {'images': retained['image_ids'],
                  'sections': {key: value['elf_sections']['.text'] for key, value in retained['observations'].items()}}
    program = '\n'.join(key + '=' + repr(value) for key, value in parameters.items()) + '\n'
    program += r'''
import json,pathlib,subprocess
directory=pathlib.Path('/var/lib/leroy-vm/diagnostics/immutable-server-code-0ad540dd5780')
assert not directory.exists();directory.mkdir(mode=0o700)
probe=r"""import pathlib,struct
with pathlib.Path('/usr/local/bin/graphato-server').open('rb') as f:
 header=struct.unpack('<16sHHIQQQIHHHHHH',f.read(64));f.seek(header[6]);rows=[struct.unpack('<IIQQQQIIQQ',f.read(64)) for _ in range(header[12])]
 f.seek(rows[header[13]][4]);strings=f.read(rows[header[13]][5])
 row,=[row for row in rows if strings[row[0]:].split(b'\0',1)[0]==b'.text']
 assert row[5]<128*1024**2;f.seek(row[4]);remaining=row[5]
 with pathlib.Path('/observations/code.bin').open('xb') as output:
  while remaining:
   chunk=f.read(min(remaining,1024**2));assert chunk;output.write(chunk);remaining-=len(chunk)
"""
for name,image in images.items():
 root=directory/name;root.mkdir(mode=0o700)
 subprocess.run(['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--user','0:0','--memory','128m','--memory-swap','128m','--pids-limit','32','--mount','type=bind,src='+str(root)+',dst=/observations','--entrypoint','python3',image,'-c',probe],check=True,capture_output=True,timeout=60)
left=(directory/'native/code.bin').read_bytes();right=(directory/'control/code.bin').read_bytes()
assert len(left)==len(right)==sections['native']['size']==sections['control']['size']
assert sections['native']['address']==sections['control']['address']
ranges=[];start=None;differences=0
for offset,(a,b) in enumerate(zip(left,right,strict=True)):
 if a!=b:
  differences+=1
  if start is None:start=offset
 elif start is not None:ranges.append((start,offset));start=None
if start is not None:ranges.append((start,len(left)))
windows=[]
for start,end in ranges[:20]:
 begin=max(0,start-12);stop=min(len(left),end+12)
 windows.append({'offset':start,'size':end-start,'native_context_hex':left[begin:stop].hex(),'control_context_hex':right[begin:stop].hex()})
disassembly={}
if differences<=100 and len(ranges)<=20:
 for name,image in images.items():
  snippets=[]
  for start,end in ranges:
   address=sections[name]['address'];r=subprocess.run(['docker','run','--rm','--network','none','--read-only','--cap-drop','ALL','--security-opt','no-new-privileges:true','--memory','128m','--pids-limit','32','--entrypoint','objdump',image,'-d','--start-address='+str(address+max(0,start-12)),'--stop-address='+str(address+end+12),'/usr/local/bin/graphato-server'],text=True,capture_output=True,timeout=30)
   assert r.returncode==0 and len(r.stdout)<16000;snippets.append(r.stdout)
  disassembly[name]=snippets
print(json.dumps({'code_section_bytes':len(left),'differing_byte_count':differences,'differing_range_count':len(ranges),'windows':windows,'disassembly':disassembly,'immutable_images_modified':False,'application_and_test_files_modified':False}))
'''
    compile(program, 'immutable server code comparison', 'exec')
    result = json.loads(guest('sudo python3 -B -', program, timeout=300))
    result['image_ids'] = retained['image_ids']
    path.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ['code_section_bytes', 'differing_byte_count',
                                                 'differing_range_count', 'application_and_test_files_modified']}), flush=True)


if __name__ == '__main__':
    main()
