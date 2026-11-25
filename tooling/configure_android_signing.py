#!/usr/bin/env python3
"""Configure the fixed Android release key without logging credentials.

CI supplies DSH_ANDROID_KEYSTORE_BASE64, DSH_ANDROID_KEY_ALIAS,
DSH_ANDROID_STORE_PASSWORD and DSH_ANDROID_KEY_PASSWORD as secrets.
Local builds may use --keystore to reuse an existing private keystore.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent


def property_value(value: str) -> str:
    # java.util.Properties.load(InputStream) uses ISO-8859-1 and escapes.
    escaped = value.encode("utf-16-be")
    result = ""
    for i in range(0, len(escaped), 2):
        code = escaped[i] * 256 + escaped[i + 1]
        char = chr(code)
        if char in "\\ =:#!":
            result += "\\" + char
        elif code < 32 or code > 126:
            result += f"\\u{code:04x}"
        else:
            result += char
    return result


def configure(keystore: Path, output: Path, certificate: Path, decode: bool) -> str:
    required = ("DSH_ANDROID_KEY_ALIAS", "DSH_ANDROID_STORE_PASSWORD", "DSH_ANDROID_KEY_PASSWORD")
    values = {}
    for name in required:
        value = os.environ.get(name, "")
        if not value or (name.endswith("ALIAS") and not value.strip()):
            raise ValueError(f"Missing signing secret: {name}")
        values[name] = value
    expected = certificate.read_text(encoding="ascii").strip().lower()
    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise ValueError("Invalid pinned release certificate SHA-256")
    created = False
    try:
        if decode:
            encoded = os.environ.get("DSH_ANDROID_KEYSTORE_BASE64", "")
            if not encoded:
                raise ValueError("Missing signing secret: DSH_ANDROID_KEYSTORE_BASE64")
            data = base64.b64decode(encoded, validate=True)
            keystore.parent.mkdir(parents=True, exist_ok=True)
            with keystore.open("xb") as stream:
                os.chmod(keystore, 0o600)
                created = True
                stream.write(data)
        # Password stays in the child environment, never in argv or logs.
        result = subprocess.run([
            "keytool", "-exportcert", "-keystore", str(keystore),
            "-alias", values["DSH_ANDROID_KEY_ALIAS"],
            "-storepass:env", "DSH_ANDROID_STORE_PASSWORD",
        ], capture_output=True, check=False)
        if result.returncode:
            raise ValueError("Cannot open the release key or export its certificate")
        actual = hashlib.sha256(result.stdout).hexdigest()
        if actual != expected:
            raise ValueError("Release certificate differs from the pinned project certificate")
        props = {
            "storeFile": str(keystore.resolve()),
            "storePassword": values["DSH_ANDROID_STORE_PASSWORD"],
            "keyAlias": values["DSH_ANDROID_KEY_ALIAS"],
            "keyPassword": values["DSH_ANDROID_KEY_PASSWORD"],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        # Never overwrite somebody else's signing configuration.
        with output.open("x", encoding="ascii") as stream:
            os.chmod(output, 0o600)
            stream.write("".join(f"{key}={property_value(value)}\n" for key, value in props.items()))
        return actual
    except Exception:
        if created:
            keystore.unlink(missing_ok=True)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--keystore", type=Path, help="Reuse an existing private keystore")
    group.add_argument("--decode-to", type=Path, help="Decode the CI keystore secret here")
    parser.add_argument("--output", type=Path, default=ROOT / "app/android/key.properties")
    parser.add_argument("--certificate", type=Path, default=ROOT / "app/android/release-certificate.sha256")
    args = parser.parse_args()
    try:
        digest = configure(args.keystore or args.decode_to, args.output, args.certificate, args.decode_to is not None)
    except (ValueError, OSError) as error:
        # Library errors may carry input fragments; do not expose them.
        if isinstance(error, ValueError) and not isinstance(error, base64.binascii.Error):
            print(f"Signing configuration failed: {error}", file=sys.stderr)
        else:
            print("Signing configuration failed: invalid input or inaccessible signing files", file=sys.stderr)
        return 1
    print(f"Fixed release certificate SHA-256: {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
