"""Faces-only subject locator — a ``MaskProvider`` backed by OpenCV.

Where ``Segmenter`` finds the whole foreground subject, ``FaceDetector``
finds faces only: it runs OpenCV's res10 SSD face detector and returns a
mask with one filled ellipse per detected face. It exposes the same
``subject_alpha`` as ``Segmenter``, so the center and animate steps can use
either one.

When several faces are detected, the ``pick-faces`` step lets the user choose
one and records it in a ``faces.json`` sidecar (filename -> chosen box). A
``FaceDetector`` built with that ``selection`` masks only the chosen face for a
photo it has an entry for, and falls back to all faces otherwise.

It needs two files: ``deploy.prototxt`` (bundled with the package) and a
~5 MB ``.caffemodel`` (downloaded on first use, cached in ``~/.slideshow``).
"""

from __future__ import annotations

import json
import shutil
import ssl
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

Box = tuple[int, int, int, int]  # (x0, y0, x1, y1) in pixels

_PROTOTXT = Path(__file__).parent / "models" / "deploy.prototxt"
_CACHE_DIR = Path.home() / ".slideshow"
_CAFFEMODEL = _CACHE_DIR / "res10_300x300_ssd_iter_140000.caffemodel"
_CAFFEMODEL_URL = (
    "https://raw.githubusercontent.com/opencv/opencv_3rdparty/"
    "dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel"
)

# The picker writes its choices here, next to the photos, so the face-targeted
# steps pick them up automatically when run on the same folder.
SIDECAR_NAME = "faces.json"


def _ssl_context() -> ssl.SSLContext | None:
    """Verify against certifi's CA bundle — Python's urllib otherwise can't
    verify TLS certs on stock macOS, which fails the download."""
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:  # noqa: BLE001 - any failure falls back to the default
        return None


def _ensure_caffemodel() -> Path:
    """Return the cached caffemodel path, downloading it on first use."""
    if _CAFFEMODEL.exists():
        return _CAFFEMODEL
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    print(f"downloading face model (~5 MB) to {_CAFFEMODEL} ...",
          file=sys.stderr, flush=True)
    tmp = _CAFFEMODEL.with_suffix(".part")
    with urllib.request.urlopen(_CAFFEMODEL_URL, context=_ssl_context()) as r, \
            open(tmp, "wb") as f:
        shutil.copyfileobj(r, f)
    tmp.replace(_CAFFEMODEL)  # atomic: a partial download never looks complete
    return _CAFFEMODEL


def faces_mask(boxes: list[Box], size: tuple[int, int]) -> np.ndarray:
    """uint8 mask of ``size`` (w, h): 255 inside a filled ellipse per box."""
    w, h = size
    mask = Image.new("L", (w, h), 0)
    draw = ImageDraw.Draw(mask)
    for x0, y0, x1, y1 in boxes:
        if x1 > x0 and y1 > y0:
            draw.ellipse((x0, y0, x1, y1), fill=255)
    return np.array(mask)


def load_selection(input_dir: Path) -> dict[str, Box | None] | None:
    """Read ``input_dir/faces.json``, or ``None`` if absent.

    Maps filename -> chosen box, or -> ``None`` for a photo marked *excluded*
    (written as JSON ``null``).
    """
    path = Path(input_dir) / SIDECAR_NAME
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return {
        name: (tuple(box) if box is not None else None)
        for name, box in data.items()
    }


def save_selection(path: Path, selection: dict[str, Box | None]) -> None:
    """Write ``selection`` as JSON to ``path``.

    A box value is the chosen face; ``None`` is written as ``null`` to mark the
    photo excluded.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = {
        n: (list(b) if b is not None else None) for n, b in selection.items()
    }
    path.write_text(json.dumps(serialized, indent=2))


class FaceDetector:
    """Lazily-loaded OpenCV res10 face detector (a ``MaskProvider``).

    ``conf_thresh`` is the minimum detector confidence (0..1) a box must
    reach to count as a face — raise it to drop weak detections.

    ``selection`` (filename -> box, or filename -> ``None``) is an optional
    ``pick-faces`` result: for a photo whose ``key`` maps to a box,
    ``subject_alpha`` masks only that one face and skips detection; a ``None``
    marks the photo *excluded* and yields an empty mask, so the calling step
    drops it. Photos with no entry fall back to all detected faces.

    ``det_size`` is the square input the photo is fed to the detector at. res10
    squashes its input to this size, so a small face in a group shot only
    survives if the input is big enough to keep it more than a few pixels wide —
    larger ``det_size`` finds more (and smaller) faces at the cost of speed.
    ``nms_thresh`` is the IoU above which two overlapping boxes are merged, so
    the bigger input doesn't return the same face several times.
    """

    def __init__(
        self,
        conf_thresh: float = 0.5,
        selection: dict[str, Box] | None = None,
        det_size: int = 900,
        nms_thresh: float = 0.3,
    ) -> None:
        self.conf_thresh = conf_thresh
        self.selection = selection
        self.det_size = det_size
        self.nms_thresh = nms_thresh
        self._net = None

    def _ensure(self):
        if self._net is None:
            import cv2

            self._net = cv2.dnn.readNetFromCaffe(
                str(_PROTOTXT), str(_ensure_caffemodel())
            )
        return self._net

    def detect(self, img: Image.Image) -> list[Box]:
        """Pixel-space box for each detected face, ordered left-to-right so a
        picker can number them stably.

        The photo is letterboxed (not squashed) onto a ``det_size`` square so
        its proportions are kept, run through res10, then overlapping boxes are
        merged with NMS.
        """
        import cv2

        rgb = np.array(img.convert("RGB"))
        h, w = rgb.shape[:2]
        # res10 was trained on BGR with these channel means; swap RGB->BGR.
        bgr = np.ascontiguousarray(rgb[:, :, ::-1])

        # Letterbox onto a det x det square: resize keeping aspect, paste at the
        # top-left, pad with the channel means so the padding is neutral once
        # the net subtracts them. Pasting at (0, 0) means a normalized output
        # coord just scales back by max(w, h); padding-only boxes fall outside
        # [0, w] x [0, h] and are dropped by the clamp below.
        det = self.det_size
        s = det / max(w, h)
        resized = cv2.resize(bgr, (max(1, round(w * s)), max(1, round(h * s))))
        canvas = np.full((det, det, 3), (104, 177, 123), dtype=np.uint8)
        canvas[: resized.shape[0], : resized.shape[1]] = resized
        blob = cv2.dnn.blobFromImage(canvas, 1.0, (det, det), (104.0, 177.0, 123.0))
        net = self._ensure()
        net.setInput(blob)
        detections = net.forward()  # shape (1, 1, N, 7): [_, _, conf, x0,y0,x1,y1]

        m = max(w, h)  # square canvas: normalized coords map back by * max(w, h)
        xywh: list[list[float]] = []
        scores: list[float] = []
        for i in range(detections.shape[2]):
            conf = float(detections[0, 0, i, 2])
            if conf < self.conf_thresh:
                continue
            x0, y0, x1, y1 = detections[0, 0, i, 3:7] * m
            x0, x1 = sorted((max(0.0, x0), min(float(w), x1)))
            y0, y1 = sorted((max(0.0, y0), min(float(h), y1)))
            if x1 > x0 and y1 > y0:
                xywh.append([x0, y0, x1 - x0, y1 - y0])
                scores.append(conf)

        boxes: list[Box] = []
        if xywh:
            keep = cv2.dnn.NMSBoxes(xywh, scores, self.conf_thresh, self.nms_thresh)
            for i in np.array(keep).flatten():
                x, y, bw, bh = xywh[int(i)]
                boxes.append((int(x), int(y), int(x + bw), int(y + bh)))
        boxes.sort(key=lambda b: (b[0], b[1]))
        return boxes

    def subject_alpha(self, img: Image.Image, key: str | None = None) -> np.ndarray:
        """uint8 mask the size of ``img``: 255 over the subject face(s).

        With a ``selection`` entry for ``key``: a box masks only that chosen
        face (no detection runs); ``None`` marks the photo excluded and returns
        an empty mask (the step then drops it). No entry -> every detected face.
        """
        if self.selection is not None and key is not None and key in self.selection:
            box = self.selection[key]
            boxes: list[Box] = [] if box is None else [box]
        else:
            boxes = self.detect(img)
        return faces_mask(boxes, img.size)
