#!/usr/bin/env python3
"""Inspect the actual release APK; never prints private signing/pairing values.
Checks identity, SDK/permission boundaries, signature and retained certificate,
alignment, ZIP integrity, loopback-only settings, lint and secret exclusion.
Produces a distributable copy under artifacts/, but does not install it.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
import zipfile

ROOT=Path(__file__).resolve().parent
DATA=Path.home()/'.hermes-pocket'
APK=ROOT/'android/app/build/outputs/apk/legacy/release/app-legacy-release.apk'
SIGN=DATA/'signing'
CHECKS=[]


def run(args, **kwargs):
    return subprocess.run(args,capture_output=True,**kwargs)


def check(name,passed):
    CHECKS.append({'name':name,'passed':bool(passed)})
    print(('PASS: ' if passed else 'FAIL: ')+name,flush=True)
    if not passed: raise AssertionError(name)


def main():
    check('Nonempty release APK',APK.is_file() and APK.stat().st_size>0)
    with zipfile.ZipFile(APK) as z:
        check('ZIP integrity',z.testzip() is None)
        entries={i.filename:z.read(i) for i in z.infolist() if not i.is_dir()}
    check('Compiled manifest and bytecode',all(n in entries for n in ['AndroidManifest.xml','classes.dex','resources.arsc']))
    badging=run(['aapt','dump','badging',str(APK)],text=True)
    check('Package metadata readable',badging.returncode==0)
    meta=badging.stdout
    check('Correct package/version',"package: name='com.hermespocket.app' versionCode='2' versionName='0.2.0'" in meta)
    check('Correct visible identity',"application-label:'Hermes Pocket'" in meta)
    check('Correct launcher',"launchable-activity: name='com.hermespocket.app.MainActivity'" in meta)
    check('SDK 26 minimum / 35 target',"sdkVersion:'26'" in meta and "targetSdkVersion:'35'" in meta)
    permissions=re.findall(r"uses-permission: name='([^']+)'",meta)
    check('Internet is the only permission',permissions==['android.permission.INTERNET'])
    manifest=run(['aapt','dump','xmltree',str(APK),'AndroidManifest.xml'],text=True)
    check('Compiled native picker/export controls',all(s in entries['classes.dex'] for s in [b'android.intent.action.OPEN_DOCUMENT',b'android.intent.action.CREATE_DOCUMENT',b'HERMES_POCKET_EXPORT',b'HermesPocket/0.2.0']))
    check('Share provider is private with URI grants','com.hermespocket.app.ExportProvider' in manifest.stdout and bool(re.search(r'android:exported[^\n]*=\(type 0x12\)0x0',manifest.stdout)) and bool(re.search(r'android:grantUriPermissions[^\n]*=\(type 0x12\)0xffffffff',manifest.stdout)))
    check('Release not debuggable',manifest.returncode==0 and not re.search(r'android:debuggable[^\n]*=\(type 0x12\)0xffffffff',manifest.stdout))
    check('Backup disabled in manifest',bool(re.search(r'android:allowBackup[^\n]*=\(type 0x12\)0x0',manifest.stdout)))
    resources=run(['aapt2','dump','resources',str(APK)],text=True)
    check('Compiled resource table readable',resources.returncode==0)
    def resource_xml(name, manifest_attribute):
        match=re.search(r'resource (0x[0-9a-f]+) xml/'+re.escape(name)+r'\n\s+\(\) \(file\) (\S+)',resources.stdout)
        if not match or not re.search(r'android:'+manifest_attribute+r'[^\n]*=@'+match.group(1),manifest.stdout):
            raise AssertionError('Manifest/resource mapping: '+name)
        result=run(['aapt2','dump','xmltree',str(APK),'--file',match.group(2)],text=True)
        if result.returncode: raise AssertionError('Resource unreadable: '+name)
        return result.stdout
    network=resource_xml('network_security_config','networkSecurityConfig')
    check('Packaged network policy restricts cleartext to loopback',
          'E: base-config' in network and 'cleartextTrafficPermitted=false' in network
          and network.count('E: domain-config')==1 and 'cleartextTrafficPermitted=true' in network
          and 'includeSubdomains=false' in network and re.findall(r"T: '([^']+)'",network)==['127.0.0.1'])
    extraction=resource_xml('data_extraction_rules','dataExtractionRules')
    check('Packaged cloud and device-transfer exclusions',
          'E: cloud-backup' in extraction and 'E: device-transfer' in extraction and extraction.count('E: exclude')==18)
    check('Bytecode points to local bridge',b'http://127.0.0.1:8766/' in entries['classes.dex'])
    check('No bundled native binaries',not any(n.startswith('lib/') for n in entries))
    signed=run(['apksigner','verify','--verbose','--print-certs',str(APK)],text=True)
    check('APK cryptographic signature valid',signed.returncode==0)
    fingerprint=re.search(r'(?:Signer #\d+|V\d(?:\.\d+)? Signer): certificate SHA-256 digest: ([0-9a-f]+)',signed.stdout)
    check('v2 or v3 signature present',bool(re.search(r'Verified using v[23][^\n]*: true',signed.stdout)))
    props=dict(line.split('=',1) for line in (SIGN/'release.properties').read_text().splitlines() if '=' in line)
    env=os.environ.copy();env['POCKET_SIGNING_PASSWORD']=props['storePassword']
    certificate=run(['keytool','-exportcert','-keystore',str(SIGN/'hermes-pocket-release.p12'),
                     '-alias',props['keyAlias'],'-storepass:env','POCKET_SIGNING_PASSWORD'],env=env)
    check('APK signed with retained private key',certificate.returncode==0 and fingerprint is not None and hashlib.sha256(certificate.stdout).hexdigest()==fingerprint.group(1))
    check('Private signing permissions',SIGN.stat().st_mode&0o777==0o700 and all((SIGN/f).stat().st_mode&0o777==0o600 for f in ['release.properties','hermes-pocket-release.p12']))
    forbidden=[(DATA/'pairing-token').read_bytes(),(SIGN/'hermes-pocket-release.p12').read_bytes(),(SIGN/'release.properties').read_bytes(),props['storePassword'].encode(),props['keyPassword'].encode()]
    variants=[]
    for value in forbidden:
        variants.append(value)
        try: variants.append(value.decode().encode('utf-16le'))
        except UnicodeDecodeError: pass
    check('No signing or pairing secret in APK',not any(value in content for value in variants for content in entries.values()))
    check('No private credential filenames packaged',not any(any(s in n.lower() for s in ['.p12','release.properties','pairing-token','auth.json','.env']) for n in entries))
    aligned=run(['zipalign','-c','-P','16','4',str(APK)],text=True)
    check('APK alignment valid',aligned.returncode==0)
    with tempfile.TemporaryDirectory() as td:
        changed=Path(td)/'tampered.apk';shutil.copyfile(APK,changed)
        with zipfile.ZipFile(changed,'a') as z: z.writestr('verification-tamper-fixture.txt','harmless fixture')
        check('Tampered APK rejected',run(['apksigner','verify',str(changed)]).returncode!=0)
    lint=ET.parse(ROOT/'android/app/build/reports/lint-results-release.xml').getroot()
    issues=lint.findall('issue')
    check('Android lint zero errors',not any(i.attrib.get('severity') in ('Error','Fatal') for i in issues))
    warning_count=sum(i.attrib.get('severity')=='Warning' for i in issues)
    dest=ROOT/'artifacts/Hermes-Pocket-0.2.0-release.apk'
    dest.parent.mkdir(exist_ok=True)
    shutil.copyfile(APK,dest)
    digest=hashlib.sha256(dest.read_bytes()).hexdigest()
    dest.with_suffix('.apk.sha256').write_text(digest+'  '+dest.name+'\n')
    report={'passed':True,'check_count':len(CHECKS),'checks':CHECKS,'apk':str(dest),
            'size_bytes':dest.stat().st_size,'sha256':digest,'certificate_sha256':fingerprint.group(1),
            'keystore_sha256':hashlib.sha256((SIGN/'hermes-pocket-release.p12').read_bytes()).hexdigest(),
            'lint_errors':0,'lint_warnings':warning_count,'package':'com.hermespocket.app',
            'version_name':'0.2.0','device_installation_verified':False,'device_launch_verified':False}
    p=DATA/'apk-report.json';fd=os.open(p,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f: json.dump(report,f,indent=2)
    print('TOTAL FAILURES: 0; checks='+str(len(CHECKS))+'; lint warnings='+str(warning_count))
    print('APK: '+str(dest))
    print('SHA256: '+digest)
    print('Device installation/launch not verified by this artifact check.')


if __name__=='__main__': main()
