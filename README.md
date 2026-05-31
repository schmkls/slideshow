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
slideshow mask         <in_dir>              # detect each subject once, write its .mask.png sidecar
slideshow silhouette   <in_dir>  <out_dir>   # white halo around subject (keeps background)
slideshow center       <in_dir>  <out_dir>   # scale + center on a canvas
slideshow fade         <in_dir>  <out_dir>   # two keyframes per photo for a cross-dissolve
slideshow linger       <in_dir>  <out_dir>   # linger each subject into the next photo
slideshow place        <in_dir>  <out_dir>   # move the subject (shrink/grow/slide/rotate)
slideshow pick-faces   <in_dir>              # pick one face per photo (writes faces.json)
slideshow video        <in_dir>  <out.mp4>   # encode frames to MP4
```

`mask` detects each subject **once** and writes a `<stem>.mask.png` beside the
photo; every other step reads that mask instead of redetecting. So **run `mask`
first** — the manipulation steps abort if a photo has no mask. `silhouette` and
`center` carry the (co-transformed) mask through to their output, so a chain
like `mask → center → silhouette` detects exactly once.

Run `slideshow <step> --help` for that step's flags.

| Step         | Key flags | Default |
|--------------|-----------|---------|
| `mask`       | `--target` | `subject` (or `faces`) |
|              | `--model` | `u2net` (ignored when `--target faces`) |
| `silhouette` | `--halo-px` | `16` |
|              | `--alpha-thresh` | `16` |
| `center`     | `--width` / `--height` | `1080` / `1920` |
|              | `--subject-frac` | `0.2` |
|              | `--background` | `transparent` (or `black`) |
|              | `--no-letterbox-crop` | off |
|              | `--alpha-thresh` | `16` |
| `fade`       | `--effect` | *(required:* `background` \| `subject`*)* |
|              | `--alpha-thresh` | `16` |
| `linger`     | `--no-loop` | off (loops last → first) |
|              | `--alpha-thresh` | `16` |
| `place`      | `--motion` | *(required:* `shrink` \| `grow` \| `left-to-right` \| `grow-and-rotate`*)* |
|              | `--frames` | `30` |
|              | `--alpha-thresh` | `16` |
| `pick-faces` | `--conf` | `0.5` (min face-detector confidence) |
|              | `--det-size` | `900` (detector input size; larger = more faces, slower) |
| `video`      | `--fps` | `10` |
|              | `--fade` | `0` (frames per dissolve; use with `fade`) |

## Examples (composing the steps)

Every chain starts with `mask` (detect once); the rest read that mask.

```sh
# Center subjects, then make a video
slideshow mask    ./photos
slideshow center  ./photos      ./centered
slideshow video   ./centered    out.mp4

# Add silhouettes, then make a video
slideshow mask       ./photos
slideshow silhouette ./photos   ./halo
slideshow video      ./halo     out.mp4

# Just add silhouettes
slideshow mask       ./photos
slideshow silhouette ./photos   ./halo

# Fade each photo's background in, then make a video
slideshow mask  ./photos
slideshow fade  ./photos      ./frames --effect background
slideshow video ./frames      out.mp4 --fade 30

# Fade each photo's subject in instead
slideshow mask  ./photos
slideshow fade  ./photos      ./frames --effect subject
slideshow video ./frames      out.mp4 --fade 30

# Linger: carry each photo's subject into the next photo, looping back to the
# first. Center first so the subjects share a canvas — center carries the mask
# through, so linger reads it without redetecting.
slideshow mask   ./photos
slideshow center ./photos    ./centered
slideshow linger ./centered  ./frames
slideshow video  ./frames    out.mp4 --fade 20

# Place: grow each photo's subject until it fills the frame, then make a video
# (plain video — place already rendered every frame, so no --fade)
slideshow mask  ./photos
slideshow place ./photos      ./frames --motion grow
slideshow video ./frames      out.mp4

# Place: slide each subject in from the left
slideshow mask  ./photos
slideshow place ./photos      ./frames --motion left-to-right --frames 24
slideshow video ./frames      out.mp4

# Center on faces only (instead of the whole subject): mask the faces, not the
# whole subject — every later step just reads the mask, with no --target of its own.
slideshow mask    ./photos --target faces
slideshow center  ./photos    ./centered
slideshow video   ./centered  out.mp4

# Several faces per photo? Pick one first, then mask --target faces uses it.
# pick-faces opens each multi-face photo: arrow keys to choose, Enter to confirm,
# Esc to skip (single-face photos are auto-chosen). It writes ./photos/faces.json.
slideshow pick-faces ./photos
slideshow mask       ./photos    --target faces
slideshow center     ./photos    ./centered
slideshow video      ./centered  out.mp4

# Silhouette, then center, then video. mask once; silhouette and center each
# carry the mask through, so center never redetects.
slideshow mask       ./photos
slideshow silhouette ./photos   ./halo
slideshow center     ./halo     ./centered
slideshow video      ./centered out.mp4
```

Detection lives in `mask` alone — the manipulation steps consume the mask it
writes (and `silhouette` / `center` co-transform and pass it on), so a whole
chain detects the subject exactly once.

## How it works

- **mask** — the one place detection happens. Segments each subject with
  `rembg` (or, with `--target faces`, OpenCV's res10 face detector) and writes
  it as a `<stem>.mask.png` beside the photo: a single-channel `L` mask, soft
  for subjects (rembg's alpha edges, kept for clean compositing) and hard
  ellipses for faces. A mask is written for *every* photo — all-zero when
  nothing is detected — so a later step can tell "no subject here" from "you
  forgot to run `mask`". Always overwrites; re-run with a different `--target` /
  `--model` to replace the masks. Every other step reads these masks instead of
  redetecting, and `silhouette` / `center` carry the (co-transformed) mask
  through to their output, so a whole chain detects exactly once.
- **silhouette** — reads each photo's mask and paints a white halo ring around
  the subject on the original photo, then carries the mask through unchanged.
  Background and resolution are kept; scaling and positioning are the `center`
  step's job.
- **center** — reads the mask, scales the subject to `subject-frac × width`, and
  centers it on the canvas. The letterbox margin shared by every frame is then
  cropped off uniformly (rounded to even dimensions for h264). The mask is
  resized, offset, and cropped by the *same* transform and written beside the
  centered frame, so it stays aligned for later steps.
- **pick-faces** — when a photo has several faces, `mask --target faces`
  otherwise keys on all of them at once. This interactive step opens each
  multi-face photo in an OpenCV window and records the choice to a `faces.json`
  next to the photos: **arrow keys / 1-9** move the highlight, **Enter** confirms
  the face, **X or Delete** excludes the photo, **Esc** skips choosing (keeps all
  faces). Single-face photos are auto-chosen; every run re-picks fresh and
  overwrites `faces.json`. `mask --target faces` reads that sidecar — when run on
  the same folder — and masks the chosen face alone; an excluded photo (`null` in
  the sidecar) yields an empty mask, so the manipulation steps drop it. Photos
  without an entry fall back to all faces.

  Detection (res10) letterboxes each photo onto a `--det-size` square (default
  900) rather than the model's native 300, so small faces in group shots aren't
  squashed away; overlapping boxes are merged with NMS. Raise `--det-size` (e.g.
  1200) to find more/smaller faces, or `--conf` to drop weak false positives.
- **fade** — reads each photo's mask and writes the two keyframes of its clip.
  `--effect background` writes the subject on black, then the full photo;
  `--effect subject` does the reverse. `video --fade` dissolves between each
  pair, so only two stills per photo are written.
- **linger** — carries each photo's subject into the next photo. Per transition
  it writes the keyframes `A → K → B`, where `K` is the next photo with the
  current subject pasted on top; `video --fade` dissolves the shared-endpoint
  pairs `(A, K)` and `(K, B)` so the subject arrives in the next scene and then
  dissolves away as it resolves. Loops back to the first photo unless
  `--no-loop`. Subjects are composited at their original position, so run
  `center` first to put every photo on one canvas.
- **place** — moves the subject geometrically, which a cross-dissolve can't
  fake, so it renders every frame itself (`--frames` per photo) and is played
  by a plain `video`. It crops the subject sprite from the photo's mask, then
  each frame resizes / rotates / pastes that sprite onto the original photo:
  `shrink` and `grow` scale it, `left-to-right` slides it, `grow-and-rotate`
  grows it while wobbling ±45°.
- **video** — flattens each frame onto black, centers it on a canvas sized to
  the largest frame, and encodes with `ffmpeg` (`libx264`, CRF 18, faststart).
  With `--fade N` it reads the folder as `(start, end)` pairs and cross-dissolves
  each pair over `N` frames.
