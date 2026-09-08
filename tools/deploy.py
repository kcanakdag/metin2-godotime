#!/usr/bin/env python3
"""Deploy only this game's Compose project; reset its game DB only with explicit opt-in."""

import argparse
import hashlib
import json
import os
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
AUTH_FILES = (
    "Dockerfile",
    ".dockerignore",
    "package.json",
    "package-lock.json",
    "tsconfig.json",
    "src/auth.ts",
    "src/config.ts",
    "src/main.ts",
    "src/server.ts",
    "test/auth.test.ts",
)


def run(command, **kwargs):
    return subprocess.run(command, check=True, **kwargs)


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def stage_auth(source, destination):
    """Copy only reviewed build inputs; never auth state, installed packages or caches."""
    for name in AUTH_FILES:
        path = source / name
        if (
            source.is_symlink()
            or not path.is_file()
            or any(
                parent.is_symlink() for parent in [path, *path.parents] if parent != source.parent
            )
            or not path.resolve().is_relative_to(source.resolve())
        ):
            raise ValueError(f"Expected an ordinary auth build input: {name}")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)


def read_pack_config(godot, pck):
    """Read connection defaults from the actual PCK without starting its game or autoloads."""
    with tempfile.TemporaryDirectory(prefix="mt2-deploy-config-") as directory:
        root = Path(directory)
        (root / "project.godot").write_text(
            'config_version=5\n[application]\nconfig/name="MT2 deployment config check"\n'
        )
        script = root / "read_config.gd"
        script.write_text("""extends SceneTree

func _initialize() -> void:
    if not ProjectSettings.load_resource_pack(OS.get_cmdline_user_args()[0]):
        push_error("Cannot mount the exported PCK")
        quit(1)
        return
    var config = JSON.parse_string(FileAccess.get_file_as_string("res://client_config.json"))
    if not config is Dictionary:
        push_error("Packaged connection defaults are missing or invalid")
        quit(1)
        return
    print("PACKAGED_CONFIG " + JSON.stringify({"database": config.get("database"), "server_url": config.get("server_url")}))
    quit()
""")
        environment = dict(os.environ)
        for variable in ["XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"]:
            path = root / variable.lower()
            path.mkdir()
            environment[variable] = str(path)
        try:
            result = subprocess.run(
                [
                    godot,
                    "--headless",
                    "--path",
                    root,
                    "--script",
                    script,
                    "--",
                    pck.resolve(),
                ],
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=30,
                check=False,
            )
        except subprocess.TimeoutExpired:
            raise ValueError("Godot packaged-config inspection timed out") from None
    if result.returncode or "SCRIPT ERROR:" in result.stdout or "\nERROR:" in result.stdout:
        raise ValueError("Godot could not inspect the actual PCK connection defaults")
    records = [
        line.removeprefix("PACKAGED_CONFIG ")
        for line in result.stdout.splitlines()
        if line.startswith("PACKAGED_CONFIG ")
    ]
    if len(records) != 1:
        raise ValueError("Godot did not report exactly one packaged connection configuration")
    config = json.loads(records[0])
    if not isinstance(config, dict) or any(
        not isinstance(config.get(key), str) or not config[key].strip()
        for key in ["database", "server_url"]
    ):
        raise ValueError("Packaged database and server URL must be nonempty strings")
    return config


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
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    parser.add_argument("--web-dir", type=Path, default=ROOT / "dist/web")
    parser.add_argument(
        "--module",
        type=Path,
        default=ROOT / "server/target/wasm32-unknown-unknown/release/mt2_server.wasm",
        help="Deploy this frozen server WASM instead of the most recent local build",
    )
    parser.add_argument("--allow-test-build", action="store_true")
    parser.add_argument(
        "--reset-database",
        action="store_true",
        help="Reset only --database during publication; preserves auth accounts and issuer keys",
    )
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
        config = read_pack_config(args.godot, args.web_dir / "index.pck")
        if config["database"] != args.database:
            raise ValueError(
                f"Packaged database {config['database']!r} does not match "
                f"requested deployment database {args.database!r}; export for that database first"
            )
    except (OSError, ValueError) as error:
        parser.error(str(error))
    wasm = args.module.resolve()
    if not wasm.is_file():
        parser.error(f"Server module does not exist: {wasm}; build or select a frozen module")
    print(f"Selected server module: {wasm} (sha256 {digest(wasm)})")
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
        stage_auth(ROOT / "auth", stage / "auth")
        config = (ROOT / "deploy/nginx.conf.in").read_text()
        for key, value in {
            "HOST": args.public_name,
            "CERT": args.certificate,
            "DATABASE": args.database,
        }.items():
            config = config.replace("@" + key + "@", value)
        (stage / "nginx.conf").write_text(config)
        (stage / ".env").write_text(
            f"GAME_PORT={args.port}\nAUTH_ISSUER=https://{args.public_name}:{args.port}/auth\n"
        )
        (stage / ".certificate").write_text(args.certificate + "\n")
        (stage / ".database").write_text(args.database + "\n")
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
            *(["--reset-database"] if args.reset_database else []),
        ]
    )
    run([*ssh, command])
    print(f"Deployed https://{args.public_name}:{args.port}/ ({args.database}), release {release}")


if __name__ == "__main__":
    main()
