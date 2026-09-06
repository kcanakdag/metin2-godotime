"""Original UI format and map orientation checks using tiny synthetic image inputs."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import import_metin_ui as ui


class UIAssets(unittest.TestCase):
    DESCRIPTOR = (
        'title subImage\nversion 1.0\nimage "Public.dds"\nleft 1\ntop 2\nright 3\nbottom 5\n'
    )

    def test_atlas_versions_and_case_normalization(self):
        atlas, crop = ui.sub_image(self.DESCRIPTOR, "D:/Ymir Work/UI/Public/Slot_Base.sub")
        self.assertEqual(atlas, "ymir work/ui/public.dds")
        self.assertEqual(crop, (1, 2, 3, 5))
        atlas, _ = ui.sub_image(
            self.DESCRIPTOR.replace("version 1.0", "version 2.0"),
            "D:/Ymir Work/UI/Public/Slot_Base.sub",
        )
        self.assertEqual(atlas, "ymir work/ui/public/public.dds")
        self.assertEqual(
            ui.output_path("D:/Ymir Work/UI/Public/Slot_Base.sub"), Path("public/slot_base.png")
        )

    def test_malformed_and_unsafe_descriptors_fail(self):
        for text in (
            self.DESCRIPTOR.replace("1.0", "3.0"),
            self.DESCRIPTOR.replace("left 1", "left -1"),
            self.DESCRIPTOR.replace("right 3", "right 1"),
            self.DESCRIPTOR.replace("Public.dds", "../outside.dds"),
            self.DESCRIPTOR.replace("Public.dds", "/outside.dds"),
            self.DESCRIPTOR + "left 8\n",
            self.DESCRIPTOR.replace("bottom 5", "bottom nan"),
            self.DESCRIPTOR.replace("title subImage", "title other"),
        ):
            with self.subTest(text=text), self.assertRaises(ValueError):
                ui.sub_image(text, "ymir work/ui/public/slot.sub")

    def test_exclusive_crop_preserves_alpha_and_rejects_padding(self):
        original = Image.new("RGBA", (4, 5), (20, 40, 60, 0))
        original.putpixel((2, 3), (10, 30, 50, 77))
        cropped = ui.crop_image(original, (1, 2, 3, 4))
        self.assertEqual(cropped.size, (2, 2))
        self.assertEqual(cropped.getpixel((1, 1)), (10, 30, 50, 77))
        self.assertEqual(cropped.getpixel((0, 0)), (20, 40, 60, 0))
        for crop in ((-1, 0, 2, 3), (0, 0, 5, 5), (0, 0, 4, 6)):
            with self.subTest(crop=crop), self.assertRaises(ValueError):
                ui.crop_image(original, crop)

    def test_stitched_map_axes_and_pixel_identity(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            class ArchiveFixture:
                def fetch_many(self, paths):
                    for path in paths:
                        self.get(path)

                def get(self, path):
                    grid = path.split("/")[-2]
                    x, z = int(grid[:3]), int(grid[3:])
                    destination = root / f"{grid}.png"
                    if not destination.exists():
                        Image.new("RGBA", (2, 3), (x, z, 123, 255)).save(destination)
                    return destination

            with patch.object(ui, "OUTPUT", root / "output"):
                result = ui.stitch_yongan(ArchiveFixture())
            self.assertEqual([result["width"], result["height"]], [8, 15])
            self.assertEqual(result["bounds_m"], [1024, 1280])
            with Image.open(root / "output/maps/metin2_map_a1.png") as stitched:
                for x in range(4):
                    for z in range(5):
                        self.assertEqual(stitched.getpixel((2 * x, 3 * z)), (x, z, 123, 255))


if __name__ == "__main__":
    unittest.main()
