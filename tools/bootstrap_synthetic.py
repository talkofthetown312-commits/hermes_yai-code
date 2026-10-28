#!/usr/bin/env python3
"""Generate only synthetic catalog entries in this extracted handoff. No private inputs."""
from pathlib import Path
import hashlib,json
ROOT=Path(__file__).resolve().parents[1]
def bootstrap():
    # Source-only publication excludes generated acceptance reports by design.
    if not ((ROOT/'HANDOFF_ACCEPTANCE.json').is_file() or
            ((ROOT/'SOURCE_PUBLICATION.md').is_file() and
             (ROOT/'phase1/implementation/synthetic-reference.md').is_file() and
             (ROOT/'phase2/schema-fixtures.json').is_file())):
        raise RuntimeError('Not a source handoff/publication')
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
