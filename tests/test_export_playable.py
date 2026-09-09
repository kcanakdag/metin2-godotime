import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from content_compile import canonical_bytes
from export_playable import stage_motion_effect_package


def write_package(root: Path, character_hash: str = "character", skill_hash: str = "skills"):
    runtime = root / "runtime"
    runtime.mkdir(parents=True)
    asset = b"texture"
    asset_hash = hashlib.sha256(asset).hexdigest()
    (runtime / "assets").mkdir()
    (runtime / f"assets/{asset_hash}.png").write_bytes(asset)
    sidecar = b"[remap]\n"
    (runtime / f"assets/{asset_hash}.png.import").write_bytes(sidecar)
    document = {
        "schema": "mt2spacetime.motion-effects",
        "version": 1,
        "character_catalog_sha256": character_hash,
        "skill_catalog_sha256": skill_hash,
        "effects": {},
        "mixed_effects": {},
        "textures": {},
        "links": {"hero.skill": []},
        "files": {f"assets/{asset_hash}.png": asset_hash},
        "import_sidecars": {f"assets/{asset_hash}.png.import": hashlib.sha256(sidecar).hexdigest()},
    }
    document["content_hash"] = hashlib.sha256(canonical_bytes(document)).hexdigest()
    (runtime / "catalog.v1.json").write_bytes(canonical_bytes(document) + b"\n")
    return document


class ExportPlayableTests(unittest.TestCase):
    def test_motion_package_is_validated_and_staged(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "package"
            write_package(package)
            destination = root / "stage/motion_effects"
            stage_motion_effect_package(package, destination, "character", "skills")
            self.assertEqual(
                (destination / "catalog.v1.json").read_bytes(),
                (package / "runtime/catalog.v1.json").read_bytes(),
            )
            self.assertTrue((destination / "assets").is_dir())

    def test_motion_package_rejects_catalog_and_resource_mismatches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package = root / "package"
            write_package(package)
            with self.assertRaisesRegex(ValueError, "staged skills"):
                stage_motion_effect_package(package, root / "stage", "character", "other")
            catalog = package / "runtime/catalog.v1.json"
            document = json.loads(catalog.read_text())
            asset = next((package / "runtime").glob("assets/*.png"))
            asset.write_bytes(b"changed")
            unsigned = dict(document)
            unsigned.pop("content_hash", None)
            document["content_hash"] = hashlib.sha256(canonical_bytes(unsigned)).hexdigest()
            catalog.write_bytes(canonical_bytes(document) + b"\n")
            with self.assertRaisesRegex(ValueError, "resource"):
                stage_motion_effect_package(package, root / "stage", "character", "skills")


if __name__ == "__main__":
    unittest.main()
