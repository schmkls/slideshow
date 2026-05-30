"""Step: encode a folder of frames into an MP4.

In: a folder of images in ``discover`` order (any names or numbering; gaps
are fine). Out: an H.264 MP4.

By default each image is one frame. With ``--fade N`` the folder is read as
``(start, end)`` keyframe pairs (what ``animate`` writes) and each pair is
cross-dissolved into an N-frame clip.

A video has no alpha and one fixed size, so each frame is flattened onto
black and centered on a canvas sized to the largest frame.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

from .images import discover


def round_up_to_even(n: int) -> int:
    return n + (n % 2)


def _concat_escape(path: Path) -> str:
    """Absolute path quoted for an ffmpeg concat ``file`` line."""
    return str(path.resolve()).replace("'", "'\\''")


def _concat_cmd(
    frames: list[Path], output_video: Path, fps: int, canvas_w: int, canvas_h: int
) -> tuple[list[str], Path]:
    """Static slideshow: one frame per image. Returns ``(cmd, list_path)``.

    Feed ffmpeg the explicit ordered file list (concat demuxer) instead of a
    ``%05d.png`` pattern: the image2 demuxer is a strict numeric counter that
    stops at the first missing index, so any gap/rename silently truncates the
    video. The concat demuxer just reads the files we hand it, in order.
    """
    per_frame = 1 / fps
    lines = ["ffconcat version 1.0"]
    for f in frames:
        lines.append(f"file '{_concat_escape(f)}'")
        lines.append(f"duration {per_frame:.6f}")
    # concat ignores the last entry's duration unless the file is repeated.
    lines.append(f"file '{_concat_escape(frames[-1])}'")

    with tempfile.NamedTemporaryFile(
        "w", suffix=".ffconcat", delete=False
    ) as listf:
        listf.write("\n".join(lines) + "\n")
        list_path = Path(listf.name)

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi",
        "-i", f"color=c=black:s={canvas_w}x{canvas_h}:r={fps}",
        "-f", "concat", "-safe", "0",
        "-i", str(list_path),
        "-filter_complex",
        f"[1:v]fps={fps},format=rgba[fg];"
        "[0:v][fg]overlay=(W-w)/2:(H-h)/2:shortest=1,format=yuv420p",
        "-c:v", "libx264",
        "-crf", "18",
        "-movflags", "+faststart",
        str(output_video),
    ]
    return cmd, list_path


def _fade_cmd(
    frames: list[Path], output_video: Path, fps: int, fade: int,
    canvas_w: int, canvas_h: int,
) -> tuple[list[str], None]:
    """Cross-dissolve each ``(start, end)`` pair into a ``fade``-frame clip,
    then concatenate the clips. Returns ``(cmd, None)``.

    Each still is looped for the clip's duration, padded onto the shared black
    canvas, and ``xfade``-d to its partner over the whole clip. ffmpeg
    interpolates the in-between frames, so only the two stills are needed.
    """
    dur = fade / fps
    pad = (
        f"scale={canvas_w}:{canvas_h}:force_original_aspect_ratio=decrease,"
        f"pad={canvas_w}:{canvas_h}:(ow-iw)/2:(oh-ih)/2:color=black,"
        f"setsar=1,fps={fps}"
    )
    inputs: list[str] = []
    for f in frames:
        inputs += ["-loop", "1", "-framerate", str(fps),
                   "-t", f"{dur:.6f}", "-i", str(f)]

    n_pairs = len(frames) // 2
    parts = [f"[{i}:v]{pad}[p{i}]" for i in range(len(frames))]
    parts += [
        f"[p{2 * k}][p{2 * k + 1}]"
        f"xfade=transition=fade:duration={dur:.6f}:offset=0[c{k}]"
        for k in range(n_pairs)
    ]
    parts.append(
        "".join(f"[c{k}]" for k in range(n_pairs))
        + f"concat=n={n_pairs}:v=1,format=yuv420p[v]"
    )

    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        *inputs,
        "-filter_complex", ";".join(parts),
        "-map", "[v]",
        "-c:v", "libx264",
        "-crf", "18",
        "-movflags", "+faststart",
        str(output_video),
    ]
    return cmd, None


def run(input_dir: Path, output_video: Path, *, fps: int = 10, fade: int = 0) -> int:
    """Encode the frames in ``input_dir``. Returns output frame count, 0 on failure.

    ``fade`` 0 (default) plays each image as one frame; ``fade > 0`` reads the
    folder as ``(start, end)`` pairs and dissolves each pair over ``fade`` frames.
    """
    frames = discover(input_dir)
    if not frames:
        return 0
    if fade > 0 and len(frames) % 2:
        print("odd frame count; dropping the last (--fade needs start/end pairs)",
              file=sys.stderr)
        frames = frames[:-1]
        if not frames:
            return 0

    sizes = [Image.open(f).size for f in frames]
    canvas_w = round_up_to_even(max(w for w, _h in sizes))
    canvas_h = round_up_to_even(max(h for _w, h in sizes))

    output_video.parent.mkdir(parents=True, exist_ok=True)
    if fade > 0:
        cmd, cleanup = _fade_cmd(frames, output_video, fps, fade, canvas_w, canvas_h)
        n_out = (len(frames) // 2) * fade
    else:
        cmd, cleanup = _concat_cmd(frames, output_video, fps, canvas_w, canvas_h)
        n_out = len(frames)

    try:
        subprocess.run(cmd, check=True)
    except FileNotFoundError:
        print("ffmpeg not found on PATH", file=sys.stderr)
        return 0
    except subprocess.CalledProcessError as e:
        print(f"ffmpeg failed (exit {e.returncode})", file=sys.stderr)
        return 0
    finally:
        if cleanup is not None:
            cleanup.unlink(missing_ok=True)
    print(f"wrote {output_video} ({n_out} frames @ {fps} fps)")
    return n_out
