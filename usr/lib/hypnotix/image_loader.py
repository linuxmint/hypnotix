"""Decode provider artwork outside the GTK process.

Native image decoders can abort, which cannot be caught as a Python exception.
Only bounded, decoded RGB pixels cross back into the application process.
"""
import functools
import os
from pathlib import Path
import struct
import subprocess
import sys

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_DIMENSION = 1024
HEADER = struct.Struct("!III")


def load_pixels(path, width, height):
    if not path or not (0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION):
        return None
    try:
        path = os.path.abspath(path)
        stat = os.stat(path)
        if stat.st_size > MAX_FILE_BYTES:
            return None
        return _load_pixels(path, stat.st_mtime_ns, stat.st_size, width, height)
    except OSError:
        return None


@functools.lru_cache(maxsize=128)
def _load_pixels(path, mtime, size, width, height):
    try:
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), path, str(width), str(height)],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=4,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode or len(result.stdout) < HEADER.size:
        return None
    actual_width, actual_height, channels = HEADER.unpack_from(result.stdout)
    pixels = result.stdout[HEADER.size:]
    if (not 0 < actual_width <= width or not 0 < actual_height <= height
            or channels not in (3, 4)
            or len(pixels) != actual_width * actual_height * channels):
        return None
    return actual_width, actual_height, channels, pixels


def _decode(path, width, height):
    import resource

    # Avoid generating large core dumps if a native decoder aborts.
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_AS, (512 * 1024 * 1024, 512 * 1024 * 1024))
    resource.setrlimit(resource.RLIMIT_CPU, (3, 3))
    if not (0 < width <= MAX_DIMENSION and 0 < height <= MAX_DIMENSION):
        raise ValueError("Invalid artwork dimensions")
    if os.stat(path).st_size > MAX_FILE_BYTES:
        raise ValueError("Artwork file is too large")

    import gi
    gi.require_version("GdkPixbuf", "2.0")
    from gi.repository import GdkPixbuf

    pixbuf = GdkPixbuf.Pixbuf.new_from_file_at_size(path, width, height)
    actual_width, actual_height = pixbuf.get_width(), pixbuf.get_height()
    channels = pixbuf.get_n_channels()
    if (not 0 < actual_width <= width or not 0 < actual_height <= height
            or channels not in (3, 4) or pixbuf.get_bits_per_sample() != 8):
        raise ValueError("Invalid decoded artwork")
    stride = pixbuf.get_rowstride()
    row_bytes = actual_width * channels
    raw = pixbuf.get_pixels()
    pixels = b"".join(raw[y * stride:y * stride + row_bytes]
                      for y in range(actual_height))
    sys.stdout.buffer.write(HEADER.pack(actual_width, actual_height, channels) + pixels)


if __name__ == "__main__":
    _decode(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
