#!/usr/bin/env python3
"""Build the native launcher on ARM64 Termux without exposing signing secrets.
Acceptance is a signed release build + Android lint; separate verify_apk.py checks
identity, signature, key continuity, packaging, and secret exclusion.
No SDK/model downloads, key rotation, shared-storage writes, or installation here.
"""
import os
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parent
HOME=Path.home()
SDK=Path(os.environ.get('ANDROID_SDK_ROOT',str(HOME/'android-sdk')))
GRADLE=Path(os.environ.get('POCKET_GRADLE',str(HOME/'.local/share/gradle-8.9/bin/gradle')))


def main():
    for p in [SDK/'platforms/android-35/android.jar',SDK/'build-tools/35.0.0/lib/d8.jar',GRADLE]:
        if not p.is_file(): raise RuntimeError('Missing build prerequisite: '+str(p))
    aapt2=shutil.which('aapt2')
    if not aapt2: raise RuntimeError('Install the native Termux aapt2 package first')
    subprocess.run([aapt2,'version'],check=True)
    subprocess.run(['python',str(ROOT/'prepare_signing.py')],check=True)
    env=os.environ.copy()
    env.update(ANDROID_HOME=str(SDK),ANDROID_SDK_ROOT=str(SDK))
    subprocess.run([str(GRADLE),'--no-daemon','--console=plain','--max-workers=2',
        '-Dorg.gradle.native=false','-Dorg.gradle.vfs.watch=false',
        '-Dorg.gradle.jvmargs=-Xmx1024m -Dfile.encoding=UTF-8',
        '-Pandroid.aapt2FromMavenOverride='+aapt2,
        ':app:assembleRelease',':app:lintRelease',':app:testReleaseUnitTest'],
        cwd=ROOT/'android',env=env,check=True)
    apk=ROOT/'android/app/build/outputs/apk/release/app-release.apk'
    if not apk.is_file() or not apk.stat().st_size: raise RuntimeError('Release APK absent')
    print('Built signed release: '+str(apk))
    print('Run: python '+str(ROOT/'verify_apk.py'))


if __name__=='__main__': main()
