#!/usr/bin/env python3
"""Install a verified presentation-only mob/projectile package into a Godot client."""

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path, PurePosixPath


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_json(path):
    return json.loads(path.read_bytes())


def relative(value):
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "\\" in value or not path.parts:
        raise ValueError("Unsafe package resource path")
    return path.as_posix()


def checked_file(root, name, expected):
    path = (root / relative(name)).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Package asset escapes its source directory")
    data = path.read_bytes()
    if digest(data) != expected:
        raise ValueError(f"Package asset hash mismatch: {name}")
    return data


def collect(content, catalog, projectiles):
    receipt = read_json(catalog / "receipt.json")
    public_bytes = checked_file(catalog, "presentation.v1.json", receipt["presentation_sha256"])
    public = json.loads(public_bytes)
    if (
        public.get("schema") != "mt2spacetime.mob-presentation-candidate"
        or public.get("version") != 1
    ):
        raise ValueError("Unsupported mob presentation schema")
    if not isinstance(public.get("actors"), list) or not 1 <= len(public["actors"]) <= 128:
        raise ValueError("Expected 1..128 mob presentation actors")
    if public["gameplay_hash"] != receipt["content_hash"]:
        raise ValueError("Mob presentation/gameplay identities differ")
    mobs = {"presentation.v1.json": public_bytes}
    prefix = "res://assets/imported/mobs/"
    for artifact in public["artifacts"]:
        if not artifact["path"].startswith(prefix):
            raise ValueError("Mob artifact is outside the installed mob namespace")
        name = relative(artifact["path"][len(prefix) :])
        if Path(name).suffix != ".glb":
            raise ValueError("Expected a converted GLB mob artifact")
        data = checked_file(content / "generated", name, artifact["sha256"])
        if name in mobs and mobs[name] != data:
            raise ValueError("Conflicting shared mob artifact")
        mobs[name] = data
    flight_receipt = read_json(projectiles / "receipt.json")
    flight_bytes = checked_file(projectiles, "catalog.v1.json", flight_receipt["catalog_sha256"])
    flights = json.loads(flight_bytes)
    if flights.get("schema") != "mt2spacetime.projectile-catalog" or flights.get("version") != 1:
        raise ValueError("Unsupported projectile package schema")
    for actor in public["actors"]:
        for mode in actor["modes"]:
            for motion in mode["motions"]:
                for launch in motion.get("projectile_launches", []):
                    if launch["fly_definition"] not in flights["flights"]:
                        raise ValueError("Mob launch has no packaged flight definition")
    projectile_files = {"catalog.v1.json": flight_bytes}
    for table in (flights["files"], flights["import_sidecars"]):
        for name, expected in table.items():
            name = relative(name)
            if not name.startswith("assets/") or Path(name).suffix not in (
                ".png",
                ".glb",
                ".import",
            ):
                raise ValueError("Unexpected projectile package resource")
            projectile_files[name] = checked_file(projectiles, name, expected)
    return {"mobs": mobs, "projectiles": projectile_files}, public["gameplay_hash"]


def import_settings(data):
    """Read scalar settings from our import seeds and Godot-expanded sidecars."""
    section = ""
    result = {}
    for line in data.decode("utf-8").splitlines():
        line = line.strip()
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
        elif "=" in line:
            key, value = line.split("=", 1)
            identity = (section, key.strip())
            if identity in result:
                raise ValueError("Duplicate import setting")
            result[identity] = value.strip()
    return result


def check_installed(root, name, expected_bytes):
    if not name.endswith(".import"):
        checked_file(root, name, digest(expected_bytes))
        return
    path = (root / relative(name)).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ValueError("Installed import sidecar escapes its directory")
    actual = import_settings(path.read_bytes())
    required = import_settings(expected_bytes)
    if not required or any(actual.get(key) != value for key, value in required.items()):
        raise ValueError(f"Installed import settings differ: {name}")


def install(client, packages, gameplay_hash, *, identity_field="mob_gameplay_hash"):
    imported = client / "assets/imported"
    imported.mkdir(parents=True, exist_ok=True)
    manifests = {
        name: {
            "version": 1,
            identity_field: gameplay_hash,
            "files": {key: digest(data) for key, data in files.items()},
        }
        for name, files in packages.items()
    }
    if any((imported / name).exists() for name in packages):
        for name, manifest in manifests.items():
            destination = imported / name
            if (
                not (destination / "install-receipt.json").is_file()
                or read_json(destination / "install-receipt.json") != manifest
            ):
                raise ValueError(
                    "Destination contains different content; use an isolated client directory"
                )
            for file, data in packages[name].items():
                check_installed(destination, file, data)
        return {"installed": False, "already_present": True, identity_field: gameplay_hash}
    with tempfile.TemporaryDirectory(prefix="mob-install-", dir=imported) as scratch:
        stage = Path(scratch)
        for name, files in packages.items():
            for file, data in files.items():
                target = stage / name / file
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
            (stage / name / "install-receipt.json").write_text(
                json.dumps(manifests[name], indent=2) + "\n"
            )
        moved = []
        try:
            for name in packages:
                os.rename(stage / name, imported / name)
                moved.append(name)
        except OSError:
            for name in reversed(moved):
                os.rename(imported / name, stage / name)
            raise
    return {
        "installed": True,
        identity_field: gameplay_hash,
        "files": {name: len(files) for name, files in packages.items()},
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("content", "catalog", "projectiles", "client"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    packages, gameplay_hash = collect(args.content, args.catalog, args.projectiles)
    print(json.dumps(install(args.client.resolve(), packages, gameplay_hash)))


if __name__ == "__main__":
    main()
