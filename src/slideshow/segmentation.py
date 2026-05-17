"""Subject segmentation — the one place the rembg model lives.

Both the silhouette and center steps need to know where the subject is.
Each step detects the subject independently (the model runs per step),
so the steps stay standalone and compose in any order. This module loads
the (~176 MB) model once per process.
"""

from __future__ import annotations

import numpy as np
from PIL import Image


def alpha_bbox(
    alpha: np.ndarray, threshold: int
) -> tuple[int, int, int, int] | None:
    """Tightest box around pixels whose alpha exceeds ``threshold``."""
    mask = alpha > threshold
    if not mask.any():
        return None
    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)
    y0, y1 = np.where(rows)[0][[0, -1]]
    x0, x1 = np.where(cols)[0][[0, -1]]
    return int(x0), int(y0), int(x1) + 1, int(y1) + 1


class Segmenter:
    """Lazily-loaded rembg session; ``model`` is downloaded on first use."""

    def __init__(self, model: str = "u2net") -> None:
        self.model = model
        self._session = None

    def _ensure(self):
        if self._session is None:
            from rembg import new_session

            self._session = new_session(self.model)
        return self._session

    def cutout(self, img: Image.Image) -> Image.Image:
        """Run the model: returns an RGBA image, background alpha == 0."""
        from rembg import remove

        return remove(img.convert("RGB"), session=self._ensure()).convert("RGBA")

    def subject_alpha(self, img: Image.Image) -> np.ndarray:
        """Subject alpha mask for ``img`` (runs the segmentation model)."""
        return np.array(self.cutout(img).split()[-1])
