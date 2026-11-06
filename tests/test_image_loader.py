import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "usr/lib/hypnotix"))
import image_loader


def png_chunk(kind, data):
    return (struct.pack("!I", len(data)) + kind + data
            + struct.pack("!I", zlib.crc32(kind + data)))


class ImageLoaderTests(unittest.TestCase):
    def setUp(self):
        image_loader._load_pixels.cache_clear()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "artwork.png"

    def write_png(self, alpha=False):
        channels = 4 if alpha else 3
        pixel = bytes([40, 80, 120, 160][:channels])
        self.path.write_bytes(
            b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", struct.pack("!IIBBBBB", 2, 1, 8, 6 if alpha else 2, 0, 0, 0))
            + png_chunk(b"IDAT", zlib.compress(b"\0" + pixel * 2))
            + png_chunk(b"IEND", b""))

    def test_rgb_and_rgba_decode_and_scale(self):
        for alpha in (False, True):
            with self.subTest(alpha=alpha):
                self.write_png(alpha)
                result = image_loader.load_pixels(self.path, 1, 1)
                self.assertIsNotNone(result)
                width, height, channels, pixels = result
                self.assertEqual((width, height), (1, 1))
                self.assertEqual(channels, 4 if alpha else 3)
                self.assertEqual(len(pixels), channels)

    def test_corrupt_and_missing_images_fall_back(self):
        self.assertIsNone(image_loader.load_pixels(self.path, 64, 32))
        self.path.write_bytes(b"invalid image")
        self.assertIsNone(image_loader.load_pixels(self.path, 64, 32))

    def test_native_abort_does_not_abort_parent(self):
        self.path.write_bytes(b"image")
        run = subprocess.run

        def abort_worker(*args, **kwargs):
            return run([sys.executable, "-c",
                        "import resource, os; resource.setrlimit(resource.RLIMIT_CORE, (0, 0)); os.abort()"],
                       **kwargs)

        with patch.object(image_loader.subprocess, "run", side_effect=abort_worker) as worker:
            self.assertIsNone(image_loader.load_pixels(self.path, 64, 32))
            self.assertIsNone(image_loader.load_pixels(self.path, 64, 32))
            self.assertEqual(worker.call_count, 1)

    def test_timeout_falls_back(self):
        self.path.write_bytes(b"image")
        with patch.object(image_loader.subprocess, "run",
                          side_effect=subprocess.TimeoutExpired("decoder", 4)):
            self.assertIsNone(image_loader.load_pixels(self.path, 64, 32))

    def test_invalid_pixel_payload_is_rejected(self):
        self.path.write_bytes(b"image")
        for payload in (b"", image_loader.HEADER.pack(5000, 1, 4),
                        image_loader.HEADER.pack(1, 1, 4) + b"x"):
            image_loader._load_pixels.cache_clear()
            with patch.object(image_loader.subprocess, "run",
                              return_value=subprocess.CompletedProcess([], 0, payload)):
                self.assertIsNone(image_loader.load_pixels(self.path, 64, 32))

    def test_oversized_input_is_rejected_before_decode(self):
        with self.path.open("wb") as file:
            file.truncate(image_loader.MAX_FILE_BYTES + 1)
        with patch.object(image_loader.subprocess, "run") as worker:
            self.assertIsNone(image_loader.load_pixels(self.path, 64, 32))
            worker.assert_not_called()

    def test_cache_invalidates_when_image_changes(self):
        self.path.write_bytes(b"image")
        payload = image_loader.HEADER.pack(1, 1, 3) + b"rgb"
        with patch.object(image_loader.subprocess, "run",
                          return_value=subprocess.CompletedProcess([], 0, payload)) as worker:
            self.assertIsNotNone(image_loader.load_pixels(self.path, 64, 32))
            self.assertIsNotNone(image_loader.load_pixels(self.path, 64, 32))
            self.path.write_bytes(b"replacement image")
            self.assertIsNotNone(image_loader.load_pixels(self.path, 64, 32))
            self.assertEqual(worker.call_count, 2)


if __name__ == "__main__":
    unittest.main()
