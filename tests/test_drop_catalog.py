"""Regression tests for the runtime drop catalog compiler.

``tools/build_drop_catalog.py`` narrows the replayed corpus into the table the
authoritative server rolls loot from.  The interesting behaviour is what the
compiler *refuses* to ship: rows the original loads but can never select, a
count column the original parses and then ignores, and group rows for mobs the
selected population cannot spawn.  Small synthetic corpora pin those rules and
the pinned ``git.old-metin2.com`` checkout re-checks the shipped numbers.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# The content builders import each other by bare module name, exactly as
# ``tools/dev.py`` runs them.
sys.path.insert(0, str(ROOT / "tools"))

from tools.build_drop_catalog import (  # noqa: E402
    SCHEMA,
    VERSION,
    DropCatalogError,
    catalog_hash,
    catalog_text,
    compile_catalog,
    load_mob_ranks,
)
from tools.metin_drops import (  # noqa: E402
    DEFAULT_SOURCE,
    GROUP_TYPES,
    MOB_RANKS,
    RANKS,
    ItemPrototype,
    ItemTable,
)

# Counts for the pinned revision ``7ee9c84``. The catalog is deliberately
# smaller than the corpus. Rows fall out for three reasons and each is counted
# in ``excluded_common_rows``: 53 loaded rows sit above the level cap and can
# never match a real level; the rest name prototypes the selected registry does
# not install, so the module could not hand them out.
PINNED = {
    "common_rows": 1220,
    "common_by_rank": {"PAWN": 277, "S_PAWN": 317, "KNIGHT": 319, "S_KNIGHT": 307},
    "unreachable": {"S_PAWN": 24, "KNIGHT": 29},
    "unregistered_item": {"PAWN": 157, "S_PAWN": 193, "KNIGHT": 191, "S_KNIGHT": 203},
    "groups": 10,
    "group_rows": 41,
    "groups_by_type": {"drop": 8, "kill": 2, "limit": 0, "thiefgloves": 0},
    "mobs_by_rank": {
        "PAWN": 4,
        "S_PAWN": 3,
        "KNIGHT": 0,
        "S_KNIGHT": 3,
        "BOSS": 0,
        "KING": 0,
    },
    "group_rows_dropped": 19,
    "notices": 561,
}

# The compiler now also takes the installed item registry and its provenance,
# because a common row whose vnum the module cannot hand out would otherwise
# become a silent no-drop. The synthetic fixtures only ship vnums 10 and 20.
REGISTRY = frozenset({10, 20})
REGISTRY_IDENTITY = {"profile": "fixture", "sha256": "0" * 64, "items": 2}

# ``PERCENT_LVDELTA`` percentages from ``src/game/src/constants.cpp``. The
# synthetic corpora only need a shape-valid table; the pinned corpus test below
# re-reads the real one from the checkout.
LEVEL_DELTA = {
    "normal_percent": [100] * 31,
    "boss_percent": [105] * 31,
    "source": {"path": "src/game/src/constants.cpp", "sha256": "0" * 64},
}


def prototypes(*vnums: int) -> ItemTable:
    return ItemTable([ItemPrototype(vnum=vnum, name=b"", vnum_range=0) for vnum in vnums])


def common_row(level_start: int, level_end: int, vnum: int, percent: int = 100, count: int = 0):
    return {
        "level_start": level_start,
        "level_end": level_end,
        "percent": percent,
        "count": count,
        "vnum": vnum,
        "name": str(vnum),
        "line": 1,
        # The reader's own verdict; the compiler re-derives it and refuses to
        # disagree silently.
        "reachable": 1 <= level_start <= 120 and level_start <= level_end,
    }


def corpus_document(
    *,
    common: dict[str, list[dict]] | None = None,
    groups: dict[str, dict[str, dict]] | None = None,
    ranks: tuple[str, ...] = RANKS,
) -> dict:
    return {
        "schema": "mt2spacetime.drop-corpus",
        "schema_version": 2,
        "ranks": list(ranks),
        "item_prototypes": {"count": 1, "range_rows": 0, "sha256": "0" * 64},
        "source": {"root": "/fixture", "revision": "fixture", "files": {}},
        "common_stats": {},
        "common": common
        if common is not None
        else {rank: [common_row(1, 15, 10)] for rank in RANKS},
        "groups": groups if groups is not None else {kind: {} for kind in GROUP_TYPES},
        "content_hash": "1" * 64,
    }


def drop_group(mob: int, *rows: tuple[int, int]) -> dict:
    return {
        "type": "drop",
        "mob_vnum": mob,
        "name": "fixture",
        "line": 1,
        "items": [
            {"vnum": vnum, "name": str(vnum), "line": 2, "count": 1, "pct_10k": pct}
            for vnum, pct in rows
        ],
    }


def mob_catalog(path: Path, *mobs: tuple[int, str]) -> Path:
    path.write_text(
        json.dumps(
            {"mobs": [{"vnum": vnum, "source_definition": {"rank": rank}} for vnum, rank in mobs]}
        )
    )
    return path


class CommonRowTests(unittest.TestCase):
    def test_unreachable_rows_are_excluded_and_counted(self) -> None:
        document = corpus_document(
            common={
                "PAWN": [common_row(1, 15, 10), common_row(320000, 0, 20, count=0)],
                "S_PAWN": [common_row(1, 15, 10)],
                "KNIGHT": [common_row(1, 15, 10)],
                "S_KNIGHT": [common_row(1, 15, 10)],
            }
        )
        catalog = compile_catalog(
            document, prototypes(10, 20), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, LEVEL_DELTA
        )
        self.assertEqual([row["vnum"] for row in catalog["common"]["PAWN"]], [10])
        self.assertEqual(
            catalog["summary"]["excluded_common_rows"],
            {"unreachable": {"PAWN": 1}, "clamped_level_end": {}, "unregistered_item": {}},
        )

    def test_a_row_whose_flag_disagrees_fails_the_build(self) -> None:
        document = corpus_document()
        document["common"]["PAWN"][0]["reachable"] = False
        with self.assertRaisesRegex(DropCatalogError, "reachability"):
            compile_catalog(
                document, prototypes(10), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, LEVEL_DELTA
            )

    def test_level_end_above_the_cap_is_clamped(self) -> None:
        document = corpus_document()
        document["common"]["PAWN"] = [common_row(1, 66666666, 10)]
        catalog = compile_catalog(
            document, prototypes(10), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, LEVEL_DELTA
        )
        self.assertEqual(catalog["common"]["PAWN"][0]["level_end"], 120)
        self.assertEqual(
            catalog["summary"]["excluded_common_rows"]["clamped_level_end"], {"PAWN": 1}
        )

    def test_common_rows_always_create_one_item(self) -> None:
        # ``CreateItem(c_rInfo.m_dwVnum, 1, 0, true)`` ignores ``iCount``, which
        # the pinned file leaves at 0 in 563 rows and once at ``INT_MAX``.
        document = corpus_document()
        document["common"]["PAWN"] = [common_row(1, 15, 10, count=65_535)]
        catalog = compile_catalog(
            document, prototypes(10), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, LEVEL_DELTA
        )
        self.assertEqual(catalog["common"]["PAWN"][0]["count"], 1)

    def test_an_undefined_vnum_fails_the_build(self) -> None:
        document = corpus_document()
        document["common"]["PAWN"] = [common_row(1, 15, 99)]
        with self.assertRaisesRegex(DropCatalogError, "undefined item vnum 99"):
            compile_catalog(
                document, prototypes(10), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, LEVEL_DELTA
            )

    def test_a_rank_with_no_reachable_rows_fails_the_build(self) -> None:
        document = corpus_document()
        document["common"]["KNIGHT"] = [common_row(8000, 0, 10)]
        with self.assertRaisesRegex(DropCatalogError, "no reachable rows"):
            compile_catalog(
                document, prototypes(10), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, LEVEL_DELTA
            )

    def test_rank_order_must_match_the_enum(self) -> None:
        document = corpus_document(ranks=tuple(reversed(RANKS)))
        with self.assertRaisesRegex(DropCatalogError, "rank order"):
            compile_catalog(
                document, prototypes(10), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, LEVEL_DELTA
            )

    def test_an_invalid_percent_fails_the_build(self) -> None:
        document = corpus_document()
        document["common"]["PAWN"] = [common_row(1, 15, 10, percent=-1)]
        with self.assertRaisesRegex(DropCatalogError, "invalid percent"):
            compile_catalog(
                document, prototypes(10), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, LEVEL_DELTA
            )


class GroupTests(unittest.TestCase):
    def test_unselected_mobs_become_notices(self) -> None:
        document = corpus_document(groups={"drop": {"103": drop_group(103, (10, 2000))}})
        catalog = compile_catalog(
            document, prototypes(10), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, LEVEL_DELTA
        )
        self.assertEqual(catalog["groups"], {})
        self.assertEqual(
            catalog["summary"]["notices"],
            [{"mob_vnum": 103, "type": "drop", "reason": "mob-not-selected"}],
        )

    def test_selected_mobs_keep_their_gate_constants(self) -> None:
        kill = {
            "type": "kill",
            "mob_vnum": 100,
            "name": "fixture",
            "line": 1,
            "kill_drop": 400,
            "items": [
                {
                    "vnum": 10,
                    "name": "10",
                    "line": 2,
                    "count": 1,
                    "part_pct": 25,
                    "cumulative_pct": 25,
                    "rare_pct": 10,
                }
            ],
        }
        limit = {
            "type": "limit",
            "mob_vnum": 100,
            "name": "fixture",
            "line": 3,
            "level_limit": 75,
            "items": [
                {"vnum": 10, "name": "10", "line": 4, "count": 1, "pct_10k": 800},
            ],
        }
        document = corpus_document(groups={"kill": {"100": kill}, "limit": {"100": limit}})
        catalog = compile_catalog(
            document, prototypes(10), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, LEVEL_DELTA
        )
        group = catalog["groups"]["100"]
        self.assertEqual(group["kill_drop"], 400)
        self.assertEqual(group["level_limit"], 75)
        self.assertEqual(group["rank"], 0)
        self.assertEqual([row["cumulative_pct"] for row in group["kill"]], [25])
        self.assertEqual([row["pct_10k"] for row in group["limit"]], [800])

    def kill_group(self, *items: dict) -> dict:
        return {
            "type": "kill",
            "mob_vnum": 100,
            "name": "fixture",
            "line": 1,
            "kill_drop": 400,
            "items": list(items),
        }

    def kill_row(self, **overrides) -> dict:
        row = {
            "vnum": 10,
            "name": "10",
            "line": 2,
            "count": 1,
            "part_pct": 25,
            "cumulative_pct": 25,
            "rare_pct": 0,
        }
        row.update(overrides)
        return row

    def test_a_kill_row_without_a_cumulative_percent_fails(self) -> None:
        # ``GetOneIndex`` cannot roll a vector the reader never filled.
        row = self.kill_row()
        del row["part_pct"]
        del row["cumulative_pct"]
        document = corpus_document(groups={"kill": {"100": self.kill_group(row)}})
        with self.assertRaisesRegex(DropCatalogError, "no cumulative percent"):
            compile_catalog(
                document, prototypes(10), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, LEVEL_DELTA
            )

    def test_a_kill_group_that_is_not_sorted_fails(self) -> None:
        # A later row may not sit below the running total of the previous one:
        # ``lower_bound`` would then hand the earlier item a negative band.
        document = corpus_document(
            groups={
                "kill": {
                    "100": self.kill_group(
                        self.kill_row(part_pct=50, cumulative_pct=50),
                        self.kill_row(part_pct=10, cumulative_pct=30),
                    )
                }
            }
        )
        with self.assertRaisesRegex(DropCatalogError, "not sorted"):
            compile_catalog(
                document, prototypes(10), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, LEVEL_DELTA
            )

    def test_a_zero_part_percent_fails(self) -> None:
        document = corpus_document(
            groups={"kill": {"100": self.kill_group(self.kill_row(part_pct=0, cumulative_pct=0))}}
        )
        with self.assertRaisesRegex(DropCatalogError, "non-positive part percent"):
            compile_catalog(
                document, prototypes(10), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, LEVEL_DELTA
            )

    def test_a_group_row_must_name_a_shipped_prototype(self) -> None:
        document = corpus_document(groups={"drop": {"100": drop_group(100, (99, 2000))}})
        with self.assertRaisesRegex(DropCatalogError, "undefined item vnum 99"):
            compile_catalog(
                document, prototypes(10), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, LEVEL_DELTA
            )


class MobCatalogTests(unittest.TestCase):
    def test_ranks_are_read_from_the_compiled_definition(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = mob_catalog(Path(directory) / "gameplay.json", (100, "S_KNIGHT"), (200, "BOSS"))
            self.assertEqual(load_mob_ranks(path), {"100": 3, "200": 4})

    def test_an_unknown_rank_fails_the_build(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = mob_catalog(Path(directory) / "gameplay.json", (100, "ARCHER"))
            with self.assertRaisesRegex(DropCatalogError, "unsupported rank"):
                load_mob_ranks(path)

    def test_a_missing_mob_list_fails_the_build(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gameplay.json"
            path.write_text("{}")
            with self.assertRaisesRegex(DropCatalogError, "has no mob list"):
                load_mob_ranks(path)

    def test_the_rank_enum_matches_the_mob_registry(self) -> None:
        # Both tools number ``EMobRank`` independently; a drift between them
        # would silently re-rank every group in the catalog.
        from tools.mob_server_registry import MOB_RANKS as REGISTRY_RANKS

        self.assertEqual(MOB_RANKS, REGISTRY_RANKS)


class ArtifactTests(unittest.TestCase):
    def test_the_catalog_is_deterministic_and_hash_covers_the_payload(self) -> None:
        document = corpus_document()
        first = compile_catalog(
            document, prototypes(10), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, LEVEL_DELTA
        )
        second = compile_catalog(
            document, prototypes(10), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, LEVEL_DELTA
        )
        self.assertEqual(catalog_text(first), catalog_text(second))
        self.assertEqual(first["content_hash"], second["content_hash"])
        self.assertEqual(catalog_hash(first), first["content_hash"])
        self.assertNotIn("content_hash", json.loads(catalog_text(first))["content_hash"])
        changed = corpus_document()
        changed["common"]["PAWN"] = [common_row(1, 15, 10, percent=101)]
        self.assertNotEqual(
            catalog_hash(
                compile_catalog(
                    changed, prototypes(10), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, LEVEL_DELTA
                )
            ),
            first["content_hash"],
        )

    def test_the_schema_and_version_are_pinned(self) -> None:
        catalog = compile_catalog(
            corpus_document(), prototypes(10), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, LEVEL_DELTA
        )
        self.assertEqual(catalog["schema"], SCHEMA)
        self.assertEqual(catalog["version"], VERSION)
        self.assertEqual(catalog["source"]["corpus_hash"], "1" * 64)

    def test_the_level_delta_tables_are_embedded_and_checked(self) -> None:
        catalog = compile_catalog(
            corpus_document(), prototypes(10), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, LEVEL_DELTA
        )
        self.assertEqual(catalog["level_delta"]["normal_percent"], [100] * 31)
        self.assertEqual(catalog["level_delta"]["boss_percent"], [105] * 31)
        self.assertEqual(catalog["level_delta"]["source"]["path"], "src/game/src/constants.cpp")

        short = {
            "normal_percent": [100] * 30,
            "boss_percent": [105] * 31,
            **{"source": LEVEL_DELTA["source"]},
        }
        with self.assertRaisesRegex(
            DropCatalogError, "Level-delta table normal_percent must contain 31 values"
        ):
            compile_catalog(
                corpus_document(), prototypes(10), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, short
            )

        out_of_range = {
            "normal_percent": [*[100] * 30, 1001],
            "boss_percent": [105] * 31,
            "source": LEVEL_DELTA["source"],
        }
        with self.assertRaisesRegex(
            DropCatalogError, "Level-delta table normal_percent must contain 31 values"
        ):
            compile_catalog(
                corpus_document(),
                prototypes(10),
                {"100": 0},
                REGISTRY,
                REGISTRY_IDENTITY,
                out_of_range,
            )

        # A boolean is an ``int`` in Python; it must not slip through as 1.
        boolean = {
            "normal_percent": [True, *[100] * 30],
            "boss_percent": [105] * 31,
            "source": LEVEL_DELTA["source"],
        }
        with self.assertRaisesRegex(
            DropCatalogError, "Level-delta table normal_percent must contain 31 values"
        ):
            compile_catalog(
                corpus_document(), prototypes(10), {"100": 0}, REGISTRY, REGISTRY_IDENTITY, boolean
            )

        without_source = {"normal_percent": [100] * 31, "boss_percent": [105] * 31}
        with self.assertRaisesRegex(
            DropCatalogError, "Level-delta tables must carry their pinned source identity"
        ):
            compile_catalog(
                corpus_document(),
                prototypes(10),
                {"100": 0},
                REGISTRY,
                REGISTRY_IDENTITY,
                without_source,
            )

        # The hash covers the tables: a different curve is a different catalog.
        changed = {**LEVEL_DELTA, "boss_percent": [106] * 31}
        self.assertNotEqual(
            catalog_hash(
                compile_catalog(
                    corpus_document(),
                    prototypes(10),
                    {"100": 0},
                    REGISTRY,
                    REGISTRY_IDENTITY,
                    changed,
                )
            ),
            catalog["content_hash"],
        )


@unittest.skipUnless(
    DEFAULT_SOURCE.is_dir(), f"pinned research checkout missing at {DEFAULT_SOURCE}"
)
class PinnedCatalogTests(unittest.TestCase):
    """The shipped catalog, compiled from the pinned original server tree."""

    @classmethod
    def setUpClass(cls) -> None:
        from tools.build_drop_catalog import DEFAULT_PROFILE, build

        content = ROOT / ".local/mobs/server-package-r2/gameplay.v1.json"
        if not content.is_file():
            raise unittest.SkipTest(f"compiled mob package missing at {content}")
        cls.catalog = build(DEFAULT_SOURCE, content, DEFAULT_PROFILE)

    def test_pinned_catalog_counts(self) -> None:
        summary = self.catalog["summary"]
        self.assertEqual(summary["common_rows"], PINNED["common_rows"])
        self.assertEqual(summary["common_by_rank"], PINNED["common_by_rank"])
        self.assertEqual(summary["excluded_common_rows"]["unreachable"], PINNED["unreachable"])
        self.assertEqual(
            summary["excluded_common_rows"]["unregistered_item"], PINNED["unregistered_item"]
        )
        self.assertEqual(summary["excluded_common_rows"]["clamped_level_end"], {})
        self.assertEqual(summary["groups"], PINNED["groups"])
        self.assertEqual(summary["group_rows"], PINNED["group_rows"])
        self.assertEqual(summary["groups_by_type"], PINNED["groups_by_type"])
        self.assertEqual(summary["mobs_by_rank"], PINNED["mobs_by_rank"])
        self.assertEqual(summary["group_rows_dropped"], PINNED["group_rows_dropped"])
        self.assertEqual(len(summary["notices"]), PINNED["notices"])

    def test_every_compiled_common_row_is_reachable_and_defined(self) -> None:
        prototypes_table = self.catalog_has_vnums()
        for rank, rows in self.catalog["common"].items():
            for row in rows:
                self.assertGreaterEqual(row["level_start"], 1, rank)
                self.assertLessEqual(row["level_end"], 120, rank)
                self.assertGreaterEqual(row["level_end"], row["level_start"], rank)
                self.assertEqual(row["count"], 1, rank)
                self.assertIn(row["vnum"], prototypes_table, rank)

    def test_the_catalog_is_deterministic(self) -> None:
        from tools.build_drop_catalog import DEFAULT_PROFILE, build

        content = ROOT / ".local/mobs/server-package-r2/gameplay.v1.json"
        self.assertEqual(build(DEFAULT_SOURCE, content, DEFAULT_PROFILE), self.catalog)

    def catalog_has_vnums(self) -> set[int]:
        from tools.metin_drops import ITEM_PROTO, load_item_table

        table = load_item_table((DEFAULT_SOURCE / ITEM_PROTO).read_bytes())
        vnums: set[int] = set()
        for row in table.prototypes:
            if row.vnum_range:
                vnums.update(range(row.vnum, row.vnum + row.vnum_range))
            else:
                vnums.add(row.vnum)
        return vnums


if __name__ == "__main__":
    unittest.main()
