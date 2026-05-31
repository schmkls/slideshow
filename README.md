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
slideshow fade       <in_dir>  <out_dir>   # two keyframes per photo for a cross-dissolve
slideshow place      <in_dir>  <out_dir>   # move the subject (shrink/grow/slide/rotate)
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
| `fade`       | `--effect` | *(required:* `background` \| `subject`*)* |
|              | `--target` | `subject` (or `faces`) |
|              | `--alpha-thresh` / `--model` | `16` / `u2net` |
| `place`      | `--motion` | *(required:* `shrink` \| `grow` \| `left-to-right` \| `grow-and-rotate`*)* |
|              | `--frames` | `30` |
|              | `--target` | `subject` (or `faces`) |
|              | `--alpha-thresh` / `--model` | `16` / `u2net` |
| `video`      | `--fps` | `10` |
|              | `--fade` | `0` (frames per dissolve; use with `fade`) |

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

# Fade each photo's background in, then make a video
slideshow fade  ./photos      ./frames --effect background
slideshow video ./frames      out.mp4 --fade 30

# Fade each photo's subject in instead
slideshow fade  ./photos      ./frames --effect subject
slideshow video ./frames      out.mp4 --fade 30

# Place: grow each photo's subject until it fills the frame, then make a video
# (plain video — place already rendered every frame, so no --fade)
slideshow place ./photos      ./frames --motion grow
slideshow video ./frames      out.mp4

# Place: slide each subject in from the left
slideshow place ./photos      ./frames --motion left-to-right --frames 24
slideshow video ./frames      out.mp4

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
- **fade** — detects the subject once per photo and writes the two keyframes
  of its clip. `--effect background` writes the subject on black, then the full
  photo; `--effect subject` does the reverse. `video --fade` dissolves between
  each pair, so only two stills per photo are written.
- **place** — moves the subject geometrically, which a cross-dissolve can't
  fake, so it renders every frame itself (`--frames` per photo) and is played
  by a plain `video`. The subject is detected once, then each frame resizes /
  rotates / pastes that subject sprite onto the original photo: `shrink` and
  `grow` scale it, `left-to-right` slides it, `grow-and-rotate` grows it while
  wobbling ±45°.
- **video** — flattens each frame onto black, centers it on a canvas sized to
  the largest frame, and encodes with `ffmpeg` (`libx264`, CRF 18, faststart).
  With `--fade N` it reads the folder as `(start, end)` pairs and cross-dissolves
  each pair over `N` frames.
