#!/usr/bin/env python3
"""Export isolated Web/Linux clients; optional instrumentation exists only in test builds."""

import argparse
import gzip
import json
import os
import shutil
import tempfile
from pathlib import Path

from check_world_packs import check_world_packs
from export_client import (
    ROOT,
    audit_pack,
    digest,
    p1_profile_requirements,
    package_notices,
    run,
    stage_project,
    template_directory,
)
from target_effect_export import (
    audit_target_effect_pack,
    prepare_target_effect_imports,
    stage_target_effects,
    target_effect_requirements,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=["web", "linux"], default="web")
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    parser.add_argument("--templates")
    parser.add_argument("--server", default="http://127.0.0.1:3210")
    parser.add_argument("--database", default="mt2-dev-world")
    parser.add_argument("--include-map", action="store_true")
    parser.add_argument("--test-probe", action="store_true")
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Write the completed export to this isolated directory instead of dist/<target>",
    )
    parser.add_argument(
        "--work-dir",
        type=Path,
        help="Use this isolated directory for staging, imports, logs and temporary export files",
    )
    parser.add_argument("--skill-catalog", type=Path, help="Stage this candidate skill catalog")
    parser.add_argument("--ui-package", type=Path, help="Stage this converted UI package")
    args = parser.parse_args()
    if args.skill_catalog and not args.skill_catalog.is_file():
        parser.error("Candidate skill catalog is missing")
    if args.ui_package and not (args.ui_package / "manifest.json").is_file():
        parser.error("Candidate UI package manifest is missing")
    p1_requirements = p1_profile_requirements()
    live_target_effects = target_effect_requirements(ROOT / "client")
    templates = template_directory(args.templates)
    template = templates / (
        "web_nothreads_release.zip" if args.target == "web" else "linux_release.x86_64"
    )
    if not template.is_file():
        parser.error(f"Missing export template: {template}")
    suffix = "-test" if args.test_probe else ""
    destination = (
        args.output_dir.resolve() if args.output_dir else ROOT / "dist" / (args.target + suffix)
    )
    local = (
        args.work_dir.resolve()
        if args.work_dir
        else ROOT / ".local" / ("export-" + args.target + suffix)
    )
    local.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    for variable in ["XDG_DATA_HOME", "XDG_CONFIG_HOME", "XDG_CACHE_HOME"]:
        folder = local / variable.lower()
        folder.mkdir(exist_ok=True)
        env[variable] = str(folder)
    with tempfile.TemporaryDirectory(prefix="stage-", dir=local) as temp:
        # Godot writes a fixed tmpproject.binary filename during pack export.
        # Give each invocation its own OS temp directory for concurrent targets.
        godot_temp = Path(temp) / "godot-temp"
        godot_temp.mkdir()
        env["TMPDIR"] = str(godot_temp)
        stage = Path(temp) / "project"
        build = Path(temp) / "build"
        build.mkdir()
        stage_project(
            stage,
            templates,
            include_maps=args.include_map,
            p1_enabled=p1_requirements is not None,
        )
        if args.skill_catalog:
            shutil.copy2(args.skill_catalog, stage / "assets/imported/skills/catalog.v1.json")
        if args.ui_package:
            shutil.rmtree(stage / "assets/imported/ui")
            shutil.copytree(args.ui_package, stage / "assets/imported/ui")
        content_inputs = {
            "skills_sha256": digest(stage / "assets/imported/skills/catalog.v1.json"),
            "ui_manifest_sha256": digest(stage / "assets/imported/ui/manifest.json"),
        }
        staged_target_effects = stage_target_effects(ROOT / "client", stage, live_target_effects)
        config = {"server_url": args.server, "database": args.database}
        (stage / "client_config.json").write_text(json.dumps(config) + "\n")
        if args.test_probe:
            shutil.copy2(ROOT / "client/tests/export_probe.gd", stage / "scripts/export_probe.gd")
            main_script = stage / "scripts/main.gd"
            main_script.write_text(
                main_script.read_text().replace(
                    "func _ready() -> void:\n",
                    'func _ready() -> void:\n\tadd_child(preload("res://scripts/export_probe.gd").new())\n',
                )
            )
        platform = "Web" if args.target == "web" else "Linux"
        preset = (
            '[preset.0]\nname="Playable"\nplatform=' + json.dumps(platform) + "\n"
            'runnable=true\nexport_filter="all_resources"\ninclude_filter="*.json"\n'
            'exclude_filter="addons/godot_mcp/*,tests/*,*.md"\nscript_export_mode=2\n'
            "[preset.0.options]\ncustom_template/release=" + json.dumps(str(template)) + "\n"
            "variant/extensions_support=false\nvariant/thread_support=false\n"
            "vram_texture_compression/for_desktop=true\n"
            "vram_texture_compression/for_mobile=false\n"
            "html/export_icon=true\nhtml/canvas_resize_policy=2\n"
            "progressive_web_app/enabled=false\n"
            'binary_format/architecture="x86_64"\nbinary_format/embed_pck=false\n'
            "texture_format/s3tc_bptc=true\ntexture_format/etc2_astc=false\n"
        )
        (stage / "export_presets.cfg").write_text(preset)
        common = [args.godot, "--headless", "--path", stage]
        run([*common, "--editor", "--import", "--quit"], local / "import.log", env)
        prepare_target_effect_imports(stage, staged_target_effects)
        run(
            [*common, "--editor", "--import", "--quit"],
            local / "target-effect-reimport.log",
            env,
        )
        if args.include_map and args.target == "web":
            full_pack = Path(temp) / "world.pck"
            run([*common, "--export-pack", "Playable", full_pack], local / "world-export.log", env)
            run(
                [
                    args.godot,
                    "--headless",
                    "--main-pack",
                    full_pack,
                    "--script",
                    ROOT / "tools/pack_world.gd",
                    "--",
                    build / "world",
                ],
                local / "world-packs.log",
                env,
            )
            check_world_packs(args.godot, build / "world", local, env)
            # World data loads separately. Re-import a core-only staged project for the boot pack.
            shutil.rmtree(stage / "assets/imported/maps")
            run([*common, "--editor", "--import", "--quit"], local / "core-import.log", env)
        executable = build / ("index.html" if args.target == "web" else "MT2Spacetime.x86_64")
        run([*common, "--export-release", "Playable", executable], local / "export.log", env)
        audit = audit_pack(
            args.godot,
            executable.with_suffix(".pck"),
            local,
            env,
            allow_test_probe=args.test_probe,
            content_root=stage,
            p1_requirements=p1_requirements,
        )
        audit["target_effects"] = audit_target_effect_pack(
            args.godot,
            executable.with_suffix(".pck"),
            local,
            env,
            staged_target_effects,
        )
        mob_manifest = stage / "assets/imported/mobs/presentation.v1.json"
        if mob_manifest.is_file():
            mob_hash = json.loads(mob_manifest.read_text())["gameplay_hash"]
            mob_report = local / "mob-pack-audit.json"
            run(
                [
                    args.godot,
                    "--headless",
                    "--main-pack",
                    executable.with_suffix(".pck"),
                    "--script",
                    ROOT / "tools/audit_mob_pack.gd",
                    "--",
                    mob_hash,
                    mob_report,
                ],
                local / "mob-pack-audit.log",
                env,
            )
            audit["mobs"] = json.loads(mob_report.read_text())
        package_notices(stage, build, local)
        if args.target == "linux":
            executable.chmod(0o755)
            (build / "client_config.json").write_text(json.dumps(config) + "\n")
        for path in list(build.rglob("*")):
            if args.target == "web" and path.suffix in {".wasm", ".pck", ".js"}:
                path.with_suffix(path.suffix + ".gz").write_bytes(
                    gzip.compress(path.read_bytes(), compresslevel=9, mtime=0)
                )
        files = {
            p.relative_to(build).as_posix(): {"bytes": p.stat().st_size, "sha256": digest(p)}
            for p in sorted(build.rglob("*"))
            if p.is_file()
        }
        manifest = {
            "target": args.target,
            "test_probe": args.test_probe,
            "template_sha256": digest(template),
            "pack_audit": audit,
            "content_inputs": content_inputs,
            "files": files,
        }
        (build / "build-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        if destination.exists():
            shutil.rmtree(destination)
        destination.parent.mkdir(exist_ok=True)
        shutil.move(build, destination)
    print(json.dumps({"output": str(destination), **manifest}, indent=2))


if __name__ == "__main__":
    main()
