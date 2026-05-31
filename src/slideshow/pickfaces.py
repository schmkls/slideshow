"""Step: choose which detected face is the subject in each photo.

Face detection can find several faces; the center/fade/place steps with
``--target faces`` otherwise key on *all* of them at once. This step opens each
multi-face photo in a picker window (arrow keys + Enter) and records the chosen
face to a ``faces.json`` sidecar next to the photos. The face-targeted steps
read that sidecar and act on the chosen face alone.

In the picker you can also *exclude* a photo (X / Delete): it is recorded as
``null`` in the sidecar, and the ``--target faces`` steps then drop it (an
excluded photo yields an empty mask, which those steps skip). Esc instead skips
*choosing* — the photo keeps all its faces.

Photos with a single face are auto-selected (no window); photos with none are
skipped. Every run re-picks every photo fresh and overwrites ``faces.json`` — to
re-pick, re-run; to start clean, delete ``faces.json`` first.
"""

from __future__ import annotations

import sys
from pathlib import Path

from .faces import SIDECAR_NAME, FaceDetector, save_selection
from .images import discover, load_upright
from .pick import EXCLUDE, choose_face


def run(
    input_dir: Path,
    *,
    conf_thresh: float = 0.5,
    det_size: int = 900,
) -> int:
    """Pick a face per photo and write ``input_dir/faces.json``.

    Always overwrites: every photo is re-picked fresh. Returns how many photos
    ended up with a selection.
    """
    photos = discover(input_dir)
    if not photos:
        return 0

    detector = FaceDetector(conf_thresh, det_size=det_size)
    selection = {}
    for idx, src in enumerate(photos):
        tag = f"[{idx + 1}/{len(photos)}] {src.name}"
        try:
            img = load_upright(src)
            boxes = detector.detect(img)
        except Exception as e:  # noqa: BLE001 - one bad image shouldn't abort the batch
            print(f"{src.name}: error ({e}), skipped", file=sys.stderr)
            continue
        if not boxes:
            print(f"{src.name}: no face detected, skipped", file=sys.stderr)
            continue
        if len(boxes) == 1:
            selection[src.name] = boxes[0]
            print(f"{tag}: 1 face, auto-selected", flush=True)
            continue

        pick = choose_face(img, boxes, title=f"{src.name}  ({len(boxes)} faces)")
        if pick == EXCLUDE:
            selection[src.name] = None
            print(f"{tag}: excluded", flush=True)
            continue
        if pick is None:
            print(f"{tag}: skipped (kept all faces)", flush=True)
            continue
        selection[src.name] = boxes[pick]
        print(f"{tag}: face {pick + 1} selected", flush=True)

    sidecar = Path(input_dir) / SIDECAR_NAME
    save_selection(sidecar, selection)
    picked = sum(1 for v in selection.values() if v is not None)
    excluded = len(selection) - picked
    print(f"wrote {picked} selection(s), {excluded} exclusion(s) to {sidecar}")
    return len(selection)
