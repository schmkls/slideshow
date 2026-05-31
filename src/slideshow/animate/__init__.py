"""Animation steps — each expands photos into a clip of frames.

- ``fade`` — writes two keyframes per photo; ``video --fade`` cross-dissolves
  them. Cheap, because ffmpeg interpolates the in-between frames.
- ``linger`` — lingers each photo's subject into the next: writes composite
  keyframes (the next photo wearing the previous subject) for ``video --fade``,
  spanning adjacent photos rather than one.
- ``place`` — moves the subject (shrink / slide / grow / grow-and-rotate),
  which is geometric, not an opacity blend, so it writes every frame itself
  and is played by a plain ``video`` (no ``--fade``).
"""

from . import fade, linger, place

__all__ = ["fade", "linger", "place"]
