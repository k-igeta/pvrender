# pvrender: parameter-study robustness and controls — design

Date: 2026-10-16
Status: ready for review

## Intent

`pvrender.py` renders a ParaView `.pvsm` state file from the command line
(`pvbatch`/`pvpython`). Its main real use is a **parameter study**: the same
state file is re-rendered over and over against different simulation results
(`-d <run dir>`), unattended. Each run's data can differ in spatial extent,
data ranges and time stepping (simulations use adaptive time stepping).

Today, outputs from such a batch quietly go wrong: tall images come out too
big, the model is cut off when its extent changes, line plots cut off data
or jump around, plots and colorbars can't be labelled per run, and some bad
inputs still exit 0 with a wrong picture. This work makes a batch of runs
produce correct, comparable, labelled outputs without anyone opening the GUI.

## Goals

1. Output size fits inside a box (default 1920 × 1920), keeping aspect ratio.
2. Optional camera fit so a model of a different extent is never cut off.
3. Line plot axis control (X and Y), mirroring the existing colorbar range
   controls, plus log scale.
4. Titles from the CLI: chart titles, chart axis titles, colorbar titles.
5. One CLI number for the Temporal Interpolator "Discrete time step interval"
   on all interpolators in the pipeline (real-time animations).
6. Fail loudly on bad input instead of producing a wrong output with exit 0.
7. Tests that check the effect of options, not just that a file was written.

## Non-goals

- Python state files (`.py`) as input. Investigated; dropped for now.
- Rendering several runs/data dirs in one invocation (batch mode).
- Supporting ParaView versions older than 6.1 (see Compatibility).
- Splitting `pvrender.py` into a package. It stays a single, copyable script.

## Anti-goals (would make this a failure even if it works)

- Any change in output for someone who passes none of the new flags, other
  than the two intended default changes: the size box (goal 1) and failing
  on missing data (goal 6).
- Silently wrong output: a computed range, fit or setting that falls back to
  a default without telling the user.
- Per-frame "jitter" introduced by our own features (camera zooming every
  frame, axes jumping when the user asked for a stable range).

## Constraints

- Single file `pvrender.py`, run by `pvbatch`/`pvpython`. No dependencies
  beyond a standard ParaView install.
- Must work headless (`pvbatch`).
- ParaView 6.1 is the reference version (installed at
  `C:\Program Files\ParaView 6.1.0`).
- Follow the existing CLI style: 1-based indices discovered via `--list-*`,
  repeatable flags with `action='append'`, validation before any rendering,
  `SystemExit("error: ...")` messages.
- Existing behavior for colorbars stays as is, including
  `_disable_auto_rescale` (the last commit's fix).

## Decided by the user

- **Size:** maximum 1920 for both width and height, aspect ratio kept.
- **Camera fit:** wanted, **off by default**. When on, it fits **once** for an
  animation (no zooming frame to frame), keeping the state's camera angle.
- **Temporal interpolation:** a single number sets `DiscreteTimeStepInterval`
  on **all** `TemporalInterpolator` filters in the pipeline. `0` means
  "use the original time steps" (ParaView's meaning).
- **Line plots:** axis ranges controllable from the CLI with modes like the
  colorbars (fixed, data range over all time steps, grow, ParaView's own
  auto refit). **Both X and Y axes.**
- **Titles:** colorbar titles and plot titles from the CLI.
- **Python state support:** dropped for now.
- **Compatibility:** keep `paraview.compatibility` pinned at 6.1 (see below).

## Design

### 1. Output size box

- `--size N` (one value) now means: scale the layout so its **longest side is
  N**, aspect ratio kept. Default `--size 1920`. A 2145×777 layout becomes
  1920×695; a 600×900 layout becomes 1280×1920.
- `--size W H` (two values) unchanged: exact size.
- `--image-resolution N` (one value) gets the same "longest side" meaning,
  for consistency. Two values unchanged; 0 / omitted unchanged.
- Small layouts are scaled up to the box, as today's width scaling does.
- *My call:* one-value semantics change rather than adding a new flag. For
  wide layouts (the common case) results are identical to today.

### 2. Camera fit — `--fit-camera`

- Off by default. When on, applies to every render view (3D/2D) in the
  rendered layout or view; chart and spreadsheet views are ignored.
- The user wants control over the fit, including zooming **in** for a
  smaller model, not only zooming out. Two modes (*proposed in chat,
  not objected to*):
  - `--fit-camera fit`: always fit the model tightly — zoom in or out — and
    re-center on the bounds' center. View direction and view-up stay as in
    the state. Use a tight fit to the bounding box (ParaView's
    `ResetCamera(bounds, closest=True)` or equivalent), not the default
    bounding-sphere fit, which leaves the model small.
  - `--fit-camera out`: only zoom out. If the bounds already fit, the camera
    stays exactly as in the state. Otherwise keep direction, view-up and focal
    point, and increase camera distance (perspective) or parallel scale
    (parallel projection) by the smallest amount that puts all eight
    bounding-box corners inside the viewport.
  - `--fit-margin PCT`: padding around the model as a percentage of the
    viewport, default 5. Applies to both modes.
- Bounds = union of the bounds of all **visible** representations in that
  view, over **all frames of the animation frame window**
  (`--frame-start/end/stride`). The same fit is used for `--save-image` and
  `--save-animation`, so a screenshot and a video of the same run are framed
  identically. *My call* (a tighter fit for the screenshot's own time step was
  the alternative).
- Fit happens once before saving; no per-frame cue.

### 3. Temporal interpolation — `--interp-interval DT`

- Sets `DiscreteTimeStepInterval = DT` on every source whose XML name is
  `TemporalInterpolator`. `DT >= 0`; `0` restores the original time steps.
- Must be applied **before** anything reads the time step list: `--time`
  default (end time), frame window, colorbar/plot precomputation, camera
  bounds. `--frame-start/end/stride` count frames of the resulting time steps.
- If no interpolator exists in the state: error (the user asked for something
  that can't happen).
- If after applying, the animation's time steps still contain time steps that
  don't come from the interpolators (e.g. a reader shown directly without
  "ignore time"), print a **warning** naming those sources; don't change the
  state. Detection approach left to the builder.

### 4. Line plot controls

**Discovery.** `--list-plots` prints the chart views in the selected
layout/view, 1-based in layout order, with view type, chart title, and for
each axis (`x`/bottom, `y`/left, and right/top if a series uses them): current
range and whether a custom range is on. Print-and-continue, like the other
`--list-*` flags.

**Which views count as plots.** Any view in the selected layout/view whose
proxy has the `LeftAxisUseCustomRange` property (covers Line Chart, Plot Data
Over Time / quartile chart, bar and point charts).

**Axis names.** `x` = bottom, `y` = left; `top` and `right` also accepted.

**Flags** (N = plot index, AXIS as above; all repeatable):

| Flag | Effect |
|---|---|
| `--plot-range N AXIS MIN MAX` | Fixed range. |
| `--plot-data-range-all N AXIS` | Data range over all frames of the frame window, applied once (static). |
| `--plot-data-range-grow N AXIS` | Per frame, grows to include the data, never shrinks. |
| `--plot-auto N AXIS` | Turn the custom range off: ParaView refits every frame. |
| `--plot-sym N AXIS` | Modifier: symmetric around zero; requires `--plot-data-range-*` for the same N/AXIS. |
| `--plot-log N AXIS on\|off` | Log scale on or off. |

- One range mode per (N, AXIS); conflicts are validation errors, like
  `validate_colorbar_args`.
- No per-frame "clamp" mode: `--plot-auto` is ParaView's own per-frame refit
  and gives the same result with nicer axis behavior. *My call.*
- Fixed/all/grow set `<Axis>UseCustomRange = 1` and the min/max properties.
- **Data ranges** come from the series actually drawn: visible series
  (`SeriesVisibility`) for the Y-type axes, mapped to the axis each series is
  plotted on (`SeriesPlotCorner`); for X, the X array (or the point index
  range when "use index for X axis" is on). Exact property handling left to
  the builder; must be correct for Line Chart (Plot Over Line) and Plot Data
  Over Time.
- **Margin:** computed ranges (all/grow) get 5 % of the span added on each
  side so curves don't sit on the frame. Fixed ranges are used as given.
  On a log axis the margin is applied in log space. *My call.*
- Log axis with a range that includes values ≤ 0: error for a fixed range;
  for a computed range, clip to the smallest positive value and warn.
- `grow` in animations uses a per-frame animation cue, like the colorbar
  `grow`. Generalize the existing cue to carry both colorbar and plot ranges
  in one `PythonAnimationCue` rather than adding a second mechanism.
- Empty/degenerate data range (no visible series, or min == max): warn and
  leave that axis untouched, never silently set `[0, 1]`.

### 5. Titles

| Flag | Sets |
|---|---|
| `--cb-title N TEXT` | Colorbar N's title (scalar bar `Title`) in every view where that colorbar is shown. `ComponentTitle` is left as in the state. |
| `--plot-title N TEXT` | Chart N's `ChartTitle`. |
| `--plot-axis-title N AXIS TEXT` | Chart N's axis title (`LeftAxisTitle`, `BottomAxisTitle`, …). |

An empty string clears a title.

### 6. Fail loudly (robustness)

Each of these was reproduced on 6.1 during review:

| Problem today | New behavior |
|---|---|
| Data file missing after remapping → renders without data, exit 0. | After `LoadState`, check every reader's file-name properties; if any file doesn't exist, exit non-zero listing reader name and path. `--allow-missing-data` turns this into a warning. |
| `--frame-start` beyond the last time step → segfault (exit 139). | Validate frame window: `0 <= start <= end < n_frames`, `stride >= 1`; clear error otherwise. |
| `--layout 0` / negative → silently picks another layout. | Index must be `1..n`; error otherwise. |
| `-o results/run_1.5` → writes `run_1.png`. | Only strip a known output extension (`.png .jpg .jpeg .bmp .tif .tiff .vtk .mp4 .avi .ogv .pvsm`); otherwise keep the name as given. |
| `--cb-range 1 abc 5` → raw traceback. `MIN >= MAX` accepted. | Parse and check `MIN < MAX` in validation (same for `--plot-range`). |
| Data range lookup swallows all exceptions and falls back to `[0, 1]`. | Warn with the source and array name when a range can't be computed; never apply a made-up range silently. |

**Fallback to the template run (decided by the user).** With `-d DIR`,
ParaView leaves a reader at its original path when its file isn't found under
`DIR` (documented `LoadState` behavior without `restrict_to_data_directory`).
The original path usually still exists, so a run folder missing a file would
silently render the template run's data. Therefore:

- With `-d DIR`, any checked reader whose file path is not inside `DIR` (any
  subfolder counts) after loading is an **error**, listing reader name and
  path.
- `--keep-path READER` (repeatable; reader name as shown in the pipeline
  browser / `--list-readers` below) exempts a reader that legitimately lives
  outside the run folder, e.g. a shared reference CSV. Its file must still
  exist. Unknown reader names are a validation error.
- `--list-readers` (print-and-continue, like the other `--list-*` flags)
  prints each reader's name and resolved path, so the user can find names for
  `--keep-path`. *My call* (needed to make `--keep-path` usable).
- With `-f` (explicit mapping), unmapped readers are not an error; only the
  existence check applies. *My call*: with `-f` the user chose readers
  explicitly.
- `--restrict-to-datadir` keeps its current, stricter meaning.
- `--allow-missing-data` downgrades both this check and the existence check
  to warnings.

Scope of the missing-data check (*my call*): only readers upstream of a
visible representation in the rendered layout/view (a reader feeding only a
layout that gets removed doesn't matter). "Exists" means the reader's own
file-name properties; for a `.pvd`, the data files it lists are checked too.

Note: the test state's CSV reader points to a non-existent path; tests pass
`-d test/data`, where the file exists, so the missing-data check won't break
them. The builder should confirm this.

### 7. Compatibility

- Keep `paraview.compatibility.major/minor = 6, 1`. On newer ParaView this
  pins the API the script was written for (no warnings; ParaView maps renamed
  properties). It is **not** bumped per ParaView release.
- At startup, if the running ParaView is older than 6.1, print one warning:
  untested version. Don't refuse to run.
- README: state "Requires ParaView 6.1 or newer (tested with 6.1.0)" and the
  explanation above in one short paragraph.

### 8. Tests

- **Unit tests must test the real code.** Today they test pasted copies of
  `estimate_mp4_bitrate`, `parse_filenames`, `apply_sym`. Make `pvrender.py`
  importable from plain Python (e.g. guard the ParaView imports so pure
  helpers load without ParaView) and import them. Approach left to the
  builder, but the script must still run unchanged under `pvbatch`.
- **Integration tests must check effects**, not only exit code + file exists:
  - image size from the PNG header (no Pillow dependency needed);
  - colorbar ranges, plot axis ranges/titles/log, camera, interpolation
    interval: read back from the saved state (`--save-state` alongside the
    render) or another reliable read-back the builder picks.
- New test fixtures as needed, generated by a pvpython script committed under
  `test/` (not hand-edited XML): a state with a Temporal Interpolator, and a
  data set whose extent differs from the state's original data (for
  `--fit-camera`). The existing state's Line Chart and Plot Data Over Time
  views serve the plot tests.
- Every bug in section 6 gets a test that failed before the fix.
- Full suite currently takes ~4 min; keep new integration tests at small
  `--size` to avoid doubling that.

### 9. Docs

Update both the module docstring and README for every new flag and the
changed `--size` meaning. README gets a short "parameter study" example
combining `-d`, `--fit-camera`, `--plot-data-range-all`, `--cb-data-range-all`
and titles.

## Left to the builder

- Internal structure and helper names; how colorbar and plot range code share
  logic.
- How to detect interpolator vs non-interpolator time steps (warning in §3).
- Exact data-range extraction for each chart representation type.
- Read-back mechanism in integration tests.
- Order of work. Suggested: robustness fixes and test infrastructure first
  (they make everything after verifiable), then size, camera, interpolation,
  plots, titles, docs.

## Calls I made (for review)

- `--size N` / `--image-resolution N` change meaning to "longest side".
- Camera fit uses the union of bounds over the frame window, also for
  screenshots.
- Camera fit modes `fit` / `out` and a 5 % default margin.
- `--list-readers` added so `--keep-path` names are discoverable.
- With `-f`, unmapped readers are not an error (existence check only).
- No `--plot-data-range-clamp`; `--plot-auto` covers per-frame refit.
- 5 % margin on computed plot ranges.
- Missing data fails by default, with `--allow-missing-data` to opt out.
- Unsupported old ParaView only warns.
- No interpolators in the state + `--interp-interval` → error.
