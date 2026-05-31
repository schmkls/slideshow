"""Composable photo-slideshow steps: mask, silhouette, center, fade, place, video.

Each step is a directory in / directory out, so any step can chain into
any other. ``mask`` detects each subject once and writes a ``<stem>.mask.png``
beside the photo; every other step reads that mask instead of redetecting, so
run ``mask`` first. The ``fade``, ``linger``, and ``place`` steps live in the
``animate`` package. ``pick-faces`` is interactive: it records a single-face
choice per photo (``faces.json``) that ``mask --target faces`` then honors.
See ``slideshow.cli`` for the command line.
"""

from . import (
    animate,
    center,
    faces,
    images,
    mask,
    pick,
    pickfaces,
    segmentation,
    silhouette,
    video,
)

__all__ = [
    "images", "segmentation", "faces", "mask", "silhouette", "center",
    "animate", "pick", "pickfaces", "video",
]
