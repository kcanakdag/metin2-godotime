import copy
import unittest

from mob_gameplay import compile_catalog
from mob_presentation import public_motion
from mob_projectiles import compile_launches
from test_mob_gameplay import fixture, sealed


def projectile_fixture():
    source = fixture()
    actor = source["actors"][0]
    motion = actor["modes"][0]["motions"][0]
    motion["events"] = []
    source["mob_catalog"][0]["battle_type"] = "MAGIC"
    source["deferred_motion_events"] = [
        {
            "actor_id": actor["id"],
            "action_id": motion["action_id"],
            "source": motion["source_msa"],
            "kind": "motion_event",
            "event_name": "Event00",
            "event_type": 6,
            "start_us": 400000,
            "end_us": 400000,
            "fields": {
                "AttachingBoneName": ["Bip01 R Hand"],
                "AttachingEnable": ["1"],
                "FlyFileName": ["d:/ymir work/effect/arrow.msf"],
                "FlyPosition": ["0", "1", "2"],
                "MotionEventType": ["6"],
                "StartingTime": ["0.400000"],
            },
        }
    ]
    return sealed(source)


class MobProjectileTests(unittest.TestCase):
    def test_projectile_keeps_visual_timing_separate_from_melee_damage_windows(self):
        source = projectile_fixture()
        before = copy.deepcopy(source)
        result = compile_catalog(source)
        attack = result["mobs"][0]["attacks"][0]
        self.assertEqual(attack["windows"], [])
        self.assertEqual(attack["delivery"], "projectile")
        self.assertEqual(attack["damage_kind"], "magic")
        launch = attack["projectile_launches"][0]
        self.assertEqual(launch["playback_start_us"], 500000)  # source fixture speed 80
        self.assertEqual(launch["fly_definition"], "ymir work/effect/arrow.msf")
        self.assertEqual(launch["source_position_cm"], [0, 1, 2])
        self.assertTrue(result["unimplemented_runtime_requirements"])
        self.assertEqual(source, before)

    def test_public_motion_keeps_source_launch_clock_and_independent_metadata(self):
        source = projectile_fixture()
        motion = source["actors"][0]["modes"][0]["motions"][0]
        motion.update(variant=1, fallback_mode=None)
        launches = compile_launches(source)[motion["action_id"]]
        public = public_motion(motion, launches)
        self.assertEqual(public["projectile_launches"][0]["start_us"], 400000)
        self.assertEqual(public["projectile_launches"][0]["bone"], "Bip01 R Hand")
        public["projectile_launches"][0]["source_position_cm"][0] = 99
        self.assertEqual(launches[0]["source_position_cm"], [0, 1, 2])

    def test_wrong_event_identity_timing_attachment_and_unsafe_asset_reject(self):
        for field, bad in (
            ("action_id", "unknown"),
            ("source", "other.msa"),
            ("start_us", -1),
            ("event_type", 7),
            ("end_us", 400001),
        ):
            source = projectile_fixture()
            source["deferred_motion_events"][0][field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                compile_catalog(sealed(source))
        for field, bad in (
            ("AttachingEnable", ["2"]),
            ("AttachingBoneName", [""]),
            ("FlyPosition", ["nan", "0", "0"]),
            ("StartingTime", ["0.8"]),
            ("FlyFileName", ["d:/ymir work/../escape.msf"]),
        ):
            source = projectile_fixture()
            source["deferred_motion_events"][0]["fields"][field] = bad
            with self.subTest(field=field), self.assertRaises(ValueError):
                compile_catalog(sealed(source))

    def test_missing_duplicate_launches_and_mismatched_battle_type_reject(self):
        for case in ("missing", "duplicate", "melee"):
            source = projectile_fixture()
            if case == "missing":
                source["deferred_motion_events"] = []
            elif case == "duplicate":
                source["deferred_motion_events"] *= 2
            else:
                source["mob_catalog"][0]["battle_type"] = "MELEE"
            with self.subTest(case=case), self.assertRaises(ValueError):
                compile_catalog(sealed(source))
