"""Step: detect each photo's subject and write its mask beside it.

In: a folder of photos. Out: the same folder, with a ``<stem>.mask.png`` written
next to every photo. This is the only place subject detection runs — every later
step reads these masks instead of redetecting, so a chain detects exactly once.

``--target subject`` uses the rembg segmenter (soft alpha, kept for clean
compositing); ``--target faces`` uses the face detector, honoring a ``faces.json``
selection from ``pick-faces``. A mask is written for *every* photo — all-zero
when nothing is detected — so a later step can tell "no subject here" (a zero
mask) from "you forgot to run ``mask``" (no file). Always overwrites.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .images import discover, load_upright, save_mask
from .segmentation import make_provider


def run(input_dir: Path, *, target: str = "subject", model: str = "u2net") -> int:
    """Detect and write one mask per photo. Returns the number written.

    ``target`` is ``"subject"`` (whole foreground, rembg) or ``"faces"`` (faces
    only, honoring ``faces.json``).
    """
    photos = discover(input_dir)
    if not photos:
        return 0

    provider = make_provider(target, model=model, input_dir=input_dir)
    written = 0
    for idx, src in enumerate(photos):
        try:
            mask = provider.subject_alpha(load_upright(src), src.name)
        except Exception as e:  # noqa: BLE001 - one bad image shouldn't abort the batch
            print(f"{src.name}: error ({e}), skipped", file=sys.stderr)
            continue
        save_mask(mask, src)
        print(f"[{idx + 1}/{len(photos)}] {src.name}", flush=True)
        written += 1

    if written == 0:
        print("no masks written", file=sys.stderr)
    return written
