"""NPC dialogue profile compiler: attribution, titles and coverage rules.

The dialogue profile is the bridge between the original quest corpus and the
interaction rows ``server/build_npcs.rs`` compiles into ``NpcDefinition``. These
tests pin the properties the build depends on: every referenced localization key
must exist in the pinned translations and must really be used by the referenced
handler, every map placement and every sampled area must carry exactly one row,
and the board title is the ``say_title`` that was in force when the shown line
executed.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_npc_interactions as npc_dialogue  # noqa: E402
from build_npc_interactions import (  # noqa: E402
    MAX_TITLE,
    SCHEMA,
    VERSION,
    _preceding_title,
    compile_profile,
)
from build_quest_catalog import TRANSLATE  # noqa: E402

SOURCE = ROOT / ".cache/full-game-research/server/source"
PROFILE = ROOT / "content/profiles/yongan-npc-dialogue.json"
INSTALLED = ROOT / "content/worlds/yongan.interactions.json"
MAP_ID = "metin2_map_a1"

# The fixture handler mirrors ``skill_group.quest``: the first title belongs to
# a branch that returns before the class-specific line, so a compiler that takes
# the first title of a handler would report the wrong one.
QUEST = """quest sample begin
    state start begin
        when 10001.chat.gameforge.sample._10_npcChat begin
            if pc.get_class() == 0 then
                say_title(gameforge.sample._110_wrongBranch)
                return
            end
            say_title(gameforge.sample._120_classTitle)
            say(gameforge.sample._130_classLine)
        end
    end
end
"""

TRANSLATIONS = """gameforge.sample._110_wrongBranch = "Body-Force training"
gameforge.sample._120_classTitle = "Weaponry training"
gameforge.sample._130_classLine = "Line[ENTER]continued"
gameforge.sample._140_missing = "unused"
"""


class NpcInteractionsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.root = root
        self.source = root / "source"
        quest = self.source / TRANSLATE.parent / "quest/sample.quest"
        quest.parent.mkdir(parents=True)
        quest.write_text(QUEST)
        (self.source / TRANSLATE).write_text(TRANSLATIONS)
        self.catalog([self.spawn("sample-10001")])

    def spawn(self, name: str) -> str:
        return f"spawn.yongan.{name}"

    def catalog(self, placements: list[str], areas: list[str] | None = None) -> None:
        path = self.root / "client/assets/imported/npcs/catalog.v1.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema": "mt2spacetime.static-npcs",
                    "version": 3,
                    "maps": [
                        {
                            "id": MAP_ID,
                            "placements": [{"id": p} for p in placements],
                            "areas": [{"id": a} for a in areas or []],
                        }
                    ],
                }
            )
        )

    def profile(self, rows: list[dict]) -> Path:
        path = self.root / "profile.json"
        path.write_text(
            json.dumps(
                {
                    "schema": SCHEMA,
                    "version": VERSION,
                    "map_id": MAP_ID,
                    "source": {
                        "repository": "https://git.old-metin2.com/",
                        "revision": "0" * 40,
                        "quests": ["gamefiles/data/quest/sample.quest"],
                    },
                    "notes": [],
                    "npcs": rows,
                }
            )
        )
        return path

    def sourced(self, spawn_id: str, key: str, line: int = 3) -> dict:
        return {
            "spawn_id": spawn_id,
            "source": {
                "quest": "gamefiles/data/quest/sample.quest",
                "line": line,
                "head": "10001.chat.gameforge.sample._10_npcChat",
            },
            "text": key,
        }

    def compile(self, rows: list[dict]) -> tuple[dict, dict]:
        original = npc_dialogue.ROOT
        npc_dialogue.ROOT = self.root
        self.addCleanup(setattr, npc_dialogue, "ROOT", original)
        return compile_profile(self.profile(rows), self.source)

    def test_corpus_row_resolves_text_and_the_title_in_force(self):
        document, receipt = self.compile(
            [self.sourced(self.spawn("sample-10001"), "gameforge.sample._130_classLine")]
        )
        row = document["interactions"][0]
        self.assertEqual(row["body"], "Line\ncontinued")
        self.assertEqual(row["title"], "Weaponry training")
        self.assertEqual(document["map_id"], MAP_ID)
        self.assertEqual(receipt["titled"], 1)
        self.assertEqual(receipt["sources"][0]["title_key"], "gameforge.sample._120_classTitle")

    def test_authored_row_needs_no_corpus_entry(self):
        document, receipt = self.compile(
            [{"spawn_id": self.spawn("sample-10001"), "text": "Hand written[ENTER]line"}]
        )
        self.assertEqual(document["interactions"][0]["body"], "Hand written\nline")
        self.assertNotIn("title", document["interactions"][0])
        self.assertEqual((receipt["authored"], receipt["titled"]), (1, 0))

    def test_missing_translation_key_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "missing from the pinned translations"):
            self.compile([self.sourced(self.spawn("sample-10001"), "gameforge.sample._999_absent")])

    def test_key_not_used_by_the_referenced_handler_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "is not used by the referenced handler"):
            self.compile(
                [self.sourced(self.spawn("sample-10001"), "gameforge.sample._140_missing")]
            )

    def test_source_must_name_one_handler(self):
        rows = [self.sourced(self.spawn("sample-10001"), "gameforge.sample._130_classLine", 99)]
        with self.assertRaisesRegex(ValueError, "does not name one handler"):
            self.compile(rows)

    def test_duplicate_spawn_id_is_rejected(self):
        rows = [
            self.sourced(self.spawn("sample-10001"), "gameforge.sample._130_classLine"),
            self.sourced(self.spawn("sample-10001"), "gameforge.sample._130_classLine"),
        ]
        with self.assertRaisesRegex(ValueError, "invalid or duplicated"):
            self.compile(rows)

    def test_rows_and_placements_must_match_exactly(self):
        self.catalog([self.spawn("sample-10001"), self.spawn("sample-10002")])
        with self.assertRaisesRegex(ValueError, "Places or areas without dialogue"):
            self.compile(
                [self.sourced(self.spawn("sample-10001"), "gameforge.sample._130_classLine")]
            )
        self.catalog([self.spawn("sample-10001")])
        with self.assertRaisesRegex(ValueError, "have no placement or area"):
            self.compile(
                [
                    self.sourced(self.spawn("sample-10001"), "gameforge.sample._130_classLine"),
                    self.sourced(self.spawn("sample-10002"), "gameforge.sample._130_classLine"),
                ]
            )

    def test_sampled_area_needs_the_same_single_row(self):
        # Original wandering townsfolk carry no static coordinate, so the
        # catalog describes an area the server samples. One profile row covers
        # both the board text and the published ``npc_spawn`` id.
        self.catalog([self.spawn("sample-10001")], [self.spawn("sample-10002")])
        with self.assertRaisesRegex(ValueError, "Places or areas without dialogue"):
            self.compile(
                [self.sourced(self.spawn("sample-10001"), "gameforge.sample._130_classLine")]
            )
        document, receipt = self.compile(
            [
                self.sourced(self.spawn("sample-10001"), "gameforge.sample._130_classLine"),
                self.sourced(self.spawn("sample-10002"), "gameforge.sample._130_classLine"),
            ]
        )
        self.assertEqual(
            [row["spawn_id"] for row in document["interactions"]],
            [self.spawn("sample-10001"), self.spawn("sample-10002")],
        )
        self.assertEqual(receipt["rows"], 2)

    def test_an_area_id_may_not_repeat_a_placement_id(self):
        self.catalog([self.spawn("sample-10001")], [self.spawn("sample-10001")])
        with self.assertRaisesRegex(ValueError, "reuses a spawn id"):
            self.compile(
                [self.sourced(self.spawn("sample-10001"), "gameforge.sample._130_classLine")]
            )

    def test_title_follows_the_referenced_line(self):
        body = (
            "say_title(gameforge.sample._110_wrongBranch)\n"
            "say(gameforge.sample._130_classLine)\n"
            "say_title(gameforge.sample._120_classTitle)\n"
        )
        self.assertEqual(
            _preceding_title(body, "gameforge.sample._130_classLine"),
            "gameforge.sample._110_wrongBranch",
        )
        # The key that sets a title is not itself a preceding call.
        self.assertEqual(
            _preceding_title(body, "gameforge.sample._120_classTitle"),
            "gameforge.sample._110_wrongBranch",
        )

    def test_dynamic_title_falls_back_and_does_not_shadow_an_earlier_literal(self):
        dynamic = 'say_title(mob_name("alchemist"))\nsay(gameforge.sample._130_classLine)\n'
        self.assertIsNone(_preceding_title(dynamic, "gameforge.sample._130_classLine"))
        after = (
            'say_title(mob_name("alchemist"))\n'
            "say_title(gameforge.sample._120_classTitle)\n"
            "say(gameforge.sample._130_classLine)\n"
        )
        self.assertEqual(
            _preceding_title(after, "gameforge.sample._130_classLine"),
            "gameforge.sample._120_classTitle",
        )
        self.assertIsNone(
            _preceding_title(
                "say(gameforge.sample._130_classLine)\n", "gameforge.sample._130_classLine"
            )
        )

    def test_overlong_title_does_not_fit_the_board(self):
        path = self.source / TRANSLATE
        path.write_text(TRANSLATIONS + f'gameforge.sample._150_long = "{"x" * (MAX_TITLE + 1)}"\n')
        quest = self.source / TRANSLATE.parent / "quest/sample.quest"
        quest.write_text(
            QUEST.replace(
                "            say(gameforge.sample._130_classLine)",
                "            say_title(gameforge.sample._150_long)\n"
                "            say(gameforge.sample._130_classLine)",
            )
        )
        with self.assertRaisesRegex(ValueError, "does not fit the dialogue board"):
            self.compile(
                [self.sourced(self.spawn("sample-10001"), "gameforge.sample._130_classLine")]
            )

    def test_installed_profile_matches_the_pinned_corpus(self):
        if not SOURCE.is_dir():
            self.fail("pinned quest corpus is missing; fetch .cache/full-game-research first")
        document, receipt = compile_profile(PROFILE, SOURCE)
        installed = json.loads(INSTALLED.read_text())
        self.assertEqual(installed, document)
        self.assertEqual((receipt["rows"], receipt["authored"]), (47, 0))
        self.assertEqual(receipt["titled"], 41)
        # Titles are literal keys or nothing; a dynamic title must not be
        # attributed to an unrelated earlier key.
        self.assertEqual(
            sorted(row["spawn_id"] for row in installed["interactions"] if "title" not in row),
            [
                "spawn.yongan.alchemist-20001-0",
                "spawn.yongan.city-guard-20354",
                "spawn.yongan.girl-lost-elder-brother-20006-0",
                "spawn.yongan.moonstone-20357-0",
                "spawn.yongan.nnflower-20358-0",
                "spawn.yongan.samahi-20090-0",
            ],
        )


if __name__ == "__main__":
    unittest.main()
