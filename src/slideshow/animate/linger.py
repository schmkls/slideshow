"""Step: linger each photo's subject into the next photo.

In: a folder of photos (typically already ``center``-ed onto a common canvas).
Out: a folder of ``NNNNN.png`` keyframes that ``video --fade N`` cross-dissolves
into the animation — so, like ``fade``, only keyframes are written here and
ffmpeg interpolates the in-between frames.

For each adjacent pair A -> B the previous subject lingers across the cut. The
one composite keyframe per transition is ``K`` — photo B with A's subject pasted
on top — giving the chain ``A -> K -> B``: A's subject arrives in the next scene
(A -> K), then dissolves away as B resolves (K -> B). Written as the pairs
``(A, K)`` and ``(K, B)``, ``video --fade`` dissolves each and concatenates them;
the shared endpoint ``K`` joins them seamlessly.

Pasting the whole photo masked by its subject needs no hole-filling — only the
subject mask, detected once per photo by the same provider the other steps use.
Subjects land at their original pixel position, so the photos should share a
canvas (run ``center`` first).
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from ..images import discover, load_upright, save_png
from ..segmentation import MaskProvider, make_provider


@dataclass
class _Layered:
    """A photo split into the two layers a transition blends: the whole photo
    (the background) and the subject cutout that rides on top of it."""

    name: str
    base: Image.Image  # full photo, RGB
    subject: Image.Image  # RGBA cutout, alpha == subject mask


def _compose(background: Image.Image, subject: Image.Image) -> Image.Image:
    """``background`` (RGB) with ``subject`` (RGBA cutout) pasted on top.

    The subject's alpha is the paste mask, so it lands at its own pixel
    position over the other photo — aligned when both share a canvas.
    """
    out = background.copy()
    out.paste(subject, (0, 0), subject)
    return out


def run(
    input_dir: Path,
    output_dir: Path,
    *,
    loop: bool = True,
    alpha_thresh: int = 16,
    model: str = "u2net",
    target: str = "subject",
) -> int:
    """Process a directory. Returns the number of keyframes written.

    Each photo is detected once, then every adjacent pair (wrapping past the
    last photo when ``loop``) yields four keyframes — ``(A, K)`` and ``(K, B)``
    — for ``video --fade`` to dissolve. Photos with no detected subject are
    dropped, joining their neighbors in the chain.
    """
    photos = discover(input_dir)
    if not photos:
        return 0

    provider: MaskProvider = make_provider(target, model=model, input_dir=input_dir)
    layered: list[_Layered] = []
    for src in photos:
        try:
            img = load_upright(src)
            mask = provider.subject_alpha(img, src.name)
        except Exception as e:  # noqa: BLE001 - one bad image shouldn't abort the batch
            print(f"{src.name}: error ({e}), skipped", file=sys.stderr)
            continue
        if not (mask > alpha_thresh).any():
            what = "face" if target == "faces" else "subject"
            print(f"{src.name}: no {what} detected, skipped", file=sys.stderr)
            continue
        rgb = np.array(img.convert("RGB"))
        subject = Image.fromarray(np.dstack([rgb, mask]), "RGBA")
        layered.append(_Layered(src.name, Image.fromarray(rgb, "RGB"), subject))

    if len(layered) < 2:
        print("need at least 2 photos with a detected subject", file=sys.stderr)
        return 0

    output_dir.mkdir(parents=True, exist_ok=True)
    n = len(layered)
    transitions = n if loop else n - 1
    written = 0
    for i in range(transitions):
        a = layered[i]
        b = layered[(i + 1) % n]
        mid = _compose(b.base, a.subject)  # B's background, A's subject
        # A -> K and K -> B as disjoint pairs; the shared K joins them seamlessly.
        for frame in (a.base, mid, mid, b.base):
            save_png(frame, output_dir / f"{written:05d}.png")
            written += 1
        print(
            f"[{i + 1}/{transitions}] {a.name} -> {b.name} -> 4 keyframes",
            flush=True,
        )

    return written
