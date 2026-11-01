#!/usr/bin/env python3
"""Generate only synthetic catalog entries in this extracted handoff. No private inputs."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
def bootstrap():
    # Git publication intentionally omits historical acceptance/authorization
    # reports. Identify the source layout without inventing approval evidence.
    required = ['SOURCE_PUBLICATION.md', 'DEPENDENCIES.json',
                'phase1/implementation/pocket/evolution.py',
                'phase2/pocket/evolution.py']
    if not all((ROOT / rel).is_file() and not (ROOT / rel).is_symlink()
               for rel in required):
        raise RuntimeError('Expected a complete synthetic source checkout')
    for rel,count in [('phase1/implementation',23),('phase2',1)]:
        stage=ROOT/rel
        ref=stage/'synthetic-reference.md'
        assert ref.is_file() and not ref.is_symlink()
        content=ref.read_bytes(); assert b'Synthetic' in content
        rows=[{'id':('synthetic-guidance-reference' if count==1 else 'synthetic-guidance-reference-%02d'%i),'path':str(ref),'sha256':hashlib.sha256(content).hexdigest()} for i in range(1,count+1)]
        dst=stage/'skill-catalog.json'; assert not dst.is_symlink()
        dst.write_text(json.dumps(rows,indent=2)+'\n');dst.chmod(0o600)
    return {'synthetic_references_phase1':23,'synthetic_references_phase2':1,'private_imports':0}
if __name__=='__main__': print(json.dumps(bootstrap()))
