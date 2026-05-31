"""Interactive face picker: show one photo, choose a face with the keyboard.

A small UI used by the ``pick-faces`` step. Given a photo and its detected face
boxes, it opens an OpenCV window with the faces numbered, highlights one, and
lets you move the highlight with the arrow keys (or number keys 1-9). Returns:

- the chosen index (Enter),
- ``None`` to skip without choosing (Esc) — the photo keeps all its faces,
- ``EXCLUDE`` to drop the photo from the slideshow (X or Delete).

Big photos are scaled down to fit the screen for display only; the returned
index refers to the ``boxes`` list as given.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

from .faces import Box

# Returned (instead of an index) when the user excludes the whole photo.
EXCLUDE = "exclude"

# OpenCV's key codes for the arrows vary by platform (and waitKeyEx vs the low
# byte), so each direction is matched against the codes seen across macOS/Linux.
_PREV = {81, 2, 63234, 65361, 82, 0, 63232, 65362}  # left or up -> previous
_NEXT = {83, 3, 63235, 65363, 84, 1, 63233, 65364}  # right or down -> next
_EXCLUDE_KEYS = {8, 127, ord("x"), ord("X")}  # Backspace / Delete / x -> exclude
_HINT = "<-/-> move   Enter: pick   X or Del: exclude   Esc: skip"
_MAX_DISP = 900  # longest displayed edge, in pixels


def _draw_hint(canvas: np.ndarray) -> None:
    """Draw a fixed-size key-hint strip across the top of the display canvas."""
    import cv2

    w = canvas.shape[1]
    cv2.rectangle(canvas, (0, 0), (w, 28), (0, 0, 0), -1)
    cv2.putText(canvas, _HINT, (8, 20),
                cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1, cv2.LINE_AA)


def choose_face(
    img: Image.Image, boxes: list[Box], *, title: str = "pick a face"
) -> int | None | str:
    """Open a window to pick one of ``boxes``.

    Returns the chosen index (Enter), ``None`` to skip without choosing (Esc),
    or ``EXCLUDE`` to drop the photo (X / Delete). Arrow keys or 1-9 move the
    highlight.
    """
    import cv2

    if not boxes:
        return None

    base = cv2.cvtColor(np.array(img.convert("RGB")), cv2.COLOR_RGB2BGR)
    h, w = base.shape[:2]
    scale = min(1.0, _MAX_DISP / max(w, h))
    sel = 0
    cv2.namedWindow(title, cv2.WINDOW_AUTOSIZE)
    try:
        while True:
            canvas = base.copy()
            for n, (x0, y0, x1, y1) in enumerate(boxes):
                chosen = n == sel
                color = (0, 255, 0) if chosen else (0, 0, 255)  # BGR: green / red
                cv2.rectangle(canvas, (x0, y0), (x1, y1), color, 4 if chosen else 2)
                cv2.putText(canvas, str(n + 1), (x0 + 5, max(20, y0 - 8)),
                            cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2, cv2.LINE_AA)
            if scale < 1.0:
                canvas = cv2.resize(canvas, (round(w * scale), round(h * scale)))
            _draw_hint(canvas)
            cv2.imshow(title, canvas)

            k = cv2.waitKeyEx(0)
            low = k & 0xFF
            if low == 27:  # Esc
                return None
            if low in (13, 10):  # Enter
                return sel
            if low in _EXCLUDE_KEYS:
                return EXCLUDE
            if k in _PREV:
                sel = (sel - 1) % len(boxes)
            elif k in _NEXT:
                sel = (sel + 1) % len(boxes)
            elif 49 <= low <= 57:  # '1'..'9'
                idx = low - 49
                if idx < len(boxes):
                    sel = idx
    finally:
        cv2.destroyWindow(title)
        cv2.waitKey(1)  # flush the event queue so the window actually closes
