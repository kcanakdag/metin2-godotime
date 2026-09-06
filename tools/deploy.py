#!/usr/bin/env python3
"""Deploy only this game's Compose project; preserve existing services and database contents."""

import argparse
import hashlib
import json
import re
import shlex
import shutil
import subprocess
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parents[1]
REMOTE = "/opt/metin2-godotime"
MANIFEST = "build-manifest.json"


def run(command, **kwargs):
    return subprocess.run(command, check=True, **kwargs)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def validate_web_build(directory, *, allow_test_build=False):
    """Verify all published bytes before opening an SSH connection."""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Expected an ordinary Web export directory")
    actual = {}
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise ValueError("Web exports cannot contain symbolic links")
        if path.is_file():
            actual[path.relative_to(directory).as_posix()] = path
    if MANIFEST not in actual:
        raise ValueError("Web build manifest missing; run the actual export command first")
    manifest = json.loads(actual.pop(MANIFEST).read_text())
    if manifest.get("target") != "web" or not isinstance(manifest.get("test_probe"), bool):
        raise ValueError("Expected a Web export with an explicit test-probe declaration")
    if manifest["test_probe"] and not allow_test_build:
        raise ValueError("Test instrumentation requires explicit --allow-test-build")
    audit = manifest.get("pack_audit", {})
    if (
        not audit.get("files_checked")
        or audit.get("test_probe_present") is not manifest["test_probe"]
    ):
        raise ValueError("Missing or inconsistent actual-PCK audit; export with current tooling")
    inventory = manifest.get("files", {})
    if not isinstance(inventory, dict) or set(inventory) != set(actual):
        raise ValueError("The manifest must cover every published file, including streamed packs")
    for name, metadata in inventory.items():
        path = PurePosixPath(name)
        if path.is_absolute() or ".." in path.parts or "\\" in name:
            raise ValueError("Unsafe path in Web build manifest")
        if any(part.startswith(".") for part in path.parts):
            raise ValueError("Hidden files cannot be published in a Web export")
        if not isinstance(metadata, dict):
            raise ValueError("Invalid file metadata in Web build manifest")
        if metadata.get("bytes") != actual[name].stat().st_size or metadata.get("sha256") != digest(
            actual[name]
        ):
            raise ValueError(f"Exported file no longer matches its manifest: {name}")
    if not {"index.html", "index.js", "index.wasm", "index.pck"} <= set(actual):
        raise ValueError("Incomplete Godot Web export")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="root@159.195.213.9")
    parser.add_argument("--public-name", default="kcanakdag.com")
    parser.add_argument("--certificate", default="kcanakdag.com")
    parser.add_argument("--port", type=int, default=8443)
    parser.add_argument("--database", default="mt2-yongan-v2")
    parser.add_argument("--web-dir", type=Path, default=ROOT / "dist/web")
    parser.add_argument("--allow-test-build", action="store_true")
    args = parser.parse_args()
    for value in [args.host, args.public_name, args.certificate, args.database]:
        if (
            not re.fullmatch(r"[a-zA-Z0-9_.@-]+", value)
            or value.startswith("-")
            or value in {".", ".."}
        ):
            parser.error("Host, certificate, and database names must be plain identifiers")
    if args.port in {22, 80, 443, 8080, 13210} or not 1024 <= args.port <= 65535:
        parser.error("Choose a separate unprivileged game port")
    try:
        validate_web_build(args.web_dir, allow_test_build=args.allow_test_build)
    except (OSError, ValueError) as error:
        parser.error(str(error))
    wasm = ROOT / "server/target/wasm32-unknown-unknown/release/mt2_server.wasm"
    if not wasm.is_file():
        parser.error("Build the server first: make server-build")
    ssh = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", args.host]
    release = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    candidate = f"{REMOTE}/incoming/{release}"
    # The archive is extracted into a fresh private candidate, never over active configuration.
    run([*ssh, f"set -eu; umask 077; mkdir -p {REMOTE}/incoming; mkdir {candidate}"])
    local = ROOT / ".local/deploy"
    local.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=local) as tmp:
        stage = Path(tmp)
        for name in [
            "Dockerfile",
            "compose.yaml",
            ".dockerignore",
            "apply.sh",
            "reload-certificate.sh",
        ]:
            shutil.copy2(ROOT / "deploy" / name, stage / name)
        shutil.copy2(wasm, stage / "mt2_server.wasm")
        config = (ROOT / "deploy/nginx.conf.in").read_text()
        for key, value in {
            "HOST": args.public_name,
            "CERT": args.certificate,
            "DATABASE": args.database,
        }.items():
            config = config.replace("@" + key + "@", value)
        (stage / "nginx.conf").write_text(config)
        (stage / ".env").write_text(f"GAME_PORT={args.port}\n")
        (stage / ".certificate").write_text(args.certificate + "\n")
        archive = local / (release + ".tar.gz")
        with tarfile.open(archive, "w:gz") as tar:
            for path in stage.iterdir():
                tar.add(path, arcname=path.name)
            tar.add(args.web_dir, arcname="web")
        with archive.open("rb") as stream:
            run([*ssh, f"tar -xzf - -C {candidate}"], stdin=stream)
    command = shlex.join(
        [
            "bash",
            f"{candidate}/apply.sh",
            release,
            args.database,
            args.public_name,
            str(args.port),
            args.certificate,
        ]
    )
    run([*ssh, command])
    print(f"Deployed https://{args.public_name}:{args.port}/ ({args.database}), release {release}")


if __name__ == "__main__":
    main()
