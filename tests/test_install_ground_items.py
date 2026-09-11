import json
import tempfile
import unittest
from pathlib import Path

from content_compile import canonical_bytes
from install_ground_items import collect
from install_mob_content import digest, install


class GroundItemInstallerTests(unittest.TestCase):
    def write_package(self, root, models, definition_vnums):
        """Write a package whose ``models`` are ``(identity, path)`` pairs."""
        (root / "generated/models").mkdir(parents=True, exist_ok=True)
        artifacts = []
        for identity, name in models:
            data = b"model bytes " + identity.encode()
            (root / "generated" / name).parent.mkdir(parents=True, exist_ok=True)
            (root / "generated" / name).write_bytes(data)
            artifacts.append(
                {
                    "id": identity,
                    "relative_path": name,
                    "sha256": digest(data),
                    "bytes": len(data),
                    "type": "item",
                    "textured_mesh_count": 1,
                }
            )
        document = {
            "schema_version": 1,
            "profile_id": "fixture",
            "actors": [],
            "items": [{"id": identity, "output": name} for identity, name in models],
            "ground_items": definition_vnums,
        }
        document["content_hash"] = digest(canonical_bytes(document))
        (root / "normalized.v1.json").write_text(json.dumps(document))
        (root / "blender-report.json").write_text(
            json.dumps({"status": "converted", "profile_id": "fixture", "artifacts": artifacts})
        )
        return document

    def test_shared_models_cover_many_vnums(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            definitions = [{"vnum": vnum, "model_id": "shared"} for vnum in range(1, 400)]
            self.write_package(root, [("shared", "models/shared.glb")], definitions)
            packages, _ = collect(root)
            catalog = json.loads(packages["ground_items"]["catalog.v1.json"])
            self.assertEqual(len(catalog["items"]), 399)
            self.assertEqual(set(catalog["models"]), {"shared"})

    def test_model_count_is_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            definitions = [{"vnum": vnum, "model_id": f"model{vnum}"} for vnum in range(1, 258)]
            self.write_package(
                root,
                [(f"model{vnum}", f"models/model{vnum}.glb") for vnum in range(1, 258)],
                definitions,
            )
            with self.assertRaisesRegex(ValueError, "converted models"):
                collect(root)

    def test_selection_without_currency_rejects(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            definitions = [{"vnum": 11, "model_id": "sword"}]
            self.write_package(root, [("sword", "models/sword.glb")], definitions)
            with self.assertRaisesRegex(ValueError, "Yang"):
                collect(root)

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
