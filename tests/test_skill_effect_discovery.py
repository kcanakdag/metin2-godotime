import hashlib
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from discover_skill_effects import discover, extract

MSA = b"""
ScriptType MotionData
MotionFileName "D:/Ymir Work/pc/warrior/skill/test.gr2"
MotionDuration 1.5
Group MotionEventData
{
 MotionEventDataCount 2
 Group Event00
 {
  MotionEventType 1
  StartingTime 0.25
  AttachingEnable 0
  AttachingBoneName "Bip01 Head"
  EffectFileName "D:/Ymir Work/pc/warrior/effect/test.mse"
  EffectPosition 100 200 300
 }
 Group Event01
 {
  MotionEventType 9
  StartingTime 0.5
 }
}
"""


class SkillEffectDiscoveryTests(unittest.TestCase):
    def test_real_parser_keeps_effect_and_other_metadata(self):
        result = extract(MSA)
        self.assertEqual(result["source_sha256"], hashlib.sha256(MSA).hexdigest())
        self.assertEqual(result["effects"][0]["position_m"], [1, 3, -2])
        self.assertEqual(result["remaining_unsupported"][0]["event_type"], 9)
        self.assertEqual(result["rejected_effects"], [])

    def test_unsupported_effect_is_retained_with_reason(self):
        result = extract(MSA.replace(b"AttachingEnable 0", b"AttachingEnable 7"))
        self.assertEqual(result["effects"], [])
        self.assertEqual(len(result["rejected_effects"]), 1)
        self.assertIn("boolean", result["rejected_effects"][0]["reason"])
        self.assertEqual(result["rejected_effects"][0]["event"]["event_name"], "Event00")
        self.assertEqual(len(result["remaining_unsupported"]), 1)

    def test_unpinned_inputs_reject_before_archive_access(self):
        with self.assertRaisesRegex(ValueError, "pinned"):
            discover({}, {}, None)
