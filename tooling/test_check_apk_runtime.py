"""Exercise final APK checks with small ZIP fixtures, no Android SDK needed."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import check_apk_runtime as checker


class ApkRuntimeTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        patched = patch.object(checker.check_runtime_bundle, "ROOT", self.root)
        patched.start()
        self.addCleanup(patched.stop)
        abi = "arm64-v8a"
        self.files = {}
        bundle = self.root / "runtime/out" / abi
        jni = {}
        for name in checker.check_runtime_bundle.REQUIRED_JNI:
            data = name.encode()
            jni[name] = self.record(data)
            path = bundle / "jniLibs" / abi / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            self.files[f"lib/{abi}/{name}"] = data
        archive = b"runtime archive fixture"
        assets = bundle / "assets/runtime"
        assets.mkdir(parents=True)
        archive_name = f"rootfs-{abi}.tar.xz"
        manifest = {"schema": 1, "abi": abi, "rootfs": archive_name,
                    "rootfsBytes": len(archive), "rootfsSha256": self.record(archive)["sha256"],
                    "jniLibs": jni}
        for name, data in ((archive_name, archive), ("manifest.json", json.dumps(manifest).encode())):
            (assets / name).write_bytes(data)
            self.files["assets/runtime/" + name] = data
        tawc = self.root / "runtime/out-tawcroot/jniLibs" / abi / "libtawcroot.so"
        tawc.parent.mkdir(parents=True)
        tawc.write_bytes(b"tawcroot")
        self.files[f"lib/{abi}/libtawcroot.so"] = b"tawcroot"
        self.apk = self.root / "fixture.apk"

    @staticmethod
    def record(data):
        return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    def write_apk(self):
        with zipfile.ZipFile(self.apk, "w") as apk:
            for name, data in self.files.items():
                apk.writestr(name, data)

    def test_complete_runtime_matches_build_inputs(self):
        self.write_apk()
        checker.check_apk(self.apk, "arm64")

    def test_missing_archive_and_launcher_are_rejected(self):
        for name in ("assets/runtime/rootfs-arm64-v8a.tar.xz", "lib/arm64-v8a/libtawcroot.so"):
            with self.subTest(name=name):
                data = self.files.pop(name)
                self.write_apk()
                with self.assertRaisesRegex(ValueError, "APK is missing"):
                    checker.check_apk(self.apk, "arm64")
                self.files[name] = data

    def test_same_size_corrupted_library_is_rejected(self):
        name = "lib/arm64-v8a/libproot.so"
        self.files[name] = b"x" * len(self.files[name])
        self.write_apk()
        with self.assertRaisesRegex(ValueError, "content mismatch"):
            checker.check_apk(self.apk, "arm64")

    def test_launcher_uses_source_namespace_and_new_package(self):
        manifest = self.root / "manifest.xml"
        xml = f'''<manifest xmlns:android="http://schemas.android.com/apk/res/android" package="{checker.PACKAGE}">
          <application><activity android:name="{checker.NAMESPACE}.MainActivity" />
          <activity-alias android:name="{checker.NAMESPACE}.LauncherMist" android:enabled="true"
            android:exported="true" android:targetActivity="{checker.NAMESPACE}.MainActivity">
            <intent-filter><action android:name="android.intent.action.MAIN" />
              <category android:name="android.intent.category.LAUNCHER" /></intent-filter>
          </activity-alias></application></manifest>'''
        manifest.write_text(xml)
        checker.check_manifest(manifest)
        manifest.write_text(xml.replace('android:enabled="true"', 'android:enabled="false"'))
        with self.assertRaisesRegex(ValueError, "invalid default launcher"):
            checker.check_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
