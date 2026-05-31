"""Animation steps — each expands a photo into a clip of frames.

- ``fade`` — writes two keyframes per photo; ``video --fade`` cross-dissolves
  them. Cheap, because ffmpeg interpolates the in-between frames.
- ``place`` — moves the subject (shrink / slide / grow / grow-and-rotate),
  which is geometric, not an opacity blend, so it writes every frame itself
  and is played by a plain ``video`` (no ``--fade``).
"""

from . import fade, place

__all__ = ["fade", "place"]
