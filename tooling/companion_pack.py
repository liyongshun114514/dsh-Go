#!/usr/bin/env python3
"""The licensed whale-girl companion pack in Android release builds.

The pack stays out of the repository (docs/design/companion.md).

  tooling/companion_pack.py place SRC         place a local zip with the canonical credit
  tooling/companion_pack.py place-release APK place the pinned official release's zip, byte for byte
  tooling/companion_pack.py check APK         check the packaged asset and credit
  tooling/companion_pack.py check-release APK also require the pinned zip in the built APK
"""
import hashlib
import importlib.util
import io
import re
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ASSET_KEY = 'assets/companion/whale-girl.zip'
ASSET = REPO / 'app' / ASSET_KEY
FLUTTER_ASSETS = 'assets/flutter_assets/'
IN_APK = FLUTTER_ASSETS + ASSET_KEY
MANIFEST = FLUTTER_ASSETS + 'AssetManifest.bin'
CHARACTER = 'character/character.json'
RUNTIME_DIGEST_SOURCE = REPO / 'app/lib/companion/companion_pack.dart'

# ccch1mneyyy/dsh-Go v1.3.0 (dsh-go-1.3.0-arm64.apk and its published SHA256SUMS).
# The original model and redistributable runtime ship together with their credit;
# see docs/design/companion.md §§3, 7. Keep the workflow's URL on this release.
RELEASE_APK_SHA256 = 'f818371f4ebf63c8b42c5a8275b2618b75852dbf4078e2959e9c8294b7658a9f'
RELEASE_PACK_SHA256 = '3aff0e7ee256dcf5a48287b25333570a0e6dc755472be851faee64a8578668a8'


def _bundle_tools():
    spec = importlib.util.spec_from_file_location('bundle_companion_pack', REPO / 'tooling/ohos/bundle-companion-pack.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _place(raw: bytes, src: Path) -> None:
    pending = ASSET.with_suffix('.zip.tmp')
    try:
        pending.write_bytes(raw)
        pending.replace(ASSET)
    finally:
        pending.unlink(missing_ok=True)
    print(f'companion pack: {ASSET} from {src}')


def place(src: Path) -> None:
    _place(_bundle_tools().credited(src), src)


def _read_from_apk(outer: zipfile.ZipFile) -> bytes:
    if IN_APK not in outer.namelist():
        raise ValueError(f'no companion pack ({IN_APK})')
    manifest = outer.read(MANIFEST)
    assets, end = _bundle_tools().decode(manifest)
    if end != len(manifest) or ASSET_KEY not in assets:
        raise ValueError(f'{ASSET_KEY} is not registered in {MANIFEST}')
    return outer.read(IN_APK)


def _check_credit(pack: zipfile.ZipFile) -> None:
    character = (REPO / 'tooling/companion/whale-girl.character.json').read_bytes()
    if pack.read(CHARACTER) != character:
        raise ValueError(f'the companion pack does not carry the canonical {CHARACTER}')


def _check_runtime(pack: zipfile.ZipFile) -> None:
    dart = RUNTIME_DIGEST_SOURCE.read_text(encoding='utf-8')
    expected = re.search(r"^const companionRuntimeDigest = '([0-9a-f]{64})';$", dart, re.MULTILINE)
    digest = hashlib.sha256()
    for name in sorted(n for n in pack.namelist() if n.startswith('runtime/') and not n.endswith('/')):
        digest.update(f'{name}\0{hashlib.sha256(pack.read(name)).hexdigest()}\n'.encode())
    if expected is None or digest.hexdigest() != expected[1]:
        raise ValueError('the source pack runtime does not match companionRuntimeDigest')


def _check_pinned_pack(raw: bytes) -> None:
    actual = hashlib.sha256(raw).hexdigest()
    if actual != RELEASE_PACK_SHA256:
        raise ValueError(f'companion ZIP SHA-256 mismatch: expected {RELEASE_PACK_SHA256}, got {actual}')


def place_release(src: Path) -> None:
    with src.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if actual != RELEASE_APK_SHA256:
            raise ValueError(f'source APK SHA-256 mismatch: expected {RELEASE_APK_SHA256}, got {actual}')
        stream.seek(0)
        with zipfile.ZipFile(stream) as outer:
            raw = _read_from_apk(outer)
    _check_pinned_pack(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as pack:
        _check_credit(pack)
        _check_runtime(pack)
    _place(raw, src)
    print(f'verified release APK {actual}, companion ZIP {RELEASE_PACK_SHA256}')


def check(apk: Path, *, pinned: bool = False) -> None:
    with zipfile.ZipFile(apk) as outer:
        raw = _read_from_apk(outer)
    if pinned:
        _check_pinned_pack(raw)
    with zipfile.ZipFile(io.BytesIO(raw)) as pack:
        _check_credit(pack)
    print(f'{apk.name}: verified {ASSET_KEY} and its Flutter asset registration')


if __name__ == '__main__':
    commands = {'place': place, 'place-release': place_release, 'check': check,
                'check-release': lambda apk: check(apk, pinned=True)}
    if len(sys.argv) != 3 or sys.argv[1] not in commands:
        sys.exit(__doc__)
    source = Path(sys.argv[2])
    try:
        commands[sys.argv[1]](source)
    except (KeyError, OSError, ValueError, zipfile.BadZipFile) as error:
        sys.exit(f'{source.name}: {error}')
