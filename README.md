# pvrender.py

Render ParaView .pvsm state files from the command line using `pvpython` or `pvbatch`,
with many customizable options.

Automate your scientific visualization workflow, without coding in ParaView's Python API.

Designed to facilite rendering your ParaView state files on the command line and with
AI agents. All you need is:

- Your ParaView state file (`.pvsm`) created in the GUI
- A ParaView installation (optionally `.../ParaView-x.x.x/bin` available in your `PATH`)
- This script (`pvrender.py`) in your project

### Motivation

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

Requires ParaView 6.1 or newer (tested with 6.1.0). Only a standard ParaView installation is required. `pvpython` and `pvbatch`
can be found in the `path/to/ParaView-x.x.x/bin` directory. You can add them to your
`PATH` environment variable for convenient command line access.

The ParaView compatibility pin (6.1) is intentional and is not bumped per release.
Older versions trigger a warning at startup, and newer versions run under the 6.1
compatibility layer.

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

**Parameter study: render the same state for many runs, each fitted to its own data:**
```bash
pvbatch pvrender.py scene.pvsm -d runs/run_042/ -o out/run_042 --suffix --save-image \
    --fit-camera fit \
    --cb-data-range-all 1 --cb-title 1 "Displacement [m]" \
    --plot-data-range-all 1 y --plot-title 1 "Displacement, run 042"
```
Here `scene.pvsm` is the template run's state, `runs/run_042/` holds the new run's data, and
the output is `out/run_042_<datetime>.png`. The camera is fitted to this run's data, the
colorbar spans this run's global range, and plot 1's y axis fits this run's curves (find the
indices with `--list-colorbars` and `--list-plots`). Repeat the command per run, changing
`-d`, `-o` and the plot title. On Windows, `\` does not continue a line: write the command on one line, or continue with `^` in `cmd` or a backtick in PowerShell. Quote titles with double quotes.

If a reader's file is missing in the run folder, pvrender stops with an error instead of
silently rendering the template run's data; use `--keep-path READER` (names from
`--list-readers`) for a file that is meant to stay elsewhere, e.g. a shared reference file.

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

**Use a run folder, keeping a shared reference file from its original location:**
```bash
pvpython pvrender.py scene.pvsm --list-readers
pvpython pvrender.py scene.pvsm -d /data/run_004/ --keep-path reference.csv --save-image
```

**Render a run whose model is larger than the template run's, moving the camera out to fit:**
```bash
pvpython pvrender.py scene.pvsm -d /data/run_005/ --fit-camera out --save-image
```

**Center the camera on the data and zoom to fit with a 10 % margin:**
```bash
pvpython pvrender.py scene.pvsm -d /data/run_005/ --fit-camera fit --fit-margin 10 --save-image
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
| `--list-readers` | Print the index, name, used flag, and file path of every reader, then continue |
| `--keep-path READER` | Allow reader `READER` (name from `--list-readers`) to stay outside `--datadir`, e.g. a shared reference file. Its file must still exist. Repeatable. An unknown name is an error |
| `--allow-missing-data` | Turn the two data-path errors below into warnings |

`-d` and `--filenames` are mutually exclusive.

After loading, pvrender checks the readers that feed the rendered layout or view
(readers used only by other layouts or views are not checked):

- **Missing data fails.** If a reader's file does not exist, or a `.pvd` lists a file that
  does not exist, pvrender stops with `error: data files not found`, listing reader name and
  path.
- **Fallback to the template run fails.** With `-d DIR`, ParaView keeps a reader's original
  path from the state file when its file is not found under `DIR`. That original file
  usually still exists, so the image would silently show the template run's data. pvrender
  therefore stops when a reader still points outside `DIR` (any subfolder of `DIR` counts as
  inside). Use `--keep-path READER` for files that intentionally live elsewhere.
- With `--filenames`, readers you did not map are not an error; only the existence check
  applies.

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
| `--interp-interval DT` | Set the Discrete Time Step Interval of every Temporal Interpolator in the state, giving evenly spaced time steps. `0` keeps the original steps. Error if the state has no Temporal Interpolator or `DT < 0`. Warns if other sources still add their own time steps (set "Ignore Time" on them in ParaView). `--frame-*` indices count the new steps. Default: not set |
| `--size N` / `--size W H` | Layout size in pixels. One value sets the longest side and preserves aspect ratio; two values set exact size. Default: `1920` |
| `--fit-camera fit\|out` | Fit the camera of each rendered 3D view to the visible data, using the data bounds over the frame window (computed once, so the camera does not move between frames). The view direction and view up are kept. `fit`: center on the data and move in or out until it just fits. `out`: only move out (or widen a parallel projection) when the data does not fit; otherwise the state's camera is kept exactly. Chart and spreadsheet views are not changed. Warns when a representation has a non-identity Translation/Scale/Orientation (the fit uses the untransformed data bounds) and when a view shows nothing (its camera is left unchanged). Only the data bounds are fitted, not annotations (colorbar, axes grid labels, text): when the state shows a colorbar or an axes grid, use `--fit-margin 10` to `20` so they do not overlap the data or get clipped. Default: not set (camera as in the state) |
| `--fit-margin PCT` | Margin on each side for `--fit-camera`, in percent of the view size (`0 <= PCT < 50`). Default: `5` |
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
| `--cb-title N TEXT` | Set colorbar N's title. Repeatable. Pass `" "` (a single space) to clear it; `""` also works on shells that can pass it, but not through pvbatch on Windows |

**Common colormap choices (case-insensitive):**

<details>
<summary>Show commonly used colormaps for scientific visualization</summary>

**ParaView Defaults:**
`Fast`, `Turbo`, `Cool to Warm`, `Cool to Warm (Extended)`, `Black-Body Radiation`,
`X Ray`, `Inferno`, `Black, Blue and White`, `Blue Orange (divergent)`, `Viridis`,
`Cold and Hot`, `Linear Green (Gr4L)`, `Rainbow Desaturated`, `Blue - Green - Orange`,
`Rainbow Uniform`, `Yellow - Gray - Blue`

**Perceptually uniform sequential:**
`Viridis`, `Plasma`, `Inferno`, `Magma`, `Fast (Blues)`, `Fast (Reds)`, `Cividis`, `Turbo`

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
`erdc_iceFire_H`, `erdc_iceFire_L`, `erdc_rainbow_bright`, `erdc_rainbow_dark`


</details>

### Plots

Plot index `N` is 1-based (chart views in layout order); use `--list-plots` to discover them.
`AXIS` is `x`/`bottom`, `y`/`left`, `right` or `top` (case-insensitive).

| Option | Description |
|---|---|
| `--list-plots` | Print the index, type, title and axis settings (custom range, range, log) of each plot, then continue |
| `--plot-range N AXIS MIN MAX` | Fix plot N's axis range to [MIN, MAX]. Repeatable. |
| `--plot-data-range-all N AXIS` | Axis range = data range over all frames of the frame window, applied once |
| `--plot-data-range-grow N AXIS` | Per-frame range that grows to include each frame's data and never shrinks (`--save-image` uses the frame at `--time`) |
| `--plot-auto N AXIS` | Use the automatic axis range (overrides a custom range in the state) |
| `--plot-sym N AXIS` | Symmetrize around zero; needs `--plot-data-range-all` or `--plot-data-range-grow` for the same axis |
| `--plot-log N AXIS on\|off` | Logarithmic axis scale. A fixed range on a log axis needs `MIN > 0` |
| `--plot-title N TEXT` | Set plot N's title. Repeatable. Pass `" "` to clear it (see below) |
| `--plot-axis-title N AXIS TEXT` | Set an axis title. Repeatable. Pass `" "` to clear it (see below) |

Range modes are mutually exclusive per plot axis.

**Data ranges** (`--plot-data-range-all` / `-grow`) come from what the chart actually draws:

- `y`/`left` and `right`: the visible series plotted on that axis (a series moved to the right axis in ParaView counts for `right` only).
- `x`/`bottom` and `top`: the X array of those series (point coordinates such as `Points_X` use the data bounds), or the point/row index when "Use Index For X Axis" is on.
- Plot Data Over Time statistics series span their `min(…)` to `max(…)` arrays, so the quartile and range bands fit.
- Series of a block (e.g. Plot Data Over Time per point, `… (id=0)`) use only that block's data; a visible series whose block the chart does not show draws nothing and is ignored.
- `--plot-sym` is applied first, then 5 % of the span is added on each side so curves don't sit on the frame (in log space on a log axis). Fixed ranges (`--plot-range`) are used as given.
- On a log axis a computed lower bound ≤ 0 is clipped to max / 1000, with a warning.
- An axis with no visible series, or whose data is a single value, keeps its range from the state, with a warning.

In a parameter study, `--plot-data-range-all` fits each run's own data, so a run with larger values is never cut off. Use `--plot-range` when the axes must be identical across runs for side-by-side comparison.

To clear a title (`--plot-title`, `--plot-axis-title`, `--cb-title`) pass a single space (`" "`); an empty string `""` also works on shells that can pass it, but not through pvbatch on Windows.

### Screenshot (`--save-image` / `--si`)

| Option | Description |
|---|---|
| `--save-image`, `--si` | Save a screenshot |
| `--image-format FMT` | Format: `png` (default), `bmp`, `jpg`, `jpeg`, `tif`, `tiff`, `vtk` |
| `--image-resolution N` / `--image-resolution W H` | Override output image resolution (independent of `--size`). One value sets the longest side |
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

Note: for a scene in `Sequence` mode, ParaView 6.1's SaveAnimation skips frame start + 1 when the window starts after frame 0 (ParaView's own behaviour, not pvrender's).

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

pvrender only inspects representations that already exist in the state and never creates new ones, so renders show exactly what the GUI state shows (colorbar ranges and camera fits ignore sources the state does not display).

Chart representations of composite data (e.g. Plot Data Over Time) only get their saved block selection back from ParaView once their input has been read, and pvbatch would not pass it on before rendering, so such a chart came out empty. pvrender reads the inputs of the displayed charts after loading and passes the saved selection on, so the charts draw the series the state shows. No chart setting is changed.

Pull requests to fix bugs or improve functionality are welcome!

Tested with ParaView 6.1.0.

---

Licensed under the [MIT License](LICENSE).
