#!/usr/bin/env python3
"""Fetch a small, pinned Metin2 fixture and the Carbon importer source.

Original assets and downloaded third-party code stay in ignored directories.
No Blender add-on is installed or executed by this script.
"""

import base64
import hashlib
import json
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METIN_COMMIT = "bb19e9abda71c4545d35a3f9bf8cfedf3ce3c7b7"
CARBON_COMMIT = "8cba23114bf1d30c9da597c1ecf49271e00b939d"
API = "https://git.old-metin2.com/api/v1/repos/metin2/client/contents/"
BASE = "bin/pack/PC/ymir work/pc/warrior/"
FILES = [
    "warrior_novice.gr2",
    "warrior_novice_red.dds",
    "warrior_novice_blue.dds",
    "warrior_novice_hair.dds",
    "warrior_face.dds",
    "general/wait.gr2",
    "general/wait.msa",
    "general/walk.gr2",
    "general/walk.msa",
    "general/run.gr2",
    "general/run.msa",
    "general/attack.gr2",
    "general/attack.msa",
]


def fetch(url):
    request = urllib.request.Request(url, headers={"User-Agent": "mt2spacetime-asset-test"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def main():
    asset_root = ROOT / "assets/source/warrior"
    asset_root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "repository": "https://git.old-metin2.com/metin2/client",
        "commit": METIN_COMMIT,
        "files": [],
    }
    for name in FILES:
        api_url = API + urllib.parse.quote(BASE + name, safe="/") + "?ref=" + METIN_COMMIT
        entry = json.loads(fetch(api_url))
        content = base64.b64decode(entry["content"])
        git_sha = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        if git_sha != entry["sha"]:
            raise ValueError(f"Git blob hash mismatch: {name}")
        destination = asset_root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
        manifest["files"].append(
            {
                "path": name,
                "source_path": BASE + name,
                "size": len(content),
                "git_sha": git_sha,
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
        print(f"Fetched {name}: {len(content)} bytes", flush=True)
    (asset_root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")

    cache = ROOT / ".cache"
    cache.mkdir(exist_ok=True)
    source_root = cache / f"tools-blender-{CARBON_COMMIT}"
    if not source_root.exists():
        archive = cache / "carbon-importer.tar.gz"
        archive.write_bytes(
            fetch(
                f"https://codeload.github.com/carbonenginejs/tools-blender/tar.gz/{CARBON_COMMIT}"
            )
        )
        with tarfile.open(archive) as tar:
            tar.extractall(cache, filter="data")
    print(f"Importer source: {source_root}")


if __name__ == "__main__":
    main()
