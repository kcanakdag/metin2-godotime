import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_motion_effect_catalog import build, digest, validate_links
from PIL import Image


def fixtures():
    skills = {
        "skills": [{"vnum": 1, "variants": [{"actor_id": "hero", "action_id": "hero.skill"}]}]
    }
    characters = {
        "actors": [{"modes": [{"motions": [{"action_id": "hero.skill", "duration_us": 1000000}]}]}]
    }
    rows = [
        {
            "actor_id": "hero",
            "skill_vnum": 1,
            "effects": [
                {
                    "source_event": "Event00",
                    "effect_path": "effect",
                    "start_us": 100000,
                    "attachment": "follow_root",
                    "bone": "",
                    "position_m": [0, 0, 0],
                }
            ],
        }
    ]
    return skills, characters, rows


class MotionEffectCatalogTests(unittest.TestCase):
    def test_complete_links_and_copy(self):
        skills, characters, rows = fixtures()
        result = validate_links(rows, skills, characters, {"effect"})
        result["hero.skill"][0]["start_us"] = 0
        self.assertEqual(rows[0]["effects"][0]["start_us"], 100000)

    def test_incomplete_duplicate_or_unresolved_links_reject(self):
        skills, characters, rows = fixtures()
        for candidate, effects in (([], {"effect"}), (rows * 2, {"effect"}), (rows, set())):
            with self.assertRaises(ValueError):
                validate_links(candidate, skills, characters, effects)
        for key, value in (
            ("start_us", 1000001),
            ("position_m", [float("nan"), 0, 0]),
            ("bone", "unexpected"),
        ):
            with self.subTest(key=key), self.assertRaises(ValueError):
                candidate = copy.deepcopy(rows)
                candidate[0]["effects"][0][key] = value
                validate_links(candidate, skills, characters, {"effect"})

    def test_canonical_png_dedup_and_hash_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = Image.new("RGBA", (4, 4), (10, 20, 30, 40))
            for name, level in (("a.png", 0), ("b.png", 9)):
                image.save(root / name, compress_level=level)
            self.assertNotEqual(digest(root / "a.png"), digest(root / "b.png"))
            particles = {
                "schema": "mt2spacetime.particle-effect-candidate",
                "version": 1,
                "effects": [
                    {"effect_path": "effect", "systems": [{"particle": {"textures": ["a", "b"]}}]}
                ],
                "textures": {
                    v: {"path": v + ".png", "sha256": digest(root / (v + ".png"))}
                    for v in ("a", "b")
                },
            }
            skills, characters, rows = fixtures()
            for name, data in (
                ("particles", particles),
                ("skills", skills),
                ("characters", characters),
                ("links", rows),
            ):
                (root / (name + ".json")).write_text(json.dumps(data))
            args = [
                root / "particles.json",
                [],
                root / "links.json",
                root / "skills.json",
                root / "characters.json",
            ]
            result = build(*args, root / "good")
            self.assertEqual(len(result["files"]), 1)
            self.assertEqual(result["textures"]["a"], result["textures"]["b"])
            self.assertFalse((root / "good/runtime/receipt.json").exists())
            (root / "a.png").write_bytes(b"modified")
            with self.assertRaises(ValueError):
                build(*args, root / "bad")


if __name__ == "__main__":
    unittest.main()
