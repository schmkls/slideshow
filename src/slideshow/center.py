"""Step: scale and center every subject on a uniform canvas.

In: a folder of images (raw photos, or the silhouette step's output).
Out: a folder of ``NNNNN.png`` frames, each the same size, with the
subject scaled to ``subject_frac`` of the width and centered on both axes.

Letterbox (the canvas area a frame's image doesn't cover) is filled with
the chosen background; afterwards the margin shared by *every* frame is
cropped off uniformly, so frames don't keep a border they all share.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

from .faces import FaceDetector
from .images import discover, load_upright, save_png
from .segmentation import MaskProvider, Segmenter, alpha_bbox

PasteBox = tuple[int, int, int, int]  # (x, y, w, h) of the image on the canvas


def scale_and_center(
    img: Image.Image,
    provider: MaskProvider,
    *,
    out_w: int,
    out_h: int,
    subject_frac: float,
    alpha_thresh: int,
    background: str,
) -> tuple[Image.Image, PasteBox] | None:
    """Scale + center one image on the canvas. ``None`` if nothing detected.

    ``provider`` decides what to center on: the whole subject (``Segmenter``)
    or faces only (``FaceDetector``).
    """
    alpha = provider.subject_alpha(img)
    bbox = alpha_bbox(alpha, alpha_thresh)
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
    mask = img_s if img_s.mode == "RGBA" else None
    canvas.paste(img_s, (paste_x, paste_y), mask)
    return canvas, (paste_x, paste_y, new_w, new_h)


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
    model: str = "u2net",
    target: str = "subject",
) -> int:
    """Process a directory. Returns the number of frames written.

    ``target`` is ``"subject"`` (whole foreground) or ``"faces"`` (faces only).
    """
    photos = discover(input_dir)
    if not photos:
        return 0

    provider: MaskProvider = (
        FaceDetector() if target == "faces" else Segmenter(model)
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    kept = 0
    boxes: list[PasteBox] = []
    written: list[Path] = []
    for src in photos:
        try:
            result = scale_and_center(
                load_upright(src),
                provider,
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
            what = "face" if target == "faces" else "subject"
            print(f"{src.name}: no {what} detected, skipped", file=sys.stderr)
            continue
        canvas, box = result
        dst = output_dir / f"{kept:05d}.png"
        save_png(canvas, dst)
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
            for path in written:
                frame = Image.open(path)
                frame.crop((left, top, left + cw, top + ch)).save(path, "PNG")

    return kept
