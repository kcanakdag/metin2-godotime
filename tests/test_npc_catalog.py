"""NPC public boundary and artifact integrity regressions."""

import copy
import hashlib
import io
import json
import math
import struct
import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_npc_catalog import (
    CATALOG,
    RESOURCE_ROOT,
    artifact_path,
    heading,
    validate_package,
    validate_public,
)


class NpcCatalogTests(unittest.TestCase):
    def test_static_presentation_is_explicit_and_cannot_discard_idle_variants(self):
        doc = self.document()
        doc["version"] = 2
        with self.assertRaises(ValueError):
            validate_public(doc)
        actor = doc["actors"][0]
        actor["presentation"] = "animated"
        validate_public(doc)
        actor["presentation"] = "static"
        with self.assertRaises(ValueError):
            validate_public(doc)
        actor["idle"] = []
        validate_public(doc)
        actor["presentation"] = "animated"
        with self.assertRaises(ValueError):
            validate_public(doc)
        actor["presentation"] = "script"
        with self.assertRaises(ValueError):
            validate_public(doc)

    def model(self):
        image = io.BytesIO()
        Image.new("RGBA", (2, 2), (122, 231, 93, 255)).save(image, format="PNG")
        binary = image.getvalue()
        document = json.dumps(
            {
                "bufferViews": [{"byteOffset": 0, "byteLength": len(binary)}],
                "images": [{"name": "guard", "mimeType": "image/png", "bufferView": 0}],
            }
        ).encode()
        document += b" " * (-len(document) % 4)
        binary += b"\0" * (-len(binary) % 4)
        payload = struct.pack("<I4s", len(document), b"JSON") + document
        payload += struct.pack("<I4s", len(binary), b"BIN\0") + binary
        return struct.pack("<4sII", b"glTF", 2, len(payload) + 12) + payload

    def document(self):
        return {
            "schema": "mt2spacetime.static-npcs",
            "version": 1,
            "actors": [
                {
                    "id": "actor.npc.guard",
                    "vnum": 20354,
                    "name": "City Guard",
                    "model": RESOURCE_ROOT + "actors/guard.glb",
                    "sha256": hashlib.sha256(self.model()).hexdigest(),
                    "label_height": 3,
                    "idle": [{"clip": "wait", "weight": 100}],
                }
            ],
            "maps": [
                {
                    "id": "metin2_map_a1",
                    "content_hash": "a" * 64,
                    "placements": [
                        {
                            "id": "spawn.guard",
                            "actor_id": "actor.npc.guard",
                            "position": [605, 198.515, 663],
                            "yaw": 0,
                        }
                    ],
                }
            ],
        }

    def test_public_package_rejects_changed_artifact_and_source_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "actors").mkdir()
            model = root / "actors/guard.glb"
            model.write_bytes(self.model())
            document = self.document()
            (root / CATALOG).write_text(json.dumps(document))
            self.assertEqual(validate_package(root), document)
            model.write_bytes(b"changed")
            with self.assertRaisesRegex(ValueError, "model differs"):
                validate_package(root)
            model.write_bytes(self.model())
            texture = root / "actors/guard_guard.png"
            Image.new("RGBA", (2, 2), (122, 231, 93, 255)).save(texture, compress_level=1)
            self.assertEqual(validate_package(root), document)
            Image.new("RGBA", (2, 2), (255, 0, 0, 255)).save(texture)
            with self.assertRaisesRegex(ValueError, "texture differs"):
                validate_package(root)
            texture.unlink()
            (root / "conversion-receipt.json").write_text("{}")
            with self.assertRaisesRegex(ValueError, "undeclared files"):
                validate_package(root)
            (root / "conversion-receipt.json").unlink()
            for field in ("source_model", "token", "script"):
                changed = copy.deepcopy(document)
                changed["actors"][0][field] = "private"
                (root / CATALOG).write_text(json.dumps(changed))
                with self.assertRaisesRegex(ValueError, "fields"):
                    validate_package(root)

    def test_model_path_cannot_escape_or_select_scripts(self):
        for relative in ("../secret.glb", "actors/../../secret.glb", "actors/run.gd", "/x.glb"):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                artifact_path(Path("/tmp/npcs"), relative)

    def test_random_heading_is_stable_and_not_an_invented_fixed_source_heading(self):
        spawn = {"id": "spawn.guard", "source_direction": 0}
        self.assertEqual(heading(spawn), heading(dict(spawn)))
        self.assertNotEqual(heading(spawn), heading({**spawn, "id": "spawn.another"}))
        with self.assertRaises(ValueError):
            heading({**spawn, "source_direction": 9})

    def test_fixed_octants_preserve_original_map_direction(self):
        for direction in range(1, 9):
            yaw = heading({"id": "spawn.guard", "source_direction": direction})
            original = (direction - 1) * math.pi / 4
            self.assertAlmostEqual(-math.sin(yaw), math.sin(original))
            self.assertAlmostEqual(-math.cos(yaw), math.cos(original))


if __name__ == "__main__":
    unittest.main()
