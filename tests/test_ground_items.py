import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from import_ground_items import (
    DEFAULT_MODEL,
    MAX_MODELS,
    MAX_VNUMS,
    YANG_VNUM,
    coverage_vnums,
    selected_models,
    selection_vnums,
)


class GroundItemSelectionTests(unittest.TestCase):
    def test_explicit_shared_models_and_original_bag_default(self):
        text = (
            "1\tETC\ticon/money.tga\td:/ymir work/item/etc/money.gr2\n"
            "27001\tETC\ticon/s.tga\td:/ymir work/item/etc/medicine_R.GR2\n"
            "27002\tETC\ticon/m.tga\td:/ymir work/item/etc/medicine_R.GR2\n"
            "99\tETC\ticon/unknown.tga\n"
        )
        result = selected_models(text, [27002, 99, 27001])
        self.assertEqual(list(result), [99, 27001, 27002])
        self.assertEqual(result[99], DEFAULT_MODEL)
        self.assertEqual(result[27001], result[27002])
        self.assertEqual(result[27001], "ymir work/item/etc/medicine_r.gr2")
        self.assertNotIn(1, result)

    def test_missing_duplicate_malformed_and_unsafe_models_reject(self):
        valid = "1\tETC\ticon/a.tga\td:/ymir work/item/etc/money.gr2"
        for text in (
            "",
            valid + "\n" + valid,
            "1\tETC",
            valid + "\textra",
            "1\tETC\ticon/a.tga\t../outside.gr2",
            "1\tETC\ticon/a.tga\t",
            "1\tETC\ticon/a.tga\tfoo.txt",
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                selected_models(text, [1])
        for vnums in ([], [0], [-1], [True], list(range(1, MAX_VNUMS + 2))):
            with self.subTest(vnums=vnums), self.assertRaises(ValueError):
                selected_models(valid, vnums)

    def test_many_rows_may_share_one_model_and_the_model_bound_still_holds(self):
        shared = "\n".join(
            f"{vnum}\tETC\ticon/a.tga\td:/ymir work/item/etc/item_bag.gr2"
            for vnum in range(1, MAX_VNUMS + 1)
        )
        result = selected_models(shared, list(range(1, MAX_VNUMS + 1)))
        self.assertEqual(len(result), MAX_VNUMS)
        self.assertEqual(set(result.values()), {DEFAULT_MODEL})
        distinct = "\n".join(
            f"{vnum}\tETC\ticon/a.tga\td:/ymir work/item/weapon/{vnum:05d}.gr2"
            for vnum in range(1, MAX_MODELS + 2)
        )
        with self.assertRaisesRegex(ValueError, "ground models"):
            selected_models(distinct, list(range(1, MAX_MODELS + 2)))

    def test_item_selection_vnums_reads_the_compiled_registry(self):
        def write(document):
            handle = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
            self.addCleanup(Path(handle.name).unlink)
            json.dump(document, handle)
            handle.close()
            return handle.name

        self.assertEqual(
            selection_vnums(write({"schema_version": 1, "items": [{"vnum": 3}, {"vnum": 1}]})),
            [1, 3],
        )
        for document in (
            {"schema_version": 2, "items": [{"vnum": 1}]},
            {"schema_version": 1, "items": []},
            {"schema_version": 1, "items": "no"},
            {"schema_version": 1, "items": [{"vnum": 1}, {"vnum": 1}]},
            {"schema_version": 1, "items": [{"vnum": 0}]},
            {"schema_version": 1, "items": [{"vnum": True}]},
            {"schema_version": 1, "items": [{"id": "item.probe.candidate"}]},
        ):
            with self.subTest(document=document), self.assertRaises(ValueError):
                selection_vnums(write(document))

    def test_currency_is_covered_even_when_the_selection_omits_it(self):
        self.assertEqual(coverage_vnums([27001, 27002]), [YANG_VNUM, 27001, 27002])
        self.assertEqual(coverage_vnums([1, 11]), [1, 11])
        text = (
            "1\tETC\ticon/money.tga\td:/ymir work/item/etc/money.gr2\n"
            "11\tWEAPON\ticon/w.tga\td:/ymir work/item/weapon/00010.gr2\n"
        )
        result = selected_models(text, coverage_vnums([11]))
        self.assertEqual(sorted(result), [1, 11])
        self.assertEqual(result[YANG_VNUM], "ymir work/item/etc/money.gr2")


if __name__ == "__main__":
    unittest.main()
