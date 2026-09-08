import copy
import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from content_compile import canonical_bytes
from mob_gameplay import compile_catalog, legacy_duration, playback_duration, validate_actor_reports


def sealed(value):
    value["content_hash"] = hashlib.sha256(
        canonical_bytes({k: v for k, v in value.items() if k != "content_hash"})
    ).hexdigest()
    return value


def fixture():
    actor_id = "actor.mob.wild-boar-108"
    motions = []
    for action in ("normal_attack", "run", "front_knockdown", "front_standup", "back_knockdown"):
        motions.append(
            {
                "action_id": f"{actor_id}.general.{action}",
                "action": action,
                "godot_name": action,
                "duration_us": 1_000_000,
                "weight": 100,
                "source_msa": f"{action}.msa",
                "source_gr2": f"{action}.gr2",
                "loop": action == "run",
                "combo": None,
                "accumulation_m": [0, 0, -3] if action == "run" else [0, 0, 0],
                "events": [],
            }
        )
    motions[0]["events"] = [
        {
            "kind": "attack_window",
            "start_us": 200_000,
            "end_us": 400_000,
            "coordinate_space": "output_actor_local_godot",
            "sample_count": 2,
            "samples": [
                {"time_us": t, "start_m": [0, 1, -1], "end_m": [0, 1, -1]}
                for t in (200_000, 400_000)
            ],
            "source_parameters": {"invisible_us": 300_000},
        }
    ]
    actor = {
        "id": actor_id,
        "vnum": 108,
        "kind": "mob",
        "model_key": "wild_boar",
        "orientation": {"output_forward": "-Z", "yaw_correction_degrees": 180.0},
        "modes": [{"id": "general", "motions": motions}],
    }
    mob = {
        "id": actor_id,
        "vnum": 108,
        "model_key": "wild_boar",
        "name": "Wild Boar",
        "stats": {
            "attack_speed": 80,
            "move_speed": 70,
            "max_hp": 248,
            "level": 7,
            "attack_range": 175,
        },
        "assets": {
            "source_collision": [
                {
                    "collision_type": 3,
                    "bone": "Bip01",
                    "spheres": [{"position_m": [0, 0.7, 0.2], "radius_m": 1.1}],
                }
            ]
        },
        "rewards": {"drop_item": 30025},
    }
    return sealed(
        {
            "schema_version": 1,
            "compiler_version": "mob-content-v1",
            "inventory": {"server_revision": "7ee9c84bd348b94326aeaa7d6bbb2c8c6ca34318"},
            "actors": [actor],
            "mob_catalog": [mob],
            "deferred_motion_events": [],
        }
    )


class MobGameplayTests(unittest.TestCase):
    def test_converted_report_must_match_exact_actor_clips(self):
        actors = fixture()["actors"]
        actors[0]["output"] = "actors/boar.glb"
        artifact = {
            "id": actors[0]["id"],
            "relative_path": actors[0]["output"],
            "motions": copy.deepcopy(actors[0]["modes"][0]["motions"]),
        }
        validate_actor_reports(actors, [artifact])
        for field in ("duration_us", "godot_name", "action_id"):
            changed = copy.deepcopy(artifact)
            changed["motions"][0][field] = 123 if field == "duration_us" else "wrong"
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_actor_reports(actors, [changed])

    def test_source_cadence_and_client_playback_are_distinct(self):
        self.assertEqual(legacy_duration(80, 2_000_000), 2_400_000)
        self.assertEqual(playback_duration(80, 1_000_000), 1_250_000)
        self.assertEqual(legacy_duration(150, 2_000_000), 1_320_000)
        self.assertEqual(playback_duration(150, 1_000_000), 666_667)
        for speed in (0, 201, True, 1.5):
            with self.assertRaises(ValueError):
                legacy_duration(speed, 2000)

    def test_per_species_motion_geometry_and_unimplemented_source_fields_survive(self):
        source = fixture()
        before = copy.deepcopy(source)
        result = compile_catalog(source)
        mob = result["mobs"][0]
        self.assertEqual(mob["health"], 248)
        self.assertEqual(mob["defending_sphere"]["radius_m"], 1.1)
        self.assertEqual(mob["source_definition"]["rewards"]["drop_item"], 30025)
        self.assertAlmostEqual(mob["movement"]["server_speed_mps"], 3 / 1.3)
        attack = mob["attacks"][0]
        self.assertEqual(attack["windows"][0]["playback_start_us"], 250_000)
        self.assertEqual(attack["windows"][0]["playback_end_us"], 500_000)
        self.assertEqual(source, before)
        self.assertEqual(result, compile_catalog(source))

    def test_weighted_attacks_keep_distinct_timings(self):
        source = fixture()
        motions = source["actors"][0]["modes"][0]["motions"]
        motions[0]["weight"] = 50
        other = copy.deepcopy(motions[0])
        other["action_id"] += ".v2"
        other["godot_name"] += "_v2"
        other["duration_us"] = 2_000_000
        motions.append(other)
        attacks = compile_catalog(sealed(source))["mobs"][0]["attacks"]
        self.assertEqual([a["weight"] for a in attacks], [50, 50])
        self.assertEqual([a["playback_duration_us"] for a in attacks], [1_250_000, 2_500_000])

    def test_invalid_hash_identity_and_deferred_events_reject(self):
        for change in ("hash", "identity", "duplicate", "deferred"):
            source = fixture()
            if change == "hash":
                source["content_hash"] = "0" * 64
            elif change == "identity":
                source["actors"][0]["vnum"] = 101
                sealed(source)
            elif change == "duplicate":
                source["actors"].append(copy.deepcopy(source["actors"][0]))
                sealed(source)
            else:
                source["deferred_motion_events"] = [{"kind": "unknown"}]
                sealed(source)
            with self.subTest(change=change), self.assertRaises(ValueError):
                compile_catalog(source)

    def test_invalid_motion_windows_weights_and_movement_reject(self):
        for change in ("weight", "duration", "window", "nan", "samples", "backwards", "missing"):
            source = fixture()
            motions = source["actors"][0]["modes"][0]["motions"]
            hit = motions[0]["events"][0]
            if change == "weight":
                motions[0]["weight"] = 50
            elif change == "duration":
                motions[0]["duration_us"] = 0
            elif change == "window":
                hit["end_us"] = 2_000_000
            elif change == "nan":
                hit["samples"][0]["start_m"][0] = float("nan")
            elif change == "samples":
                hit["samples"].reverse()
            elif change == "backwards":
                motions[1]["accumulation_m"][2] = 3
            else:
                motions.pop(1)
            with self.subTest(change=change), self.assertRaises(ValueError):
                compile_catalog(sealed(source))
