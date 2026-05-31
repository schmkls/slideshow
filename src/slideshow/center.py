"""Step: scale and center every subject on a uniform canvas.

In: a folder of images and their masks (raw photos, or the silhouette step's
output). Out: a folder of ``NNNNN.png`` frames, each the same size, with the
subject scaled to ``subject_frac`` of the width and centered on both axes.

The mask moves with the pixels: each photo's mask is resized and offset by the
*same* transform applied to its image (and cropped by the same shared
letterbox), then written beside the centered frame so it stays valid for later
steps.

Letterbox (the canvas area a frame's image doesn't cover) is filled with
the chosen background; afterwards the margin shared by *every* frame is
cropped off uniformly, so frames don't keep a border they all share.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

from .images import (
    discover,
    load_mask,
    load_upright,
    mask_path,
    require_masks,
    save_mask,
    save_png,
)
from .segmentation import alpha_bbox

PasteBox = tuple[int, int, int, int]  # (x, y, w, h) of the image on the canvas


def scale_and_center(
    img: Image.Image,
    mask: np.ndarray,
    *,
    out_w: int,
    out_h: int,
    subject_frac: float,
    alpha_thresh: int,
    background: str,
) -> tuple[Image.Image, Image.Image, PasteBox] | None:
    """Scale + center one image and its mask on the canvas.

    Returns ``(canvas, mask_canvas, box)``, or ``None`` if the mask is empty.
    The mask is co-transformed — same scale and paste offset — so it lines up
    with the moved subject.
    """
    bbox = alpha_bbox(mask, alpha_thresh)
    if bbox is None:
        return None
    x0, y0, x1, y1 = bbox

    scale = (out_w * subject_frac) / (x1 - x0)
    new_w = round(img.width * scale)
    new_h = round(img.height * scale)
    img_s = img.resize((new_w, new_h), Image.LANCZOS)

    cx = (x0 + x1) / 2 * scale
    cy = (y0 + y1) / 2 * scale
    paste_x = round(out_w / 2 - cx)
    paste_y = round(out_h / 2 - cy)

    fill = (0, 0, 0, 255) if background == "black" else (0, 0, 0, 0)
    canvas = Image.new("RGBA", (out_w, out_h), fill)
    paste_mask = img_s if img_s.mode == "RGBA" else None
    canvas.paste(img_s, (paste_x, paste_y), paste_mask)

    mask_s = Image.fromarray(mask, "L").resize((new_w, new_h), Image.LANCZOS)
    mask_canvas = Image.new("L", (out_w, out_h), 0)
    mask_canvas.paste(mask_s, (paste_x, paste_y))

    return canvas, mask_canvas, (paste_x, paste_y, new_w, new_h)


def _shared_crop(
    boxes: list[PasteBox], out_w: int, out_h: int
) -> tuple[int, int, int, int] | None:
    """(left, top, cw, ch) for the letterbox margin common to all frames."""
    left = min(max(px, 0) for px, _py, _w, _h in boxes)
    top = min(max(py, 0) for _px, py, _w, _h in boxes)
    right = min(max(out_w - px - w, 0) for px, _py, w, _h in boxes)
    bottom = min(max(out_h - py - h, 0) for _px, py, _w, h in boxes)
    # yuv420p needs even dimensions — trim each margin down to even.
    left -= left % 2
    top -= top % 2
    right -= right % 2
    bottom -= bottom % 2
    cw = out_w - left - right
    ch = out_h - top - bottom
    if not (left or top or right or bottom) or cw <= 0 or ch <= 0:
        return None
    return left, top, cw, ch


def run(
    input_dir: Path,
    output_dir: Path,
    *,
    width: int = 1080,
    height: int = 1920,
    subject_frac: float = 0.2,
    alpha_thresh: int = 16,
    background: str = "transparent",
    letterbox_crop: bool = True,
) -> int:
    """Process a directory. Returns the number of frames written."""
    photos = discover(input_dir)
    if not photos:
        return 0
    require_masks(photos)

    output_dir.mkdir(parents=True, exist_ok=True)
    kept = 0
    boxes: list[PasteBox] = []
    written: list[Path] = []
    for src in photos:
        try:
            result = scale_and_center(
                load_upright(src),
                load_mask(src),
                out_w=width,
                out_h=height,
                subject_frac=subject_frac,
                alpha_thresh=alpha_thresh,
                background=background,
            )
        except Exception as e:  # noqa: BLE001 - one bad image shouldn't abort the batch
            print(f"{src.name}: error ({e}), skipped", file=sys.stderr)
            continue
        if result is None:
            print(f"{src.name}: empty mask, skipped", file=sys.stderr)
            continue
        canvas, mask_canvas, box = result
        dst = output_dir / f"{kept:05d}.png"
        save_png(canvas, dst)
        save_mask(np.array(mask_canvas), dst)
        boxes.append(box)
        written.append(dst)
        print(f"[{kept + 1}/{len(photos)}] {src.name}", flush=True)
        kept += 1

    if kept == 0:
        print("no frames produced", file=sys.stderr)
        return 0

    if letterbox_crop:
        crop = _shared_crop(boxes, width, height)
        if crop is None:
            print("no uniform letterbox to crop")
        else:
            left, top, cw, ch = crop
            print(f"cropping all frames: left={left} top={top} -> {cw}x{ch}")
            box = (left, top, left + cw, top + ch)
            for path in written:
                for f in (path, mask_path(path)):  # crop image and mask alike
                    Image.open(f).crop(box).save(f, "PNG")

    return kept
