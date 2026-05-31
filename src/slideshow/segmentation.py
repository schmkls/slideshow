"""Subject segmentation backed by the rembg model.

The silhouette, center, and animate steps all need to know where the
subject is. Each step detects it independently, so the steps stay
standalone and compose in any order. The model (~176 MB) loads once per
process and downloads on first use.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image


class MaskProvider(Protocol):
    """Locates the subject in an image.

    Implemented by ``Segmenter`` (whole subject) and ``FaceDetector`` (faces
    only), so the center and animate steps can use either one.
    """

    def subject_alpha(self, img: Image.Image, key: str | None = None) -> np.ndarray:
        """A uint8 mask the size of ``img``: high where the subject is.

        ``key`` (the photo's filename) lets a face provider apply a saved
        single-face selection; providers that don't select ignore it.
        """
        ...


def make_provider(
    target: str, *, model: str = "u2net", input_dir: Path | None = None
) -> MaskProvider:
    """The ``MaskProvider`` for a step's ``--target``.

    ``"faces"`` -> a ``FaceDetector`` honoring a ``faces.json`` selection in
    ``input_dir`` (if present); anything else -> a whole-subject ``Segmenter``.
    """
    if target == "faces":
        from .faces import FaceDetector, load_selection

        selection = load_selection(input_dir) if input_dir is not None else None
        return FaceDetector(selection=selection)
    return Segmenter(model)


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

    def subject_alpha(self, img: Image.Image, key: str | None = None) -> np.ndarray:
        """Subject alpha mask for ``img`` (runs the segmentation model).

        ``key`` is part of the ``MaskProvider`` interface (face selection) and
        is ignored here — the whole subject is always returned.
        """
        return np.array(self.cutout(img).split()[-1])
