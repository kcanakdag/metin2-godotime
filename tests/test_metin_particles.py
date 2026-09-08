import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from metin_particles import parse_particle_mse, sample_curve, texture_path

PATH = "ymir work/effect/test/bolt.mse"


def fixture():
    emitter = """MaxEmissionCount 30
CycleLength 0.1
CycleLoopEnable 1
LoopCount 10
EmitterShape 0
EmitterAdvancedType 0
EmitterEmitFromEdgeFlag 0
EmittingDirection 0 0 0
"""
    for name in (
        "EmittingSize",
        "EmittingAngularVelocity",
        "EmittingDirectionX",
        "EmittingDirectionY",
        "EmittingDirectionZ",
        "EmittingVelocity",
        "EmissionCountPerSecond",
        "LifeTime",
        "SizeX",
        "SizeY",
    ):
        emitter += f"List TimeEvent{name}\n{{\n0 1\n}}\n"
    particle = """SrcBlendType 5
DestBlendType 6
ColorOperationType 4
BillboardType 1
RotationType 4
RotationSpeed 32
RotationRandomStartingBegin 0
RotationRandomStartingEnd 40
AttachEnable 0
StretchEnable 1
TexAniType 4
TexAniDelay 0.028
TexAniRandomStartFrameEnable 1
List TextureFiles
{
"frame 1.dds"
"frame 2.dds"
"frame 1.dds"
}
"""
    for name, rows in {
        "Gravity": "",
        "AirResistance": "",
        "ScaleX": "0 0.5\n1 1",
        "ScaleY": "0 0.5\n1 1",
        "ColorRed": "0 0\n1 1",
        "ColorGreen": "0 0.5",
        "ColorBlue": "0 1",
        "Alpha": "0 0\n0.5 1\n1 0",
        "Rotation": "0 0",
    }.items():
        particle += f"List TimeEvent{name}\n{{\n{rows}\n}}\n"
    return (
        "BoundingSphereRadius 50\nBoundingSpherePosition 0 0 0\nGroup Particle\n{\n"
        "StartTime 0\nList TimeEventPosition\n{\n0 MOVING_TYPE_DIRECT 0 -2 0\n}\n"
        f"Group EmitterProperty\n{{\n{emitter}}}\n"
        f"Group ParticleProperty\n{{\n{particle}}}\n}}\n"
    )


class ParticleTests(unittest.TestCase):
    def test_preserves_animation_order_attachment_and_packed_color_union(self):
        result = parse_particle_mse(fixture(), PATH)["systems"][0]
        self.assertEqual(result["position_keys_cm"], [[0, 0, -2, 0]])
        self.assertEqual(result["emitter"]["LoopCount"], 10)
        p = result["particle"]
        self.assertEqual(
            p["textures"],
            ["ymir work/effect/test/" + n for n in ("frame 1.dds", "frame 2.dds", "frame 1.dds")],
        )
        self.assertEqual(
            p["packed_color_keys"],
            [[0, 0, 128, 255, 0], [0.5, 128, 128, 255, 255], [1, 255, 128, 255, 0]],
        )
        self.assertEqual((p["AttachEnable"], p["StretchEnable"], p["TexAniType"]), (0, 1, 4))

    def test_curves_clamp_and_empty_defaults_to_zero(self):
        keys = [[0.25, 2], [0.75, 6]]
        self.assertEqual([sample_curve(keys, t) for t in (0, 0.25, 0.5, 0.75, 1)], [2, 2, 4, 6, 6])
        self.assertEqual(sample_curve([], 0.5), 0)
        with self.assertRaises(ValueError):
            sample_curve(keys, float("nan"))

    def test_malformed_or_unsupported_records_reject(self):
        for old, new in (
            ("MaxEmissionCount 30", "MaxEmissionCount 999999"),
            ("StartTime 0", "StartTime nan"),
            ("LoopCount 10", "LoopCount 1.5"),
            ("AttachEnable 0", "AttachEnable 2"),
            ("0 0.5\n1 1", "0 0.5\n0 1"),
            ("MOVING_TYPE_DIRECT", "MOVING_TYPE_BEZIER"),
            ("Group ParticleProperty", "Group UnknownProperty"),
            ("RotationSpeed 32", "RotationSpeed 32\nUnknownField 1"),
            ("List TimeEventRotation", "List MissingRotation"),
        ):
            with self.subTest(new=new), self.assertRaises(ValueError):
                parse_particle_mse(fixture().replace(old, new), PATH)

    def test_texture_paths_are_bounded_to_original_assets(self):
        self.assertEqual(
            texture_path(PATH, r"D:\Ymir Work\effect\test\a.dds"), "ymir work/effect/test/a.dds"
        )
        for path in ("../a.dds", "/a.dds", "C:/secrets/a.dds", "bad\x00.dds", "a.py"):
            with self.subTest(path=path), self.assertRaises(ValueError):
                texture_path(PATH, path)


if __name__ == "__main__":
    unittest.main()
