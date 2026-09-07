import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from content_formats import parse_race_script  # noqa: E402


class HairContentTests(unittest.TestCase):
    def test_race_parser_selects_exact_default_hair(self):
        race = parse_race_script(
            """
            ScriptType RaceDataScript
            BaseModelFileName "d:/ymir work/pc/warrior/warrior_novice.gr2"
            Group HairData {
              PathName "d:/ymir work/pc/warrior/"
              HairDataCount 1
              Group HairData00 {
                HairIndex 0
                Model "hair/hair_1_1.gr2"
                SourceSkin "hair/hair_1_1.dds"
                TargetSkin "warrior_hair_01.dds"
              }
            }
            """
        )
        self.assertEqual(
            race["hair"],
            [
                {
                    "hair_index": 0,
                    "model": "ymir work/pc/warrior/hair/hair_1_1.gr2",
                    "source_skin": "ymir work/pc/warrior/hair/hair_1_1.dds",
                    "target_skin": "ymir work/pc/warrior/warrior_hair_01.dds",
                }
            ],
        )

    def test_race_parser_rejects_hair_count_mismatch(self):
        with self.assertRaisesRegex(ValueError, "HairDataCount"):
            parse_race_script(
                """
                ScriptType RaceDataScript
                BaseModelFileName "base.gr2"
                Group HairData {
                  PathName "d:/hair"
                  HairDataCount 1
                }
                """
            )


if __name__ == "__main__":
    unittest.main()
