import contextlib
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

import companion_pack as companion


class CompanionPackTest(unittest.TestCase):
    def setUp(self):
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.asset = self.root / companion.ASSET_KEY
        self.asset.parent.mkdir(parents=True)
        self.enterContext(patch.object(companion, 'ASSET', self.asset))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.credit = (companion.REPO / 'tooling/companion/whale-girl.character.json').read_bytes()
        support = companion._bundle_tools()
        self.manifest = support.encode({companion.ASSET_KEY: [{'asset': companion.ASSET_KEY}]}, bytearray())
        self.empty_manifest = support.encode({}, bytearray())

    @staticmethod
    def pack(credit, runtime=b'fixture runtime'):
        output = io.BytesIO()
        with zipfile.ZipFile(output, 'w') as archive:
            archive.writestr(companion.CHARACTER, credit)
            archive.writestr('runtime/live2dcubismcore.min.js', runtime)
        return output.getvalue()

    def apk(self, pack=None, *, manifest=True):
        path = self.root / 'test.apk'
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr(companion.MANIFEST, self.manifest if manifest else self.empty_manifest)
            if pack is not None:
                archive.writestr(companion.IN_APK, pack)
        return path

    def test_places_verified_release_asset_without_rewriting_it(self):
        raw = self.pack(self.credit)
        apk = self.apk(raw)
        digest = hashlib.sha256(b'runtime/live2dcubismcore.min.js\0' +
                                hashlib.sha256(b'fixture runtime').hexdigest().encode() + b'\n').hexdigest()
        dart = self.root / 'companion_pack.dart'
        dart.write_text(f"const companionRuntimeDigest = '{digest}';\n", encoding='utf-8')
        with patch.object(companion, 'RUNTIME_DIGEST_SOURCE', dart), \
                patch.object(companion, 'RELEASE_APK_SHA256', hashlib.sha256(apk.read_bytes()).hexdigest()), \
                patch.object(companion, 'RELEASE_PACK_SHA256', hashlib.sha256(raw).hexdigest()):
            companion.place_release(apk)
            self.assertEqual(self.asset.read_bytes(), raw)
            companion.check(apk, pinned=True)

    def test_local_place_keeps_the_runtime_and_adds_canonical_credit(self):
        source = self.root / 'local-pack.zip'
        source.write_bytes(self.pack(b'{}'))
        companion.place(source)
        with zipfile.ZipFile(self.asset) as placed:
            self.assertEqual(placed.read(companion.CHARACTER), self.credit)
            self.assertEqual(placed.read('runtime/live2dcubismcore.min.js'), b'fixture runtime')
        companion.check(self.apk(self.asset.read_bytes()))

    def test_rejects_unpinned_release_apk_before_placement(self):
        self.asset.write_bytes(b'previous asset')
        with self.assertRaisesRegex(ValueError, 'source APK SHA-256 mismatch'):
            companion.place_release(self.apk(self.pack(self.credit)))
        self.assertEqual(self.asset.read_bytes(), b'previous asset')

    def test_rejects_pack_with_incompatible_runtime(self):
        raw = self.pack(self.credit)
        apk = self.apk(raw)
        with patch.object(companion, 'RELEASE_APK_SHA256', hashlib.sha256(apk.read_bytes()).hexdigest()), \
                patch.object(companion, 'RELEASE_PACK_SHA256', hashlib.sha256(raw).hexdigest()):
            with self.assertRaisesRegex(ValueError, 'does not match companionRuntimeDigest'):
                companion.place_release(apk)
        self.assertFalse(self.asset.exists())

    def test_requires_the_asset_and_its_flutter_manifest_registration(self):
        with self.assertRaisesRegex(ValueError, 'no companion pack'):
            companion.check(self.apk())
        with self.assertRaisesRegex(ValueError, 'is not registered'):
            companion.check(self.apk(self.pack(self.credit), manifest=False))

    def test_checks_the_credit_and_rejects_a_substituted_pinned_pack(self):
        with self.assertRaisesRegex(ValueError, 'canonical character/character.json'):
            companion.check(self.apk(self.pack(b'{}')))
        with self.assertRaisesRegex(ValueError, 'companion ZIP SHA-256 mismatch'):
            companion.check(self.apk(self.pack(self.credit)), pinned=True)


if __name__ == '__main__':
    unittest.main()
