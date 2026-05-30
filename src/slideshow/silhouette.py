"""Step: paint a white halo ring around each subject.

In: a folder of photos. Out: a folder of ``NNNNN.png`` frames — each the
original photo (background kept) with a white halo ring drawn around the
subject. Images with no detectable subject are skipped. Output size and
background match the input; positioning/scaling is the ``center`` step's job.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

from .images import discover, load_upright, save_png
from .segmentation import Segmenter


def add_silhouette(
    img: Image.Image,
    segmenter: Segmenter,
    *,
    halo_px: int,
    alpha_thresh: int,
) -> Image.Image | None:
    """Paint a white halo ring around the subject on the original photo.

    Returns the photo with the ring drawn on (background kept), or
    ``None`` if no subject is detected.
    """
    alpha = np.array(segmenter.cutout(img).split()[-1])
    if not (alpha > alpha_thresh).any():
        return None

    base = np.array(img.convert("RGB"))
    if halo_px > 0:
        mask = Image.fromarray(alpha)
        dilated = np.array(mask.filter(ImageFilter.MaxFilter(halo_px * 2 + 1)))
        ring = (dilated > alpha_thresh) & (alpha <= alpha_thresh)
        base[ring] = (255, 255, 255)

    return Image.fromarray(base, "RGB")


def run(
    input_dir: Path,
    output_dir: Path,
    *,
    halo_px: int = 16,
    alpha_thresh: int = 16,
    model: str = "u2net",
) -> int:
    """Process a directory. Returns the number of frames written."""
    photos = discover(input_dir)
    if not photos:
        return 0

    segmenter = Segmenter(model)
    output_dir.mkdir(parents=True, exist_ok=True)
    kept = 0
    for src in photos:
        try:
            result = add_silhouette(
                load_upright(src),
                segmenter,
                halo_px=halo_px,
                alpha_thresh=alpha_thresh,
            )
        except Exception as e:  # noqa: BLE001 - one bad image shouldn't abort the batch
            print(f"{src.name}: error ({e}), skipped", file=sys.stderr)
            continue
        if result is None:
            print(f"{src.name}: no subject detected, skipped", file=sys.stderr)
            continue
        save_png(result, output_dir / f"{kept:05d}.png")
        print(f"[{kept + 1}/{len(photos)}] {src.name}", flush=True)
        kept += 1

    if kept == 0:
        print("no frames produced", file=sys.stderr)
    return kept
