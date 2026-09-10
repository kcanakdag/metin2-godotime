import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from test_browser_self_buffs import database_scope_error as browser_scope_error
from test_native_browser_self_buffs import database_scope_error as native_scope_error


class SelfBuffDatabaseScopeTest(unittest.TestCase):
    def test_disposable_development_databases_are_accepted(self):
        for guard in (browser_scope_error, native_scope_error):
            self.assertIsNone(guard("mt2-p2-self-buffs-r1-20260910"))
            self.assertIsNone(guard("mt2-p2-self-buffs-r1-20260910", allowed_public_qa="other"))

    def test_only_the_explicitly_named_public_qa_database_is_accepted(self):
        release = "mt2-public-self-buffs-v31-20260910"
        for guard in (browser_scope_error, native_scope_error):
            self.assertEqual(
                guard(release),
                "Use a disposable mt2-p2- database; this replay spends skill points",
            )
            self.assertIsNone(guard(release, allowed_public_qa=release))

    def test_opt_in_still_rejects_retained_and_other_public_databases(self):
        for guard in (browser_scope_error, native_scope_error):
            for name in (
                "mt2-accounts-v3",
                "mt2-public-skills-v26-20260908",
                "mt2-public-self-buffs-v31-20260910-secondary",
                "mt2-public",
                "self-buffs",
            ):
                with self.subTest(database=name):
                    self.assertIsNotNone(
                        guard(name, allowed_public_qa="mt2-public-self-buffs-v31-20260910")
                    )


if __name__ == "__main__":
    unittest.main()
