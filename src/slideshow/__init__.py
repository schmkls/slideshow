"""Composable photo-slideshow steps: silhouette, center, animate, video.

Each step is a directory in / directory out, so any step can chain into
any other. See ``slideshow.cli`` for the command line.
"""

from . import animate, center, images, segmentation, silhouette, video

__all__ = [
    "images", "segmentation", "silhouette", "center", "animate", "video",
]
