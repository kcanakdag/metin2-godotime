import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_projectile_catalog import build
from content_compile import canonical_bytes


def seal(path, document):
    document.pop("content_hash", None)
    document["content_hash"] = hashlib.sha256(canonical_bytes(document)).hexdigest()
    path.write_text(json.dumps(document))


class ProjectileCatalogTests(unittest.TestCase):
    def fixture(self, root):
        texture = root / "texture.png"
        texture.write_bytes(b"fixture copied without re-encoding")
        particle = {
            "schema": "mt2spacetime.particle-effect-candidate",
            "version": 1,
            "source_revision": "a" * 40,
            "effects": [{"effect_path": "fx", "systems": [{"particle": {"textures": ["tex"]}}]}],
            "textures": {
                "tex": {
                    "path": "texture.png",
                    "sha256": hashlib.sha256(texture.read_bytes()).hexdigest(),
                }
            },
        }
        flight = {
            "schema": "mt2spacetime.projectile-source-inventory",
            "version": 1,
            "source_revision": "a" * 40,
            "flight_definitions": [
                {"path": "flight", "attachments": [{"effect": "fx"}], "bomb_effect": None}
            ],
        }
        particles, flights = root / "particles.json", root / "flights.json"
        seal(particles, particle)
        seal(flights, flight)
        return particles, flights

    def test_repeatable_package_preserves_bytes_and_import_policy(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            particles, flights = self.fixture(root)
            first = build(particles, flights, [], root / "first")
            second = build(particles, flights, [], root / "second")
            self.assertEqual(first, second)
            for path in first["files"]:
                self.assertEqual(
                    (root / "first" / path).read_bytes(), (root / "texture.png").read_bytes()
                )
                sidecar = (root / "first" / (path + ".import")).read_text()
                self.assertIn("process/fix_alpha_border=false", sidecar)
                self.assertIn("detect_3d/compress_to=0", sidecar)

    def test_tampered_resource_and_catalog_reject(self):
        for case in ("resource", "catalog"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                particles, flights = self.fixture(root)
                if case == "resource":
                    (root / "texture.png").write_bytes(b"changed")
                else:
                    document = json.loads(flights.read_text())
                    document["flight_definitions"][0]["path"] = "changed"
                    flights.write_text(json.dumps(document))
                with self.assertRaises(ValueError):
                    build(particles, flights, [], root / "out")

    def test_missing_dependency_and_unsafe_path_reject(self):
        for case in ("dependency", "path", "revision"):
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                particles, flights = self.fixture(root)
                document = json.loads(particles.read_text())
                if case == "dependency":
                    document["effects"] = []
                elif case == "path":
                    document["textures"]["tex"]["path"] = "../escape.png"
                else:
                    document["source_revision"] = "b" * 40
                seal(particles, document)
                with self.assertRaises(ValueError):
                    build(particles, flights, [], root / "out")
