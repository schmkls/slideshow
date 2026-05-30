"""Step: turn each photo into the two keyframes of an animated clip.

In: a folder of photos. Out: a folder of ``NNNNN.png`` stills — *two* per
photo, the start and end of a fade. ``video --fade N`` cross-dissolves each
pair into an ``N``-frame clip, so the animation is built at encode time
instead of being materialised as every in-between frame here.

The subject is detected once per photo (the model is the expensive part);
the effect then derives the two endpoints from that one detection. A fade is
a *linear cross-dissolve* between its endpoints, so those two stills carry all
the information the clip needs — writing the in-between frames here would just
re-encode the same pixels ``N`` times (and the ``video`` step would re-read
them all). Keeping the clip as its two endpoints is the whole speedup.

Effects (chosen with ``--effect``):

- ``fade-background`` — start: the subject on black; end: the full photo.
  Dissolved, the subject stays solid while the background fades in.

More effects (``fade-subject``, ``place``) slot into ``EFFECTS`` as we add them.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

from .faces import FaceDetector
from .images import discover, load_upright, save_png
from .segmentation import MaskProvider, Segmenter


def fade_background(
    base: np.ndarray, mask: np.ndarray
) -> tuple[Image.Image, Image.Image]:
    """Endpoints of the background fade-in.

    ``base`` is the photo as an ``(H, W, 3)`` RGB array; ``mask`` is the soft
    subject alpha (``0..255``, high on the subject). Returns ``(start, end)``:

    - ``start`` — the subject composited on black (``base * mask/255``): only
      the subject shows, with its soft edges kept.
    - ``end`` — the full photo.

    A linear dissolve ``start*(1-t) + end*t`` equals ``base * alpha_t/255`` with
    ``alpha_t = mask + (255-mask)*t`` exactly: the subject stays solid while the
    background ramps from invisible to fully opaque.
    """
    subject = (base * mask[:, :, None].astype(np.uint16) // 255).astype(np.uint8)
    return Image.fromarray(subject, "RGB"), Image.fromarray(base, "RGB")


# effect name -> function(base_rgb, subject_mask) -> (start_img, end_img)
EFFECTS = {
    "fade-background": fade_background,
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

    Each photo is detected once (whole ``subject`` or ``faces`` only) and turned
    into its clip's two keyframes by ``effect``; ``video --fade N`` expands each
    pair into the animation.
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
