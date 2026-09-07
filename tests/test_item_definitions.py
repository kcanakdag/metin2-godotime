from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from tools.item_definitions import compile_catalog, public_catalog, validate_catalog

ROOT = Path(__file__).resolve().parents[1]


class ItemDefinitionsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        profile = json.loads((ROOT / "content/profiles/p0-warrior-dog.json").read_text())
        reference = profile["source"]["server_reference"]
        cache = ROOT / "assets/source/content/server" / reference["revision"]
        cls.proto = (cache / "gamefiles/conf/item_proto.txt").read_text(encoding="latin-1")
        cls.names = (cache / "gamefiles/conf/item_names_en.txt").read_text(encoding="latin-1")
        source = next(
            row for row in reference["files"] if row["path"] == "gamefiles/conf/item_proto.txt"
        )
        cls.source = {**source, "revision": reference["revision"]}
        cls.selection = profile["item_catalog"]
        cls.catalog = compile_catalog(cls.selection, cls.proto, cls.names, cls.source)

    def test_selected_items_derive_distinct_values_and_source_restrictions(self) -> None:
        sword, fan, small, medium = self.catalog["items"]
        self.assertEqual(
            (sword["height"], sword["stack_limit"], sword["allowed_classes"]), (2, 1, 7)
        )
        self.assertEqual(sword["weapon"]["power_max"], 15)
        self.assertEqual((fan["height"], fan["allowed_classes"], fan["allowed_sexes"]), (1, 8, 3))
        self.assertEqual(
            fan["weapon"], {"class": "fan", "power_min": 11, "power_max": 15, "refine_attack": 0}
        )
        self.assertEqual(
            small["recovery"], {"handler": "item.recovery.pool.v1", "hp": 300, "sp": 0}
        )
        self.assertEqual(medium["recovery"]["hp"], 800)
        self.assertEqual(
            compile_catalog(self.selection, self.proto, self.names, self.source), self.catalog
        )

    def test_additional_source_definition_requires_only_a_selection_record(self) -> None:
        selection = copy.deepcopy(self.selection)
        selection["items"].append(
            {
                "id": "item.consumable.red-potion-large",
                "revision": 1,
                "vnum": 27003,
                "icon": "icon/item/27003",
            }
        )
        result = compile_catalog(selection, self.proto, self.names, self.source)
        self.assertEqual(len(result["items"]), 5)
        self.assertEqual(result["items"][-1]["recovery"]["hp"], 1200)
        self.assertEqual(
            result["items"][-1]["recovery"]["handler"], result["items"][2]["recovery"]["handler"]
        )
        # This compiler-only fixture does not add its original icon to the player package.

    def test_numeric_bounds_and_unsupported_handlers_fail_closed(self) -> None:
        mutations = [
            ("height", 0),
            ("height", 10),
            ("stack_limit", 201),
            ("vnum", True),
            ("revision", 1.0),
            ("allowed_classes", 0),
            ("allowed_sexes", 4),
            ("minimum_level", -1),
            ("kind", "execute_script"),
        ]
        for key, value in mutations:
            with self.subTest(key=key, value=value):
                changed = copy.deepcopy(self.catalog)
                changed["items"][1][key] = value
                with self.assertRaises(ValueError):
                    validate_catalog(changed)
        for value in [True, -1, 65536, float("nan"), float("inf"), 1.1]:
            changed = copy.deepcopy(self.catalog)
            changed["items"][2]["recovery"]["hp"] = value
            with self.assertRaises(ValueError):
                validate_catalog(changed)
        changed = copy.deepcopy(self.catalog)
        changed["items"][2]["recovery"]["handler"] = "grant_experience"
        with self.assertRaises(ValueError):
            validate_catalog(changed)

    def test_duplicate_ids_vnums_and_ambiguous_source_rows_are_rejected(self) -> None:
        for key in ("id", "vnum"):
            changed = copy.deepcopy(self.catalog)
            changed["items"][1][key] = changed["items"][0][key]
            with self.assertRaises(ValueError):
                validate_catalog(changed)
        line = next(line for line in self.proto.splitlines() if line.startswith("27001\t"))
        with self.assertRaisesRegex(ValueError, "exactly one"):
            compile_catalog(self.selection, self.proto + "\n" + line, self.names, self.source)

    def test_public_projection_omits_provenance_and_policy(self) -> None:
        public = public_catalog(self.catalog)
        self.assertNotIn("recovery_policy", public)
        self.assertTrue(all("source" not in row for row in public["items"]))
        self.assertEqual(public["items"][3]["recovery"]["hp"], 800)

    def test_unsupported_source_limits_flags_and_types_are_rejected(self) -> None:
        for index, value in ((2, "ITEM_QUEST"), (5, "ANTI_DROP"), (14, "REAL_TIME"), (26, "10")):
            line = next(line for line in self.proto.splitlines() if line.startswith("27001\t"))
            columns = line.split("\t")
            columns[index] = value
            with self.subTest(index=index), self.assertRaisesRegex(ValueError, "unsupported"):
                compile_catalog(
                    self.selection,
                    self.proto.replace(line, "\t".join(columns)),
                    self.names,
                    self.source,
                )
