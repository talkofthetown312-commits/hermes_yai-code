#!/usr/bin/env python3
"""Create ONCE and retain a private Android release key. Never prints passwords."""
import os
from pathlib import Path
import secrets
import shutil
import subprocess

BASE=Path.home()/'.hermes-pocket/signing'
KEY=BASE/'hermes-pocket-release.p12'
PROPS=BASE/'release.properties'

def main():
    BASE.mkdir(parents=True,exist_ok=True,mode=0o700)
    BASE.chmod(0o700)
    if KEY.exists() or PROPS.exists():
        if not (KEY.is_file() and PROPS.is_file()):
            raise RuntimeError('Incomplete signing setup; existing files left untouched.')
        print('Retained existing signing key: '+str(KEY))
        return
    keytool=shutil.which('keytool')
    if not keytool:
        raise RuntimeError('keytool is not installed; no JDK was installed automatically.')
    password=secrets.token_urlsafe(40)
    environment=os.environ.copy()
    environment['POCKET_SIGNING_PASSWORD']=password
    result=subprocess.run([keytool,'-genkeypair','-keystore',str(KEY),'-storetype','PKCS12',
        '-storepass:env','POCKET_SIGNING_PASSWORD','-keypass:env','POCKET_SIGNING_PASSWORD',
        '-alias','hermes-pocket','-keyalg','RSA','-keysize','3072','-validity','10000',
        '-dname','CN=Hermes Pocket'],env=environment,capture_output=True,text=True,timeout=60)
    if result.returncode:
        raise RuntimeError('keytool failed; inspect the private signing directory. No password was printed.')
    KEY.chmod(0o600)
    fd=os.open(PROPS,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:
        f.write('storeFile='+str(KEY)+'\nstoreType=PKCS12\nkeyAlias=hermes-pocket\nstorePassword='+password+'\nkeyPassword='+password+'\n')
    check=subprocess.run([keytool,'-list','-keystore',str(KEY),'-storepass:env','POCKET_SIGNING_PASSWORD',
        '-alias','hermes-pocket'],env=environment,capture_output=True,text=True,timeout=30)
    if check.returncode:
        raise RuntimeError('Key verification failed; key and properties preserved for inspection.')
    print('Created and verified persistent signing key: '+str(KEY))
    print('Private signing properties: '+str(PROPS))
    print('Back up both files privately. No APK was built.')

if __name__=='__main__':
    main()
