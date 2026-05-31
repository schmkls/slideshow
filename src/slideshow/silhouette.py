"""Step: paint a white halo ring around each subject.

In: a folder of photos and their masks. Out: a folder of ``NNNNN.png`` frames —
each the original photo (background kept) with a white halo ring drawn around
the subject. The subject doesn't move, so each photo's mask is carried through
unchanged (renumbered to match its output). Photos with an empty mask are
skipped. Output size and background match the input; positioning/scaling is the
``center`` step's job.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from .images import (
    discover,
    load_mask,
    load_upright,
    require_masks,
    save_mask,
    save_png,
)


def add_silhouette(
    img: Image.Image,
    mask: np.ndarray,
    *,
    halo_px: int,
    alpha_thresh: int,
) -> Image.Image | None:
    """Paint a white halo ring around the subject on the original photo.

    Returns the photo with the ring drawn on (background kept), or ``None`` if
    the mask is empty (no subject).
    """
    if not (mask > alpha_thresh).any():
        return None

    base = np.array(img.convert("RGB"))
    if halo_px > 0:
        dilated = np.array(
            Image.fromarray(mask).filter(ImageFilter.MaxFilter(halo_px * 2 + 1))
        )
        ring = (dilated > alpha_thresh) & (mask <= alpha_thresh)
        base[ring] = (255, 255, 255)

    return Image.fromarray(base, "RGB")


def run(
    input_dir: Path,
    output_dir: Path,
    *,
    halo_px: int = 16,
    alpha_thresh: int = 16,
) -> int:
    """Process a directory. Returns the number of frames written."""
    photos = discover(input_dir)
    if not photos:
        return 0
    require_masks(photos)

    output_dir.mkdir(parents=True, exist_ok=True)
    kept = 0
    for src in photos:
        mask = load_mask(src)
        try:
            result = add_silhouette(
                load_upright(src), mask, halo_px=halo_px, alpha_thresh=alpha_thresh,
            )
        except Exception as e:  # noqa: BLE001 - one bad image shouldn't abort the batch
            print(f"{src.name}: error ({e}), skipped", file=sys.stderr)
            continue
        if result is None:
            print(f"{src.name}: empty mask, skipped", file=sys.stderr)
            continue
        dst = output_dir / f"{kept:05d}.png"
        save_png(result, dst)
        save_mask(mask, dst)  # carry the mask through, renumbered to the output
        print(f"[{kept + 1}/{len(photos)}] {src.name}", flush=True)
        kept += 1

    if kept == 0:
        print("no frames produced", file=sys.stderr)
    return kept
