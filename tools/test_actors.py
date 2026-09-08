#!/usr/bin/env python3
"""Exercise generated actor resources and presentation in an isolated Godot project."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from actor_texture_import import configure_actor_texture_imports

ROOT = Path(__file__).resolve().parents[1]
ACTOR_PROFILE = ROOT / "client/assets/imported/content/p0-warrior-dog"
TARGET_EFFECT_PROFILE = ROOT / "client/assets/imported/content/p2-target-effects"
PROJECT = """config_version=5
[application]
config/name="MT2 Actor Test"
[display]
window/size/viewport_width=1280
window/size/viewport_height=800
[rendering]
renderer/rendering_method="gl_compatibility"
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(command: list[str], environment: dict[str, str], log: Path) -> str:
    result = subprocess.run(
        command,
        env=environment,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=180,
        check=False,
    )
    log.write_text(result.stdout)
    if result.returncode or "SCRIPT ERROR:" in result.stdout or "\nERROR:" in result.stdout:
        raise SystemExit(f"Godot actor check failed; see {log}\n{result.stdout[-5000:]}")
    return result.stdout


def editor_scene_use(godot: str, project: Path, environment: dict[str, str], log: Path) -> str:
    return run(
        [
            "xvfb-run",
            "-a",
            "-s",
            "-screen 0 1280x800x24",
            godot,
            "--editor",
            "--path",
            str(project),
            "--quit-after",
            "180",
        ],
        environment,
        log,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    parser.add_argument(
        "--scenario",
        choices=[
            "actors",
            "fan",
            "class_skills",
            "equipped_skills",
            "skill_effects",
            "training_dummy",
            "mobs",
        ],
        default="actors",
    )
    parser.add_argument(
        "--character-package", type=Path, default=ROOT / "client/assets/imported/characters"
    )
    parser.add_argument("--authored-package", type=Path)
    parser.add_argument("--mob-content", type=Path, help="Converted wildlife for the mobs scenario")
    parser.add_argument("--native", action="store_true", help="Render under Xvfb and save a PNG.")
    parser.add_argument(
        "--texture-editor-check",
        action="store_true",
        help="Exercise the actor PNG policy through an Xvfb editor 3D-scene negative control.",
    )
    parser.add_argument("--effect-package", type=Path)
    parser.add_argument("--effect-catalog", type=Path)
    parser.add_argument("--effect-links", type=Path)
    parser.add_argument("--mixed-effect-catalog", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / ".local/actors")
    options = parser.parse_args()
    if (options.scenario == "mobs") != (options.mob_content is not None):
        parser.error("The mobs scenario requires --mob-content exclusively")
    if (
        options.scenario == "skill_effects"
        and not options.effect_package
        and (not options.effect_catalog or not options.effect_links)
    ):
        parser.error("skill_effects requires --effect-catalog and --effect-links")
    options.output = options.output.resolve()
    options.output.mkdir(parents=True, exist_ok=True)
    report_path = options.output / "report.json"
    report_path.write_text(json.dumps({"passed": False, "status": "started"}, indent=2) + "\n")
    if not (ACTOR_PROFILE / "manifest.v1.json").is_file():
        raise SystemExit("Missing P1 actor profile; run the content import first.")
    target_effect_catalog = TARGET_EFFECT_PROFILE / "runtime-catalog.v1.json"
    if not target_effect_catalog.is_file():
        raise SystemExit(
            "Missing target-effect catalog; run import_target_effects.py --install first."
        )
    texture_editor_check = options.texture_editor_check or (
        options.native and options.scenario not in ("training_dummy", "mobs", "skill_effects")
    )
    if texture_editor_check and not shutil.which("xvfb-run"):
        raise SystemExit("Actor texture editor import verification requires xvfb-run.")
    with tempfile.TemporaryDirectory(prefix="project-", dir=options.output) as scratch:
        stage = Path(scratch)
        shutil.copytree(
            ROOT / "client" / "assets/imported/skills", stage / "assets/imported/skills"
        )
        shutil.copytree(ROOT / "client/scripts/actors", stage / "scripts/actors")
        shutil.copytree(ROOT / "client/scripts/content", stage / "scripts/content")
        (stage / "scripts/world").mkdir()
        shutil.copy2(
            ROOT / "client/scripts/world/world_picker.gd", stage / "scripts/world/world_picker.gd"
        )
        if options.scenario == "skill_effects":
            shutil.copy2(
                ROOT / "client/scripts/world/world_motion_effects.gd",
                stage / "scripts/world/world_motion_effects.gd",
            )
            shutil.copy2(
                ROOT / "client/scripts/world/world_skill_effects.gd",
                stage / "scripts/world/world_skill_effects.gd",
            )
        if options.scenario == "skill_effects" and not options.effect_package:
            effects = stage / "effect-candidate"
            effects.mkdir()
            shutil.copy2(options.effect_catalog, effects / "effects.v1.json")
            shutil.copy2(options.effect_links, effects / "links.json")
            for texture in json.loads(options.effect_catalog.read_text())["textures"].values():
                relative = Path(texture["path"])
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("Unsafe effect texture path")
                source = options.effect_catalog.resolve().parent / relative
                if sha256(source) != texture["sha256"]:
                    raise ValueError("Effect texture hash mismatch")
                destination = effects / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
        if options.effect_package:
            package = json.loads((options.effect_package / "catalog.v1.json").read_text())
            destination = stage / "effect-package"
            destination.mkdir()
            shutil.copy2(
                options.effect_package / "catalog.v1.json", destination / "catalog.v1.json"
            )
            for relative, expected in {**package["files"], **package["import_sidecars"]}.items():
                path = Path(relative)
                if path.is_absolute() or ".." in path.parts:
                    raise ValueError("Unsafe packaged effect path")
                source = options.effect_package / path
                if sha256(source) != expected:
                    raise ValueError("Packaged effect resource differs")
                target = destination / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        if options.mixed_effect_catalog:
            mixed_dir = stage / "mixed-candidate"
            mixed_dir.mkdir()
            mixed = json.loads(options.mixed_effect_catalog.read_text())
            shutil.copy2(options.mixed_effect_catalog, mixed_dir / "catalog.json")
            assets = [(t["path"], t["sha256"]) for t in mixed["textures"].values()]
            for mesh in mixed["meshes"]:
                assets.append((mesh["model"], mesh["model_sha256"]))
                assets.extend((g["texture"], g["texture_sha256"]) for g in mesh["geometries"])
            for name, expected in assets:
                relative = Path(name)
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("Unsafe mixed effect asset path")
                source = options.mixed_effect_catalog.resolve().parent / relative
                if sha256(source) != expected:
                    raise ValueError("Mixed effect asset hash mismatch")
                target = mixed_dir / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        shutil.copytree(ACTOR_PROFILE, stage / "assets/imported/content/p0-warrior-dog")
        shutil.copytree(options.character_package, stage / "assets/imported/characters")
        shutil.copytree(TARGET_EFFECT_PROFILE, stage / "assets/imported/content/p2-target-effects")
        if options.authored_package:
            authored = stage / "assets/imported/authored/training-dummy"
            authored.mkdir(parents=True)
            for name in ("training-dummy.glb", "manifest.v1.json"):
                shutil.copy2(options.authored_package / name, authored / name)
        if options.mob_content:
            generated = stage / "mob-candidate"
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/build_mob_catalog.py"),
                    "--content",
                    str(options.mob_content.resolve()),
                    "--output",
                    str(generated),
                ],
                check=True,
            )
            shutil.copytree(options.mob_content / "generated", stage / "assets/imported/mobs")
            shutil.copy2(
                generated / "presentation.v1.json",
                stage / "assets/imported/mobs/presentation.v1.json",
            )
            shutil.copy2(generated / "gameplay.v1.json", stage / "mob-gameplay.json")
        (stage / "tests").mkdir()
        shutil.copy2(ROOT / "client/tests/mob_actor_smoke.gd", stage / "tests/mob_actor_smoke.gd")
        selected_smoke = {
            "actors": "actor_smoke.gd",
            "fan": "fan_actor_smoke.gd",
            "class_skills": "class_skill_actor_smoke.gd",
            "equipped_skills": "equipped_skill_actor_smoke.gd",
            "skill_effects": "skill_effect_actor_smoke.gd",
            "training_dummy": "training_dummy_smoke.gd",
            "mobs": "mob_actor_smoke.gd",
        }[options.scenario]
        shutil.copy2(ROOT / "client/tests" / selected_smoke, stage / "tests" / selected_smoke)
        shutil.copy2(
            ROOT / "client/tests/training_dummy_smoke.gd", stage / "tests/training_dummy_smoke.gd"
        )
        shutil.copy2(
            ROOT / "client/tests/class_skill_actor_smoke.gd",
            stage / "tests/class_skill_actor_smoke.gd",
        )
        shutil.copy2(ROOT / "client/tests/fan_actor_smoke.gd", stage / "tests/fan_actor_smoke.gd")
        shutil.copy2(ROOT / "client/tests/actor_smoke.gd", stage / "tests/actor_smoke.gd")
        shutil.copy2(
            ROOT / "tools/actor_texture_import_probe.gd",
            stage / "tests/actor_texture_import_probe.gd",
        )
        shutil.copy2(
            ROOT / "tools/actor_texture_3d_probe.gd",
            stage / "tests/actor_texture_3d_probe.gd",
        )
        shutil.copy2(
            ROOT / "tools/actor_texture_3d_scene.tscn",
            stage / "tests/actor_texture_3d_scene.tscn",
        )
        if texture_editor_check:
            plugin = stage / "addons/actor_texture_3d_probe"
            plugin.mkdir(parents=True)
            shutil.copy2(ROOT / "tools/actor_texture_3d_editor_plugin.cfg", plugin / "plugin.cfg")
            shutil.copy2(
                ROOT / "tools/actor_texture_3d_editor_plugin.gd",
                plugin / "actor_texture_3d_editor_plugin.gd",
            )
            project = PROJECT + (
                "[editor_plugins]\n"
                'enabled=PackedStringArray("res://addons/actor_texture_3d_probe/plugin.cfg")\n'
            )
        else:
            plugin = None
            project = PROJECT
        (stage / "project.godot").write_text(project)
        actor_texture_sidecars = configure_actor_texture_imports(
            stage / "assets/imported/content/p0-warrior-dog/actors"
        )
        actor_texture_policy_sha256 = {path.name: sha256(path) for path in actor_texture_sidecars}
        if texture_editor_check:
            negative = stage / "negative-3d-compression"
            shutil.copytree(
                stage,
                negative,
                ignore=shutil.ignore_patterns(".cache", ".config", ".data", ".godot"),
            )
            negative_sidecars = [
                negative / path.relative_to(stage) for path in actor_texture_sidecars
            ]
            for sidecar in negative_sidecars:
                sidecar.write_text(
                    sidecar.read_text().replace(
                        "detect_3d/compress_to=0", "detect_3d/compress_to=1"
                    )
                )
        staged_target_catalog = (
            stage / "assets/imported/content/p2-target-effects/runtime-catalog.v1.json"
        )
        tested_files = {
            "actor_profile_manifest": sha256(
                stage / "assets/imported/content/p0-warrior-dog/manifest.v1.json"
            ),
            "actor_catalog": sha256(stage / "scripts/content/actor_catalog.gd"),
            "actor_node": sha256(stage / "scripts/actors/pve_actor.gd"),
            "actor_presentation": sha256(stage / "scripts/actors/actor_presentation.gd"),
            "target_effect_catalog": sha256(stage / "scripts/content/target_effect_catalog.gd"),
            "target_effect_node": sha256(stage / "scripts/actors/target_effect.gd"),
            "target_effect_runtime_catalog": sha256(staged_target_catalog),
            "smoke": sha256(stage / "tests" / selected_smoke),
            "smoke_base": sha256(stage / "tests/actor_smoke.gd"),
            "character_catalog": sha256(stage / "assets/imported/characters/catalog.v1.json"),
            "attack_input": sha256(stage / "scripts/actors/attack_input.gd"),
            "actor_texture_import_probe": sha256(stage / "tests/actor_texture_import_probe.gd"),
            "actor_texture_3d_probe": sha256(stage / "tests/actor_texture_3d_probe.gd"),
            "actor_texture_3d_scene": sha256(stage / "tests/actor_texture_3d_scene.tscn"),
            **(
                {
                    "actor_texture_3d_editor_plugin": sha256(
                        plugin / "actor_texture_3d_editor_plugin.gd"
                    )
                }
                if plugin is not None
                else {}
            ),
        }
        if options.mob_content:
            tested_files["mob_gameplay"] = sha256(stage / "mob-gameplay.json")
            tested_files["mob_presentation"] = sha256(stage / "mob-candidate/presentation.v1.json")
        if options.authored_package:
            tested_files["authored_manifest"] = sha256(authored / "manifest.v1.json")
            tested_files["authored_model"] = sha256(authored / "training-dummy.glb")
        if options.scenario == "skill_effects" and not options.effect_package:
            tested_files["effect_catalog"] = sha256(options.effect_catalog)
            tested_files["effect_links"] = sha256(options.effect_links)
            tested_files["world_motion_effects"] = sha256(
                stage / "scripts/world/world_motion_effects.gd"
            )
        if options.mixed_effect_catalog:
            tested_files["mixed_effect_catalog"] = sha256(options.mixed_effect_catalog)
        if options.effect_package:
            tested_files["effect_package"] = sha256(options.effect_package / "catalog.v1.json")
            tested_files["motion_effect_loader"] = sha256(
                stage / "scripts/content/motion_effect_catalog.gd"
            )
            tested_files["world_motion_effects"] = sha256(
                stage / "scripts/world/world_motion_effects.gd"
            )
        environment = {
            **os.environ,
            "XDG_DATA_HOME": str(stage / ".data"),
            "XDG_CONFIG_HOME": str(stage / ".config"),
            "XDG_CACHE_HOME": str(stage / ".cache"),
        }
        run(
            [
                options.godot,
                "--headless",
                "--path",
                str(stage),
                "--import",
                "--quit-after",
                "2",
            ],
            environment,
            options.output / "import.log",
        )
        first_import_sha256 = {path.name: sha256(path) for path in actor_texture_sidecars}
        for sidecar in actor_texture_sidecars:
            settings = sidecar.read_text()
            for line in (
                "compress/mode=0",
                "mipmaps/generate=true",
                "detect_3d/compress_to=0",
                "process/fix_alpha_border=true",
            ):
                if line not in settings:
                    raise SystemExit(
                        f"Godot removed selected actor texture policy {line}: {sidecar}"
                    )
            if "compress/mode=2" in settings or '"vram_texture": true' in settings:
                raise SystemExit(
                    f"Godot enabled VRAM compression for selected actor texture: {sidecar}"
                )
        if texture_editor_check:
            material_output = run(
                [
                    "xvfb-run",
                    "-a",
                    "-s",
                    "-screen 0 1280x800x24",
                    options.godot,
                    "--path",
                    str(stage),
                    "--scene",
                    "res://tests/actor_texture_3d_scene.tscn",
                    "--quit-after",
                    "8",
                ],
                environment,
                options.output / "texture-3d.log",
            )
            if "SCRIPT ERROR:" in material_output:
                raise SystemExit("Actor texture 3D material scene did not run.")
            editor_output = editor_scene_use(
                options.godot, stage, environment, options.output / "texture-3d-editor.log"
            )
            if "ACTOR_TEXTURE_EDITOR_SCENE PASS" not in editor_output:
                raise SystemExit("Actor texture editor scene probe did not report completion.")
            negative_environment = {
                **environment,
                "XDG_DATA_HOME": str(negative / ".data"),
                "XDG_CONFIG_HOME": str(negative / ".config"),
                "XDG_CACHE_HOME": str(negative / ".cache"),
            }
            negative_output = editor_scene_use(
                options.godot,
                negative,
                negative_environment,
                options.output / "texture-3d-negative.log",
            )
            if "ACTOR_TEXTURE_EDITOR_SCENE PASS" not in negative_output:
                raise SystemExit(
                    "Actor texture negative-control editor scene did not report completion."
                )
            for sidecar in negative_sidecars:
                settings = sidecar.read_text()
                if "compress/mode=2" not in settings or "detect_3d/compress_to=0" not in settings:
                    raise SystemExit(
                        "Old 3D auto-compression policy did not reproduce a VRAM rewrite."
                    )
        else:
            run(
                [
                    options.godot,
                    "--headless",
                    "--editor",
                    "--path",
                    str(stage),
                    "--import",
                    "--quit-after",
                    "2",
                ],
                environment,
                options.output / "repeat-import.log",
            )
        material_output = run(
            [
                options.godot,
                "--headless",
                "--path",
                str(stage),
                "--script",
                "res://tests/actor_texture_3d_probe.gd",
            ],
            environment,
            options.output / "texture-3d-pixels.log",
        )
        if "ACTOR_TEXTURE_3D PASS" not in material_output:
            raise SystemExit("Actor texture 3D material probe did not report completion.")
        if first_import_sha256 != {path.name: sha256(path) for path in actor_texture_sidecars}:
            raise SystemExit(
                "Godot changed selected actor texture import settings after editor scene use."
            )
        texture_output = run(
            [
                options.godot,
                "--headless",
                "--path",
                str(stage),
                "--script",
                "res://tests/actor_texture_import_probe.gd",
            ],
            environment,
            options.output / "texture-import.log",
        )
        texture_match = re.search(r"ACTOR_TEXTURE_IMPORT PASS (\d+) textures", texture_output)
        if not texture_match:
            raise SystemExit("Actor texture import probe did not report completion.")
        command = [options.godot, "--path", str(stage), "--script", "res://tests/" + selected_smoke]
        if options.native:
            command = ["xvfb-run", "-a", "-s", "-screen 0 1280x800x24", *command]
        else:
            command.insert(1, "--headless")
        try:
            output = run(command, environment, options.output / "runtime.log")
        finally:
            for screenshot in (stage / ".data/godot/app_userdata/MT2 Actor Test").glob(
                "actors-*.png"
            ):
                shutil.copy2(screenshot, options.output / screenshot.name)
        match = re.search(r"ACTOR_SMOKE PASS (\d+) checks", output)
        if not match:
            raise SystemExit("Godot actor smoke did not report completion.")
        report: dict[str, object] = {
            "passed": True,
            "checks": int(match.group(1)),
            "native": options.native,
            "scenario": options.scenario,
            "profile": "p0-warrior-dog",
            "target_effect_content_hash": json.loads(staged_target_catalog.read_text())[
                "content_hash"
            ],
            "actor_texture_import": {
                "textures": int(texture_match.group(1)),
                "material_3d": True,
                "editor_3d_negative_control_vram_rewrite": texture_editor_check,
                "requested_sidecar_sha256": actor_texture_policy_sha256,
                "effective_sidecar_sha256": first_import_sha256,
            },
            "tested_sha256": tested_files,
        }
        capture_directory = stage / ".data/godot/app_userdata/MT2 Actor Test"
        if options.native:
            screenshots = sorted(capture_directory.glob("actors-*.png"))
            required_captures = 2 if options.scenario == "training_dummy" else 6
            if len(screenshots) < required_captures:
                raise SystemExit("Native actor smoke did not produce its staged screenshots.")
            for screenshot in screenshots:
                shutil.copy2(screenshot, options.output / screenshot.name)
            report["screenshots"] = [screenshot.name for screenshot in screenshots]
        report_path.write_text(json.dumps(report, indent=2) + "\n")
        print(f"Verified {match.group(1)} Godot actor checks; evidence: {options.output}")


if __name__ == "__main__":
    main()
