import copy
import unittest

from mob_gameplay import compile_catalog
from mob_server_registry import compile_registry
from test_mob_gameplay import fixture


def catalog():
    result = compile_catalog(fixture())
    source = result["mobs"][0]["source_definition"]
    source["battle_type"] = "MELEE"
    source["flags"] = {"ai_flag": [], "immune_flag": []}
    source["rewards"].update(exp=15, gold_min=18, gold_max=27)
    source["stats"].update(
        st=3,
        ht=5,
        dx=6,
        aggressive_sight=2000,
        damage_min=20,
        damage_max=24,
        **{"def": 4, "damage_multiplier": 1.4},
    )
    source["combat_modifiers"] = dict(
        resist_sword=0, resist_fan=0, enchant_critical=1, enchant_penetrate=1
    )
    return result


class MobServerRegistryTests(unittest.TestCase):
    def test_immunity_bits_preserve_source_order_and_reject_missing_metadata(self):
        names = ["STUN", "SLOW", "FALL", "CURSE", "POISON", "TERROR", "REFLECT"]
        for index, name in enumerate(names):
            data = catalog()
            data["mobs"][0]["source_definition"]["flags"]["immune_flag"] = [name]
            self.assertIn(f"immunity_flags: {1 << index}", compile_registry(data))
        data["mobs"][0]["source_definition"]["flags"]["immune_flag"] = names
        self.assertIn("immunity_flags: 127", compile_registry(data))
        for invalid in (None, "STUN", ["STUN", "STUN"], ["UNKNOWN"], [1]):
            data["mobs"][0]["source_definition"]["flags"]["immune_flag"] = invalid
            with self.assertRaises(ValueError):
                compile_registry(data)

    def test_deterministic_typed_tables_preserve_damage_and_motion_values(self):
        data = catalog()
        before = copy.deepcopy(data)
        generated = compile_registry(data)
        self.assertEqual(generated, compile_registry(data))
        self.assertEqual(data, before)
        self.assertIn("damage_multiplier: 1.4", generated)
        self.assertIn("penetrate_percent: 1", generated)
        self.assertIn("experience: 15, gold_min: 18, gold_max: 27", generated)
        self.assertIn("MobSpeciesDefinition", generated)
        self.assertIn("target_chase_limit_cm: Some(4000), respawn_us: 10000000", generated)
        self.assertIn("acquisition_range_m: 20.0", generated)
        self.assertIn("hit_start_us: 250000", generated)

    def test_invalid_values_and_inconsistent_dispatch_reject(self):
        for mutate in (
            lambda d: d["mobs"][0].update(health=999),
            lambda d: d["mobs"][0]["source_definition"]["rewards"].update(gold_min=28),
            lambda d: d["mobs"][0]["movement"].update(server_speed_mps=float("nan")),
            lambda d: d["mobs"].append(copy.deepcopy(d["mobs"][0])),
            lambda d: d["mobs"][0]["attacks"][0].update(weight=99),
            lambda d: d["mobs"][0]["attacks"][0].update(damage_kind="magic"),
            lambda d: d["mobs"][0]["source_definition"]["stats"].update(
                damage_multiplier=float("nan")
            ),
            lambda d: d["mobs"][0]["source_definition"]["combat_modifiers"].update(
                enchant_penetrate=101
            ),
            lambda d: d["mobs"][0]["source_definition"]["stats"].update(damage_min=25),
        ):
            data = catalog()
            mutate(data)
            with self.assertRaises(ValueError):
                compile_registry(data)

    def test_magic_uses_immediate_hit_without_a_fabricated_melee_window(self):
        data = catalog()
        data["mobs"][0]["source_definition"]["battle_type"] = "MAGIC"
        data["mobs"][0]["attacks"][0].update(
            damage_kind="magic",
            delivery="projectile",
            windows=[],
            projectile_launches=[{"start_us": 300000}],
        )
        generated = compile_registry(data)
        self.assertIn("Kind::Magic", generated)
        self.assertIn("hit_start_us: 0, hit_end_us: 0", generated)
