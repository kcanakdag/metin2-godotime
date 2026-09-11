"""Regression tests for the compiled original drop corpus.

``tools/metin_drops.py`` replays ``ITEM_MANAGER::ReadCommonDropItemFile`` and
``ReadMonsterDropItemGroup`` over the pinned ``git.old-metin2.com`` tables.  The
corpus is the input the authoritative server rolls loot from, so the fixed
quirks matter as much as the happy path: which row wins a duplicate key, which
group wins a duplicate mob, how a percent is scaled, and where a row probe
stops.  These tests pin those behaviours on small synthetic tables and then
re-check the real pinned corpus when the ignored research checkout is present.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tools.metin_drops import (
    DEFAULT_SOURCE,
    RANKS,
    DropCorpusError,
    ItemPrototype,
    ItemTable,
    compile_corpus,
    corpus_hash,
    load_item_table,
    parse_common_drop,
    percent_to_10k_value,
    read_monster_drop_item_group,
    split_line,
    strncasecmp_prefix,
)

ROOT = Path(__file__).resolve().parents[1]
SOURCE = DEFAULT_SOURCE

# Counts observed on the pinned revision ``7ee9c84``.  They are the corpus the
# server ships, so a changed count means the compiler or the inputs moved.
PINNED = {
    "prototypes": 5743,
    "range_rows": 150,
    "common_rows": 2017,
    "common_lines": 540,
    "common_skipped_level_start_zero": 143,
    "common_resolved_by_number": 2046,
    "common_empty_names": 114,
    "common_by_rank": {"PAWN": 434, "S_PAWN": 534, "KNIGHT": 539, "S_KNIGHT": 510},
    "group_nodes": 578,
    "group_installed": 568,
    "group_distinct_names": 442,
    "group_rows": 4395,
    "groups_by_type": {"drop": 298, "kill": 192, "limit": 78, "thiefgloves": 0},
    "rows_by_type": {"drop": 2953, "kill": 719, "limit": 723, "thiefgloves": 0},
    "merged_drop_groups": 2,
    "skipped_kill_drop_zero": 10,
}


def item_table(*rows: tuple[int, bytes, int]) -> ItemTable:
    """``ItemTable`` straight from ``(vnum, name, vnum_range)`` triples."""
    return ItemTable(
        [ItemPrototype(vnum=vnum, name=name, vnum_range=span) for vnum, name, span in rows]
    )


def mob_group(
    name: str,
    group_type: str,
    mob: int,
    rows: list[tuple[str, str]],
    **extra: str,
) -> bytes:
    """One ``Group`` block as the loader reads it (tab or space delimited)."""
    lines = [f"Group\t{name}", "{", f"\tType\t{group_type}", f"\tMob\t{mob}"]
    lines.extend(f"\t{key}\t{value}" for key, value in extra.items())
    lines.extend(f"\t{key}\t{value}" for key, value in rows)
    lines.append("}")
    return ("\n".join(lines) + "\n").encode("latin-1")


def common_drop(*blocks: tuple[str, str, str, str, str, str]) -> bytes:
    """One ``common_drop_item.txt`` line: four six-field rank blocks."""
    return ("\t".join(field for block in blocks for field in block) + "\n").encode("latin-1")


def pawn_line(level_start: str, level_end: str) -> bytes:
    """A line that fills only the PAWN block (the rest never see a tab)."""
    return f"name\t{level_start}\t{level_end}\t0.1\t11\t1\n".encode("latin-1")


PROTO_TEXT = b"VNUM\tNAME\n10\tPotion\n20\tPotion Big\n30\tSword\n100~110\tRange Row\n"


class LibcHelperTests(unittest.TestCase):
    def test_strncasecmp_prefix_compares_only_the_token_length(self) -> None:
        self.assertTrue(strncasecmp_prefix(b"pot", b"Potter"))
        self.assertTrue(strncasecmp_prefix(b"POTTER", b"potter"))
        self.assertFalse(strncasecmp_prefix(b"potters", b"Potter"))
        self.assertFalse(strncasecmp_prefix(b"potter ", b"Potter"))
        # An empty token compares zero bytes, so it always agrees.
        self.assertTrue(strncasecmp_prefix(b"", b"anything"))

    def test_percent_scales_through_binary32_and_truncates(self) -> None:
        self.assertEqual(percent_to_10k_value(0.2), 2000)
        self.assertEqual(percent_to_10k_value(0.08), 800)
        # ``(DWORD)(fPercent * 10000.0f)`` truncates toward zero rather than
        # rounding, so a product of 2899.5 becomes 2899.
        self.assertEqual(percent_to_10k_value(0.28995), 2899)
        # 0.29 is not representable in binary32, but the scaled product rounds
        # back up to exactly 2900.0 inside the same float multiply.
        self.assertEqual(percent_to_10k_value(0.29), 2900)

    def test_split_line_skips_comments_and_quoted_fields(self) -> None:
        self.assertEqual(split_line(b"a\tb  c"), [b"a", b"b", b"c"])
        self.assertIsNone(split_line(b"# comment"))
        self.assertIsNone(split_line(b"   "))
        middle = bytearray(b"a\t")
        hello = b"c\t"
        self.assertEqual(
            split_line(bytes(middle) + b'"c c"\t' + bytes(hello[:1])), [b"a", b"c c", b"c"]
        )


class ItemTableTests(unittest.TestCase):
    def test_name_lookup_is_a_folded_prefix_and_first_vnum_wins(self) -> None:
        table = item_table((30, b"Sword", 0), (20, b"Potion Big", 0), (10, b"Potion", 0))
        self.assertEqual(table.by_original_name(b"poti"), 10)
        self.assertEqual(table.by_original_name(b"POTION B"), 20)
        self.assertIsNone(table.by_original_name(b"Potions Extra"))
        # Vnum order decides, not declaration order.
        self.assertEqual(table.by_original_name(b"S"), 30)

    def test_empty_token_matches_the_first_prototype(self) -> None:
        table = item_table((30, b"Sword", 0), (10, b"Potion", 0))
        self.assertEqual(table.by_original_name(b""), 10)

    def test_an_empty_stored_name_only_matches_an_empty_token(self) -> None:
        table = item_table((5, b"", 0), (10, b"Potion", 0))
        self.assertEqual(table.by_original_name(b""), 5)
        self.assertEqual(table.by_original_name(b"p"), 10)

    def test_contains_matches_exact_vnums_then_open_ranges(self) -> None:
        table = item_table((100, b"Range", 10), (200, b"Plain", 0))
        self.assertTrue(table.contains(100))  # the row's own vnum
        self.assertTrue(table.contains(105))  # strictly inside 100..110
        self.assertFalse(table.contains(110))  # the range's exclusive end
        self.assertTrue(table.contains(200))
        self.assertTrue(table.contains(101))
        self.assertFalse(table.contains(111))
        self.assertFalse(table.contains(99))

    def test_duplicate_vnums_are_rejected(self) -> None:
        with self.assertRaisesRegex(DropCorpusError, "repeats vnum 10"):
            item_table((10, b"A", 0), (10, b"B", 0))

    def test_resolve_falls_back_to_a_numeric_token(self) -> None:
        table = item_table((100, b"Range", 10), (200, b"Plain", 0))
        self.assertEqual(table.resolve(b"105"), 105)
        self.assertEqual(table.resolve(b"plain"), 200)
        self.assertIsNone(table.resolve(b"999"))
        self.assertIsNone(table.resolve(b"not an item"))

    def test_load_item_table_truncates_names_to_24_bytes(self) -> None:
        long_name = b"L" * 40
        table = load_item_table(b"VNUM\tNAME\n7\t" + long_name + b"\n")
        self.assertEqual(table.prototypes[0].name, b"L" * 24)
        self.assertEqual(table.by_original_name(b"L" * 24), 7)
        self.assertIsNone(table.by_original_name(b"L" * 25))

    def test_load_item_table_rejects_quoted_fields(self) -> None:
        with self.assertRaisesRegex(DropCorpusError, "quote"):
            load_item_table(b'VNUM\tNAME\n7\t"Quoted"\n')


class CommonDropTests(unittest.TestCase):
    def test_each_block_feeds_its_own_rank_from_the_later_columns(self) -> None:
        # Field 4 is the item token (a vnum in the pinned table) and field 5 is a
        # count the original parses but never uses when creating the drop.
        line = common_drop(
            ("name", "1", "15", "0.08", "11", "5000"),
            ("name", "2", "25", "0.104", "11", "3846"),
            ("name", "0", "15", "0.12", "11", "3333"),
            ("name", "3", "35", "0.32", "11", "1250"),
        )
        ranks, stats = parse_common_drop(line, item_table((11, b"Potion", 0)), "fixture")

        self.assertEqual(stats["lines"], 1)
        self.assertEqual(stats["rows_kept"], 3)
        self.assertEqual(stats["skipped_level_start_zero"], 1)
        self.assertEqual(stats["resolved_by_number"], 4)
        self.assertEqual(stats["empty_name_resolutions"], 0)
        self.assertEqual(
            [(row["level_start"], row["level_end"], row["percent"]) for row in ranks["PAWN"]],
            [(1, 15, 800)],
        )
        self.assertEqual(
            [(row["level_start"], row["level_end"], row["percent"]) for row in ranks["S_PAWN"]],
            [(2, 25, 1040)],
        )
        self.assertEqual(ranks["KNIGHT"], [])
        self.assertEqual(
            [(row["level_start"], row["level_end"], row["percent"]) for row in ranks["S_KNIGHT"]],
            [(3, 35, 3200)],
        )
        self.assertEqual([row["vnum"] for row in ranks["PAWN"]], [11])
        # A field is only read when another tab follows it, so a line's last
        # column is never stored unless the line ends with a tab.
        self.assertEqual(ranks["PAWN"][0]["count"], 5000)
        self.assertEqual(ranks["S_KNIGHT"][0]["count"], 0)

    def test_rows_are_sorted_by_level_end_not_source_order(self) -> None:
        data = b"".join([pawn_line("3", "40"), pawn_line("1", "10"), pawn_line("2", "25")])
        ranks, stats = parse_common_drop(data, item_table((11, b"Potion", 0)), "fixture")
        self.assertEqual([row["level_end"] for row in ranks["PAWN"]], [10, 25, 40])
        self.assertEqual(stats["lines"], 3)
        # Every line's untouched later blocks keep lv_start 0.
        self.assertEqual(stats["skipped_level_start_zero"], 9)

    def test_an_unreached_block_keeps_its_own_zeroed_defaults(self) -> None:
        # Only the first two blocks and part of the third carry fields.  The
        # blocks that never see a tab keep lv_start 0 (and an empty name, which
        # resolves to the first prototype like the original's zero-length
        # ``strncasecmp``), instead of inheriting the previous block's values.
        line = (
            common_drop(
                ("x", "1", "9", "0.5", "11", "1"),
                ("x", "1", "9", "0.5", "11", "1"),
            )[:-1]
            + b"\t1\t9\t0.5\n"
        )
        ranks, stats = parse_common_drop(line, item_table((11, b"Potion", 0)), "fixture")
        self.assertEqual(stats["lines"], 1)
        self.assertEqual(stats["resolved_by_number"], 2)
        self.assertEqual(stats["empty_name_resolutions"], 2)
        self.assertEqual(stats["skipped_level_start_zero"], 1)
        self.assertEqual(stats["rows_kept"], 3)
        self.assertEqual(
            {rank: len(rows) for rank, rows in ranks.items()},
            {"PAWN": 1, "S_PAWN": 1, "KNIGHT": 1, "S_KNIGHT": 0},
        )
        self.assertEqual(ranks["KNIGHT"][0]["vnum"], 11)

    def test_an_unresolvable_item_token_aborts_the_line(self) -> None:
        line = common_drop(("x", "1", "9", "0.5", "999", "1"))
        with self.assertRaisesRegex(DropCorpusError, "no such item"):
            parse_common_drop(line, item_table((11, b"Potion", 0)), "fixture")


class MonsterGroupTests(unittest.TestCase):
    def test_drop_rows_scale_the_percent_and_stop_at_the_first_gap(self) -> None:
        data = mob_group(
            "mob_drop",
            "drop",
            103,
            [("1", "10\t1\t0.2"), ("2", "20\t1\t0.28995"), ("4", "30\t1\t0.5")],
        )
        drop, kill, limit, gloves, stats = read_monster_drop_item_group(
            data, item_table((10, b"a", 0), (20, b"b", 0), (30, b"c", 0)), "fixture"
        )

        # Key ``3`` is missing, so the walk stops and never reads key ``4``.
        self.assertEqual([item["vnum"] for item in drop[103]["items"]], [10, 20])
        self.assertEqual([item["pct_10k"] for item in drop[103]["items"]], [2000, 2899])
        self.assertEqual(stats["first_gap_histogram"], {"3": 1})
        self.assertEqual(stats["by_type"]["drop"], 1)
        self.assertEqual((kill, limit, gloves), ({}, {}, {}))

    def test_kill_rows_carry_raw_cumulative_percentages_and_clamped_rare(self) -> None:
        data = mob_group(
            "kill_group",
            "kill",
            1902,
            [
                ("1", "10\t2\t100\t0"),
                ("2", "20\t15\t30\t250"),
                ("3", "30\t1\t40\t-5"),
            ],
            kill_drop="1",
        )
        _drop, kill, _limit, _gloves, _stats = read_monster_drop_item_group(
            data, item_table((10, b"a", 0), (20, b"b", 0), (30, b"c", 0)), "fixture"
        )
        group = kill[1902]
        self.assertEqual(group["kill_drop"], 1)
        self.assertEqual([item["part_pct"] for item in group["items"]], [100, 30, 40])
        self.assertEqual([item["cumulative_pct"] for item in group["items"]], [100, 130, 170])
        self.assertEqual([item["rare_pct"] for item in group["items"]], [0, 100, 0])

    def test_a_kill_group_with_kill_drop_zero_is_skipped_entirely(self) -> None:
        data = mob_group("kill_group", "kill", 1902, [("1", "10\t1\t50\t0")], kill_drop="0")
        _drop, kill, _limit, _gloves, stats = read_monster_drop_item_group(
            data, item_table((10, b"a", 0)), "fixture"
        )
        self.assertEqual(kill, {})
        self.assertEqual(stats["groups"], 1)
        self.assertEqual(stats["by_type"]["kill"], 0)
        self.assertEqual(stats["skipped_kill_drop_zero"], 1)

    def test_repeated_drop_groups_for_one_mob_merge(self) -> None:
        data = mob_group("first", "drop", 103, [("1", "10\t1\t0.2")]) + mob_group(
            "second", "drop", 103, [("1", "20\t1\t0.2")]
        )
        drop, _kill, _limit, _gloves, stats = read_monster_drop_item_group(
            data, item_table((10, b"a", 0), (20, b"b", 0)), "fixture"
        )
        self.assertEqual([item["vnum"] for item in drop[103]["items"]], [10, 20])
        self.assertEqual(drop[103]["name"], "first")
        self.assertEqual(stats["by_type"]["drop"], 2)
        self.assertEqual(stats["merged_drop_groups"], 1)

    def test_a_repeated_kill_group_is_dropped_because_the_map_insert_wins(self) -> None:
        data = mob_group("first", "kill", 1902, [("1", "10\t1\t50\t0")], kill_drop="1") + mob_group(
            "second", "kill", 1902, [("1", "20\t1\t50\t0")], kill_drop="1"
        )
        _drop, kill, _limit, _gloves, stats = read_monster_drop_item_group(
            data, item_table((10, b"a", 0), (20, b"b", 0)), "fixture"
        )
        self.assertEqual([item["vnum"] for item in kill[1902]["items"]], [10])
        self.assertEqual(kill[1902]["name"], "first")
        self.assertEqual(stats["duplicates_dropped"]["kill"], 1)
        self.assertEqual(stats["by_type"]["kill"], 2)

    def test_limit_rows_need_a_level_limit(self) -> None:
        data = mob_group("no_limit", "limit", 1401, [("1", "10\t1\t2")])
        with self.assertRaisesRegex(DropCorpusError, "no level_limit"):
            read_monster_drop_item_group(data, item_table((10, b"a", 0)), "fixture")

    def test_duplicate_row_keys_keep_the_first_row(self) -> None:
        data = mob_group("dupes", "drop", 103, [("1", "10\t1\t0.2"), ("1", "20\t1\t0.5")])
        drop, _kill, _limit, _gloves, _stats = read_monster_drop_item_group(
            data, item_table((10, b"a", 0), (20, b"b", 0)), "fixture"
        )
        self.assertEqual([item["vnum"] for item in drop[103]["items"]], [10])

    def test_a_kr_prefixed_group_name_is_still_parsed(self) -> None:
        # ``GetCurrentNodeName`` runs on the parentless global node, so the
        # original's ``kr_`` skip is dead code and the name is not inspected.
        data = mob_group("kr_test", "drop", 103, [("1", "10\t1\t0.2")])
        drop, _kill, _limit, _gloves, stats = read_monster_drop_item_group(
            data, item_table((10, b"a", 0)), "fixture"
        )
        self.assertEqual(stats["by_type"]["drop"], 1)
        self.assertIn(103, drop)
        self.assertEqual(drop[103]["name"], "kr_test")

    def test_a_short_drop_row_is_reported(self) -> None:
        data = mob_group("short", "drop", 103, [("1", "10\t1")])
        with self.assertRaisesRegex(DropCorpusError, "value"):
            read_monster_drop_item_group(data, item_table((10, b"a", 0)), "fixture")

    def test_unknown_group_type_and_missing_mob_are_reported(self) -> None:
        with self.assertRaisesRegex(DropCorpusError, "invalid type"):
            read_monster_drop_item_group(
                mob_group("bad", "treasure", 103, [("1", "10\t1\t0.2")]),
                item_table((10, b"a", 0)),
                "fixture",
            )
        with self.assertRaisesRegex(DropCorpusError, "no mob vnum"):
            read_monster_drop_item_group(
                b"Group\tg\n{\n\tType\tdrop\n\t1\t10\t1\t0.2\n}\n",
                item_table((10, b"a", 0)),
                "fixture",
            )

    def test_an_unresolvable_item_aborts_the_group(self) -> None:
        data = mob_group("bad_item", "drop", 103, [("1", "999\t1\t0.2")])
        with self.assertRaisesRegex(DropCorpusError, "no such item"):
            read_monster_drop_item_group(data, item_table((10, b"a", 0)), "fixture")

    def test_a_value_less_row_is_reported_instead_of_truncating(self) -> None:
        # The original's ``break`` makes every enclosing ``LoadGroup`` re-read
        # the same line, silently ending the file.  The compiler refuses.
        data = mob_group("trunc", "drop", 103, [("1", "10\t1\t0.2")]) + b"\tstray\n"
        with self.assertRaisesRegex(DropCorpusError, "stop parsing"):
            read_monster_drop_item_group(data, item_table((10, b"a", 0)), "fixture")


@unittest.skipUnless(SOURCE.is_dir(), f"pinned research checkout missing at {SOURCE}")
class PinnedCorpusTests(unittest.TestCase):
    """The shipped corpus, recompiled from the pinned ``git.old-metin2.com`` tree."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.corpus = compile_corpus(SOURCE)

    def test_prototype_and_common_drop_counts(self) -> None:
        corpus = self.corpus
        self.assertEqual(corpus["item_prototypes"]["count"], PINNED["prototypes"])
        self.assertEqual(corpus["item_prototypes"]["range_rows"], PINNED["range_rows"])

        common = corpus["common_stats"]
        self.assertEqual(common["lines"], PINNED["common_lines"])
        self.assertEqual(common["rows_kept"], PINNED["common_rows"])
        self.assertEqual(common["kept_by_rank"], PINNED["common_by_rank"])
        self.assertEqual(
            common["skipped_level_start_zero"], PINNED["common_skipped_level_start_zero"]
        )
        self.assertEqual(common["resolved_by_number"], PINNED["common_resolved_by_number"])
        # Every non-empty token fails the name lookup: the table stores vnums.
        self.assertEqual(common["empty_name_resolutions"], PINNED["common_empty_names"])
        self.assertEqual(
            common["resolved_by_number"] + common["empty_name_resolutions"], 4 * common["lines"]
        )
        for rank in RANKS:
            self.assertEqual(len(corpus["common"][rank]), PINNED["common_by_rank"][rank])

    def test_monster_group_counts(self) -> None:
        corpus = self.corpus
        stats = corpus["group_stats"]
        self.assertEqual(stats["groups"], PINNED["group_nodes"])
        self.assertEqual(sum(stats["by_type"].values()), PINNED["group_installed"])
        self.assertEqual(stats["distinct_names"], PINNED["group_distinct_names"])
        self.assertEqual(stats["by_type"], PINNED["groups_by_type"])
        self.assertEqual(stats["items"], PINNED["rows_by_type"])
        self.assertEqual(stats["merged_drop_groups"], PINNED["merged_drop_groups"])
        self.assertEqual(stats["skipped_kill_drop_zero"], PINNED["skipped_kill_drop_zero"])
        self.assertEqual(
            stats["duplicates_dropped"], {kind: 0 for kind in stats["duplicates_dropped"]}
        )
        self.assertEqual(
            stats["groups"] - stats["skipped_kill_drop_zero"], PINNED["group_installed"]
        )

    def test_every_group_row_names_a_shipped_prototype(self) -> None:
        corpus = self.corpus
        table = load_item_table((SOURCE / "gamefiles/conf/item_proto.txt").read_bytes())
        vnums = {row["vnum"] for rank in RANKS for row in corpus["common"][rank]}
        for kind, groups in corpus["groups"].items():
            for vnum, group in groups.items():
                self.assertEqual(group["type"], kind)
                self.assertEqual(int(vnum), group["mob_vnum"])
                for item in group["items"]:
                    self.assertIn(item["vnum"], table._vnums)  # noqa: SLF001 - test-only read
                    vnums.add(item["vnum"])
        self.assertTrue(vnums)

    def test_kill_group_cumulative_percentages_are_monotonic(self) -> None:
        for group in self.corpus["groups"]["kill"].values():
            previous = 0
            for item in group["items"]:
                self.assertGreater(item["cumulative_pct"], previous)
                previous = item["cumulative_pct"]
                self.assertGreaterEqual(item["rare_pct"], 0)
                self.assertLessEqual(item["rare_pct"], 100)

    def test_the_corpus_is_deterministic_and_json_safe(self) -> None:
        corpus = self.corpus
        self.assertEqual(corpus["content_hash"], corpus_hash(corpus))
        encoded = json.dumps(corpus, sort_keys=True)
        self.assertEqual(json.loads(encoded)["content_hash"], corpus["content_hash"])
        revision = corpus["source"]["revision"]
        if revision is not None:
            self.assertTrue(revision.startswith("7ee9c84"), revision)


if __name__ == "__main__":
    unittest.main()
