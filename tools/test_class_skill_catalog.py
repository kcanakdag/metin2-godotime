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
    initial = hashlib.sha256(catalog.read_bytes()).hexdigest()
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
        "pub mod definitions { include!(" + json.dumps(str(generated)) + "); }\n"
        """fn main() {
    assert_eq!(definitions::CLASS_SKILLS.len(),44);
    assert_eq!(definitions::CLASS_SKILL_MOTIONS.len(),88);
    let powers = [0.0,5.0,6.0,8.0,10.0,12.0,14.0,16.0,18.0,20.0,22.0,24.0,26.0,28.0,30.0,32.0,34.0,36.0,38.0,40.0,50.0];
    let mut checks = 0;
    for skill in definitions::CLASS_SKILLS {
        for power in powers.iter().skip(1) {
            for mut vars in [[60.0,6.0,3.0,4.0,0.0,5.0,6.0,15.0,0.8,0.0], [10000.0,90.0,90.0,90.0,0.0,99.0,90.0,10000.0,1.0,6.0]] {
                vars[4] = power / 100.0;
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
    if hashlib.sha256(catalog.read_bytes()).hexdigest() != initial:
        raise RuntimeError("Candidate catalog changed during qualification")
    report = {
        "passed": True,
        "skills": 44,
        "appearances": 88,
        "formula_checks": checks,
        "catalog_sha256": initial,
        "runtime_sha256": hashlib.sha256(
            (ROOT / "server/src/skill_formula.rs").read_bytes()
        ).hexdigest(),
    }
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
