"""Image discovery and IO shared by every step.

Steps chain through directories: each step reads a sorted folder of images
and writes ``NNNNN.png`` in the same order, so any step can feed any other.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageOps

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()  # adds .heic/.heif support to PIL.Image.open
except ImportError:
    pass


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".bmp"}


def discover(input_dir: Path) -> list[Path]:
    """Sorted list of supported images in ``input_dir`` (name order == slide order)."""
    photos = sorted(
        p for p in input_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS
    )
    if not photos:
        print(f"no images found in {input_dir}", file=sys.stderr)
    return photos


def load_upright(path: Path) -> Image.Image:
    """Open an image, apply its EXIF orientation, keep its mode (RGB or RGBA)."""
    img = ImageOps.exif_transpose(Image.open(path))
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA" if "A" in img.getbands() else "RGB")
    return img


def save_png(img: Image.Image, path: Path) -> None:
    """Write a lossless PNG, preserving alpha."""
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "PNG")
