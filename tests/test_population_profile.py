import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from build_population_profile import build_profile
from content_compile import canonical_bytes


def seal(row):
    row["content_hash"] = hashlib.sha256(
        canonical_bytes({k: v for k, v in row.items() if k != "content_hash"})
    ).hexdigest()
    return row


class PopulationProfileTests(unittest.TestCase):
    def fixture(self):
        base = {
            "source": {"server_reference": {"revision": "pinned"}},
            "mobs": [
                {
                    "id": "actor.mob.wild-dog-101",
                    "vnum": 101,
                    "source_root": "ymir work/monster/stray_dog",
                }
            ],
        }
        population = seal(
            {
                "schema": "mt2spacetime.original-mob-population",
                "version": 1,
                "source_revision": "pinned",
                "map": "metin2_map_a1",
                "required_mob_vnums": [101, 104],
                "required_definitions": [
                    {
                        "vnum": 101,
                        "name": "Different Display Name",
                        "type": "MONSTER",
                        "source_folder": "stray_dog",
                    },
                    {"vnum": 104, "name": "Blue Wolf", "type": "MONSTER", "source_folder": "wolf"},
                ],
            }
        )
        return population, base

    def test_preserves_existing_ids_and_derives_only_required_dependencies(self):
        population, base = self.fixture()
        result = build_profile(population, base)
        self.assertEqual(result["mobs"][0], base["mobs"][0])
        self.assertEqual(
            result["mobs"][1],
            {"id": "actor.mob.blue-wolf-104", "vnum": 104, "source_root": "ymir work/monster/wolf"},
        )
        self.assertEqual(result["population_source"]["content_hash"], population["content_hash"])
        self.assertEqual(result, build_profile(population, base))

    def test_incomplete_tampered_or_unsafe_population_rejects(self):
        for change in ("hash", "closure", "folder", "type"):
            population, base = self.fixture()
            if change == "hash":
                population["content_hash"] = "0" * 64
            elif change == "closure":
                population["required_mob_vnums"].append(999)
                seal(population)
            else:
                population["required_definitions"][1][
                    "source_folder" if change == "folder" else "type"
                ] = "../wolf" if change == "folder" else "NPC"
                seal(population)
            with self.subTest(change=change), self.assertRaises(ValueError):
                build_profile(population, base)
