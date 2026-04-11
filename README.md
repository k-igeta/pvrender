# pvrender.py

Render ParaView .pvsm state files from the command line using `pvpython` or `pvbatch`,
with many customizable options.

Automate your scientific visualization workflow, without coding in ParaView's Python API.

## Motivation

Complex visualizations are easily created in the [ParaView](https://www.paraview.org/)
GUI and can be saved as **XML based .pvsm state files or Python .py script files**.

However, data file paths are stored as absolute paths. This prohibits relocating
files to another computer as well as command line automated rendering with different
data files, without clicking through the GUI to update paths or manually editing the
.pvsm/.py files. Furthermore, any modification to the .pvsm/.py files is lost when
saving a new state after tweaking the visualization in the GUI.

**`pvrender.py` is a scripting layer between .pvsm state files and ParaView's Python
interpreters `pvpython`/`pvbatch`, with options to change data paths, save screenshots,
animations and extracts, or save a new .pvsm file with relocated paths.**

It allows you to keep tweaking your visualization in the GUI without knowledge of the
ParaView Python API. Simply save your state as a .pvsm file and `pvrender.py` allows you
to render it with different data files or on another computer. All from the command line,
without modifying files manually or writing Python code.

## Requirements

`pvrender.py` requires no setup. It is a standalone Python script to translate
command line options to ParaView's Python API when executed with `pvpython` or `pvbatch`.

Only a standard ParaView installation is required. `pvpython` and `pvbatch`
can be found in the `path/to/ParaView-x.x.x/bin` directory. You can add them to your
`PATH` environment variable for convenient command line access.

## Usage

```
pvpython pvrender.py <statefile.pvsm> [options]
pvbatch  pvrender.py <statefile.pvsm> [options]
```

Use `pvpython` for interactive use before saving outputs (`--interact`). For non-interactive
usage, add `--force-offscreen-rendering` before the script name to suppress the render window
or use `pvbatch` for fully headless/offscreen rendering (e.g. on a server).

Common options:

- Set data directory:                   `--datadir DIR`  (`-d`)
- Set output name (without extension):  `--outputname NAME`  (`-o`)
- Save a screenshot:                    `--save-image`  (`--si`)
- Save an animation:                    `--save-animation` (`--sa`)
- Save pipeline extracts:               `--save-extracts`  (`--se`)
- Save a relocated state file:          `--save-state`  (`--ss`)
- Preview interactively:                `--interact` (`-i`)

## Examples

**Save a screenshot of a state with a datetime file name:**
```bash
pvpython pvrender.py scene.pvsm --save-image --suffix
```

**Save a screenshot with data in a different directory:**
```bash
pvpython pvrender.py scene.pvsm -d /data/run_002/ --save-image
```

**Map a specific reader to a new file path:**
```bash
pvpython pvrender.py scene.pvsm --filenames "{'MyReader.pvd': '/data/run_003/result.pvd'}" --save-image
```

**Save a screenshot with custom file name and with a white background:**
```bash
pvpython pvrender.py scene.pvsm -o results/mises_stress --save-image --palette white
```

**Save a screenshot of a specific view at 640 px wide (height scaled to preserve aspect ratio):**
```bash
pvpython pvrender.py scene.pvsm --save-image --view 2 --image-resolution 640
```

**Save a screenshot at a specific time, 1920×1080, JPEG:**
```bash
pvpython pvrender.py scene.pvsm --save-image --time 5.0 --size 1920 1080 --image-format jpg
```

**Save an MP4 animation at 10 fps:**
```bash
pvpython pvrender.py scene.pvsm --save-animation --framerate 10
```

**Save an animation covering only frames 10–50:**
```bash
pvpython pvrender.py scene.pvsm --save-animation --frame-start 10 --frame-end 50
```

**Save an animation as a PNG image sequence:**
```bash
pvpython pvrender.py scene.pvsm --save-animation --animation-format png
```

**Save both a screenshot and an animation in one run:**
```bash
pvpython pvrender.py scene.pvsm --save-image --save-animation -o output/render
```

**Save pipeline extracts (e.g. configured in the GUI via Extractors):**
```bash
pvpython pvrender.py scene.pvsm --save-extracts -o output/extracts
```

**Save a relocated state file (with new paths and options baked in):**
```bash
pvpython pvrender.py scene.pvsm -d /data/run_002/ -o newstate --save-state
```

**Open an interactive window (useful for adjustments before saving, press q to continue):**
```bash
pvpython pvrender.py scene.pvsm -d /data/run_002/ --interact
```

**Fix colorbar 1 to an explicit range (0 to 500):**
```bash
pvpython pvrender.py scene.pvsm --cb-range 1 0 500 --save-image
```

**Auto-range colorbar 1 from global data range (all time steps):**
```bash
pvpython pvrender.py scene.pvsm --cb-data-range-all 1 --save-image
```

**Same but symmetrized around zero:**
```bash
pvpython pvrender.py scene.pvsm --cb-data-range-all 1 --cb-sym 1 --save-animation
```

**Per-frame clamp — color range tracks data at each time step:**
```bash
pvpython pvrender.py scene.pvsm --cb-data-range-clamp 1 --save-animation
```

**Per-frame grow, symmetrized, for two colorbars at once:**
```bash
pvpython pvrender.py scene.pvsm --cb-data-range-grow 1 2 --cb-sym 1 2 --save-animation
```

## Options

### Input

| Option | Description |
|---|---|
| `statefile` | Path to the `.pvsm` state file to load (required) |
| `-d`, `--datadir DIR` | Redirect all data file paths to a new directory (matched by filename) |
| `--restrict-to-datadir` | Only load files found inside `--datadir`; fail on missing files |
| `-f`, `--filenames DICT` | Explicitly map reader names to new file paths: `"{'reader.pvd': 'path/to/file.pvd'}"` |

`-d` and `--filenames` are mutually exclusive.

### Output

| Option | Description |
|---|---|
| `-o`, `--outputname NAME` | Output path/name without extension. Directories are created automatically. Default: `rendered` |
| `--suffix` | Append a `_YYYYMMDD_HHMMSS` datetime suffix to the output name |

### Layout and view

| Option | Description |
|---|---|
| `--list-layouts` | Print the index, name, and size of every layout in the state file, then continue |
| `--layout INDEX\|NAME` | Layout to render, by one-based index or name (e.g. `"Layout #1"`). Default: `1` |
| `--list-views` | Print the index, type, and size of every view in the selected layout, then continue |
| `--view INDEX` | One-based index of a single view within the layout. Default: `0` (all views) |
| `--size W [H]` | Layout size in pixels. One value scales width and preserves aspect ratio; two values set exact size. Default: `1920` |
| `--palette NAME` | Background color palette. Default: `warmgray` |
| `--time T` | Timestep to render. Default: last timestep |

**Palette choices:** `gray` == `warmgray`, `darkgray`, `neutralgray`, `lightgray`,
`white`, `black`, `gradient`.

### Colorbars

| Option | Description |
|---|---|
| `--list-colorbars` | Print the index, array name, and current range of each colorbar, then continue |
| `--cb-range N MIN MAX` | Set colorbar N's range to [MIN, MAX]. Repeatable. |
| `--cb-data-range-all N [N …]` | Set colorbar N's range to the global min/max across **all** time steps (applied once) |
| `--cb-data-range-clamp N [N …]` | Per-frame: set colorbar N's range to the data range at each time step |
| `--cb-data-range-grow N [N …]` | Per-frame: grow colorbar N's range monotonically; never shrinks |
| `--cb-sym N [N …]` | After any `--cb-data-range-*` mode: symmetrize to `[-A, +A]` where `A = max(\|min\|, \|max\|)` |
| `--list-colormaps` | Print a sorted, numbered list of all available colormap preset names (for use with `--cb-colormap`), then continue |
| `--cb-colormap N COLORMAP` | Set colorbar N's colormap to a ParaView preset name (case-insensitive). Repeatable. |
| `--cb-discretize N STEPS` | Divide colorbar N's colormap into STEPS uniform color bands (integer ≥ 2). Repeatable. |

**Common colormap choices (case-insensitive):**

<details>
<summary>Show commonly used colormaps for scientific visualization</summary>

**ParaView Defaults:**
`Fast`, `Turbo`, `Cool to Warm`, `Cool to Warm (Extended)`, `Black-Body Radiation`,
`Fast (Blues)`, `Fast (Reds)`, `X Ray`, `Inferno`, `Black, Blue and White`,
`Blue Orange (divergent)`, `Viridis`, `Cold and Hot`, `Linear Green (Gr4L)`,
`Rainbow Desaturated`, `Blue - Green - Orange`, `Rainbow Uniform`, `Yellow - Gray - Blue`

**Perceptually uniform sequential:**
`Viridis`, `Plasma`, `Inferno`, `Magma`, `Cividis`, `Turbo`

**Diverging:**
`Cool to Warm`, `Cool to Warm (Extended)`, `Warm to Cool`, `Warm to Cool (Extended)`,
`Blue Orange (divergent)`, `CIELab Blue to Red`, `Cold and Hot`,
`BrBG`, `PRGn`, `PiYG`, `PuOr`, `BuRd`

**Sequential:**
`Blues`, `Greens`, `Reds`, `Oranges`, `Purples`, `BuGn`, `BuPu`, `Grayscale`

**Rainbow / multi-hue:**
`Blue to Red Rainbow`, `Rainbow Desaturated`, `Rainbow Uniform`,
`Rainbow Blended White`, `Rainbow Blended Black`, `Rainbow Blended Grey`,
`Spectrum`, `Jet`, `Fast`

**Specialized scientific:**
`Black-Body Radiation`, `X Ray`, `Gray and Red`,
`Green-Blue Asymmetric Divergent (62Blbc)`, `Haze`,
`erdc_iceFire_H`, `erdc_iceFire_L`, `erdc_rainbow_bright`, `erdc_rainbow_dark`,
`   `

</details>

### Screenshot (`--save-image` / `--si`)

| Option | Description |
|---|---|
| `--save-image`, `--si` | Save a screenshot |
| `--image-format FMT` | Format: `png` (default), `bmp`, `jpg`, `jpeg`, `tif`, `tiff`, `vtk` |
| `--image-resolution W [H]` | Override output image resolution (independent of `--size`) |
| `--output-palette NAME` | Override background palette for the saved image only |
| `--transparent-background` | Save with a transparent background (PNG/TIFF only) |
| `--no-font-scaling` | Disable proportional font scaling |

### Animation (`--save-animation` / `--sa`)

| Option | Description |
|---|---|
| `--save-animation`, `--sa` | Save an animation |
| `--animation-format FMT` | Format: `mp4` (default), `avi`, `ogv`, `png`, `jpg`, `jpeg`, `tif`, `tiff` |
| `--framerate N` | Frames per second. Default: `30` |
| `--frame-start N` | First frame index (zero-based). Default: `0` |
| `--frame-end N` | Last frame index (zero-based, inclusive). Default: last frame |
| `--frame-stride N` | Step between frames. Default: `1` |
| `--bitrate N` | MP4 bitrate in bps. Default: auto-estimated from resolution and framerate |
| `--motion-factor F` | Motion factor for bitrate estimation (`0.05`–`0.2`). Default: `0.1` |
| `--output-palette NAME` | Override background palette for the saved animation only |
| `--no-font-scaling` | Disable proportional font scaling |

### Extracts (`--save-extracts` / `--se`)

| Option | Description |
|---|---|
| `--save-extracts`, `--se` | Run SaveExtracts (uses Extractor filters configured in the GUI) |
| `--frame-start N` | First frame index. Default: `0` |
| `--frame-end N` | Last frame index. Default: last frame |
| `--frame-stride N` | Step between frames. Default: `1` |
| `--framerate N` | Framerate passed to extractors that support it. Default: `30` |

### State file (`--save-state` / `--ss`)

| Option | Description |
|---|---|
| `--save-state`, `--ss` | Save the loaded state (with resolved absolute data paths) to `<outputname>.pvsm` |

### Interactive

| Option | Description |
|---|---|
| `-i`, `--interact` | Open an interactive render window after loading. Press `q` to continue. |

## Implementation

Pull requests to fix bugs or improve functionality are welcome!

Tested with ParaView 6.1.0.

---

Licensed under the [MIT License](LICENSE).
