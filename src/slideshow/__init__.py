"""Composable photo-slideshow steps: silhouette, center, fade, place, video.

Each step is a directory in / directory out, so any step can chain into
any other. The ``fade`` and ``place`` steps live in the ``animate`` package.
``pick-faces`` is interactive: it records a single-face choice per photo
(``faces.json``) that the ``--target faces`` steps then honor.
See ``slideshow.cli`` for the command line.
"""

from . import (
    animate,
    center,
    faces,
    images,
    pick,
    pickfaces,
    segmentation,
    silhouette,
    video,
)

__all__ = [
    "images", "segmentation", "faces", "silhouette", "center", "animate",
    "pick", "pickfaces", "video",
]
