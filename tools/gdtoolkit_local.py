#!/usr/bin/env python3
"""Launch pinned gdtoolkit with its grammar cache inside the repository."""

import importlib
import sys
from importlib.metadata import version
from pathlib import Path

from gdtoolkit.parser import parser

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    modules = {"lint": "linter", "format": "formatter"}
    if len(sys.argv) < 2 or sys.argv[1] not in modules:
        raise SystemExit("Usage: gdtoolkit_local.py lint|format [gdtoolkit options and paths]")
    if version("gdtoolkit") != "4.5.0":
        raise SystemExit("The local-cache adapter requires pinned gdtoolkit 4.5.0.")
    # Upstream 4.5.0 ignores XDG_CACHE_HOME and unconditionally writes to ~/.cache.
    # Redirect only this parser instance; leave dependency source and HOME intact.
    parser._cache_dirpath = str(ROOT / ".cache/gdtoolkit")
    operation = sys.argv.pop(1)
    sys.argv[0] = "gdlint" if operation == "lint" else "gdformat"
    importlib.import_module(f"gdtoolkit.{modules[operation]}.__main__").main()


if __name__ == "__main__":
    main()
