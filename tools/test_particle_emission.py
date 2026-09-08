#!/usr/bin/env python3
"""Run isolated Godot particle/flight component checks or the native effect gallery."""

import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--godot", required=True)
    parser.add_argument(
        "--scenario",
        choices=("emission", "motion", "render", "flight", "projectile", "mesh", "package"),
        default="emission",
    )
    parser.add_argument(
        "--expected-systems",
        type=int,
        default=22,
        help="Expected emission fixture system count (default: 22)",
    )
    parser.add_argument("--flights", type=Path)
    parser.add_argument(
        "--meshes", type=Path, help="Optional converted mesh catalog for projectiles"
    )
    args = parser.parse_args()
    if args.expected_systems < 1:
        parser.error("--expected-systems must be positive")
    output = args.output.resolve()
    scene = f"tests/particle_{args.scenario}_smoke.gd"
    if args.scenario == "flight":
        scene = "tests/projectile_flight_smoke.gd"
    if args.scenario == "mesh":
        scene = "tests/projectile_mesh_smoke.gd"
    if args.scenario in ("projectile", "package"):
        if args.scenario == "projectile" and args.flights is None:
            parser.error("--scenario projectile requires --flights")
        scene = "tests/projectile_effect_smoke.gd"
    files = ["scripts/actors/particle_emission.gd", scene]
    if args.scenario == "mesh":
        files = ["scripts/actors/projectile_mesh_effect.gd", scene]
    if args.scenario in ("motion", "render", "projectile", "package"):
        files += ["scripts/actors/particle_motion.gd", "scripts/actors/particle_simulation.gd"]
        files += ["scripts/actors/particle_style.gd"]
    if args.scenario in ("render", "projectile", "package"):
        files += ["scripts/actors/particle_effect.gd"]
    if args.scenario in ("projectile", "package"):
        files += [
            "scripts/actors/projectile_flight.gd",
            "scripts/actors/projectile_effect.gd",
            "scripts/actors/projectile_trail.gd",
            "scripts/actors/projectile_mesh_effect.gd",
            "scripts/world/world_projectiles.gd",
            "scripts/content/projectile_catalog.gd",
        ]
    if args.scenario == "flight":
        files += ["scripts/actors/particle_motion.gd", "scripts/actors/projectile_flight.gd"]
    inputs = [ROOT / "client" / f for f in files] + [args.catalog.resolve(), Path(__file__)]
    if args.scenario == "projectile":
        inputs.append(args.flights.resolve())
        if args.meshes is not None:
            inputs.append(args.meshes.resolve())
    frozen = {str(p.resolve()): digest(p) for p in inputs}
    output.mkdir(parents=True, exist_ok=False)
    (output / "project.godot").write_text(
        'config_version=5\n[application]\nconfig/name="Particle emission QA"\n'
    )
    for relative in files:
        destination = output / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / "client" / relative, destination)
    shutil.copy2(args.catalog, output / "effects.v1.json")
    extra_args = [str(args.expected_systems)] if args.scenario == "emission" else []
    if args.scenario == "projectile":
        shutil.copy2(args.flights, output / "flights.v1.json")
        extra_args = [str(output / "flights.v1.json")]
        if args.meshes is not None:
            shutil.copy2(args.meshes, output / "mesh-effects.v1.json")
            extra_args.append(str(output / "mesh-effects.v1.json"))
    if args.scenario in ("render", "projectile"):
        catalog = json.loads(args.catalog.read_text())
        for texture in catalog["textures"].values():
            relative = Path(texture["path"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe particle texture path")
            source = args.catalog.resolve().parent / relative
            if digest(source) != texture["sha256"]:
                raise ValueError("Particle texture does not match catalog")
            destination = output / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if digest(destination) != texture["sha256"]:
                raise ValueError("Particle texture changed while copying")
    env = {**os.environ, "XDG_DATA_HOME": str(output / "userdata")}
    mesh_catalog = args.catalog if args.scenario in ("mesh", "package") else args.meshes
    if mesh_catalog is not None:
        catalog = json.loads(mesh_catalog.read_text())
        assets = []
        if args.scenario == "package":
            assets = list(catalog["files"].items()) + list(catalog["import_sidecars"].items())
        else:
            for mesh in catalog["meshes"]:
                assets.append((mesh["model"], mesh["model_sha256"]))
                assets.extend((g["texture"], g["texture_sha256"]) for g in mesh["geometries"])
        for path, expected in assets:
            relative = Path(path)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Unsafe mesh asset path")
            source = mesh_catalog.resolve().parent / relative
            destination = output / relative
            if digest(source) != expected:
                raise ValueError("Mesh asset differs from catalog")
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)
            if digest(destination) != expected:
                raise ValueError("Mesh asset changed while copying")
        with (output / "import.log").open("w") as log:
            imported = subprocess.run(
                [
                    args.godot,
                    "--headless",
                    "--editor",
                    "--import",
                    "--path",
                    str(output),
                    "--lsp-port",
                    "6481",
                    "--dap-port",
                    "6482",
                ],
                env=env,
                stdout=log,
                stderr=subprocess.STDOUT,
                timeout=60,
                check=False,
            )
        if imported.returncode or "ERROR:" in (output / "import.log").read_text():
            raise RuntimeError(f"Mesh fixture import failed: {output / 'import.log'}")
    prefix = [args.godot, "--headless"]
    if args.scenario in ("render", "projectile", "mesh", "package"):
        prefix = ["xvfb-run", "-a", args.godot, "--rendering-method", "gl_compatibility"]
    with (output / "run.log").open("w") as log:
        process = subprocess.Popen(
            [
                *prefix,
                "--path",
                str(output),
                "--script",
                "res://" + scene,
                "--",
                str(output / "effects.v1.json"),
                *extra_args,
            ],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            process.wait(timeout=120)
        except subprocess.TimeoutExpired:
            # xvfb-run launches children: terminate the entire isolated group.
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise
    log = (output / "run.log").read_text()
    rows = [json.loads(line) for line in log.splitlines() if line.startswith('{"checks":')]
    if process.returncode or "ERROR:" in log or len(rows) != 1 or rows[0]["failures"]:
        raise RuntimeError(f"Particle emission QA failed; inspect {output / 'run.log'}")
    if any(digest(Path(p)) != expected for p, expected in frozen.items()):
        raise RuntimeError("Particle emission QA inputs changed during the run")
    report = {
        **rows[0],
        "scenario": args.scenario,
        "inputs": frozen,
        "engine_log_sha256": digest(output / "run.log"),
        "rendering_verified": args.scenario in ("render", "projectile", "mesh", "package"),
        "server_integration_verified": False,
        "captures": {p.name: digest(p) for p in sorted(output.glob("effect-*.png"))},
    }
    (output / "report.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"checks": report["checks"], "failures": report["failures"]}))


if __name__ == "__main__":
    main()
