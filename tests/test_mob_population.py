import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from mob_population import compile_population, interval_us

GROUPS = """Group pack
{
Vnum 900
Leader Wolf 102
1 Dog 101
2 Dog 101
}
Group pack2
{
Vnum 901
Leader Bear 110
1 Tiger 114
}
"""
CHOICES = """Group selector
{
Vnum 101
1 900 100
2 901 0
}
"""
REGEN = "r 700 500 10 20 0 0 1m5s 10 2 101"


class MobPopulationTests(unittest.TestCase):
    def test_group_selector_id_is_not_a_mob_and_source_weights_are_not_effective_weights(self):
        result = compile_population(REGEN, GROUPS, CHOICES, {101, 102})
        self.assertEqual(result["required_mob_vnums"], [101, 102, 110, 114])
        self.assertEqual(result["outside_selected_vnums"], [110, 114])
        self.assertEqual(result["covered_entries"], 0)
        variants = result["group_selectors"][0]["variants"]
        self.assertEqual([v["source_weight"] for v in variants], [100, 0])
        self.assertEqual([v["effective_weight"] for v in variants], [1, 1])
        entry = result["entries"][0]
        self.assertEqual(entry["bounds_cm"], [69000, 48000, 71000, 52000])
        self.assertEqual(entry["interval_us"], 65_000_000)
        self.assertEqual(entry["source_percent"], 10)
        self.assertEqual(entry["percent_policy"], "ignored-by-original-loader")
        self.assertEqual(entry["initial_member_upper_bound"], 6)

    def test_direct_and_forced_aggressive_group_spawns_remain_distinct(self):
        result = compile_population(
            "m 5 5 0 0 0 8 0s 100 1 114\nga 50 50 1 1 0 2 5s 100 1 900",
            GROUPS,
            CHOICES,
            {101, 102, 114},
        )
        self.assertEqual(result["covered_entries"], 2)
        self.assertFalse(result["entries"][0]["forced_aggressive"])
        self.assertTrue(result["entries"][1]["forced_aggressive"])
        self.assertEqual(result["entries"][0]["interval_us"], 0)
        self.assertFalse(result["entries"][0]["enabled"])
        self.assertEqual(result["entries"][0]["initial_member_upper_bound"], 0)
        self.assertTrue(result["entries"][1]["enabled"])
        self.assertEqual(result["initial_member_upper_bound"], 3)

    def test_disabled_selector_retains_dependencies_without_inflating_population(self):
        result = compile_population(REGEN.replace("1m5s", "0s"), GROUPS, CHOICES, {101, 102})
        self.assertEqual(result["initial_member_upper_bound"], 0)
        self.assertEqual(result["required_mob_vnums"], [101, 102, 110, 114])
        self.assertEqual(result["outside_selected_vnums"], [110, 114])
        self.assertEqual(len(result["groups"]), 2)

    def test_source_loader_stops_after_slot_gap_and_records_ignored_data(self):
        choices = CHOICES.replace("2 901 0", "3 999 0")
        result = compile_population(REGEN, GROUPS, choices, {101, 102})
        self.assertEqual(result["covered_entries"], 1)
        self.assertEqual(result["required_mob_vnums"], [101, 102])
        self.assertEqual(
            result["group_selectors"][0]["ignored_after_slot_gap"], {"3": ["999", "0"]}
        )

    def test_referenced_missing_or_duplicate_groups_reject(self):
        for groups, choices in (
            ("", CHOICES),
            (GROUPS + GROUPS, CHOICES),
            (GROUPS, CHOICES + CHOICES),
        ):
            with self.assertRaises(ValueError):
                compile_population(REGEN, groups, choices, {101})
        # Irrelevant duplicate legacy groups do not prevent auditing this selected map.
        unrelated = "Group unused\n{\nVnum 999\nLeader Unused 999\n}\n"
        result = compile_population(REGEN, GROUPS + unrelated * 2, CHOICES, set())
        self.assertEqual(len(result["groups"]), 2)

    def test_malformed_spawn_geometry_families_and_intervals_reject(self):
        self.assertEqual(interval_us("1h2m3s"), 3_723_000_000)
        for interval in ("-1s", "1", "25h", "1sX"):
            with self.assertRaises(ValueError):
                interval_us(interval)
        for line in (
            "r 1",
            REGEN.replace("r ", "s "),
            REGEN.replace("700", "1"),
            REGEN.replace("10 20", "0 0"),
            REGEN.replace("0 0 1m5s", "0 9 1m5s"),
        ):
            with self.subTest(line=line), self.assertRaises(ValueError):
                compile_population(line, GROUPS, CHOICES, set())
