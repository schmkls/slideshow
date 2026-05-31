"""Composable photo-slideshow steps: silhouette, center, fade, place, video.

Each step is a directory in / directory out, so any step can chain into
any other. The ``fade`` and ``place`` steps live in the ``animate`` package.
See ``slideshow.cli`` for the command line.
"""

from . import animate, center, images, segmentation, silhouette, video

__all__ = [
    "images", "segmentation", "silhouette", "center", "animate", "video",
]
