import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from test_probe_activation import collect_console


class ConsoleClassificationTests(unittest.TestCase):
    def test_godot_fallback_warning_is_retained_without_hiding_errors(self):
        errors, warnings = [], []
        messages = [
            "WARNING: invalid UID - using text path instead",
            "   at: open (core/io/resource_format_binary.cpp:1028)",
            "ERROR: Failed to load resource",
            " SCRIPT ERROR: Invalid call",
            "Uncaught RuntimeError: unreachable",
            "Unexpected WebGL failure",
        ]
        for text in messages:
            collect_console(SimpleNamespace(type="error", text=text), errors, warnings)
        self.assertEqual(warnings, messages[:2])
        self.assertEqual(errors, messages[2:])


if __name__ == "__main__":
    unittest.main()
