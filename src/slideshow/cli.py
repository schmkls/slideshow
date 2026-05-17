"""Single CLI exposing each step as a subcommand.

    python -m slideshow silhouette IN_DIR  OUT_DIR  [--halo-px N] ...
    python -m slideshow center     IN_DIR  OUT_DIR  [--width N] ...
    python -m slideshow video      IN_DIR  OUT.mp4  [--fps N]

Steps chain through directories, so the user composes the user stories:
e.g. silhouette -> center -> video, or just center -> video.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import center, silhouette, video


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="slideshow", description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("silhouette", help="Add a white halo around each subject.")
    s.add_argument("input_dir", type=Path)
    s.add_argument("output_dir", type=Path)
    s.add_argument("--halo-px", type=int, default=16,
                   help="Halo thickness in pixels (0 disables).")
    s.add_argument("--alpha-thresh", type=int, default=16,
                   help="Alpha cutoff for what counts as subject.")
    s.add_argument("--model", default="u2net", help="rembg model.")

    c = sub.add_parser("center", help="Scale + center subjects on a canvas.")
    c.add_argument("input_dir", type=Path)
    c.add_argument("output_dir", type=Path)
    c.add_argument("--width", type=int, default=1080, help="Canvas width.")
    c.add_argument("--height", type=int, default=1920, help="Canvas height.")
    c.add_argument("--subject-frac", type=float, default=0.2,
                   help="Subject width as a fraction of canvas width.")
    c.add_argument("--alpha-thresh", type=int, default=16,
                   help="Alpha cutoff for what counts as subject.")
    c.add_argument("--background", choices=("transparent", "black"),
                   default="transparent", help="Letterbox fill.")
    c.add_argument("--no-letterbox-crop", action="store_true",
                   help="Skip the uniform crop of the shared letterbox.")
    c.add_argument("--model", default="u2net", help="rembg model.")

    v = sub.add_parser("video", help="Encode a folder of frames into an MP4.")
    v.add_argument("input_dir", type=Path)
    v.add_argument("output_video", type=Path)
    v.add_argument("--fps", type=int, default=10, help="Frames per second.")

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    if args.command == "silhouette":
        kept = silhouette.run(
            args.input_dir, args.output_dir,
            halo_px=args.halo_px,
            alpha_thresh=args.alpha_thresh,
            model=args.model,
        )
        return 0 if kept else 1

    if args.command == "center":
        kept = center.run(
            args.input_dir, args.output_dir,
            width=args.width,
            height=args.height,
            subject_frac=args.subject_frac,
            alpha_thresh=args.alpha_thresh,
            background=args.background,
            letterbox_crop=not args.no_letterbox_crop,
            model=args.model,
        )
        return 0 if kept else 1

    if args.command == "video":
        kept = video.run(args.input_dir, args.output_video, fps=args.fps)
        return 0 if kept else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
