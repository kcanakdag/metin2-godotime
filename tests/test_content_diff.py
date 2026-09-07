from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import content_diff


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def seal(server, client):
    server.pop("gameplay_definition_hash", None)
    server["gameplay_definition_hash"] = digest(server)
    client.update({key: server[key] for key in content_diff.SERVER_METADATA})
    client["presentation_output_hash"] = digest(client["artifacts"])
    return server, client


def fixture():
    server = {
        "schema": content_diff.SERVER_SCHEMA,
        "schema_version": 6,
        "profile_id": "fixture",
        "content_hash": "a" * 64,
        "actions": [{"id": "attack", "hit_start_us": 200000}],
        "base_combo_prefix": ["first", "second"],
    }
    client = {
        "schema": content_diff.CLIENT_SCHEMA,
        "schema_version": 1,
        "profile_id": "fixture",
        "actors": [{"id": "warrior", "attachment_transform": {"angle": 90}}],
        "artifacts": [{"id": "warrior", "sha256": "b" * 64}],
    }
    return seal(server, client)


class ContentDiffTests(unittest.TestCase):
    def test_identical_pair_needs_no_content_regression(self):
        before = fixture()
        result = content_diff.compare_pairs(*before, *copy.deepcopy(before))
        self.assertEqual(result["category"], "unchanged")
        self.assertEqual(result["recommended_checks"], [])

    def test_visual_asset_change_does_not_require_gameplay_regression(self):
        before = fixture()
        server, client = copy.deepcopy(before)
        server["content_hash"] = "c" * 64
        client["artifacts"][0]["sha256"] = "d" * 64
        client["actors"][0]["attachment_transform"]["angle"] = 91
        after = seal(server, client)
        result = content_diff.compare_pairs(*before, *after)
        self.assertEqual(result["category"], "presentation")
        self.assertEqual(result["gameplay_changes"], [])
        self.assertTrue(any("rendered Godot" in check for check in result["recommended_checks"]))
        self.assertFalse(any("two-client" in check for check in result["recommended_checks"]))

    def test_attack_timing_and_combo_order_require_gameplay_checks(self):
        before = fixture()
        for kind in ("timing", "order", "number_type"):
            with self.subTest(kind=kind):
                server, client = copy.deepcopy(before)
                if kind == "order":
                    server["base_combo_prefix"].reverse()
                else:
                    server["actions"][0]["hit_start_us"] = 200001 if kind == "timing" else 200000.0
                result = content_diff.compare_pairs(*before, *seal(server, client))
                self.assertEqual(result["category"], "gameplay")
                self.assertTrue(
                    any("two-client" in check for check in result["recommended_checks"])
                )

    def test_source_only_change_is_visible_without_fabricated_gameplay_diff(self):
        before = fixture()
        server, client = copy.deepcopy(before)
        server["content_hash"] = "c" * 64
        result = content_diff.compare_pairs(*before, *seal(server, client))
        self.assertEqual(result["category"], "provenance")
        self.assertEqual(len(result["recommended_checks"]), 1)

    def test_stale_or_mixed_hashes_and_unknown_schemas_fail_closed(self):
        before = fixture()
        for kind in ("payload", "artifact", "mixed", "schema", "boolean_schema"):
            with self.subTest(kind=kind):
                server, client = copy.deepcopy(before)
                if kind == "payload":
                    server["actions"][0]["hit_start_us"] += 1
                elif kind == "artifact":
                    client["artifacts"][0]["sha256"] = "c" * 64
                elif kind == "mixed":
                    client["gameplay_definition_hash"] = "c" * 64
                elif kind == "schema":
                    server["schema_version"] = 99
                else:
                    client["schema_version"] = True
                with self.assertRaises(ValueError):
                    content_diff.compare_pairs(*before, server, client)

    def test_ambiguous_or_non_finite_json_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "invalid.json"
            for text in ('{"value": 1, "value": 2}', '{"value": NaN}', '{"value": 1e999}', "[]"):
                path.write_text(text)
                with self.assertRaises(ValueError):
                    content_diff._load(path)


if __name__ == "__main__":
    unittest.main()
