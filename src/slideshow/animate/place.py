"""Step: move the subject around to make an animated clip.

In: a folder of photos. Out: a folder of ``NNNNN.png`` frames — ``--frames``
of them per photo, the full motion already rendered. A plain ``video`` plays
them (no ``--fade``): the motion is geometric, not an opacity blend, so unlike
``fade`` it can't be reconstructed by cross-dissolving two keyframes.

Motions (``--motion``), where the subject travels from the *first* frame to
its original place (or the reverse) over the clip:

- ``shrink`` — starts filling the frame, shrinks back to its real size.
- ``grow`` — starts at its real size, grows until it fills the frame.
- ``left-to-right`` — starts at the frame's left edge, slides back home.
- ``grow-and-rotate`` — grows like ``grow`` while wobbling between -45° and
  +45° in 5° steps.

Kept cheap by splitting the work: the subject is detected once per photo (the
expensive part), then each frame is a few PIL ops — resize / rotate / paste the
subject sprite onto the original photo. So detection is O(photos) and the
geometry is O(photos × frames).

The sprite rides on the *original photo*, so where a motion uncovers the
subject's home spot (only ``left-to-right`` does) the original subject shows
through until the sprite slides back over it.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from ..faces import FaceDetector
from ..images import discover, load_upright, save_png
from ..segmentation import MaskProvider, Segmenter, alpha_bbox


@dataclass(frozen=True)
class Geom:
    """Where the subject sits in a photo: the canvas size and subject bbox.

    Motions read this to size their moves relative to the subject and frame.
    """

    img_w: int
    img_h: int
    bbox: tuple[int, int, int, int]  # (x0, y0, x1, y1) of the subject

    @property
    def bw(self) -> int:
        return self.bbox[2] - self.bbox[0]

    @property
    def bh(self) -> int:
        return self.bbox[3] - self.bbox[1]

    @property
    def cx(self) -> float:
        return (self.bbox[0] + self.bbox[2]) / 2

    @property
    def cy(self) -> float:
        return (self.bbox[1] + self.bbox[3]) / 2

    @property
    def full_scale(self) -> float:
        """Scale at which the subject bbox covers the whole frame."""
        return max(self.img_w / self.bw, self.img_h / self.bh)


# A motion's per-frame transform of the subject sprite about its home center.
Transform = tuple[float, float, float, float]  # (scale, dx, dy, angle_deg)


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _wobble(i: int, step: int = 5, amp: int = 45) -> float:
    """Triangle wave 0 → +amp → 0 → -amp → 0 …, ``step`` degrees per frame."""
    pos = (i * step) % (4 * amp)
    if pos <= amp:
        return pos
    if pos <= 3 * amp:
        return 2 * amp - pos
    return pos - 4 * amp


# Each motion maps (progress t∈[0,1], frame index i, geometry) -> Transform.
# Home is (1, 0, 0, 0): the sprite lands back exactly on its original spot, so
# that frame reproduces the photo. shrink/left-to-right reach home at t=1 (the
# last frame); grow/grow-and-rotate start there at t=0 and leave it.
def _shrink(t: float, i: int, g: Geom) -> Transform:
    return (_lerp(g.full_scale, 1.0, t), 0.0, 0.0, 0.0)


def _grow(t: float, i: int, g: Geom) -> Transform:
    return (_lerp(1.0, g.full_scale, t), 0.0, 0.0, 0.0)


def _left_to_right(t: float, i: int, g: Geom) -> Transform:
    # dx = -x0 puts the sprite's left edge on the frame's left edge.
    return (1.0, _lerp(-g.bbox[0], 0.0, t), 0.0, 0.0)


def _grow_and_rotate(t: float, i: int, g: Geom) -> Transform:
    return (_lerp(1.0, g.full_scale, t), 0.0, 0.0, _wobble(i))


MOTIONS = {
    "shrink": _shrink,
    "grow": _grow,
    "left-to-right": _left_to_right,
    "grow-and-rotate": _grow_and_rotate,
}


def _render(
    base: Image.Image, sprite: Image.Image, g: Geom, transform: Transform
) -> Image.Image:
    """Composite the transformed subject ``sprite`` onto a copy of ``base``.

    ``base`` is the full RGBA photo; ``sprite`` is the subject cropped to its
    bbox. Scaling and rotation pivot about the sprite's center, which is then
    placed so it lands at the subject's home center shifted by ``(dx, dy)``.
    """
    scale, dx, dy, angle = transform
    spr = sprite.resize(
        (max(1, round(g.bw * scale)), max(1, round(g.bh * scale))), Image.LANCZOS
    )
    if angle:
        spr = spr.rotate(angle, resample=Image.BICUBIC, expand=True)
    paste_x = round(g.cx + dx - spr.width / 2)
    paste_y = round(g.cy + dy - spr.height / 2)
    frame = base.copy()
    frame.paste(spr, (paste_x, paste_y), spr)  # spr's alpha is the paste mask
    return frame


def run(
    input_dir: Path,
    output_dir: Path,
    *,
    motion: str,
    frames: int = 30,
    alpha_thresh: int = 16,
    model: str = "u2net",
    target: str = "subject",
) -> int:
    """Process a directory. Returns the number of frames written.

    Each photo is detected once (whole ``subject`` or ``faces`` only), then
    ``motion`` renders ``frames`` frames moving the subject sprite over it.
    """
    photos = discover(input_dir)
    if not photos:
        return 0

    move = MOTIONS[motion]
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
        bbox = alpha_bbox(mask, alpha_thresh)
        if bbox is None:
            what = "face" if target == "faces" else "subject"
            print(f"{src.name}: no {what} detected, skipped", file=sys.stderr)
            continue

        base = img.convert("RGBA")
        rgb = np.array(img.convert("RGB"))
        subject_layer = Image.fromarray(np.dstack([rgb, mask]), "RGBA")
        sprite = subject_layer.crop(bbox)
        g = Geom(img.width, img.height, bbox)
        for i in range(frames):
            t = i / (frames - 1) if frames > 1 else 1.0
            frame = _render(base, sprite, g, move(t, i, g))
            save_png(frame, output_dir / f"{written:05d}.png")
            written += 1
        print(f"[{idx + 1}/{len(photos)}] {src.name} -> {frames} frames", flush=True)

    if written == 0:
        print("no frames produced", file=sys.stderr)
    return written
