from __future__ import annotations

import base64
import copy
import hashlib
import importlib.util
import io
import json
import math
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location(
    "physical_content_compile", TOOLS / "content_compile.py"
)
assert spec and spec.loader
compiler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compiler)

PROFILE_PATH = ROOT / "content/profiles/p0-warrior-dog.json"
NORMALIZED_PATH = ROOT / ".local/content/p0-warrior-dog/normalized-manifest.v1.json"
SERVER_PATH = ROOT / "server/content/p0-warrior-dog/actions.v1.json"
CLIENT_PATH = ROOT / "client/assets/imported/content/p0-warrior-dog/manifest.v1.json"


def rehash(payload: dict) -> dict:
    payload = copy.deepcopy(payload)
    payload.pop("gameplay_definition_hash", None)
    payload["gameplay_definition_hash"] = compiler.digest(payload)
    return payload


class PhysicalContentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.profile = compiler.load_profile(PROFILE_PATH)
        cls.normalized = json.loads(NORMALIZED_PATH.read_text())
        cls.server = json.loads(SERVER_PATH.read_text())
        cls.client = json.loads(CLIENT_PATH.read_text())

    def test_payload_is_deterministic_and_source_derived(self) -> None:
        first = compiler.make_server_payload(self.profile, self.normalized)
        second = compiler.make_server_payload(self.profile, self.normalized)
        self.assertEqual(first, second)
        self.assertEqual(first["gameplay_definition_hash"], self.server["gameplay_definition_hash"])
        weapon = first["physical_damage"]["weapons"][0]
        self.assertEqual(
            (weapon["power_min"], weapon["power_max"], weapon["refine_attack"]), (13, 15, 0)
        )
        mob = first["physical_damage"]["mobs"][0]
        self.assertEqual(
            (mob["level"], mob["strength"], mob["vitality"], mob["dexterity"]),
            (1, 3, 5, 6),
        )
        self.assertEqual((mob["proto_defense"], mob["power_min"], mob["power_max"]), (4, 20, 24))
        self.assertEqual(mob["damage_multiplier"], 1.0)
        self.assertEqual(mob["sword_resistance_percent"], 0)

    def test_client_exposes_only_three_public_physical_values(self) -> None:
        item = self.client["items"][0]
        self.assertEqual(
            item["physical"],
            {"power_min": 13, "power_max": 15, "refine_attack": 0},
        )
        self.assertNotIn("policy", item["physical"])
        self.assertNotIn("attack_bonus", item)

    def test_selected_zero_policy_rejects_nonzero_missing_and_unknown(self) -> None:
        for mutation in ("nonzero", "missing", "unknown"):
            with self.subTest(mutation=mutation):
                payload = copy.deepcopy(self.server)
                policy = payload["physical_damage"]["policy"]
                if mutation == "nonzero":
                    policy["critical_percent"] = 1
                elif mutation == "missing":
                    del policy["reflect_percent"]
                else:
                    policy["unsupported_bonus"] = 0
                with self.assertRaisesRegex(ValueError, "physical policy"):
                    compiler.validate_server_payload(rehash(payload), "p0-warrior-dog")

    def test_wrong_physical_columns_and_inverted_range_are_rejected(self) -> None:
        payload = copy.deepcopy(self.server)
        weapon = payload["physical_damage"]["weapons"][0]
        weapon["power_min"], weapon["power_max"] = 15, 19
        with self.assertRaisesRegex(ValueError, "Sword"):
            compiler.validate_server_payload(rehash(payload), "p0-warrior-dog")
        payload = copy.deepcopy(self.server)
        payload["physical_damage"]["mobs"][0]["power_min"] = 25
        with self.assertRaisesRegex(ValueError, "Wild Dog"):
            compiler.validate_server_payload(rehash(payload), "p0-warrior-dog")

    def test_legacy_fixed_damage_inputs_are_rejected(self) -> None:
        raw = json.loads(PROFILE_PATH.read_text())
        cases = (
            ("player", "base_damage", 25),
            ("item", "attack_bonus", 10),
            ("mob", "damage_min", 20),
            ("mob", "damage_max", 20),
        )
        for section, field, value in cases:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as temporary:
                mutated = copy.deepcopy(raw)
                mutated["trusted_gameplay"][section][field] = value
                path = Path(temporary) / "profile.json"
                path.write_text(json.dumps(mutated))
                with self.assertRaisesRegex(ValueError, "Legacy fixed damage inputs"):
                    compiler.load_profile(path)

    def test_source_pin_and_duplicate_selected_row_are_rejected(self) -> None:
        mutated = copy.deepcopy(self.profile)
        battle = next(
            row
            for row in mutated["source"]["server_reference"]["files"]
            if row["path"] == "src/game/src/battle.cpp"
        )
        battle["sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "source identity changed"):
            compiler._selected_physical_definitions(mutated)

        original = compiler._server_reference_text

        def duplicate_item(profile: dict, relative: str) -> str:
            text = original(profile, relative)
            if relative == "gamefiles/conf/item_proto.txt":
                lines = text.splitlines()
                selected = next(line for line in lines[1:] if line.split("\t", 1)[0] == "10")
                return text.rstrip("\n") + "\n" + selected
            return text

        with mock.patch.object(compiler, "_server_reference_text", side_effect=duplicate_item):
            with self.assertRaisesRegex(ValueError, "exactly one Sword"):
                compiler._selected_physical_definitions(self.profile)

    def test_server_payload_has_no_legacy_formula_inputs(self) -> None:
        player = next(row for row in self.server["actors"] if row["id"] == compiler.PLAYER_ACTOR_ID)
        mob = next(row for row in self.server["actors"] if row["id"] == compiler.MOB_ACTOR_ID)
        item = self.server["items"][0]
        self.assertNotIn("base_damage", player)
        self.assertNotIn("damage_min", mob)
        self.assertNotIn("damage_max", mob)
        self.assertNotIn("attack_bonus", item)

    def test_numeric_boundaries_reject_without_truncation_or_overflow(self) -> None:
        fields = (
            ("policy", None, "final_multiplier"),
            ("policy", None, "critical_percent"),
            ("weapons", 0, "power_min"),
            ("mobs", 0, "damage_multiplier"),
            ("mobs", 0, "strength"),
        )
        for section, index, field in fields:
            for value in (True, None, "1", -1, 0.5, 2**80, 1e300, math.nan, math.inf, -math.inf):
                with self.subTest(section=section, field=field, value=value):
                    payload = copy.deepcopy(self.server)
                    row = payload["physical_damage"][section]
                    if index is not None:
                        row = row[index]
                    row[field] = value
                    with self.assertRaises(ValueError):
                        compiler._validate_physical_damage(payload)

    def test_multiplier_does_not_accept_values_that_merely_round_to_one(self) -> None:
        payload = copy.deepcopy(self.server)
        payload["physical_damage"]["policy"]["final_multiplier"] = 1.0 + 1e-10
        with self.assertRaisesRegex(ValueError, "final_multiplier"):
            compiler._validate_physical_damage(payload)

    def test_source_row_requires_an_integer_and_exact_fields(self) -> None:
        for field, value in (("row_number", 4.0), ("extra", "unsupported")):
            with self.subTest(field=field):
                payload = copy.deepcopy(self.server)
                payload["physical_damage"]["weapons"][0]["source"][field] = value
                with self.assertRaises(ValueError):
                    compiler._validate_physical_damage(payload)


class PinnedReferenceFetchTests(unittest.TestCase):
    def test_fresh_client_reference_is_verified_cached_and_available_offline(self) -> None:
        content = b"reference fixture\n"
        git_sha = hashlib.sha1(b"blob " + str(len(content)).encode() + b"\0" + content).hexdigest()
        source = {
            "revision": "a" * 40,
            "files": [
                {
                    "path": "src/display.cpp",
                    "git_sha": git_sha,
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            ],
        }
        entry = {"sha": git_sha, "content": base64.b64encode(content).decode()}
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(compiler, "ROOT", Path(temporary)),
        ):
            with self.assertRaisesRegex(FileNotFoundError, "client/src/display.cpp"):
                compiler.fetch_code_references(source, "client", offline=True)
            with mock.patch.object(
                compiler.urllib.request,
                "urlopen",
                return_value=io.BytesIO(json.dumps(entry).encode()),
            ) as fetch:
                records = compiler.fetch_code_references(source, "client", offline=False)
            self.assertIn(
                "/metin2/client/contents/src/display.cpp?ref=", fetch.call_args.args[0].full_url
            )
            self.assertEqual(records[0]["role"], "client-reference")
            self.assertEqual(
                compiler.fetch_code_references(source, "client", offline=True), records
            )

    def test_bad_reference_bytes_do_not_poison_cache(self) -> None:
        source = {
            "revision": "a" * 40,
            "files": [{"path": "src/display.cpp", "git_sha": "b" * 40, "sha256": "c" * 64}],
        }
        entry = {"sha": "b" * 40, "content": base64.b64encode(b"wrong bytes").decode()}
        with (
            tempfile.TemporaryDirectory() as temporary,
            mock.patch.object(compiler, "ROOT", Path(temporary)),
        ):
            with mock.patch.object(
                compiler.urllib.request,
                "urlopen",
                return_value=io.BytesIO(json.dumps(entry).encode()),
            ):
                with self.assertRaisesRegex(ValueError, "hash mismatch"):
                    compiler.fetch_code_references(source, "client", offline=False)
            self.assertFalse((Path(temporary) / "assets").exists())


if __name__ == "__main__":
    unittest.main()
