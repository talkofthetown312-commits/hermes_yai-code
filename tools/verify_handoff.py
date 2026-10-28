#!/usr/bin/env python3
"""Read-only source ZIP verifier. Prints locations/rule names, never matched secrets."""
from pathlib import Path, PurePosixPath
import argparse, ast, collections, hashlib, json, math, re, stat, zipfile
BLOCK_PARTS={'preservation','prechange-backup','__pycache__','node_modules','.git','.cache','runtime-home','qa-temp','qa-scope','test-runs','test-tmp','handoff-runtime','portable-test-runtime'}
BLOCK_SUFFIX={'.db','.sqlite','.sqlite3','.wal','.shm','.pyc','.pyo','.apk','.aab','.dex','.class','.jar','.so','.gguf','.safetensors','.bin','.pt','.pth','.ckpt','.p12','.pfx','.jks','.keystore','.pem','.key','.zip','.gz','.tgz','.tar','.7z','.bak'}
PATTERNS={
 'credential_vendor':re.compile(r'(?:sk-(?:or-v1-)?[A-Za-z0-9_-]{16,}|AIza[A-Za-z0-9_-]{25,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[A-Z0-9]{16})'),
 'jwt':re.compile(r'eyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}'),
 'private_key_material':re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----\s+[A-Za-z0-9+/=]{30,}'),
 'credential_in_url':re.compile(r'https?://[^\s/:]+:[^\s/@]+@|[?&#](?:access_token|refresh_token|api_key|token|pairing)=[A-Za-z0-9_-]{20,}',re.I),
}
def entropy(s):
 c=collections.Counter(s);n=len(s);return -sum((v/n)*math.log2(v/n) for v in c.values())
def inspect(name,raw):
 findings=[];p=PurePosixPath(name)
 if p.is_absolute() or '..' in p.parts or '\\' in name:findings.append({'path':name,'rule':'unsafe_path'})
 if set(p.parts)&BLOCK_PARTS or p.suffix.lower() in BLOCK_SUFFIX or p.name.startswith('.env') or p.name in {'pairing-token','auth.json','RUNNING.json','release.properties'}:findings.append({'path':name,'rule':'forbidden_file'})
 if raw.startswith(b'SQLite format 3') or b'\0' in raw:findings.append({'path':name,'rule':'binary_payload'})
 try:text=raw.decode('utf-8')
 except UnicodeDecodeError:return findings+[{'path':name,'rule':'non_utf8'}]
 for rule,pat in PATTERNS.items():
  for match in pat.finditer(text):findings.append({'path':name,'line':text.count('\n',0,match.start())+1,'rule':rule})
 for match in re.finditer(r'[A-Za-z0-9_.+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}',text):
  if not match.group().endswith(('@invalid.test','@example.com','@example.invalid')):findings.append({'path':name,'line':text.count('\n',0,match.start())+1,'rule':'non_fixture_email'})
 for match in re.finditer(r'''["']([A-Za-z0-9_+/=-]{32,})["']''',text):
  value=match.group(1)
  if re.fullmatch('[0-9a-fA-F]{32,128}',value):continue
  if entropy(value)>=4.3 and re.search('[A-Z]',value) and re.search('[a-z]',value) and re.search('[0-9]',value):
   findings.append({'path':name,'line':text.count('\n',0,match.start())+1,'rule':'opaque_high_entropy_literal'})
 # Directly embedded secret values; intentional synthetic tests are permitted.
 for match in re.finditer(r'''(?i)["']?(?:api_key|access_token|refresh_token|password|pairing_token|token)["']?\s*[:=]\s*["']([^"'\n]{8,})["']''',text):
  value=match.group(1)
  if any(x in value.lower() for x in ['fixture','synthetic','redacted','example','placeholder']):continue
  # Expressions/code strings and identifier names are not credential values.
  if not re.fullmatch(r'[A-Za-z0-9_+/.=-]{16,}',value):continue
  findings.append({'path':name,'line':text.count('\n',0,match.start())+1,'rule':'embedded_secret_literal'})
 return findings

def verify(path):
 findings=[];hash_errors=[];syntax=[]
 with zipfile.ZipFile(path) as z:
  crc=z.testzip(); names=z.namelist()
  assert len(names)==len(set(names)), 'Duplicate ZIP members'
  assert names and all(n.startswith('hermes-evolution-handoff/') for n in names)
  manifest=json.loads(z.read('hermes-evolution-handoff/MANIFEST.sha256.json'))
  files={n.removeprefix('hermes-evolution-handoff/'):z.read(n) for n in names if not n.endswith('/')}
  for info in z.infolist():
   if stat.S_ISLNK(info.external_attr>>16):findings.append({'path':info.filename,'rule':'symlink'})
  for name,raw in files.items():
   findings.extend(inspect(name,raw))
   try:
    if name.endswith('.py'):ast.parse(raw.decode(),filename=name)
    if name.endswith('.json'):json.loads(raw)
   except Exception as e:syntax.append({'path':name,'error_type':type(e).__name__})
   if name!='MANIFEST.sha256.json' and manifest.get(name)!=hashlib.sha256(raw).hexdigest():hash_errors.append(name)
  expected=set(files)-{'MANIFEST.sha256.json'}
  if set(manifest)!=expected:hash_errors.append('manifest_membership_mismatch')
 return {'files':len(files),'uncompressed_bytes':sum(map(len,files.values())),'crc_error':crc,'secret_or_exclusion_findings':findings,'hash_errors':hash_errors,'syntax_errors':syntax,'safe':not (crc or findings or hash_errors or syntax)}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('zip');a=p.parse_args();result=verify(a.zip);print(json.dumps(result,indent=2));raise SystemExit(0 if result['safe'] else 1)
