# pvrender Parameter-Study Robustness and Controls — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make repeated, unattended rendering of one `.pvsm` state against many simulation runs produce correct, comparable, labelled outputs, and fail loudly instead of rendering wrong data.

**Architecture:** Everything stays in the single script `pvrender.py`. Logic that does not need ParaView is written as pure functions, which become unit-testable once the ParaView imports are guarded. ParaView-side effects are verified by an inspection harness, `test/pv_inspect.py`. It runs `pvrender.main(argv)` under `pvbatch` and dumps the resulting proxy state as JSON. Test fixtures (scaled data, adaptive time steps, generated states) are generated per test session by `test/make_fixtures.py` into the gitignored `test/output/fixtures/`.

**Tech Stack:** ParaView 6.1 `pvbatch`/`pvpython` (`paraview.simple`), Python stdlib only, pytest (run with plain `python -m pytest`).

**Spec:** `docs/superpowers/specs/2026-10-16-pvrender-parameter-study-design.md`

## Global Constraints

- Single file `pvrender.py`; no dependencies beyond a standard ParaView install. Tests: stdlib + pytest only (no Pillow, no numpy).
- Must work headless under `pvbatch`. Reference version ParaView 6.1 (`C:\Program Files\ParaView 6.1.0`).
- Keep `paraview.compatibility.major = 6`, `minor = 1`.
- CLI style: 1-based indices discovered via `--list-*`; repeatable flags use `action='append'`; all validation before any rendering; errors are `raise SystemExit("error: ...")`; warnings go to stderr as `warning: ...` via the `warn()` helper (Task 2).
- Anti-goal: no change in output when no new flag is passed, except two intended changes: `--size N`/`--image-resolution N` now mean the longest side, and missing or out-of-run-folder data now fails.
- Anti-goal: never apply a made-up range, fit or setting silently. Every fallback warns.
- Anti-goal: no per-frame camera motion; the camera fit is computed once.
- Existing colorbar behavior stays, including `_disable_auto_rescale`.
- `main()` processing order, after all tasks:
  1. parse/validate args, version warning
  2. `LoadState`
  3. select the layout (validated index), list layouts/views, remove the other layouts, select the view
  4. `--list-readers`, data-path checks
  5. `--interp-interval`
  6. `--size`
  7. set time, validate the frame window
  8. colorbars: colormap, discretize, titles, static ranges, dynamic precompute
  9. plots: static settings, ranges, dynamic precompute
  10. camera fit
  11. interact / save-state / save-image / save-animation / save-extracts
- Every new flag is documented in both the module docstring and `README.md` within the task that adds it.
- Integration tests use small sizes (`--size 320` unless the test is about size) to keep suite time down. The current suite takes about 4 min.
- Commit after each task on the working branch, with messages ending in the `Co-Authored-By` line from the session's attribution instructions.

## Review Focus

These are inputs the spec implies but that no task's tests would otherwise exercise. Each has a test added to the owning task.

1. **A state whose representation has a non-identity `Position`/`Scale`/`Orientation`.** The camera fit computes bounds from the data, not the displayed geometry, so the fit would be off. Expected: a warning naming the representation, and the fit still runs. Test in Task 6.
2. **A chart series plotted on the right or top axis** (`SeriesPlotCorner` ≠ 0). Range modes on `right`/`top` must use only those series, and `y` must not include them. Test in Task 8.
3. **A static data set (single time step, no `TimestepValues`).** The frame window is `[0, 0]`, `--cb/--plot-data-range-all` and `--fit-camera` work, and `--interp-interval` on a state without interpolators errors cleanly. Test in Task 2 (static state renders, frame window) and Task 6 (fit on static state).
4. **Windows path forms in the data-dir check.** Mixed case, forward vs back slashes, trailing separators, and a relative `-d` must all count as "inside". `C:\data\run1` must not count as inside `C:\data\run`. Test in Task 3 (unit, `is_inside_dir`).
5. **`--keep-path` naming a reader that exists but does not feed the rendered layout.** Accepted silently: the reader is known, just not checked. A name that matches no reader at all is an error. Test in Task 3.

---

### Task 1: Test infrastructure — importable script, real unit tests, inspection harness

**Files:**
- Modify: `pvrender.py:191-198` (guard ParaView imports), `pvrender.py:692` (`parse_args`), `pvrender.py:886` (`main`)
- Create: `test/pv_inspect.py`
- Modify: `test/test_pvrender.py` (delete the pasted copies at lines ~48-90 and ~509-512; import from `pvrender`; add helpers)

**Interfaces:**
- Produces:
  - `parse_args(argv: list[str] | None = None) -> argparse.Namespace`
  - `main(argv: list[str] | None = None) -> None`
  - Module importable from plain Python, where `paraview` is `None` and the pure helpers work.
  - `test/pv_inspect.py`, used as `pvbatch test/pv_inspect.py REPORT_JSON <pvrender args...>`. It runs `pvrender.main(args)`, then writes REPORT_JSON:
    ```json
    {"time": 0.0, "timesteps": [0.0], "layout_size": [w, h],
     "colorbars": [{"array": "...", "range": [lo, hi], "titles": ["..."]}],
     "plots": [{"type": "XYChartView", "title": "...",
                "axes": {"Left": {"custom": true, "range": [mn, mx], "log": false, "title": "..."},
                         "Bottom": {}, "Right": {}, "Top": {}}}],
     "cameras": [{"position": [], "focal_point": [], "view_up": [], "view_angle": 30.0,
                  "parallel": false, "parallel_scale": 1.0}],
     "interpolators": [0.0]}
    ```
    Views are those of the single remaining layout, in layout order. `colorbars` comes from `pvrender.enumerate_colorbars(views)`, and the range is `RGBPoints[0]`, `RGBPoints[-4]`. `titles` holds the `Title` of each `ScalarBarWidgetRepresentation` in those views whose `LookupTable` is that LUT. `plots` uses `pvrender.enumerate_plots(views)` once Task 7 exists; until then, emit `[]` when the attribute is missing. `cameras` covers render views in layout order. `interpolators` holds `DiscreteTimeStepInterval` of every `TemporalInterpolator` source.
  - Test helpers in `test/test_pvrender.py`:
    - `_inspect(*extra_args, outname, state=STATE, datadir=DATA) -> tuple[subprocess.CompletedProcess, dict | None]`. Passes `-d datadir` unless `datadir is None`, and returns the parsed report when returncode is 0.
    - `png_size(path) -> tuple[int, int]`, which reads the IHDR width and height (big-endian uint32 at bytes 16 and 20).

- [ ] **Step 1: Write failing tests.** Replace the pasted copies with `from pvrender import estimate_mp4_bitrate, parse_filenames, apply_sym, _PALETTE_ALIASES`, with `ROOT` inserted on `sys.path`. Point the palette-alias tests at `pvrender._PALETTE_ALIASES` too. Add:
  ```python
  def test_pvrender_imports_without_paraview():
      import pvrender
      assert pvrender.paraview is None

  # integration
  def test_inspect_harness_reports_defaults(self, outdir):
      r, rep = _inspect("--time", "1", "--size", "320", outname=os.path.join(outdir, "out"))
      assert r.returncode == 0, r.stderr
      assert rep["time"] == 1.0 and len(rep["timesteps"]) == 21
      assert rep["layout_size"][0] == 320
      assert len(rep["colorbars"]) == 1 and len(rep["cameras"]) == 1
  ```
- [ ] **Step 2: Run** `python -m pytest test/test_pvrender.py -q -k "imports_without or harness or Bitrate or ParseFilenames or Palette or ApplySym"`. Expected: FAIL on import (ParaView not importable) and a missing harness.
- [ ] **Step 3: Implement.**
  - Wrap the ParaView setup in `try: import paraview` / `except ImportError: paraview = None`.
  - Under `if paraview is not None:`, set compatibility, run `from paraview.simple import *` (allowed at module level inside `if`) and `_DisableFirstRenderCameraReset()`.
  - Thread `argv` through `parse_args`/`main`.
  - Write `test/pv_inspect.py`.
- [ ] **Step 4: Run** the same command, then the full suite `python -m pytest test/test_pvrender.py -q`. Expected: all pass, with the existing 99 still passing.
- [ ] **Step 5: Commit** with the message `test: import real pvrender helpers; add pvbatch inspection harness`.

---

### Task 2: Argument robustness and version warning

**Files:**
- Modify: `pvrender.py` (new helpers near `parse_filenames`; `validate_colorbar_args`; `_get_data_range_at_time`, `_get_global_data_range`, `apply_static_colorbar_limits`, `precompute_dynamic_colorbar_ranges`; `main` layout/frame/output handling)
- Modify: `README.md` (Requirements: "Requires ParaView 6.1 or newer (tested with 6.1.0)", plus one paragraph saying the compatibility pin is intentional and not bumped per release), module docstring
- Test: `test/test_pvrender.py`

**Interfaces:**
- Produces:
  - `warn(msg: str) -> None`: prints `warning: {msg}` to stderr.
  - `_KNOWN_OUTPUT_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.vtk', '.mp4', '.avi', '.ogv', '.pvsm'}`
  - `strip_output_extension(name: str) -> str`: lowercases the extension when comparing.
  - `resolve_layout_index(value: str, names: list[str]) -> int`: returns a 0-based index. An integer must be in `1..len(names)`; otherwise the value is matched exactly against `names`. Raises `SystemExit`.
  - `resolve_frame_window(start: int, end: int, stride: int, n_frames: int) -> tuple[int, int]`:
    - A negative `end` means `n_frames - 1`.
    - Requires `0 <= start <= end < n_frames` and `stride >= 1`; otherwise raises `SystemExit`.
    - `n_frames` is `max(1, len(TimestepValues))`.
  - `paraview_version_warning(version: tuple[int, int]) -> str | None`: returns a message when `version < (6, 1)`. `main` calls it with `GetParaViewVersion()`, which compares like a tuple, and passes the result to `warn`.
  - `_get_data_range_at_time(cb, views, t) -> tuple[float, float] | None` (changed contract) and `_get_global_data_range(cb, views) -> tuple[float, float] | None`. Neither returns `(0.0, 1.0)` any more.
    - Exceptions raised per source become `warn(f"cannot read range of '{array}' from '{source_name}': {e}")`.
    - When the result is `None`, callers warn `colorbar {n}: no data range found for '{array}'; range left as in state` and skip that colorbar. For dynamic modes, frames without a range are skipped.
  - `validate_colorbar_args` parses the `--cb-range` MIN/MAX as floats (`error: --cb-range: MIN and MAX must be numbers, got ...`) and requires `MIN < MAX`.

- [ ] **Step 1: Write failing unit tests.**
  ```python
  @pytest.mark.parametrize("name,expected", [
      ("results/run_1.5", "results/run_1.5"), ("out.png", "out"), ("out.MP4", "out"),
      ("a.b/c", "a.b/c"), ("x.pvsm", "x")])
  def test_strip_output_extension(name, expected): ...
  def test_resolve_layout_index(): # "1"->0, "2"->1, "Layout #2"->1; "0", "-1", "3", "nope" -> SystemExit
  def test_resolve_frame_window(): # (0,-1,1,21)->(0,20); (50,-1,1,21) SystemExit; (5,3,1,21) SystemExit;
                                   # (0,-1,0,21) SystemExit; (0,-1,1,1)->(0,0)
  def test_version_warning(): # (5,13)->str; (6,1)->None; (7,0)->None
  def test_validate_cb_range_non_numeric_and_order(): # Namespace with cb_range=[['1','abc','5']] -> SystemExit;
                                                      # [['1','5','1']] -> SystemExit; [['1','1','1']] -> SystemExit
  ```
  `validate_colorbar_args` tests build an `argparse.Namespace` with every `cb_*` attribute that `parse_args([...])` produces. Get that namespace from `pvrender.parse_args(["x.pvsm", ...])` so the tests stay in sync.
- [ ] **Step 2: Write failing integration tests.**
  - `test_layout_zero_fails`: `--layout 0` gives returncode ≠ 0.
  - `test_frame_start_beyond_end_fails`: `--sa --frame-start 50 --animation-format png` gives returncode ≠ 0, with `error:` in stderr (not 139).
  - `test_dotted_outname_kept`: `-o <outdir>/run_1.5 --si` writes `run_1.5.png`.
  - `test_cb_range_non_numeric_fails`: returncode ≠ 0, and `Traceback` is not in stderr.
  - `test_static_state_renders` (Review Focus 3): uses `static_state.pvsm` from Task 3's fixtures. **Write this test in Task 3**, after the fixture exists.
- [ ] **Step 3: Run** `python -m pytest test/test_pvrender.py -q -k "strip_output or layout_index or frame_window or version_warning or cb_range or layout_zero or frame_start_beyond or dotted"`. Expected: FAIL.
- [ ] **Step 4: Implement** the helpers and wire them into `main` (`outputname`, layout pick, frame window computed once and reused for `anim_frame_times`, `framewindow`, extracts). Add the README Requirements text and the docstring note.
- [ ] **Step 5: Run** the step 3 command, then the full suite. Expected: all pass.
- [ ] **Step 6: Commit** with the message `fix: validate layout index, frame window, output name, cb-range; warn instead of fake ranges`.

---

### Task 3: Data-path checks — missing files and template-run fallback

**Files:**
- Create: `test/make_fixtures.py` (run under `pvbatch`, takes `OUT_DIR`)
- Modify: `pvrender.py` (reader helpers, CLI flags, `main` step 4)
- Modify: `test/test_pvrender.py`:
  - add a session fixture `fixtures`;
  - update `test_filenames_mapping` so it also maps `probe_points.csv` to `test/data/probe_points.csv`;
  - add `test_static_state_renders` from Task 2.
- Modify: `README.md`, docstring (input section: `--keep-path`, `--list-readers`, `--allow-missing-data`, and the template-fallback explanation)

**Interfaces:**
- Produces (fixtures, in `test/output/fixtures/`). Generate them with `paraview.simple`. Never hand-edit XML.
  - `data_adaptive/radial_wave.pvd`, plus copies of the 21 `.vtp` files. Timestep values are `10*(i/20)**2` for `i = 0..20`, so the steps are non-uniform and run from 0 to 10.
  - `data_partial/`: the same `.pvd` and `.vtp` as `data_adaptive`, with **no** CSV.
  - `data_missing_step/`: like `data_adaptive`, but `radial_wave_0_7.vtp` is deleted.
  - `interp_state.pvsm`:
    - pipeline: `PVDReader(data_adaptive/radial_wave.pvd)` → `TemporalInterpolator` (interval 0) → shown in one render view, colored by `z-Displacement [m]`, with a scalar bar;
    - plus `CSVReader(<repo>/test/data/probe_points.csv)` → `TableToPoints(x, y, z)`, shown in the same view;
    - the PVD reader is listed in `GetTimeKeeper().SuppressedTimeSources`.
  - `interp_state_unsuppressed.pvsm`: the same pipeline without suppression.
  - `static_state.pvsm`: `XMLPolyDataReader(<repo>/test/data/radial_wave/radial_wave_0_5.vtp)` in one render view.
  - Later tasks extend this script; Tasks 6 and 8 list their additions.
  - Pytest: a session-scoped `fixtures` fixture runs `pvbatch test/make_fixtures.py <dir>` once and returns the directory path. It is only requested by integration tests.
- Produces (`pvrender.py`):
  - `parse_pvd_files(pvd_path: str) -> list[str]`: the absolute paths of every `DataSet/@file`, resolved relative to the `.pvd` folder.
  - `is_inside_dir(path: str, directory: str) -> bool`: compares `os.path.normcase(os.path.abspath(...))`, uses `os.path.commonpath`, and returns False across drives.
  - `check_data_paths(readers: list[dict], datadir: str | None, keep: set[str]) -> tuple[list[str], list[str]]`. Each reader is `{'name': str, 'paths': list[str], 'used': bool}`. Returns `(missing, outside)` message lists, covering only `used` readers.
    - `missing`: a path that doesn't exist, or a `.pvd` listed file that doesn't exist, as `"{name}: {path}"`.
    - `outside`: only when `datadir` is set and the name is not in `keep`, for a path not inside `datadir`.
  - `find_readers(views) -> list[dict]`. Over all sources in `GetSources()`, a reader is a source that has a `FileName` or `FileNames` property (a str or a list, flattened). Its name is the registration name from the `GetSources()` key. `used` is True when the reader is upstream of a representation with `Visibility == 1` in `views`. Walk upstream through every property that is a `servermanager.InputProperty`; there may be several, such as `DestinationMesh`/`SourceDataArrays`.
    - For chart views, a representation counts only when its `SeriesVisibility` is non-empty. Chart representations report `Visibility == 1` for every source, so `Visibility` alone is not enough there.
  - `print_readers(readers) -> None`: a table with `#`, `Name`, `Used`, `Path`.
  - CLI:
    - `--list-readers` (print and continue);
    - `--keep-path READER` (`action='append'`, default `[]`); a name not in `find_readers` is an error;
    - `--allow-missing-data`: both message lists become warnings.
    - Otherwise each non-empty list raises one `SystemExit`:
      - missing files: `error: data files not found:\n  ...`;
      - fallback outside the data directory: `error: readers still point outside --datadir (the file was not found there, so ParaView kept the state's original path):\n  ...\n  Use --keep-path NAME for files that intentionally live elsewhere.`

- [ ] **Step 1: Write failing unit tests.**
  - `test_parse_pvd_files`: use the repo's `test/data/radial_wave.pvd`. Expect 21 entries, the first ending in `radial_wave_0_0.vtp`, all absolute.
  - `test_is_inside_dir`, covering:
    - forward and back slashes;
    - a trailing separator on `directory`;
    - case differences, on Windows only (`os.name == 'nt'`);
    - `C:\data\run1` not inside `C:\data\run`;
    - a relative directory resolved against the cwd.
  - `test_check_data_paths`: build readers by hand using paths from `tmp_path`. Cover:
    - a missing file;
    - a missing `.pvd` member;
    - a file outside the data dir;
    - a reader in `keep` whose file exists;
    - a reader in `keep` whose file is missing, which still appears in `missing`;
    - an unused reader with a missing file, which is ignored;
    - `datadir=None`, where `outside` is always empty.
- [ ] **Step 2: Write failing integration tests.**
  - `test_missing_datadir_file_fails`: `interp_state.pvsm -d data_missing_step` → returncode ≠ 0, with `radial_wave_0_7.vtp` in stderr.
  - `test_fallback_outside_datadir_fails`: `interp_state.pvsm -d data_partial` → returncode ≠ 0, with `probe_points.csv` and `--keep-path` in stderr.
  - `test_keep_path_allows_shared_file`: the same with `--keep-path probe_points.csv --si` → returncode 0 and a PNG exists.
  - `test_keep_path_unknown_reader_fails`: `--keep-path nope.csv` → returncode ≠ 0.
  - `test_keep_path_unused_reader_ok` (Review Focus 5): the main test state with `--layout 2 --keep-path radial_wave.pvd --si`. The PVD reader exists, so this succeeds, whether or not layout 2 uses it.
  - `test_allow_missing_data_warns`: `-d data_missing_step --allow-missing-data --si` → returncode 0, with `warning:` in stderr.
  - `test_filenames_unmapped_missing_csv_fails`: `-f` mapping only `radial_wave.pvd` → returncode ≠ 0. The state's CSV path doesn't exist.
  - `test_list_readers`: stdout contains `radial_wave.pvd` and `probe_points.csv`.
  - `test_static_state_renders`: `static_state.pvsm --si --sa --animation-format png` with `datadir=None` → returncode 0, and `--cb-data-range-all 1` does not error.
- [ ] **Step 3: Run** `python -m pytest test/test_pvrender.py -q -k "pvd_files or inside_dir or check_data_paths or datadir or keep_path or allow_missing or unmapped or list_readers or static_state or filenames_mapping"`. Expected: FAIL.
- [ ] **Step 4: Implement** the fixture script, the helpers, the flags, and `main` step 4. Confirm that the existing tests, which pass `-d test/data`, still pass. Spec §6 note: the CSV exists there.
- [ ] **Step 5: Run** the step 3 command, then the full suite. Expected: all pass.
- [ ] **Step 6: Commit** with the message `feat: fail on missing data and template-run fallback; add --keep-path, --list-readers, --allow-missing-data`.

---

### Task 4: Output size box

**Files:**
- Modify: `pvrender.py` (`main` size and image-resolution blocks; `--size`/`--image-resolution` help), README, docstring
- Test: `test/test_pvrender.py`

**Interfaces:**
- Produces `fit_to_box(width: int, height: int, n: int) -> tuple[int, int]`: scale is `n / max(width, height)`, each side is `round()`ed, and the minimum is 1. Used for one-value `--size` (base = current layout size) and one-value `--image-resolution` (base = view `ViewSize`, or the layout size).

- [ ] **Step 1: Write failing tests.**
  - Unit `test_fit_to_box`:
    - `(2145, 777, 1920) == (1920, 695)`
    - `(600, 900, 1920) == (1280, 1920)`
    - `(100, 50, 1920) == (1920, 960)`
    - `(1000, 1000, 500) == (500, 500)`
  - Integration `test_size_box_wide`: `--si --time 1 --size 400` → `png_size == (400, 145)`. The layout is 2145×777: 400 × 777 / 2145 = 144.9, which rounds to 145.
  - Integration `test_image_resolution_box`: `--view 1 --si --time 1 --size 400 --image-resolution 300` → `max(png_size) == 300`.
  - Integration `test_size_box_tall`: `static_state.pvsm` (Task 3 fixture; its layout is generated at 600×900), `--si --size 400`, `datadir=None` → `png_size == (267, 400)`. Add `SetSize(600, 900)` on that layout in `make_fixtures.py`.
  - Integration `test_size_two_values_exact`: `--size 640 480 --si` → `png_size == (640, 480)`.
- [ ] **Step 2: Run** `python -m pytest test/test_pvrender.py -q -k "fit_to_box or size_box or image_resolution_box or size_two_values_exact"`. Expected: FAIL.
- [ ] **Step 3: Implement**, and update the help text, README table and docstring to say "longest side".
- [ ] **Step 4: Run** the step 2 command, then the full suite. Fix any existing test that assumed width semantics only if it asserts width explicitly. None do today.
- [ ] **Step 5: Commit** with the message `feat: --size/--image-resolution one value = longest side (fit in box)`.

---

### Task 5: Temporal interpolation interval

**Files:**
- Modify: `pvrender.py` (helpers, `--interp-interval` flag, `main` step 5), README, docstring
- Test: `test/test_pvrender.py`

**Interfaces:**
- Produces:
  - `apply_interp_interval(dt: float) -> list[str]`: sets `DiscreteTimeStepInterval = dt` on every source with `GetXMLName() == 'TemporalInterpolator'` and returns their registration names. If there are none, it raises `SystemExit("error: --interp-interval: no Temporal Interpolator in the state")`.
  - `unsuppressed_time_sources() -> list[str]`: the registration names of sources that are in `GetTimeKeeper().TimeSources`, not in `SuppressedTimeSources`, not `TemporalInterpolator`, and have a non-empty `TimestepValues`. `main` warns once if the list is non-empty: `warning: these sources still add their own time steps to the animation (set "Ignore Time" on them in ParaView): ...`.
  - CLI: `--interp-interval DT` (float, default `None`). `parse_args` rejects `DT < 0`.
  - Applied before anything reads `TimestepValues` (Global Constraints order).

- [ ] **Step 1: Write failing integration tests.**
  - `test_interp_interval_sets_all`: `interp_state.pvsm -d data_adaptive --interp-interval 0.5 --keep-path probe_points.csv` → `rep["interpolators"] == [0.5]`, and `rep["timesteps"]` equals `[0.5*i for i in range(21)]` within 1e-9.
  - `test_interp_interval_zero_original_steps`: `--interp-interval 0` → timesteps equal `10*(i/20)**2`.
  - `test_interp_interval_frame_window_counts_new_steps`: `--interp-interval 0.25 --sa --animation-format png --frame-end 40 --size 160` → returncode 0, with 41 PNG files.
  - `test_interp_interval_no_interpolator_fails`: the main test state → returncode ≠ 0.
  - `test_interp_interval_negative_fails`.
  - `test_interp_unsuppressed_warns`: `interp_state_unsuppressed.pvsm` → returncode 0, and stderr mentions `radial_wave.pvd`.
- [ ] **Step 2: Run** `python -m pytest test/test_pvrender.py -q -k interp`. Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** the step 2 command, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** with the message `feat: --interp-interval sets DiscreteTimeStepInterval on all Temporal Interpolators`.

---

### Task 6: Camera fit

**Files:**
- Modify: `pvrender.py` (pure fit math, bounds collection, flags, `main` step 10), README, docstring
- Modify: `test/make_fixtures.py`:
  - `data_big/`: the radial-wave data scaled ×3 through `Transform` and saved with `SaveData(..., WriteTimeSteps=1)` as `radial_wave.pvd`, plus a copy of `probe_points.csv`;
  - `data_small/`: the same, scaled ×0.3;
  - `scaled_rep_state.pvsm`: like `static_state.pvsm`, with the representation's `Scale = [2, 1, 1]`.
- Test: `test/test_pvrender.py`

**Interfaces:**
- Produces:
  - `fit_camera(position, focal_point, view_up, view_angle, parallel, parallel_scale, aspect, bounds, margin_pct, mode) -> dict`. Returns `{'position': [x, y, z], 'focal_point': [x, y, z], 'parallel_scale': float}`. Inputs are plain lists or floats, `bounds` is `[xmin, xmax, ymin, ymax, zmin, zmax]`, `aspect` is width/height, and `mode` is `'fit'` or `'out'`.
  - `collect_view_bounds(view, frame_times: list[float]) -> list[float] | None`: the union over frames of the data bounds of visible representations that have an `Input`. Call `UpdatePipeline(t)` on the source, then use `GetDataInformation().GetBounds()`, and skip invalid bounds (min > max). It warns once per representation whose `Position`, `Scale` or `Orientation` is not identity (Review Focus 1). It returns None when nothing is visible, and the caller warns and leaves that view's camera unchanged.
  - CLI: `--fit-camera {fit,out}` (default None) and `--fit-margin PCT` (float, default 5.0, `0 <= PCT < 50`, else a parse error).
  - In `main`, for each render view in the rendered views, call `Render(view)` first so `ViewSize` is current. Use `aspect = ViewSize[0] / ViewSize[1]`. Compute bounds over `anim_frame_times` (the same list as the colorbars), apply the fit, then restore the scene time.

  `fit_camera` algorithm. It isn't fixed by the signature, so here it is:
  ```text
  d = normalize(focal - position); u = normalize(view_up orthogonalised against d); r = d × u
  s = 1 - 2*margin_pct/100                       # usable fraction of each half-extent
  tv = tan(radians(view_angle)/2); th = tv*aspect
  center = bounds center if mode == 'fit' else focal
  for each of 8 corners c: x = (c-center)·r, y = (c-center)·u, z = (c-center)·d
  perspective: need = max over corners of max(|x|/(th*s), |y|/(tv*s)) - z
               dist  = need if mode == 'fit' else max(|focal-position|, need)
               position = center - d*dist; focal = center
  parallel:    need = max over corners of max(|x|/(aspect*s), |y|/s)
               scale = need if mode == 'fit' else max(parallel_scale, need)
               keep camera distance, but at least max(-z)+1e-6 so all corners are in front
  ```
  In `'out'` mode, when nothing needs to change, return the input values unchanged (exact equality).

- [ ] **Step 1: Write failing unit tests (`TestFitCamera`).**
  - **Corners inside the frustum.** After `'fit'`, every corner projects inside the viewport scaled by `s`. Check this by recomputing x, y, z against the returned camera, for:
    - perspective at aspect 1 and 2;
    - parallel projection.
  - **Tightness.** After `'fit'`, at least one corner sits on the margin boundary (within 1e-6).
  - **`'out'` with bounds already inside.** Returns exactly the input.
  - **`'out'` with large bounds.** The distance grows, and the focal point and direction are unchanged.
  - **`'fit'` with small bounds.** The distance shrinks.
  - **Margin.** `margin_pct=0` puts a corner exactly on the edge.
- [ ] **Step 2: Write failing integration tests.** The main state uses `datadir` = `data_big` or `data_small`.
  - `test_no_fit_camera_unchanged`: with `data_big` and no flag, the harness camera equals the camera reported for `test/data` with no flag.
  - `test_fit_out_big_moves_back`: `--fit-camera out` with `data_big` → distance (|position − focal_point|) greater than the default's.
  - `test_fit_out_small_unchanged`: `--fit-camera out` with `data_small` → camera equals the default.
  - `test_fit_fit_small_moves_in`: `--fit-camera fit` with `data_small` → distance less than the default's.
  - `test_fit_same_for_image_and_animation`: with `data_big`, `--fit-camera fit --si` and `--fit-camera fit --sa --animation-format png --frame-end 3` report the same camera within 1e-9.
  - `test_fit_static_state` (Review Focus 3): `static_state.pvsm --fit-camera fit --si` → returncode 0.
  - `test_fit_scaled_rep_warns` (Review Focus 1): `scaled_rep_state.pvsm --fit-camera fit` → returncode 0, with `Scale` or `transform` in the stderr warning.
  - `test_fit_margin_out_of_range_fails`: `--fit-margin 60`.
- [ ] **Step 3: Run** `python -m pytest test/test_pvrender.py -q -k "FitCamera or fit_"`. Expected: FAIL.
- [ ] **Step 4: Implement.**
- [ ] **Step 5: Run** the step 3 command, then the full suite. Expected: PASS.
- [ ] **Step 6: Commit** with the message `feat: --fit-camera fit|out and --fit-margin`.

---

### Task 7: Plot discovery, fixed/auto/log axis controls, titles

**Files:**
- Modify: `pvrender.py` (plot helpers, flags, `main` step 9 (static part), colorbar titles in step 8), README (new "Plots" options table; `--cb-title` in the colorbar table), docstring
- Test: `test/test_pvrender.py`

**Interfaces:**
- Produces:
  - `_AXIS_ALIASES = {'x': 'Bottom', 'bottom': 'Bottom', 'y': 'Left', 'left': 'Left', 'top': 'Top', 'right': 'Right'}`
  - `normalize_axis(name: str) -> str`: case-insensitive; raises `SystemExit` on an unknown name.
  - `enumerate_plots(views) -> list`: the views that have a `LeftAxisUseCustomRange` property, in the given order.
  - `print_plots(plots) -> None`: `#`, type, chart title, then for each axis `Bottom/Left/Right/Top`: `custom on/off`, `[min, max]`, `log`.
  - `build_plot_specs(args, n_plots) -> dict[tuple[int, str], dict]`. The key is `(n, 'Left' | 'Bottom' | 'Right' | 'Top')`, and the value is `{'mode': 'fixed' | 'all' | 'grow' | 'auto' | None, 'min': float | None, 'max': float | None, 'sym': bool, 'log': bool | None, 'title': str | None}`. It does all validation:
    - index range;
    - numeric `MIN < MAX`;
    - one range mode per key;
    - `sym` needs `all` or `grow`;
    - `on|off` for log;
    - a fixed range on a log axis must have `MIN > 0`. The log state comes from `--plot-log` only; when absent, the axis's current `LogScale` is checked at apply time.
  - `apply_plot_static(specs, plots, chart_titles: dict[int, str]) -> None`. Per key:
    - `fixed` sets `<Axis>AxisUseCustomRange = 1`, `<Axis>AxisRangeMinimum/Maximum`;
    - `auto` sets `<Axis>AxisUseCustomRange = 0`;
    - `log` sets `<Axis>AxisLogScale`;
    - `title` sets `<Axis>AxisTitle`;
    - chart titles set `ChartTitle`.
  - `apply_colorbar_titles(args, colorbars, views) -> None`: sets `Title` on the existing `ScalarBarWidgetRepresentation`s in `views` whose `LookupTable` is the LUT. It never creates a scalar bar (do not use `GetScalarBar`, which creates one). It warns when colorbar N has no scalar bar shown.
  - CLI, all `action='append'`, default `None`:
    - `--plot-range N AXIS MIN MAX` (nargs 4)
    - `--plot-data-range-all N AXIS`, `--plot-data-range-grow N AXIS`, `--plot-auto N AXIS`, `--plot-sym N AXIS` (nargs 2)
    - `--plot-log N AXIS on|off` (nargs 3)
    - `--plot-title N TEXT` (nargs 2)
    - `--plot-axis-title N AXIS TEXT` (nargs 3)
    - `--cb-title N TEXT` (nargs 2; index validated in `validate_colorbar_args`)
    - `--list-plots` (store_true)
    - `all`/`grow` are parsed and validated here but applied in Task 8.
  - The harness `plots` report is now filled from `enumerate_plots`.

- [ ] **Step 1: Write failing unit tests.**
  - `test_normalize_axis`: `x`→`Bottom`, `Y`→`Left`, `right`, `top`, and `z` → SystemExit.
  - `test_build_plot_specs`, using `parse_args` namespaces. The valid cases are:
    - fixed;
    - auto;
    - log on;
    - a title;
    - `x` and `bottom` merging into the same key.

    These must raise `SystemExit`:
    - a fixed range and `all` on the same key;
    - `sym` without `all`/`grow`;
    - `MIN >= MAX`;
    - non-numeric MIN;
    - index 0;
    - index > n;
    - log `maybe`;
    - a fixed range with `MIN <= 0` plus `--plot-log ... on`.
- [ ] **Step 2: Write failing integration tests.** The main state has 2 plots: 1 is the Line Chart (`XYChartView`) and 2 is `QuartileChartView`.
  - `test_list_plots`: stdout has both view types.
  - `test_plot_range_fixed_x_and_y`: `--plot-range 1 x -0.2 0.3 --plot-range 1 y -2 2` → Bottom `custom` True, range [-0.2, 0.3]; Left [-2, 2].
  - `test_plot_auto`: `--plot-range 1 y -2 2 --plot-auto 1 x` → Bottom custom False.
  - `test_plot_log`: `--plot-log 2 x on` → Bottom log True.
  - `test_plot_titles`: `--plot-title 1 "Run A" --plot-axis-title 1 y "w [m]"` → title "Run A", Left title "w [m]".
  - `test_plot_title_empty_clears`: `--plot-title 1 ""` → title "".
  - `test_cb_title`: `--cb-title 1 "Displacement"` → `rep["colorbars"][0]["titles"] == ["Displacement"]`.
  - `test_plot_index_out_of_range_fails`: `--plot-range 3 y 0 1`.
- [ ] **Step 3: Run** `python -m pytest test/test_pvrender.py -q -k "normalize_axis or plot_specs or list_plots or plot_range_fixed or plot_auto or plot_log or plot_title or cb_title or plot_index"`. Expected: FAIL.
- [ ] **Step 4: Implement.**
- [ ] **Step 5: Run** the step 3 command, then the full suite. Expected: PASS.
- [ ] **Step 6: Commit** with the message `feat: --list-plots, fixed/auto/log plot axes, plot/axis/colorbar titles`.

---

### Task 8: Plot data ranges (all/grow/sym), shared per-frame cue

**Files:**
- Modify: `pvrender.py`:
  - range helpers;
  - refactor `precompute_dynamic_colorbar_ranges` to use `grow_entries`;
  - replace `build_dynamic_colorbar_cue`/`apply_dynamic_colorbar_ranges_at_time` with the generalized versions;
  - `main` step 9 (dynamic part).
- Modify: `test/make_fixtures.py`: add `right_axis_state.pvsm`. It contains a line chart of `PlotOverLine` on the `static_state` data with two visible series: `z-Displacement [m]` on corner 0 and `arc_length` on corner 1 (right axis).
- Modify: README (parameter-study note on plot ranges), docstring
- Test: `test/test_pvrender.py`

**Interfaces:**
- Consumes: `build_plot_specs`, `enumerate_plots`, `normalize_axis` (Task 7); `warn`, the `_get_data_range_at_time` contract (Task 2).
- Produces:
  - `pad_range(lo: float, hi: float, frac: float = 0.05, log: bool = False) -> tuple[float, float]`:
    - linear: `lo - frac*span`, `hi + frac*span`;
    - log: the same in log10 space, and requires `lo > 0`.
  - `grow_entries(entries: list[list[float]]) -> list[list[float]]`: for `[[t, lo, hi], ...]` sorted by t, returns the running min/max. Also used by the colorbar grow.
  - `axis_series(series_visibility: list[str], plot_corners: list[str], axis: str) -> list[str]`. `plot_corners` is the flat `[name, corner, ...]` from `SeriesPlotCorner`, and series not listed are on corner `'0'`. Corners follow `vtkChart`:
    - `0` = bottom-left, `1` = bottom-right, `2` = top-right, `3` = top-left.
    - `Left` takes series on 0 or 3, and `Right` on 1 or 2.
    - `Bottom`/`Top` are X axes: return `[]`, since X comes from the X array.
    - Verify this corner mapping once in the GUI or VTK docs, and note the result in a code comment.
  - `split_series_name(series: str, array_names: list[str]) -> tuple[str, int] | None`:
    - Strip a trailing `" (stats)"` or `" (id=<n>)"`.
    - An exact array name gives `(name, -1)`.
    - Otherwise split the last `_`; the suffix `X/Y/Z/Magnitude/<int>` gives component `0/1/2/-1/int`.
    - `Points` is a valid array name here, meaning point coordinates.
    - Unresolvable gives None.
  - `_get_plot_axis_range_at_time(view, axis: str, t: float) -> tuple[float, float] | None`. It looks at every chart representation in `view` with a non-empty `SeriesVisibility`.
    - **Y axes:** resolve `axis_series` through `split_series_name` against the input's arrays for `AttributeType` (`'Point Data'` → point data, `'Row Data'` → row data, `'Cell Data'` → cell data).
      - `Points_X/Y/Z` use the data bounds for that coordinate.
      - A `(stats)` series uses the union of the ranges of row arrays named `min(<array>)` and `max(<array>)`. These bound everything the quartile chart draws.
      - **Verify the actual array names** on the test state's `PlotDataOverTime1` output, and adapt to them if they differ. The intent is: the range must enclose every drawn curve or band.
    - **X axes:** `XArrayName[0]`, resolved the same way, or `[0, n-1]` when `UseIndexForXAxis`. Here `n` is the number of points or rows.
    - Unresolvable series warn once and are skipped. No series at all returns None.
  - `precompute_plot_ranges(specs, plots, frame_times) -> tuple[dict[tuple[int, str], tuple[float, float]], list[dict]]`. Returns:
    - static ranges for `all` keys, as a union over `frame_times`;
    - dynamic entries for `grow` keys: `{'view': <registration name>, 'axis': 'Left', 'log': bool, 'entries': [[t, lo, hi], ...]}`.
    - Then:
      - `sym` → `apply_sym`;
      - pad with `pad_range` (log from the spec, or the axis's current `LogScale`);
      - on a log axis with computed `lo <= 0`, clip to `hi / 1000` and warn. This is a deviation from the spec, explained in the plan handoff;
      - a degenerate `lo == hi` or None warns and leaves the axis untouched.
    - The view registration name comes from `servermanager.ProxyManager().GetProxyName('views', view)`. The cue finds it with `FindView(name)`.
  - `build_dynamic_cue(dynamic: dict, scene) -> cue` and `apply_dynamic_ranges_at_time(dynamic: dict, t: float) -> None`. `dynamic = {'colorbars': {array: [[t, lo, hi], ...]}, 'plots': [ ...entries above ]}`. They replace the colorbar-only versions; behavior for colorbars is unchanged. Plot ticks set `<Axis>AxisUseCustomRange = 1` and min/max using the nearest-time entry.

- [ ] **Step 1: Write failing unit tests.**
  - `test_pad_range`:
    - `(0, 10)` → `(-0.5, 10.5)`;
    - log `(1, 100)` → `(10**-0.1, 10**2.1)`;
    - log with `lo = 0` → ValueError.
  - `test_grow_entries`: `[[0, -1, 1], [1, -0.5, 2], [2, -3, 0]]` → `[[0, -1, 1], [1, -1, 2], [2, -3, 2]]`.
  - `test_axis_series` (Review Focus 2). With visible `['a', 'b']` and corners `['b', '1']`:
    - Left → `['a']`;
    - Right → `['b']`;
    - Bottom → `[]`.
  - `test_split_series_name`, with `arrays = ['z-Displacement [m]', 'Points', 'U']`:
    - `'z-Displacement [m] (stats)'` → `('z-Displacement [m]', -1)`;
    - `'U_X'` → `('U', 0)`;
    - `'U_Magnitude'` → `('U', -1)`;
    - `'U_2'` → `('U', 2)`;
    - `'Points_X'` → `('Points', 0)`;
    - `'nope'` → None.
- [ ] **Step 2: Write failing integration tests.**
  - `test_plot_all_y_line_chart`: `--plot-data-range-all 1 y` → Left custom True, `lo < 0 < hi`. The range contains the Left range that `--plot-data-range-grow 1 y --sa --animation-format png --size 160` reports for the last frame. Grow ends at the union, so `all` ⊇ grow's last frame within 1e-9.
  - `test_plot_all_x_line_chart`: `--plot-data-range-all 1 x` → Bottom custom True, range == [-0.55, 0.55] within 1e-6. The Plot Over Line runs from x = -0.5 to 0.5 in the state, and 5 % padding is added.
  - `test_plot_all_x_quartile_time`: `--plot-data-range-all 2 x` → Bottom range == [-0.5, 10.5] within 1e-6 (time 0–10, padded).
  - `test_plot_sym`: `--plot-data-range-all 1 y --plot-sym 1 y` → Left `min == -max`.
  - `test_plot_all_quartile`: `--plot-data-range-all 2 y` → Left custom True, `lo < 0 < hi`.
  - `test_plot_grow_animation`: as above; returncode 0 and Left custom True.
  - `test_plot_right_axis_separate` (Review Focus 2): `right_axis_state.pvsm --plot-data-range-all 1 y --plot-data-range-all 1 right` → the Right range contains the `arc_length` range, which starts ≥ 0. The Left range is within the z-displacement magnitude, so Left max < Right max.
  - `test_plot_no_visible_series_warns`: `right_axis_state.pvsm` with `--plot-data-range-all 1 top`. The top axis has no series → returncode 0, a warning in stderr, and Top custom unchanged.
  - **Colorbar regression:** the existing `--cb-data-range-grow`/`clamp` animation tests still pass unchanged.
- [ ] **Step 3: Run** `python -m pytest test/test_pvrender.py -q -k "pad_range or grow_entries or axis_series or split_series or plot_all or plot_sym or plot_grow or right_axis or no_visible_series or cb_data_range"`. Expected: FAIL for the new tests.
- [ ] **Step 4: Implement.**
- [ ] **Step 5: Run** the step 3 command, then the full suite. Expected: PASS.
- [ ] **Step 6: Commit** with the message `feat: plot data-range all/grow/sym with margin; shared per-frame range cue`.

---

### Task 9: Parameter-study documentation and final verification

**Files:**
- Modify: `README.md` (new "Parameter studies" example section near the top of Examples), `pvrender.py` docstring (matching example)

**Interfaces:** none.

- [ ] **Step 1: Write the example.** It uses one command combining `-d`, `--fit-camera fit`, `--cb-data-range-all`, `--plot-data-range-all ... y`, `--cb-title`, `--plot-title`, `--suffix`. Add two sentences on `--keep-path` and on failing on missing data.
- [ ] **Step 2: Check the docs against the CLI.**
  - Every flag in `pvrender.parse_args(['x.pvsm', '--help'])` output appears in both the README and the docstring. Write a small throwaway check, or do it by eye; don't commit it.
  - The README options tables match the `--help` defaults.
- [ ] **Step 3: Run** the full suite: `python -m pytest test/test_pvrender.py -q`. Expected: all pass. Report the count and duration.
- [ ] **Step 4: Run** the example command against `test/radial_wave_state.pvsm -d test/data` by hand, and look at the PNG.
- [ ] **Step 5: Commit** with the message `docs: parameter-study example and flag reference`.
