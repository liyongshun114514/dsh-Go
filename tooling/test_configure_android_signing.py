import base64
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from configure_android_signing import configure, property_value


class SigningConfigTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.key = self.root / "release.p12"
        self.output = self.root / "key.properties"
        self.cert = self.root / "certificate.sha256"
        self.cert.write_text(hashlib.sha256(b"public certificate").hexdigest())
        self.env = {
            "DSH_ANDROID_KEY_ALIAS": "release",
            "DSH_ANDROID_STORE_PASSWORD": "private-store-test",
            "DSH_ANDROID_KEY_PASSWORD": "private-key-test",
            "DSH_ANDROID_KEYSTORE_BASE64": base64.b64encode(b"private key fixture").decode(),
        }

    def exported(self, data=b"public certificate", code=0):
        return subprocess.CompletedProcess([], code, data, b"private diagnostic")

    def test_decodes_key_and_writes_restricted_config(self):
        with patch.dict(os.environ, self.env, clear=True), patch("subprocess.run", return_value=self.exported()) as run:
            configure(self.key, self.output, self.cert, True)
        self.assertEqual(self.key.read_bytes(), b"private key fixture")
        self.assertEqual(self.key.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)
        text = self.output.read_text()
        self.assertIn("storeFile=" + str(self.key), text)
        self.assertNotIn("private-store-test", str(run.call_args.args))
        self.assertIn("-storepass:env", run.call_args.args[0])

    def test_missing_secrets_leave_no_files(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "Missing signing secret"):
                configure(self.key, self.output, self.cert, True)
        self.assertFalse(self.key.exists())
        self.assertFalse(self.output.exists())

    def test_mismatched_certificate_deletes_decoded_key(self):
        with patch.dict(os.environ, self.env, clear=True), patch("subprocess.run", return_value=self.exported(b"wrong cert")):
            with self.assertRaisesRegex(ValueError, "differs"):
                configure(self.key, self.output, self.cert, True)
        self.assertFalse(self.key.exists())
        self.assertFalse(self.output.exists())

    def test_existing_config_is_not_overwritten(self):
        self.output.write_text("original")
        with patch.dict(os.environ, self.env, clear=True), patch("subprocess.run", return_value=self.exported()):
            with self.assertRaises(FileExistsError):
                configure(self.key, self.output, self.cert, True)
        self.assertEqual(self.output.read_text(), "original")
        self.assertFalse(self.key.exists())

    def test_existing_key_is_not_overwritten(self):
        self.key.write_bytes(b"original")
        with patch.dict(os.environ, self.env, clear=True):
            with self.assertRaises(FileExistsError):
                configure(self.key, self.output, self.cert, True)
        self.assertEqual(self.key.read_bytes(), b"original")

    def test_export_failure_does_not_expose_diagnostic(self):
        self.key.write_bytes(b"existing private key")
        with patch.dict(os.environ, self.env, clear=True), patch("subprocess.run", return_value=self.exported(code=1)):
            with self.assertRaises(ValueError) as result:
                configure(self.key, self.output, self.cert, False)
        self.assertNotIn("private diagnostic", str(result.exception))
        self.assertTrue(self.key.exists())
        self.assertFalse(self.output.exists())

    def test_properties_escape_whitespace_and_unicode(self):
        self.assertEqual(property_value(" a:b=c\\d\n雪"), "\\ a\\:b\\=c\\\\d\\u000a\\u96ea")


if __name__ == "__main__":
    unittest.main()
