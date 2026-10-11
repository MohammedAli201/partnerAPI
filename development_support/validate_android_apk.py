"""Validate a standalone Android testing distribution without installing it."""
import argparse
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


def run(tool, *args):
    result = subprocess.run([str(tool), *map(str, args)], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout + result.stderr


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, required=True)
    parser.add_argument('--previous-apk', type=Path, required=True)
    parser.add_argument('--build-tools', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    signature = run(args.build_tools / 'apksigner.bat', 'verify', '--verbose', '--print-certs', args.apk)
    previous = run(args.build_tools / 'apksigner.bat', 'verify', '--print-certs', args.previous_apk)
    digest = re.compile(r'certificate SHA-256 digest: ([0-9a-f]+)')
    assert digest.findall(signature) == digest.findall(previous), 'Signing identity changed'
    assert 'Verified using v2 scheme (APK Signature Scheme v2): true' in signature
    alignment = run(args.build_tools / 'zipalign.exe', '-c', '-P', '16', '-v', '4', args.apk)
    badging = run(args.build_tools / 'aapt.exe', 'dump', 'badging', args.apk)
    binary_manifest = run(args.build_tools / 'aapt.exe', 'dump', 'xmltree', args.apk, 'AndroidManifest.xml')
    assert 'android:testOnly' not in binary_manifest
    assert 'android:debuggable' not in binary_manifest
    assert 'android:isSplitRequired' not in binary_manifest
    permission_pattern = re.compile(r"uses-permission: name='([^']+)'")
    permissions = permission_pattern.findall(run(args.build_tools / 'aapt.exe', 'dump', 'permissions', args.apk))
    old_permissions = permission_pattern.findall(run(args.build_tools / 'aapt.exe', 'dump', 'permissions', args.previous_apk))
    assert set(permissions) == set(old_permissions), 'Worker permissions changed'
    assert "name='no.jubapay.payoutworker'" in badging
    assert "sdkVersion:'24'" in badging and "targetSdkVersion:'37'" in badging
    with zipfile.ZipFile(args.apk) as archive:
        assert archive.testzip() is None, 'ZIP integrity failure'
        abis = sorted({name.split('/')[1] for name in archive.namelist() if name.startswith('lib/') and name.endswith('.so')})
        assert {'arm64-v8a', 'armeabi-v7a'}.issubset(abis)
        assert 'classes.dex' in archive.namelist()
    android = '{http://schemas.android.com/apk/res/android}'
    manifest = ET.parse(args.manifest).getroot()
    assert 'split' not in manifest.attrib
    app = manifest.find('application')
    assert app.get(android + 'debuggable', 'false') == 'false'
    assert app.get(android + 'testOnly', 'false') == 'false'
    assert app.get(android + 'usesCleartextTraffic') == 'false'
    assert app.get(android + 'allowBackup') == 'false'
    components = [node.get(android + 'name') for node in app]
    assert 'no.jubapay.payoutworker.SmsSessionService' in components
    assert 'no.jubapay.payoutworker.device.EvcAccessibilityService' in components
    assert 'androidx.compose.ui.tooling.PreviewActivity' not in components
    report = dict(apk=str(args.apk.resolve()), sha256=hashlib.sha256(args.apk.read_bytes()).hexdigest(),
                  size_bytes=args.apk.stat().st_size, abis=abis, signer_sha256=digest.findall(signature),
                  signature=signature, alignment=alignment, badging=badging,
                  permissions=permissions, binary_manifest=binary_manifest,
                  zip_integrity='passed', standalone=True, device_installation='not tested')
    args.report.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({key: report[key] for key in ('sha256', 'size_bytes', 'abis', 'zip_integrity', 'standalone', 'device_installation')}, indent=2))


if __name__ == '__main__':
    main()
