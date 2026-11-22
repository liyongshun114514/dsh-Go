#!/usr/bin/env python3
"""Verify the runtime files and launcher in the APK that will be delivered."""

import argparse
import hashlib
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
import zipfile

import check_runtime_bundle


ANDROID = "{http://schemas.android.com/apk/res/android}"
PACKAGE = "io.github.ccch1mneyyy.dsh_app_next"
NAMESPACE = "io.github.ccch1mneyyy.dsh_app"


def check_manifest(path):
    manifest = ET.parse(path).getroot()
    if manifest.get("package") != PACKAGE:
        raise ValueError("APK has the wrong application ID")
    app = manifest.find("application")
    if app is None:
        raise ValueError("APK has no application")
    activities = {node.get(ANDROID + "name") for node in app.findall("activity")}
    if NAMESPACE + ".MainActivity" not in activities:
        raise ValueError("APK is missing MainActivity in the source namespace")
    launcher = next((node for node in app.findall("activity-alias")
                     if node.get(ANDROID + "name") == NAMESPACE + ".LauncherMist"), None)
    if (launcher is None or launcher.get(ANDROID + "enabled", "true") != "true"
            or launcher.get(ANDROID + "exported") != "true"
            or launcher.get(ANDROID + "targetActivity") != NAMESPACE + ".MainActivity"):
        raise ValueError("APK has an invalid default launcher alias")
    if not any(
        any(node.get(ANDROID + "name") == "android.intent.action.MAIN"
            for node in intent.findall("action"))
        and any(node.get(ANDROID + "name") == "android.intent.category.LAUNCHER"
                for node in intent.findall("category"))
        for intent in launcher.findall("intent-filter")
    ):
        raise ValueError("APK launcher is missing its MAIN/LAUNCHER intent")


def check_apk(apk_path, flavor):
    check_runtime_bundle.check_bundle(flavor)
    abi = check_runtime_bundle.ABIS[flavor]
    root = check_runtime_bundle.ROOT
    bundle = root / "runtime/out" / abi
    expected = [(path, path.relative_to(bundle).as_posix())
                for directory in (bundle / "assets", bundle / "jniLibs" / abi)
                for path in directory.rglob("*") if path.is_file()]
    expected = [(path, name.replace("jniLibs/", "lib/", 1)) for path, name in expected]
    tawc = root / "runtime/out-tawcroot/jniLibs" / abi / "libtawcroot.so"
    expected.append((tawc, f"lib/{abi}/libtawcroot.so"))
    with zipfile.ZipFile(apk_path) as apk:
        for source, name in expected:
            if not source.is_file() or source.stat().st_size == 0:
                raise ValueError(f"missing build input: {source}")
            try:
                info = apk.getinfo(name)
            except KeyError as error:
                raise ValueError(f"APK is missing {name}") from error
            if info.file_size != source.stat().st_size:
                raise ValueError(f"APK size mismatch: {name}")
            digest = hashlib.sha256()
            with apk.open(info) as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
            with source.open("rb") as stream:
                original = hashlib.file_digest(stream, "sha256").hexdigest()
            if digest.hexdigest() != original:
                raise ValueError(f"APK content mismatch: {name}")
    print(f"APK runtime verified: {abi}, {len(expected)} files including archives and launchers")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--flavor", choices=check_runtime_bundle.ABIS, default="arm64")
    parser.add_argument("--manifest", type=Path, required=True,
                        help="compiled APK manifest decoded by apkanalyzer manifest print")
    args = parser.parse_args()
    try:
        check_manifest(args.manifest)
        check_apk(args.apk, args.flavor)
    except (OSError, ValueError, KeyError, ET.ParseError, zipfile.BadZipFile) as error:
        print(f"APK runtime check failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
