"""Step: turn each photo into the two keyframes of a fade clip.

In: a folder of photos. Out: a folder of ``NNNNN.png`` stills, two per
photo — the start and end of a fade. ``video --fade N`` cross-dissolves each
pair into an N-frame clip, so only the two endpoints are written here.

The subject is detected once per photo, then the chosen effect derives the
two endpoints from that detection.

Effects (``--effect``):

- ``background`` — start: subject on black; end: the full photo.
  Dissolved, the background fades in while the subject stays solid.
- ``subject`` — start: background on black; end: the full photo.
  Dissolved, the subject fades in while the background stays solid.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

from ..faces import FaceDetector
from ..images import discover, load_upright, save_png
from ..segmentation import MaskProvider, Segmenter


def _on_black(base: np.ndarray, keep: np.ndarray) -> Image.Image:
    """Composite ``base`` on black, keeping it where ``keep`` (0..255) is high.

    Pixels fade to black as ``keep`` drops, so soft mask edges are preserved.
    Both fade effects use this; they differ only in what they keep.
    """
    kept = (base * keep[:, :, None].astype(np.uint16) // 255).astype(np.uint8)
    return Image.fromarray(kept, "RGB")


def fade_background(
    base: np.ndarray, mask: np.ndarray
) -> tuple[Image.Image, Image.Image]:
    """Start and end frames of the background fade-in.

    ``base`` is the photo as an ``(H, W, 3)`` RGB array; ``mask`` is the
    subject alpha (0..255, high on the subject). Returns ``(start, end)``:
    the subject on black, then the full photo. Dissolving between them fades
    the background in while the subject stays solid.
    """
    return _on_black(base, mask), Image.fromarray(base, "RGB")


def fade_subject(
    base: np.ndarray, mask: np.ndarray
) -> tuple[Image.Image, Image.Image]:
    """Start and end frames of the subject fade-in.

    Keeps the background (``255 - mask``) on black instead of the subject.
    Returns ``(start, end)``: the background on black (subject area black),
    then the full photo. Dissolving between them fades the subject in while
    the background stays solid.
    """
    return _on_black(base, 255 - mask), Image.fromarray(base, "RGB")


# effect name -> function(base_rgb, subject_mask) -> (start_img, end_img)
EFFECTS = {
    "background": fade_background,
    "subject": fade_subject,
}


def run(
    input_dir: Path,
    output_dir: Path,
    *,
    effect: str,
    alpha_thresh: int = 16,
    model: str = "u2net",
    target: str = "subject",
) -> int:
    """Process a directory. Returns the number of stills written (2 per photo).

    Each photo is detected once (whole ``subject`` or ``faces`` only), then
    ``effect`` turns it into two keyframes.
    """
    photos = discover(input_dir)
    if not photos:
        return 0

    make_endpoints = EFFECTS[effect]
    provider: MaskProvider = (
        FaceDetector() if target == "faces" else Segmenter(model)
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for idx, src in enumerate(photos):
        try:
            img = load_upright(src)
            mask = provider.subject_alpha(img)
        except Exception as e:  # noqa: BLE001 - one bad image shouldn't abort the batch
            print(f"{src.name}: error ({e}), skipped", file=sys.stderr)
            continue
        if not (mask > alpha_thresh).any():
            what = "face" if target == "faces" else "subject"
            print(f"{src.name}: no {what} detected, skipped", file=sys.stderr)
            continue
        base = np.array(img.convert("RGB"))
        for frame in make_endpoints(base, mask):
            save_png(frame, output_dir / f"{written:05d}.png")
            written += 1
        print(f"[{idx + 1}/{len(photos)}] {src.name} -> 2 keyframes", flush=True)

    if written == 0:
        print("no frames produced", file=sys.stderr)
    return written
