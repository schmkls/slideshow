"""Single CLI exposing each step as a subcommand.

    python -m slideshow silhouette IN_DIR  OUT_DIR  [--halo-px N] ...
    python -m slideshow center     IN_DIR  OUT_DIR  [--width N] ...
    python -m slideshow fade   IN_DIR OUT_DIR --effect E [--target T] ...
    python -m slideshow linger IN_DIR OUT_DIR [--no-loop] [--target T] ...
    python -m slideshow place  IN_DIR OUT_DIR --motion M [--frames N] ...
    python -m slideshow pick-faces   IN_DIR         [--conf C] [--redo]
    python -m slideshow video        IN_DIR OUT.mp4 [--fps N] [--fade N]

Steps chain through directories, so they compose: e.g.
silhouette -> center -> video, or fade -> video, or place -> video, or
center -> linger -> video --fade.
``pick-faces`` writes a faces.json the --target faces steps read.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import center, pickfaces, silhouette, video
from .animate import fade, linger, place


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
    c.add_argument("--target", choices=("subject", "faces"), default="subject",
                   help="What to center on: whole subject (rembg) or faces only.")
    c.add_argument("--model", default="u2net",
                   help="rembg model (ignored when --target faces).")

    f = sub.add_parser(
        "fade", help="Expand each photo into the two keyframes of a fade clip."
    )
    f.add_argument("input_dir", type=Path)
    f.add_argument("output_dir", type=Path)
    f.add_argument("--effect", required=True, choices=tuple(fade.EFFECTS),
                   help="Which layer fades in: background or subject.")
    f.add_argument("--target", choices=("subject", "faces"), default="subject",
                   help="What to detect: whole subject (rembg) or faces only.")
    f.add_argument("--alpha-thresh", type=int, default=16,
                   help="Alpha cutoff for what counts as subject.")
    f.add_argument("--model", default="u2net",
                   help="rembg model (ignored when --target faces).")

    lg = sub.add_parser(
        "linger",
        help="Linger each photo's subject into the next photo.",
    )
    lg.add_argument("input_dir", type=Path)
    lg.add_argument("output_dir", type=Path)
    lg.add_argument("--no-loop", action="store_true",
                    help="Stop at the last photo instead of looping back to "
                         "the first.")
    lg.add_argument("--target", choices=("subject", "faces"), default="subject",
                    help="What to detect: whole subject (rembg) or faces only.")
    lg.add_argument("--alpha-thresh", type=int, default=16,
                    help="Alpha cutoff for what counts as subject.")
    lg.add_argument("--model", default="u2net",
                    help="rembg model (ignored when --target faces).")

    pl = sub.add_parser(
        "place", help="Expand each photo into a clip moving the subject."
    )
    pl.add_argument("input_dir", type=Path)
    pl.add_argument("output_dir", type=Path)
    pl.add_argument("--motion", required=True, choices=tuple(place.MOTIONS),
                    help="How the subject moves across the clip.")
    pl.add_argument("--frames", type=int, default=30,
                    help="Frames rendered per photo (play with plain video).")
    pl.add_argument("--target", choices=("subject", "faces"), default="subject",
                    help="What to detect: whole subject (rembg) or faces only.")
    pl.add_argument("--alpha-thresh", type=int, default=16,
                    help="Alpha cutoff for what counts as subject.")
    pl.add_argument("--model", default="u2net",
                    help="rembg model (ignored when --target faces).")

    pf = sub.add_parser(
        "pick-faces",
        help="Choose which detected face is the subject (writes faces.json).",
    )
    pf.add_argument("input_dir", type=Path)
    pf.add_argument("--conf", type=float, default=0.5,
                    help="Min detector confidence (0..1) for a face.")
    pf.add_argument("--det-size", type=int, default=900,
                    help="Detector input size; larger finds more (and smaller) "
                         "faces, but is slower. Try 1200 for dense crowds.")
    pf.add_argument("--redo", action="store_true",
                    help="Re-pick photos already in faces.json.")

    v = sub.add_parser("video", help="Encode a folder of frames into an MP4.")
    v.add_argument("input_dir", type=Path)
    v.add_argument("output_video", type=Path)
    v.add_argument("--fps", type=int, default=10, help="Frames per second.")
    v.add_argument("--fade", type=int, default=0,
                   help="Cross-dissolve each (start, end) input pair over N "
                        "frames (0: each image is one frame). Use with fade.")

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
            target=args.target,
        )
        return 0 if kept else 1

    if args.command == "fade":
        kept = fade.run(
            args.input_dir, args.output_dir,
            effect=args.effect,
            alpha_thresh=args.alpha_thresh,
            model=args.model,
            target=args.target,
        )
        return 0 if kept else 1

    if args.command == "linger":
        kept = linger.run(
            args.input_dir, args.output_dir,
            loop=not args.no_loop,
            alpha_thresh=args.alpha_thresh,
            model=args.model,
            target=args.target,
        )
        return 0 if kept else 1

    if args.command == "place":
        kept = place.run(
            args.input_dir, args.output_dir,
            motion=args.motion,
            frames=args.frames,
            alpha_thresh=args.alpha_thresh,
            model=args.model,
            target=args.target,
        )
        return 0 if kept else 1

    if args.command == "pick-faces":
        chosen = pickfaces.run(
            args.input_dir, conf_thresh=args.conf,
            det_size=args.det_size, redo=args.redo,
        )
        return 0 if chosen else 1

    if args.command == "video":
        kept = video.run(args.input_dir, args.output_video,
                         fps=args.fps, fade=args.fade)
        return 0 if kept else 1

    return 2


if __name__ == "__main__":
    sys.exit(main())
