# silhouette-slideshow

Composable steps that turn a folder of photos into a slideshow video.
Each step reads a folder of images and writes a folder of `NNNNN.png`
frames (or, for `video`, an MP4), so any step chains into any other.

## Requirements

- Python 3.10+
- `ffmpeg` on `PATH`
- First run downloads a ~176 MB segmentation model (cached in `~/.u2net`)
- HEIC/HEIF input is supported via `pillow-heif`

## Install

```sh
python3 -m venv .venv
source .venv/bin/activate          # do this in every new shell
pip install -e .
```

This installs the dependencies and a `slideshow` command **into the
venv**. You must use that venv to run it — either:

- **activate it** (`source .venv/bin/activate`) in each new terminal, then
  use `slideshow ...` (and `python`, which only exists once activated); or
- don't activate and call it directly: `.venv/bin/slideshow ...`.

Running the system `python3 -m slideshow` will fail with
`No module named slideshow` — that interpreter is not the venv.

> Running from source without installing: `PYTHONPATH=src python3 -m slideshow ...`

## Steps

With the venv activated:

```sh
slideshow silhouette <in_dir>  <out_dir>   # white halo around subject (keeps background)
slideshow center     <in_dir>  <out_dir>   # scale + center on a canvas
slideshow video      <in_dir>  <out.mp4>   # encode frames to MP4
```

Run `slideshow <step> --help` for that step's flags.

| Step         | Key flags | Default |
|--------------|-----------|---------|
| `silhouette` | `--halo-px` | `16` |
|              | `--alpha-thresh` | `16` |
|              | `--model` | `u2net` |
| `center`     | `--width` / `--height` | `1080` / `1920` |
|              | `--subject-frac` | `0.2` |
|              | `--background` | `transparent` (or `black`) |
|              | `--no-letterbox-crop` | off |
|              | `--alpha-thresh` / `--model` | `16` / `u2net` |
| `video`      | `--fps` | `10` |

## User stories (how to compose the steps)

```sh
# Center subjects, then make a video
slideshow center  ./photos      ./centered
slideshow video   ./centered    out.mp4

# Add silhouettes, then make a video
slideshow silhouette ./photos   ./halo
slideshow video      ./halo     out.mp4

# Just add silhouettes
slideshow silhouette ./photos   ./halo

# Silhouette, then center, then video
slideshow silhouette ./photos   ./halo
slideshow center     ./halo     ./centered
slideshow video      ./centered out.mp4
```

Each step detects the subject on its own, so they're standalone and
compose in any order — `center` finds the subject itself whether or not
`silhouette` ran first.

## How it works

- **silhouette** — segments the subject with `rembg` and paints a white
  halo ring around it on the *original photo* (background kept; input
  resolution, no scaling/positioning here).
- **center** — finds the subject, scales it to `subject-frac × width`,
  and centers it on both axes of the canvas. The letterbox margin shared
  by *every* frame is then cropped off uniformly (even-rounded for h264).
- **video** — flattens each frame onto black, centers it on a canvas sized
  to the largest frame, and stitches them with `ffmpeg`
  (`libx264`, CRF 18, faststart).
