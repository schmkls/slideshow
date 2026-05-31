"""Image discovery and IO shared by every step.

Steps chain through directories: each step reads a sorted folder of images
and writes ``NNNNN.png`` in the same order, so any step can feed any other.

A photo carries its subject mask beside it as ``<stem>.mask.png`` — detected
once by the ``mask`` step and consumed (and co-transformed) by the rest.
``discover`` lists base photos and skips these sidecars.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps

try:
    from pillow_heif import register_heif_opener

    register_heif_opener()  # adds .heic/.heif support to PIL.Image.open
except ImportError:
    pass


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".bmp"}
MASK_SUFFIX = ".mask.png"  # a photo's subject mask rides beside it under this name


def discover(input_dir: Path) -> list[Path]:
    """Sorted list of supported images in ``input_dir`` (name order == slide order).

    Mask sidecars (``*.mask.png``) are skipped — they ride alongside photos but
    are not photos themselves.
    """
    photos = sorted(
        p for p in input_dir.iterdir()
        if p.suffix.lower() in IMAGE_EXTS and not is_mask(p)
    )
    if not photos:
        print(f"no images found in {input_dir}", file=sys.stderr)
    return photos


def mask_path(photo: Path) -> Path:
    """The mask sidecar beside ``photo`` (``IMG.jpg`` -> ``IMG.mask.png``)."""
    return photo.with_name(photo.stem + MASK_SUFFIX)


def is_mask(path: Path) -> bool:
    """True for a mask sidecar (``*.mask.png``), not a base photo."""
    return path.name.endswith(MASK_SUFFIX)


def save_mask(mask: np.ndarray, photo: Path) -> None:
    """Write ``photo``'s subject mask as a single-channel ``L`` PNG beside it."""
    path = mask_path(photo)
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(mask, "L").save(path, "PNG")


def load_mask(photo: Path) -> np.ndarray:
    """Read ``photo``'s subject mask as a uint8 array (high where the subject is)."""
    return np.array(Image.open(mask_path(photo)).convert("L"))


def require_masks(photos: list[Path]) -> None:
    """Abort the run if any photo is missing its mask sidecar.

    Detection happens only in the ``mask`` step; every other step reads what it
    wrote. A missing mask is a hard error, not a silent half-processed run.
    """
    for photo in photos:
        if not mask_path(photo).exists():
            sys.exit(f"no mask for {photo.name} — run 'slideshow mask' first")


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
