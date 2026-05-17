"""Composable photo-slideshow steps: silhouette, center, video.

Each step is a directory in / directory out, so any step can chain into
any other. See ``slideshow.cli`` for the command line.
"""

from . import center, images, segmentation, silhouette, video

__all__ = ["images", "segmentation", "silhouette", "center", "video"]
