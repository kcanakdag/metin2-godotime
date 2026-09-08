import tempfile
import unittest
from pathlib import Path

from install_mob_content import checked_file, digest, install, relative


class MobInstallTests(unittest.TestCase):
    def test_paths_and_hashes_fail_before_copying(self):
        for path in ("../escape", "/absolute", "assets/../../escape", "assets\\escape"):
            with self.assertRaises(ValueError):
                relative(path)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "asset.glb").write_bytes(b"model")
            self.assertEqual(checked_file(root, "asset.glb", digest(b"model")), b"model")
            with self.assertRaises(ValueError):
                checked_file(root, "asset.glb", digest(b"different"))

    def test_repeat_is_idempotent_and_different_package_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as temp:
            client = Path(temp)
            package = {"mobs": {"model.glb": b"model"}, "projectiles": {"asset.png": b"image"}}
            self.assertTrue(install(client, package, "a" * 64)["installed"])
            self.assertTrue(install(client, package, "a" * 64)["already_present"])
            changed = {**package, "mobs": {"model.glb": b"changed"}}
            with self.assertRaises(ValueError):
                install(client, changed, "b" * 64)
            self.assertEqual((client / "assets/imported/mobs/model.glb").read_bytes(), b"model")

    def test_partial_existing_destination_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            client = Path(temp)
            existing = client / "assets/imported/mobs"
            existing.mkdir(parents=True)
            (existing / "keep.txt").write_text("user work")
            with self.assertRaises(ValueError):
                install(client, {"mobs": {"model.glb": b"x"}, "projectiles": {}}, "a" * 64)
            self.assertEqual((existing / "keep.txt").read_text(), "user work")
            self.assertFalse((client / "assets/imported/projectiles").exists())

    def test_godot_import_metadata_is_allowed_but_texture_policy_is_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            client = Path(temp)
            seed = b'[remap]\nimporter="texture"\n[params]\ncompress/mode=0\n'
            package = {"projectiles": {"texture.png.import": seed}}
            install(client, package, "a" * 64)
            sidecar = client / "assets/imported/projectiles/texture.png.import"
            expanded = seed + b'mipmaps/limit=-1\n[deps]\nsource_file="res://texture.png"\n'
            sidecar.write_bytes(expanded)
            self.assertTrue(install(client, package, "a" * 64)["already_present"])
            sidecar.write_bytes(expanded.replace(b"compress/mode=0", b"compress/mode=2"))
            with self.assertRaises(ValueError):
                install(client, package, "a" * 64)
