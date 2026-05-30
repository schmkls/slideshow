"""Step: expand each photo into an animated clip of frames.

In: a folder of photos. Out: a folder of ``NNNNN.png`` frames where *every*
input photo becomes ``frames`` consecutive frames — an animation. Played in
order (via the ``video`` step) it's a slideshow of animated clips.

This is the one place the "turn one image into many frames" concern lives.
The subject is detected once per photo (the model is the expensive part);
each effect then cheaply derives ``frames`` frames from that one detection.

Effects (chosen with ``--effect``):

- ``fade-background`` — the subject stays fully visible while the non-subject
  background ramps from invisible to full opacity across the clip.

More effects (``fade-subject``, ``place``) slot into ``EFFECTS`` as we add them.
"""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import numpy as np
from PIL import Image

from .faces import FaceDetector
from .images import discover, load_upright, save_png
from .segmentation import MaskProvider, Segmenter


def _ramp(frames: int) -> Iterator[float]:
    """Yield ``frames`` progress values from 0.0 to 1.0 inclusive."""
    if frames <= 1:
        yield 1.0
        return
    for i in range(frames):
        yield i / (frames - 1)


def fade_background(
    base: np.ndarray, mask: np.ndarray, frames: int
) -> Iterator[Image.Image]:
    """Subject stays solid; the background fades in over the clip.

    ``base`` is the photo as an ``(H, W, 3)`` RGB array; ``mask`` is the soft
    subject alpha (``0..255``, high on the subject). Per pixel the output alpha
    is ``mask + (255 - mask) * t``: at ``t=0`` only the subject shows (soft
    edges kept), at ``t=1`` the whole photo is opaque.
    """
    m = mask.astype(np.float32)
    inv = 255.0 - m
    for t in _ramp(frames):
        alpha = (m + inv * t).round().clip(0, 255).astype(np.uint8)
        yield Image.fromarray(np.dstack([base, alpha]), "RGBA")


# effect name -> function(base_rgb, subject_mask, frames) -> frames iterator
EFFECTS = {
    "fade-background": fade_background,
}


def run(
    input_dir: Path,
    output_dir: Path,
    *,
    effect: str,
    frames: int = 30,
    alpha_thresh: int = 16,
    model: str = "u2net",
    target: str = "subject",
) -> int:
    """Process a directory. Returns the total number of frames written.

    Each photo is detected once (whole ``subject`` or ``faces`` only) and then
    expanded into ``frames`` frames by ``effect``.
    """
    photos = discover(input_dir)
    if not photos:
        return 0

    make_frames = EFFECTS[effect]
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
        for frame in make_frames(base, mask, frames):
            save_png(frame, output_dir / f"{written:05d}.png")
            written += 1
        print(f"[{idx + 1}/{len(photos)}] {src.name} -> {frames} frames",
              flush=True)

    if written == 0:
        print("no frames produced", file=sys.stderr)
    return written
