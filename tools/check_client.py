#!/usr/bin/env python3
"""Use the real Godot parser/runtime without sharing player settings with the editor."""

import argparse
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--godot", default=os.environ.get("GODOT", "godot"))
    options = parser.parse_args()
    output = ROOT / ".local/client-check"
    output.mkdir(parents=True, exist_ok=True)
    environment = {
        **os.environ,
        "XDG_DATA_HOME": str(output / "data"),
        "XDG_CONFIG_HOME": str(output / "config"),
    }
    for name, arguments in [
        (
            "import",
            [
                "--editor",
                "--import",
                "--quit",
                "--lsp-port",
                "6115",
                "--dap-port",
                "6116",
                "--debug-server",
                "tcp://127.0.0.1:6117",
            ],
        ),
        ("runtime", ["--quit-after", "180"]),
    ]:
        result = subprocess.run(
            [options.godot, "--headless", "--path", str(ROOT / "client"), *arguments],
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
            check=False,
        )
        log = output / f"{name}.log"
        log.write_text(result.stdout)
        if result.returncode or "SCRIPT ERROR:" in result.stdout or "ERROR:" in result.stdout:
            raise SystemExit(f"Godot {name} failed; see {log}\n{result.stdout[-5000:]}")
        print(f"Godot {name}: OK ({log})")


if __name__ == "__main__":
    main()
