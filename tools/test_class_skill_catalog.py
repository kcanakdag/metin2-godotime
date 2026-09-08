#!/usr/bin/env python3
"""Compile and execute every candidate class-skill formula with the actual Rust interpreter."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(command, log):
    result = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=180,
        check=False,
    )
    log.write_text(result.stdout)
    if result.returncode:
        raise RuntimeError(f"Class skill qualification failed; see {log}")
    return result.stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    catalog = args.catalog.resolve()
    inputs = {
        "catalog": catalog,
        "runtime": ROOT / "server/src/skill_formula.rs",
        "compiler": ROOT / "server/build_class_skills.rs",
        "geometry_compiler": ROOT / "server/build_skill_geometry.rs",
        "hit_runtime": ROOT / "server/src/skill_hits.rs",
        "harness": Path(__file__).resolve(),
    }
    hashes = {name: hashlib.sha256(path.read_bytes()).hexdigest() for name, path in inputs.items()}
    initial = hashes["catalog"]
    source = json.loads(catalog.read_bytes())
    window_checks = []
    metadata_checks = []
    for skill in source["skills"]:
        for variant in skill["variants"]:
            windows = [[hit["start_us"], hit["end_us"]] for hit in variant["hits"]]
            shapes = []
            for hit in variant["hits"]:
                if hit["kind"] == "attack_area":
                    spheres = []
                    for sphere in hit["spheres"]:
                        position = ",".join(f"{float(v)!r}f32" for v in sphere["position_m"])
                        spheres.append(
                            "definitions::SkillHitSphere { position_m:["
                            + position
                            + "],radius_m:"
                            + f"{float(sphere['radius_m'])!r}f32"
                            + "}"
                        )
                    shapes.append(
                        "definitions::SkillHitGeometry::Area { spheres:&["
                        + ",".join(spheres)
                        + "]}"
                    )
                else:
                    shapes.append(
                        "definitions::SkillHitGeometry::Weapon { bone:"
                        + json.dumps(hit["bone"])
                        + ",length_m:"
                        + f"{float(hit['weapon_length_m'])!r}f32"
                        + "}"
                    )
            shape_assert = (
                "let shapes: &[definitions::SkillHitGeometry] = &["
                + ",".join(shapes)
                + "]; assert_eq!(motion.hit_geometry, shapes);"
            )
            window_checks.append(
                "{ let motion = definitions::CLASS_SKILL_MOTIONS.iter().find(|m|"
                + f"m.skill_vnum == {skill['vnum']} && m.actor_id == "
                + json.dumps(variant["actor_id"])
                + " ).unwrap(); let expected: &[[i64; 2]] = &"
                + json.dumps(windows)
                + "; assert_eq!(motion.hit_windows_us, expected); "
                + shape_assert
                + " }\n"
            )
        attribute = {"NORMAL": "Normal", "MELEE": "Melee", "RANGE": "Range", "MAGIC": "Magic"}[
            skill["attribute"]
        ]
        affects = [
            f"Some({int(skill[field])})" if skill[field] else "None"
            for field in ("affect", "secondary_affect")
        ]
        metadata_checks.append(
            "{ let skill = definitions::CLASS_SKILLS.iter().find(|s|s.vnum == "
            + str(skill["vnum"])
            + ").unwrap();\n"
            + f"assert_eq!(skill.minimum_level, {skill['minimum_level']});\n"
            + f"assert_eq!(skill.maximum_rank, {skill['maximum_rank']});\n"
            + f"assert_eq!(skill.attribute, definitions::SkillAttribute::{attribute});\n"
            + f"assert_eq!(skill.affect, {affects[0]});\n"
            + f"assert_eq!(skill.secondary_affect, {affects[1]}); }}\n"
        )
    generated = output / "definitions.rs"
    run(
        [
            shutil.which("cargo") or "cargo",
            "run",
            "--manifest-path",
            str(ROOT / "server/Cargo.toml"),
            "--features",
            "yongan",
            "--offline",
            "--example",
            "compile_class_skills",
            "--",
            str(catalog),
            str(generated),
        ],
        output / "compile.log",
    )
    harness = output / "formulas.rs"
    harness.write_text(
        "#[path="
        + json.dumps(str(ROOT / "server/src/skill_formula.rs"))
        + "] pub mod skill_formula;\n"
        + "#[path="
        + json.dumps(str(ROOT / "server/src/skill_hits.rs"))
        + "] pub mod skill_hits;\n"
        + "pub mod definitions { include!("
        + json.dumps(str(generated))
        + "); }\n"
        "fn main() {\n"
        + "".join(metadata_checks)
        + "".join(window_checks)
        + f"assert_eq!(definitions::CLASS_SKILL_RANK_POWERS, {source['rank_power_percent']});\n"
        + """
    assert_eq!(definitions::CLASS_SKILLS.len(),44);
    assert_eq!(definitions::CLASS_SKILL_MOTIONS.len(),88);
    for motion in definitions::CLASS_SKILL_MOTIONS.iter().filter(|m| m.skill_vnum == 1) {
        let mut receipts = Vec::new();
        for now in [0,162206,200000,362207,434712,500000,634713,849959,900000,1049960] {
            let active = skill_hits::active_events(motion.hit_windows_us, now).unwrap();
            for event in 0..motion.hit_windows_us.len() {
                if active & (1 << event) != 0 && skill_hits::admits(&receipts, 10, 1, event as u8, 3, 5).unwrap() {
                    receipts.push(skill_hits::receipt(10, 1, event as u8));
                }
            }
        }
        assert_eq!(receipts, vec!["10:1", "10:1:1", "10:1:2"]);
    }
    let powers = definitions::CLASS_SKILL_RANK_POWERS;
    let mut checks = 0;
    for skill in definitions::CLASS_SKILLS {
        for power in powers.iter().skip(1) {
            for mut vars in [[60.0,6.0,3.0,4.0,0.0,5.0,6.0,15.0,0.8,0.0], [10000.0,90.0,90.0,90.0,0.0,99.0,90.0,10000.0,1.0,6.0]] {
                vars[4] = f64::from(*power) / 100.0;
                for program in [skill.programs.amount, skill.programs.secondary, skill.programs.duration, skill.programs.secondary_duration, skill.programs.upkeep, skill.programs.splash_scale] {
                    let low = skill_formula::evaluate(program, &vars, |lo,_|lo).unwrap();
                    let high = skill_formula::evaluate(program, &vars, |_,hi|hi).unwrap();
                    assert!(low.is_finite() && high.is_finite());
                    checks += 2;
                }
            }
        }
    }
    println!("{}",checks);
}
"""
    )
    binary = output / ("formulas.exe" if os.name == "nt" else "formulas")
    run(
        [shutil.which("rustc") or "rustc", "--edition", "2024", str(harness), "-o", str(binary)],
        output / "rustc.log",
    )
    checks = int(run([str(binary)], output / "runtime.log").strip())
    for name, path in inputs.items():
        if hashlib.sha256(path.read_bytes()).hexdigest() != hashes[name]:
            raise RuntimeError(f"Class skill {name} changed during qualification")
    report = {
        "passed": True,
        "skills": 44,
        "appearances": 88,
        "formula_checks": checks,
        "metadata_checks": len(metadata_checks) * 5 + 1,
        "motion_window_checks": len(window_checks),
        "motion_geometry_checks": len(window_checks),
        "three_way_cut_timing_replays": 2,
        "catalog_sha256": initial,
        "runtime_sha256": hashes["runtime"],
        "compiler_sha256": hashes["compiler"],
        "geometry_compiler_sha256": hashes["geometry_compiler"],
        "hit_runtime_sha256": hashes["hit_runtime"],
        "harness_sha256": hashes["harness"],
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
