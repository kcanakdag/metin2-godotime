"""Build a Windows client ZIP from an isolated copy of the Godot project.

python3 tools/export_client.py --server http://192.168.1.20:3210 --database mt2-training-v2
python3 tools/export_client.py --wine-smoke
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
GODOT_VERSION = "4.7.2"
PRESET = "Windows Desktop"
DEV_ADDONS = ("godot_mcp", "mt2_dev_bridge")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def run(command, log, env, timeout=180):
    # File output also avoids Wine background services retaining a pipe after exit.
    with log.open("w") as stream:
        try:
            result = subprocess.run(
                [str(part) for part in command],
                stdout=stream,
                stderr=subprocess.STDOUT,
                env=env,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"Command timed out after {timeout}s; see {log}") from error
    stdout = log.read_text(errors="replace")
    if result.returncode or "SCRIPT ERROR:" in stdout or "ERROR:" in stdout:
        raise RuntimeError(f"Command failed; see {log}\n{stdout[-5000:]}")
    return stdout


def template_directory(explicit):
    candidates = (
        [Path(explicit)]
        if explicit
        else [
            ROOT / ".cache" / "export_templates" / f"{GODOT_VERSION}.stable",
            Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
            / "godot/export_templates"
            / f"{GODOT_VERSION}.stable",
            Path.home() / ".local/share/godot/export_templates" / f"{GODOT_VERSION}.stable",
        ]
    )
    for directory in candidates:
        if (directory / "windows_release_x86_64.exe").is_file():
            return directory.resolve()
    raise RuntimeError(
        f"Godot {GODOT_VERSION} Windows x86_64 export template missing. Install matching "
        "templates in Godot's Export Template Manager or pass --templates DIRECTORY."
    )


def stage_project(stage, templates, include_maps=True):
    def ignored(directory, names):
        exclusions = {".godot", ".git", "tests"}
        if Path(directory).name == "addons":
            exclusions.update(DEV_ADDONS)
        if Path(directory).name == "imported" and not include_maps:
            exclusions.add("maps")
        return set(names).intersection(exclusions)

    shutil.copytree(ROOT / "client", stage, ignore=ignored)
    project = stage / "project.godot"
    lines = []
    section = ""
    for line in project.read_text().splitlines():
        if line.startswith("["):
            section = line
        if section == "[editor_plugins]":
            continue
        if any(f"addons/{addon}/" in line for addon in DEV_ADDONS):
            continue
        lines.append(line)
    project.write_text("\n".join(lines) + "\n")
    preset = stage / "export_presets.cfg"
    text = preset.read_text()
    for kind in ("debug", "release"):
        value = json.dumps(str(templates / f"windows_{kind}_x86_64.exe"))
        text = re.sub(
            rf"^custom_template/{kind}=.*$",
            f"custom_template/{kind}={value}",
            text,
            flags=re.MULTILINE,
        )
    preset.write_text(text)


def validate_pack_paths(paths, *, allow_test_probe=False):
    """Reject development bridges and private/source files in the actual exported pack."""
    forbidden = []
    probes = []
    for path in paths:
        relative = path.removeprefix("res://")
        parts = Path(relative.lower()).parts
        name = parts[-1] if parts else ""
        if "export_probe" in name:
            probes.append(path)
        if (
            any(part in {".git", ".local", "identities", "tests", "logs"} for part in parts)
            or any(addon in parts for addon in DEV_ADDONS)
            or relative.lower().startswith("assets/source/")
            or name == ".env"
            or name.startswith(".env.")
            or Path(name).suffix
            in {
                ".pem",
                ".key",
                ".token",
                ".log",
                ".gr2",
                ".epk",
                ".eix",
                ".blend",
                ".zip",
                ".tar",
                ".gz",
            }
        ):
            forbidden.append(path)
    if forbidden:
        raise RuntimeError("Forbidden packaged files: " + ", ".join(forbidden[:12]))
    if probes and not allow_test_probe:
        raise RuntimeError("Test probe included in a player export: " + ", ".join(probes))
    if allow_test_probe and not probes:
        raise RuntimeError("The requested test export has no packaged test probe")
    return {"files_checked": len(paths), "test_probe_present": bool(probes)}


def audit_pack(godot, pck, output, env, *, allow_test_probe=False):
    # Load the actual exported PCK, checking remapped meshes and animations too.
    probe = output / "audit_pack.gd"
    probe.write_text("""extends SceneTree

func _initialize() -> void:
    var directories: Array[String] = ["res://"]
    var paths: Array[String] = []
    while not directories.is_empty():
        var path: String = directories.pop_back()
        var directory := DirAccess.open(path)
        if not directory:
            push_error("Cannot inspect packaged directory: " + path)
            quit(1)
            return
        directory.include_hidden = true
        directory.include_navigational = false
        directory.list_dir_begin()
        var entry := directory.get_next()
        while not entry.is_empty():
            var resource_path := path.path_join(entry)
            if directory.current_is_dir():
                directories.append(resource_path)
            else:
                paths.append(resource_path)
            entry = directory.get_next()
        directory.list_dir_end()
    paths.sort()
    var inventory := FileAccess.open(OS.get_cmdline_user_args()[1], FileAccess.WRITE)
    if not inventory:
        push_error("Could not write packaged file inventory")
        quit(1)
        return
    inventory.store_string(JSON.stringify(paths, "  "))
    inventory.close()
    for setting in ProjectSettings.get_property_list():
        var key := str(setting["name"])
        if key.begins_with("autoload/") and "mcp" in key.to_lower():
            push_error("Development MCP autoload included: " + key)
            quit(1)
            return
    if DirAccess.dir_exists_absolute("res://addons/godot_mcp"):
        push_error("Development MCP addon included")
        quit(1)
        return
    if FileAccess.file_exists("res://client_config.json"):
        var config = JSON.parse_string(FileAccess.get_file_as_string("res://client_config.json"))
        if not config is Dictionary:
            push_error("Invalid packaged connection defaults")
            quit(1)
            return
        for key in config:
            if key not in ["server_url", "database", "default_player_name"]:
                push_error("Unexpected packaged connection setting: " + str(key))
                quit(1)
                return
    var ui_images := audit_ui()
    if ui_images < 0:
        quit(1)
        return
    var packed := load("res://assets/imported/warrior.glb") as PackedScene
    if not packed:
        push_error("Packaged warrior could not load")
        quit(1)
        return
    var model := packed.instantiate()
    var pending: Array[Node] = [model]
    var meshes := 0
    var textured_meshes := 0
    var bones := 0
    var clips: Array[String] = []
    while not pending.is_empty():
        var node: Node = pending.pop_back()
        if node is MeshInstance3D:
            meshes += 1
            var textured := false
            for surface in range(node.mesh.get_surface_count()):
                var material = node.get_active_material(surface)
                if material is BaseMaterial3D and material.albedo_texture:
                    textured = true
            if textured:
                textured_meshes += 1
        if node is Skeleton3D:
            bones += node.get_bone_count()
        if node is AnimationPlayer:
            for clip in node.get_animation_list():
                clips.append(str(clip))
        for child in node.get_children():
            pending.append(child)
    model.free()
    var license_file := FileAccess.open(OS.get_cmdline_user_args()[0], FileAccess.WRITE)
    if not license_file:
        push_error("Could not write engine notices")
        quit(1)
        return
    license_file.store_line(Engine.get_license_text())
    license_file.store_line("Third-party copyrights:")
    license_file.store_line(JSON.stringify(Engine.get_copyright_info(), "  "))
    license_file.store_line("Third-party licenses:")
    license_file.store_line(JSON.stringify(Engine.get_license_info(), "  "))
    license_file.close()
    print("PACK_AUDIT " + JSON.stringify({"meshes": meshes, "textured_meshes": textured_meshes, "bones": bones, "animations": clips, "ui_images": ui_images, "ui_pixels_verified": true}))
    quit(0 if meshes >= 3 and textured_meshes == meshes and bones >= 75 and clips.size() >= 4 else 1)

func audit_ui() -> int:
    var path := "res://assets/imported/ui/manifest.json"
    if not FileAccess.file_exists(path):
        push_error("Original UI manifest missing. Run make import-ui before exporting.")
        return -1
    var manifest = JSON.parse_string(FileAccess.get_file_as_string(path))
    if not manifest is Dictionary or not manifest.get("assets") is Dictionary or not manifest.get("maps") is Dictionary:
        push_error("Invalid original UI manifest")
        return -1
    var entries: Array = manifest.assets.values() + manifest.maps.values()
    if entries.is_empty():
        push_error("Original UI fixture is empty")
        return -1
    for entry in entries:
        var resource := str(entry.get("resource", ""))
        if not resource.begins_with("res://assets/imported/ui/") or not resource.ends_with(".png"):
            push_error("Invalid original UI resource path")
            return -1
        var texture := load(resource) as Texture2D
        if not texture:
            push_error("Missing packaged UI image: " + resource)
            return -1
        var image := texture.get_image()
        if not image or image.is_compressed() or image.has_mipmaps():
            push_error("UI texture must remain lossless without mipmaps: " + resource)
            return -1
        image.convert(Image.FORMAT_RGBA8)
        var hash := HashingContext.new()
        hash.start(HashingContext.HASH_SHA256)
        hash.update(image.get_data())
        if hash.finish().hex_encode() != str(entry.get("rgba_sha256", "")):
            push_error("Packaged UI pixels differ from the pinned conversion: " + resource)
            return -1
    return entries.size()
""")
    stdout = run(
        [
            godot,
            "--headless",
            "--main-pack",
            pck,
            "--script",
            probe,
            "--",
            output / "godot-licenses.txt",
            output / "pack-inventory.json",
        ],
        output / "pack-audit.log",
        env,
    )
    line = next(line for line in stdout.splitlines() if line.startswith("PACK_AUDIT "))
    audit = json.loads(line.removeprefix("PACK_AUDIT "))
    audit.update(
        validate_pack_paths(
            json.loads((output / "pack-inventory.json").read_text()),
            allow_test_probe=allow_test_probe,
        )
    )
    return audit


def package_notices(stage, build, local):
    notices = build / "licenses"
    notices.mkdir()
    shutil.copy2(local / "godot-licenses.txt", notices / "Godot.txt")
    addon_directory = stage / "addons"
    names = {"license", "license.txt", "license.md", "copying", "notice", "notice.txt"}
    if addon_directory.is_dir():
        for path in addon_directory.rglob("*"):
            if path.is_file() and path.name.lower() in names:
                destination = notices / path.relative_to(addon_directory)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    parser.add_argument(
        "--templates", help="Directory containing matching Windows export templates"
    )
    parser.add_argument("--server", default="http://127.0.0.1:3210")
    parser.add_argument("--database", default="mt2-training-v2")
    parser.add_argument("--player-name", default="")
    parser.add_argument(
        "--wine-smoke", action="store_true", help="Run the Windows EXE headlessly under Wine"
    )
    options = parser.parse_args()
    server = urlparse(options.server)
    if server.scheme not in ("http", "https") or not server.hostname:
        parser.error("--server must be an http:// or https:// SpacetimeDB address")
    if not options.database:
        parser.error("--database cannot be empty")
    if not (ROOT / "client/assets/imported/warrior.glb").is_file():
        parser.error("Warrior asset missing: run make assets and make import-assets first")
    godot = shutil.which(options.godot)
    if not godot:
        parser.error(f"Godot executable not found: {options.godot}")
    version = subprocess.check_output([godot, "--version"], text=True).strip()
    if not version.startswith(GODOT_VERSION + ".stable"):
        parser.error(f"Expected Godot {GODOT_VERSION}.stable, found {version}")
    templates = template_directory(options.templates)
    local = ROOT / ".local/export"
    local.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    for variable, folder in (
        ("XDG_DATA_HOME", "data"),
        ("XDG_CONFIG_HOME", "config"),
        ("XDG_CACHE_HOME", "cache"),
    ):
        directory = local / folder
        directory.mkdir(exist_ok=True)
        env[variable] = str(directory)
    destination = ROOT / "dist/windows-x86_64"
    destination.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="client-", dir=local) as temporary:
        stage = Path(temporary) / "project"
        build = Path(temporary) / "windows-x86_64"
        build.mkdir()
        stage_project(stage, templates, include_maps=False)
        executable = build / "MT2Spacetime.exe"
        run(
            [godot, "--headless", "--path", stage, "--editor", "--import", "--quit"],
            local / "import.log",
            env,
        )
        run(
            [godot, "--headless", "--path", stage, "--export-release", PRESET, executable],
            local / "export.log",
            env,
        )
        pack_audit = audit_pack(godot, executable.with_suffix(".pck"), local, env)
        package_notices(stage, build, local)
        connection = {
            "server_url": options.server.rstrip("/"),
            "database": options.database,
            "default_player_name": options.player_name,
        }
        (build / "client_config.json").write_text(json.dumps(connection, indent=2) + "\n")
        (build / "README.txt").write_text(
            "MT2 Spacetime development client\n\n"
            "Extract the whole ZIP into a folder, then run MT2Spacetime.exe.\n"
            "Keep MT2Spacetime.pck and client_config.json next to the executable.\n"
            "No Godot, Blender, Rust, Python or SpacetimeDB SDK installation is needed.\n"
            "Choose a name and connect to the host's server and database.\n"
            "The host must run SpacetimeDB; localhost means your own computer.\n"
            "Edit client_config.json to change the default server address.\n"
            "See the repository docs/distribution.md for hosting and connection help.\n"
        )
        manifest = {
            "godot": version,
            "target": "windows-x86_64",
            "mode": "release",
            "pack_audit": pack_audit,
            "connection_defaults": connection,
            "template_sha256": digest(templates / "windows_release_x86_64.exe"),
            "files": {
                p.relative_to(build).as_posix(): digest(p)
                for p in sorted(build.rglob("*"))
                if p.is_file()
            },
        }
        if options.wine_smoke:
            wine = shutil.which("wine")
            if not wine:
                parser.error("Wine was requested but is not installed")
            wine_env = {
                **env,
                "WINEPREFIX": str(ROOT / ".local/wine-client"),
                "WINEARCH": "win64",
                "WINEDEBUG": "-all",
                "WINEDLLOVERRIDES": "mscoree,mshtml=d",
            }
            wine_output = run(
                [wine, executable, "--headless", "--quit-after", "90"],
                local / "wine-smoke.log",
                wine_env,
                timeout=120,
            )
            if GODOT_VERSION not in wine_output:
                raise RuntimeError("Wine smoke run did not print the expected Godot version")
            manifest["wine_smoke"] = {
                "status": "passed",
                "mode": "headless",
                "version": subprocess.check_output([wine, "--version"], text=True).strip(),
            }
        (build / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        if destination.exists():
            shutil.rmtree(destination)
        shutil.copytree(build, destination)
    archive = destination.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(destination.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(destination.parent))
    print(
        json.dumps(
            {
                "archive": str(archive),
                "archive_sha256": digest(archive),
                "executable": str(destination / "MT2Spacetime.exe"),
                "pack_audit": pack_audit,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit(str(error)) from error
