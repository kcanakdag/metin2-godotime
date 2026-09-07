from __future__ import annotations

import copy
import unittest

from tools.audit_items import reconcile


def fixture():
    definitions = {
        "item_catalog": {
            "items": [{"vnum": 27001, "stack_limit": 200, "height": 1, "kind": "recovery"}]
        }
    }
    event = {
        "id": 1,
        "item_id": 1,
        "drop_id": 0,
        "owner": "character",
        "account": "account",
        "vnum": 27001,
        "previous_count": 0,
        "count": 5,
        "revision": 1,
        "cause": "starter",
    }
    ground = {
        **event,
        "id": 2,
        "item_id": 0,
        "drop_id": 1,
        "count": 1,
        "revision": 0,
        "cause": "monster",
        "account": "zero",
    }
    audit = [
        event,
        ground,
        {
            **event,
            "id": 3,
            "drop_id": 1,
            "previous_count": 5,
            "count": 6,
            "revision": 2,
            "cause": "pickup",
        },
        {**ground, "id": 4, "previous_count": 1, "count": 0, "cause": "pickup"},
        {**event, "id": 5, "previous_count": 6, "count": 5, "revision": 4, "cause": "consume"},
    ]
    item = {
        "id": 1,
        "owner": "character",
        "account": "account",
        "vnum": 27001,
        "count": 5,
        "revision": 5,
        "cell": 0,
        "equipped": False,
    }
    return {"inventory": [item], "drops": [], "audit": audit}, definitions


class ItemAuditTests(unittest.TestCase):
    def test_reconciles_mint_merge_consume_and_non_quantity_revision_changes(self):
        snapshot, definitions = fixture()
        result = reconcile(snapshot, definitions)
        self.assertTrue(result["passed"])
        self.assertEqual(result["minted"], {27001: 6})
        self.assertEqual(result["held"], {27001: 5})

    def test_detects_duplication_lost_stock_replay_and_identity_tampering(self):
        original, definitions = fixture()
        cases = []
        for field, value in [
            ("count", 6),
            ("account", "thief"),
            ("owner", "thief"),
            ("revision", 1),
            ("cell", 255),
        ]:
            changed = copy.deepcopy(original)
            changed["inventory"][0][field] = value
            cases.append(changed)
        changed = copy.deepcopy(original)
        changed["inventory"] *= 2
        cases.append(changed)
        changed = copy.deepcopy(original)
        changed["audit"].append(
            {**changed["audit"][2], "id": 6, "previous_count": 5, "count": 6, "revision": 6}
        )
        cases.append(changed)
        changed = copy.deepcopy(original)
        changed["audit"].pop(3)
        cases.append(changed)
        changed = copy.deepcopy(original)
        changed["inventory"] = []
        cases.append(changed)
        for index, snapshot in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(ValueError):
                reconcile(snapshot, definitions)

    def test_rejects_resurrecting_an_exhausted_id(self):
        snapshot, definitions = fixture()
        mint = {**snapshot["audit"][0], "count": 1}
        snapshot["audit"] = [
            mint,
            {**mint, "id": 2, "previous_count": 1, "count": 0, "revision": 2, "cause": "consume"},
        ]
        snapshot["inventory"] = []
        self.assertTrue(reconcile(snapshot, definitions)["passed"])
        snapshot["audit"].append({**mint, "id": 3, "revision": 3})
        with self.assertRaisesRegex(ValueError, "reused ID"):
            reconcile(snapshot, definitions)
