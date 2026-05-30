# silhouette-slideshow

Composable steps that turn a folder of photos into a slideshow video.
Each step reads a folder of images and writes a folder of `NNNNN.png`
frames (or, for `video`, an MP4), so any step chains into any other.

## Requirements

- Python 3.10+
- `ffmpeg` on `PATH`
- First run downloads a ~176 MB segmentation model (cached in `~/.u2net`)
- First `--target faces` run downloads a ~5 MB face model (cached in `~/.slideshow`)
- HEIC/HEIF input is supported via `pillow-heif`

## Install

```sh
python3 -m venv .venv
source .venv/bin/activate          # do this in every new shell
pip install -e .
```

This installs the dependencies and a `slideshow` command into the venv. Run it
either by activating the venv (`source .venv/bin/activate`) and calling
`slideshow ...`, or directly via `.venv/bin/slideshow ...`. The system
`python3 -m slideshow` won't work — that interpreter isn't the venv.

> Run from source without installing: `PYTHONPATH=src python3 -m slideshow ...`

## Steps

With the venv activated:

```sh
slideshow silhouette <in_dir>  <out_dir>   # white halo around subject (keeps background)
slideshow center     <in_dir>  <out_dir>   # scale + center on a canvas
slideshow animate    <in_dir>  <out_dir>   # expand each photo into an animated clip
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
|              | `--target` | `subject` (or `faces`) |
|              | `--alpha-thresh` / `--model` | `16` / `u2net` |
| `animate`    | `--effect` | *(required:* `fade-background` \| `fade-subject`*)* |
|              | `--target` | `subject` (or `faces`) |
|              | `--alpha-thresh` / `--model` | `16` / `u2net` |
| `video`      | `--fps` | `10` |
|              | `--fade` | `0` (frames per dissolve; use with `animate`) |

## Examples (composing the steps)

```sh
# Center subjects, then make a video
slideshow center  ./photos      ./centered
slideshow video   ./centered    out.mp4

# Add silhouettes, then make a video
slideshow silhouette ./photos   ./halo
slideshow video      ./halo     out.mp4

# Just add silhouettes
slideshow silhouette ./photos   ./halo

# Animate: fade each photo's background in, then make a video
slideshow animate ./photos      ./frames --effect fade-background
slideshow video   ./frames      out.mp4 --fade 30

# Animate: fade each photo's subject in instead
slideshow animate ./photos      ./frames --effect fade-subject
slideshow video   ./frames      out.mp4 --fade 30

# Center on faces only (instead of the whole subject)
slideshow center  ./photos    ./centered --target faces
slideshow video   ./centered  out.mp4

# Silhouette, then center, then video
slideshow silhouette ./photos   ./halo
slideshow center     ./halo     ./centered
slideshow video      ./centered out.mp4
```

Each step detects the subject on its own, so they're standalone and
compose in any order — `center` finds the subject itself whether or not
`silhouette` ran first.

## How it works

- **silhouette** — segments the subject with `rembg` and paints a white halo
  ring around it on the original photo. Background and resolution are kept;
  scaling and positioning are the `center` step's job.
- **center** — finds the subject, scales it to `subject-frac × width`, and
  centers it on the canvas. With `--target faces` it centers on detected faces
  instead (OpenCV's res10 detector). The letterbox margin shared by every frame
  is then cropped off uniformly (rounded to even dimensions for h264).
- **animate** — detects the subject once per photo and writes the two keyframes
  of its clip. `fade-background` writes the subject on black, then the full
  photo; `fade-subject` does the reverse. `video --fade` dissolves between each
  pair, so only two stills per photo are written.
- **video** — flattens each frame onto black, centers it on a canvas sized to
  the largest frame, and encodes with `ffmpeg` (`libx264`, CRF 18, faststart).
  With `--fade N` it reads the folder as `(start, end)` pairs and cross-dissolves
  each pair over `N` frames.
