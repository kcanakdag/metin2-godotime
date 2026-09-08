import json
import tempfile
import unittest
from pathlib import Path

from content_compile import canonical_bytes
from install_ground_items import collect
from install_mob_content import digest, install


class GroundItemInstallerTests(unittest.TestCase):
    def package(self, root):
        name = "models/coins.glb"
        data = b"test model bytes"
        (root / "generated/models").mkdir(parents=True)
        (root / "generated" / name).write_bytes(data)
        document = {
            "schema_version": 1,
            "profile_id": "fixture",
            "actors": [],
            "items": [{"id": "coins", "output": name}],
            "ground_items": [{"vnum": 1, "model_id": "coins"}],
        }
        document["content_hash"] = digest(canonical_bytes(document))
        (root / "normalized.v1.json").write_text(json.dumps(document))
        (root / "blender-report.json").write_text(
            json.dumps(
                {
                    "status": "converted",
                    "profile_id": "fixture",
                    "artifacts": [
                        {
                            "id": "coins",
                            "relative_path": name,
                            "sha256": digest(data),
                            "bytes": len(data),
                            "type": "item",
                            "textured_mesh_count": 1,
                        }
                    ],
                }
            )
        )
        return document

    def test_scoped_install_repeat_and_corruption(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.package(root / "source")
            packages, identity = collect(root / "source")
            client = root / "client"
            first = install(client, packages, identity, identity_field="ground_content_hash")
            self.assertTrue(first["installed"])
            second = install(client, packages, identity, identity_field="ground_content_hash")
            self.assertTrue(second["already_present"])
            dest = client / "assets/imported/ground_items"
            self.assertEqual(
                {p.name for p in dest.iterdir()},
                {"models", "catalog.v1.json", "install-receipt.json"},
            )
            (dest / "models/coins.glb").write_bytes(b"corrupt")
            with self.assertRaises(ValueError):
                install(client, packages, identity, identity_field="ground_content_hash")
            self.assertEqual((dest / "models/coins.glb").read_bytes(), b"corrupt")

    def test_manifest_and_model_corruption_reject_before_install(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            document = self.package(root)
            document["ground_items"][0]["vnum"] = 2
            (root / "normalized.v1.json").write_text(json.dumps(document))
            with self.assertRaises(ValueError):
                collect(root)
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.package(root)
            (root / "generated/models/coins.glb").write_bytes(b"corrupt")
            with self.assertRaises(ValueError):
                collect(root)


if __name__ == "__main__":
    unittest.main()
