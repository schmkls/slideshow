"""Face detection — a faces-only alternative subject locator for the steps.

Where ``Segmenter`` finds the whole foreground subject, ``FaceDetector``
finds *faces only*: it runs OpenCV's res10 SSD face detector and returns a
mask with one filled ellipse per detected face. It exposes the same
``subject_alpha(img) -> np.ndarray`` as ``Segmenter`` (the ``MaskProvider``
protocol), so the silhouette and center steps use either interchangeably.

The detector needs two files: a small ``deploy.prototxt`` (bundled with the
package) and a ~5 MB ``.caffemodel`` (downloaded on first use and cached in
``~/.slideshow``, mirroring how rembg caches its model in ``~/.u2net``).
"""

from __future__ import annotations

import shutil
import ssl
import sys
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

_PROTOTXT = Path(__file__).parent / "models" / "deploy.prototxt"
_CACHE_DIR = Path.home() / ".slideshow"
_CAFFEMODEL = _CACHE_DIR / "res10_300x300_ssd_iter_140000.caffemodel"
_CAFFEMODEL_URL = (
    "https://raw.githubusercontent.com/opencv/opencv_3rdparty/"
    "dnn_samples_face_detector_20170830/res10_300x300_ssd_iter_140000.caffemodel"
)


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


class FaceDetector:
    """Lazily-loaded OpenCV res10 face detector; a faces-only MaskProvider.

    ``conf_thresh`` is the minimum detector confidence (0..1) a box must
    reach to count as a face — raise it to drop shaky detections.
    """

    def __init__(self, conf_thresh: float = 0.5) -> None:
        self.conf_thresh = conf_thresh
        self._net = None

    def _ensure(self):
        if self._net is None:
            import cv2

            self._net = cv2.dnn.readNetFromCaffe(
                str(_PROTOTXT), str(_ensure_caffemodel())
            )
        return self._net

    def subject_alpha(self, img: Image.Image) -> np.ndarray:
        """uint8 mask the size of ``img``: 255 over each detected face."""
        import cv2

        rgb = np.array(img.convert("RGB"))
        h, w = rgb.shape[:2]
        # res10 was trained on BGR with these channel means; swap RGB->BGR.
        bgr = np.ascontiguousarray(rgb[:, :, ::-1])
        blob = cv2.dnn.blobFromImage(bgr, 1.0, (300, 300), (104.0, 177.0, 123.0))
        net = self._ensure()
        net.setInput(blob)
        detections = net.forward()  # shape (1, 1, N, 7): [_, _, conf, x0,y0,x1,y1]

        mask = Image.new("L", (w, h), 0)
        draw = ImageDraw.Draw(mask)
        for i in range(detections.shape[2]):
            if detections[0, 0, i, 2] < self.conf_thresh:
                continue
            x0, y0, x1, y1 = detections[0, 0, i, 3:7] * (w, h, w, h)
            x0, x1 = sorted((max(0.0, x0), min(float(w), x1)))
            y0, y1 = sorted((max(0.0, y0), min(float(h), y1)))
            if x1 > x0 and y1 > y0:
                draw.ellipse((x0, y0, x1, y1), fill=255)  # oval over the face
        return np.array(mask)
