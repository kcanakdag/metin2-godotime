import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from import_ground_items import DEFAULT_MODEL, selected_models


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
        for vnums in ([], [0], [-1], [True], list(range(1, 258))):
            with self.subTest(vnums=vnums), self.assertRaises(ValueError):
                selected_models(valid, vnums)


if __name__ == "__main__":
    unittest.main()
