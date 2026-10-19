"""
pvrender.py

Render ParaView .pvsm state files from the command line using `pvpython` or `pvbatch`,
with many customizable options.

Documentation: https://github.com/k-igeta/pvrender

# Usage

    pvbatch  pvrender.py <statefile.pvsm> [options]
    pvpython pvrender.py <statefile.pvsm> [options]

Requires ParaView 6.1 or newer (tested with 6.1.0); older versions trigger a warning.
The compatibility pin is intentional and is not bumped per release.

IMPORTANT: This script must be run with `pvbatch` or `pvpython` from a ParaView
installation — NOT with a regular `python` interpreter. Use `pvbatch` for headless/
offscreen rendering (servers, CI). Use `pvpython` for interactive use; add
`--force-offscreen-rendering` before the script name to suppress the render window.

## What it does

Loads a .pvsm state file, optionally remaps data file paths to a new location,
then saves any combination of outputs (screenshot, animation, extracts, state file)
or opens an interactive preview. Multiple outputs can be produced in a single run.

## Data path remapping

.pvsm files contain hardcoded absolute data paths. These options redirect them:

    -d, --datadir DIR              Remap all data files to DIR (matched by filename).
    -f, --filenames DICT           Explicit reader-to-file mapping as a Python dict string:
                                   "{'ReaderName.pvd': '/new/path/to/file.pvd'}"
    --restrict-to-datadir          Only load files found inside --datadir; fail on missing.
    --list-readers                 Print every reader (index, name, used, path), then continue.
    --keep-path READER             Allow reader READER (see --list-readers) to stay outside
                                   --datadir, e.g. a shared reference file. Its file must
                                   still exist. Repeatable; an unknown name is an error.
    --allow-missing-data           Warn instead of failing on the two checks below.

    -d and --filenames are mutually exclusive.

After loading, the readers feeding the rendered layout/view are checked:

    - Missing data: a reader's file, or a file listed in its .pvd, does not exist
      -> error (reader name and path listed).
    - Fallback to the template run: with -d DIR, ParaView keeps a reader's original path
      when its file is not found under DIR, so a run folder missing a file would silently
      render the template run's data. A reader still pointing outside DIR (any subfolder
      counts as inside) -> error. Use --keep-path for files that live elsewhere on purpose.
    - With --filenames, unmapped readers are not an error; only the existence check applies.

## Output actions (combine freely)

    --save-image       (--si)      Save a screenshot (PNG by default).
    --save-animation   (--sa)      Save an animation (MP4 by default).
    --save-extracts    (--se)      Save pipeline extracts (configured in ParaView GUI).
    --save-state       (--ss)      Save a .pvsm state file with current (remapped) paths.
    --interact         (-i)        Open interactive preview window (press q to continue).

## Output path

    -o, --outputname NAME          Base path/name without extension (default: "rendered").
                                   Directories are created automatically.
    --suffix                       Append _YYYYMMDD_HHMMSS to prevent overwriting.

## Layout, view, and timing

    --layout INDEX|NAME            Layout by 1-based index or name (default: 1).
    --view INDEX                   View within layout, 1-based. 0 = all views (default).
    --time T                       Time step to render (default: last time step).
    --interp-interval DT           Set the Discrete Time Step Interval of every Temporal
                                   Interpolator, giving evenly spaced steps (0 = original
                                   steps). Error if the state has none. Sources that still add
                                   their own time steps trigger a warning (set "Ignore Time"
                                   on them in ParaView). Frame indices count the new steps.
    --size N | W H                 Layout size in pixels (default: 1920). One value sets the
                                   longest side and preserves aspect ratio; two values set exact size.
    --fit-camera fit|out           Fit the camera of each rendered 3D view to the visible data
                                   (bounds over the frame window, computed once; the view
                                   direction is kept). fit: center on the data and move in or
                                   out until it just fits. out: only move out (or widen a
                                   parallel projection) when the data doesn't fit; otherwise
                                   the state's camera is kept exactly. Warns when a
                                   representation has a Translation/Scale/Orientation (the fit
                                   uses the data bounds) or a view shows nothing. Only the
                                   data bounds are fitted, not annotations (colorbar, axes
                                   grid labels, text): with a colorbar or axes grid shown,
                                   use --fit-margin 10 to 20.
    --fit-margin PCT              Margin on each side for --fit-camera, in percent of the
                                   view size, 0 <= PCT < 50 (default: 5).
    --palette NAME                 Background palette (default: gray).
                                   Aliases: white, black, gray, darkgray, neutralgray,
                                   lightgray, gradient.

## Screenshot options

    --image-format FMT             png (default), jpg, bmp, tif, tiff, vtk.
    --image-resolution N | W H     Override output resolution (independent of --size). One value
                                   sets the longest side; two values set exact size.
    --output-palette NAME          Override palette for saved output only.
    --transparent-background       Transparent background (if format supports it).
    --no-font-scaling              Disable automatic font scaling for saved outputs.

## Animation options

    --animation-format FMT         mp4 (default), avi, png, jpg, ogv, tif.
    --framerate N                  Frames per second (default: 30).
    --frame-start N                Start frame, 0-based (default: 0).
    --frame-end N                  End frame, 0-based, inclusive. -1 = last (default).
    --frame-stride N               Frame stride (default: 1).
    --bitrate N                    MP4 bitrate in bps (auto-estimated if 0 or omitted).
    --motion-factor F              Factor for bitrate estimation (default: 0.1).

## Colorbar options

    Colorbar index N is always 1-based. Use --list-colorbars to discover indices.

    Range modes (mutually exclusive per colorbar index):
    --cb-range N MIN MAX           Set a fixed range [MIN, MAX]. Repeatable.
    --cb-data-range-all N [N...]   Global min/max across all time steps (static).
    --cb-data-range-clamp N [N...] Per-frame range that tracks data each time step.
    --cb-data-range-grow N [N...]  Per-frame range that grows monotonically (never shrinks).

    Modifiers:
    --cb-sym N [N...]              Symmetrize range around zero: [-A, +A] where
                                   A = max(|min|, |max|). Requires a --cb-data-range-* flag
                                   for the same index.

    Appearance:
    --cb-colormap N COLORMAP       Set colormap preset name (case-insensitive). Repeatable.
    --cb-discretize N STEPS        Divide colormap into STEPS uniform bands (>= 2). Repeatable.
    --cb-title N TEXT              Set the colorbar title. Repeatable. Pass " " (a single space)
                                   to clear it; "" also works on shells that can pass it, but
                                   not through pvbatch on Windows.

## Plot options

    Plot index N is 1-based (chart views in layout order); use --list-plots to discover
    them. AXIS is x|bottom, y|left, right or top (case-insensitive).

    --list-plots                   Print plots (index, type, title, axis settings).
    --plot-range N AXIS MIN MAX    Fix the axis range to [MIN, MAX]. Repeatable.
    --plot-data-range-all N AXIS   Axis range = data range over all frames of the frame
                                   window, applied once.
    --plot-data-range-grow N AXIS  Per-frame range that grows to include each frame (never
                                   shrinks); --save-image uses the frame at --time.
    --plot-auto N AXIS             Automatic axis range (overrides a custom range in the state).
    --plot-sym N AXIS              Symmetrize around zero; needs a --plot-data-range-* flag
                                   for the same axis.
    --plot-log N AXIS on|off       Logarithmic axis scale. A fixed range on a log axis needs
                                   MIN > 0.
    --plot-title N TEXT            Set the plot title.
    --plot-axis-title N AXIS TEXT  Set an axis title.

    To clear a title (--plot-title, --plot-axis-title, --cb-title) pass a single space (" ");
    an empty string "" also works on shells that can pass it, but not through pvbatch on
    Windows.

    Range modes are mutually exclusive per plot axis.

    Data ranges (all/grow) come from what the chart draws: for y/left and right the visible
    series plotted on that axis, for x/bottom and top the X array (or the point/row index)
    of the series on that axis. A Plot Data Over Time statistics series spans its min()
    to max() arrays; a block's series ('<array> (id=0)') uses only that block, and is
    ignored if the chart doesn't show that block. --plot-sym is applied, then 5 % of the
    span is added on each side (in log space on a log axis). On a log axis a lower bound <= 0 is clipped to max / 1000
    (warning). An axis with no visible series or a single-valued range warns and keeps
    its state range. In a parameter study, all/grow fit each run's data; use --plot-range
    for axes that must be identical across runs.

### Commonly used colormaps

ParaView Defaults:
    `Fast`, `Turbo`, `Cool to Warm`, `Cool to Warm (Extended)`, `Black-Body Radiation`,
    `X Ray`, `Inferno`, `Black, Blue and White`, `Blue Orange (divergent)`, `Viridis`,
    `Cold and Hot`, `Linear Green (Gr4L)`, `Rainbow Desaturated`, `Blue - Green - Orange`,
    `Rainbow Uniform`, `Yellow - Gray - Blue`

Perceptually uniform sequential:
    `Viridis`, `Plasma`, `Inferno`, `Magma`, `Fast (Blues)`, `Fast (Reds)`, `Cividis`, `Turbo`

Diverging:
    `Cool to Warm`, `Cool to Warm (Extended)`, `Warm to Cool`, `Warm to Cool (Extended)`,
    `Blue Orange (divergent)`, `CIELab Blue to Red`, `Cold and Hot`,
    `BrBG`, `PRGn`, `PiYG`, `PuOr`, `BuRd`

Sequential:
    `Blues`, `Greens`, `Reds`, `Oranges`, `Purples`, `BuGn`, `BuPu`, `Grayscale`

Rainbow / multi-hue:
    `Blue to Red Rainbow`, `Rainbow Desaturated`, `Rainbow Uniform`,
    `Rainbow Blended White`, `Rainbow Blended Black`, `Rainbow Blended Grey`,
    `Spectrum`, `Jet`, `Fast`

Specialized scientific:
    `Black-Body Radiation`, `X Ray`, `Gray and Red`,
    `Green-Blue Asymmetric Divergent (62Blbc)`, `Haze`,
    `erdc_iceFire_H`, `erdc_iceFire_L`, `erdc_rainbow_bright`, `erdc_rainbow_dark`

## Inspection flags (print and continue, do not exit)

    --list-layouts                 Print all layouts (index, name, size).
    --list-views                   Print views in the selected layout.
    --list-colorbars               Print colorbars (index, array name, current range).
    --list-plots                   Print plots (index, type, title, axis settings).
    --list-colormaps               Print all available colormap preset names.
    --list-readers                 Print all readers (index, name, used, path).

## Examples

    # Parameter study: one run folder, everything fitted to that run's own data.
    # Find the indices with --list-colorbars and --list-plots. A missing reader file is an
    # error (no silent fallback to the template run); --keep-path READER exempts a file
    # that stays elsewhere on purpose. On Windows write it on one line (or continue with ^ in cmd, a backtick in PowerShell).
    pvbatch pvrender.py scene.pvsm -d runs/run_042/ -o out/run_042 --suffix --si \\
        --fit-camera fit --cb-data-range-all 1 --cb-title 1 "Displacement [m]" \\
        --plot-data-range-all 1 y --plot-title 1 "Displacement, run 042"

    # Screenshot with data from a different directory
    pvbatch pvrender.py scene.pvsm -d /data/run_002/ --save-image

    # Custom output name, white background, datetime suffix
    pvbatch pvrender.py scene.pvsm -o results/stress --si --palette white --suffix

    # Run folder with a larger model than the template run: move the camera out to fit
    pvbatch pvrender.py scene.pvsm -d /data/run_005/ --fit-camera out --si

    # Specific time step, exact resolution, JPEG format
    pvbatch pvrender.py scene.pvsm --si --time 5.0 --size 1920 1080 --image-format jpg

    # Animation at 10 fps, only frames 10 through 50
    pvbatch pvrender.py scene.pvsm --sa --framerate 10 --frame-start 10 --frame-end 50

    # Screenshot and animation in one run
    pvbatch pvrender.py scene.pvsm --si --sa -o output/render

    # Fix colorbar 1 to range [0, 500]
    pvbatch pvrender.py scene.pvsm --cb-range 1 0 500 --si

    # Auto-range from global data, symmetrized around zero
    pvbatch pvrender.py scene.pvsm --cb-data-range-all 1 --cb-sym 1 --si

    # Per-frame dynamic range for animation
    pvbatch pvrender.py scene.pvsm --cb-data-range-clamp 1 --sa

    # Change colormap to Viridis with 17 discrete color bands
    pvbatch pvrender.py scene.pvsm --cb-colormap 1 Viridis --cb-discretize 1 17 --si

    # Explicit reader-to-file mapping
    pvbatch pvrender.py scene.pvsm -f "{'reader.pvd': '/data/result.pvd'}" --si

    # Discover available colorbars and colormaps
    pvbatch pvrender.py scene.pvsm --list-colorbars --list-colormaps

# License

MIT License

Copyright (c) 2026: Ken Igeta.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software
and associated documentation files (the "Software"), to deal in the Software without
restriction, including without limitation the rights to use, copy, modify, merge, publish,
distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the
Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or
substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING
BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

# ParaView setup must precede stdlib imports — pvbatch initialises the
# rendering backend when these lines execute.
# The import is guarded so that plain Python (e.g. the unit tests) can import
# this module and use the pure helpers.
try:
    import paraview
except ImportError:
    paraview = None

if paraview is not None:
    paraview.compatibility.major = 6
    paraview.compatibility.minor = 1

    from paraview.simple import *
    paraview.simple._DisableFirstRenderCameraReset()

import ast
import argparse
import datetime
import inspect
import json
import math
import os
import re
import sys
import xml.etree.ElementTree as ET
from os.path import abspath, dirname

# ----------------------------------------------------------------
# Constants
# ----------------------------------------------------------------

_VIDEO_FORMATS = {'mp4', 'avi', 'ogv'}

_PALETTE_CHOICES = [
    'WarmGrayBackground', 'DarkGrayBackground', 'NeutralGrayBackground',
    'LightGrayBackground', 'WhiteBackground', 'BlackBackground',
    'GradientBackground', 'gray', 'grey', 'warmgray', 'warmgrey',
    'darkgray', 'darkgrey', 'neutralgray', 'neutralgrey', 'lightgray', 'lightgrey',
    'white', 'black', 'gradient',
]

_PALETTE_ALIASES = {
    'gray': 'WarmGrayBackground',
    'grey': 'WarmGrayBackground',
    'warmgray': 'WarmGrayBackground',
    'warmgrey': 'WarmGrayBackground',
    'darkgray': 'DarkGrayBackground',
    'darkgrey': 'DarkGrayBackground',
    'neutralgray': 'NeutralGrayBackground',
    'neutralgrey': 'NeutralGrayBackground',
    'lightgray': 'LightGrayBackground',
    'lightgrey': 'LightGrayBackground',
    'white': 'WhiteBackground',
    'black': 'BlackBackground',
    'gradient': 'GradientBackground',
}

# ----------------------------------------------------------------
# Functions
# ----------------------------------------------------------------

def fit_to_box(width, height, n):
    """Scale (width, height) so its longest side is n, preserving aspect ratio."""
    scale = n / max(width, height)
    return max(1, round(width * scale)), max(1, round(height * scale))


def estimate_mp4_bitrate(width, height, framerate=30, motion_factor=0.1,
        min_bitrate=200e3, max_bitrate=50e6):
    """
    Estimates a reasonable bitrate for MP4 video in bits per second (bps).
    """
    if width <= 0 or height <= 0 or framerate <= 0:
        raise ValueError("width, height and framerate must be positive")
    if motion_factor <= 0:
        raise ValueError("""motion_factor must be positive (default 0.1):
            - Low motion (e.g., slideshow, talking head): 0.05 - 0.07
            - Medium motion (e.g., typical movie/show): 0.1
            - High motion (e.g., sports, action scenes): 0.15 - 0.2""")

    pixels = width * height
    bitrate = pixels * framerate * motion_factor

    bitrate = max(bitrate, min_bitrate)
    bitrate = min(bitrate, max_bitrate)

    # Round to nearest 0.1 Mbps
    bitrate = int(round(bitrate / 1e6, 1) * 1e6)

    return bitrate


def warn(msg):
    """Print a warning to stderr."""
    print(f"warning: {msg}", file=sys.stderr)


_KNOWN_OUTPUT_EXTS = {'.png', '.jpg', '.jpeg', '.bmp', '.tif', '.tiff', '.vtk',
                      '.mp4', '.avi', '.ogv', '.pvsm'}


def strip_output_extension(name):
    """Strip a known output extension (case-insensitive); keep other dots (e.g. run_1.5)."""
    base, ext = os.path.splitext(name)
    return base if ext.lower() in _KNOWN_OUTPUT_EXTS else name


def resolve_layout_index(value, names):
    """Return the 0-based layout index for a 1-based index or an exact layout name."""
    value = str(value)
    try:
        i = int(value)
    except ValueError:
        i = None
    if i is not None and 1 <= i <= len(names):
        return i - 1
    if value in names:
        return names.index(value)
    if i is not None:
        raise SystemExit(f"error: --layout {i} out of range, must be between 1 and {len(names)}")
    raise SystemExit(f"error: --layout: layout '{value}' not found; available: {names}")


def _source_names_by_id():
    """Map each registered source's global id to its registration name."""
    return {src.GetGlobalIDAsString(): key[0] for key, src in GetSources().items()}


def apply_interp_interval(dt):
    """Set DiscreteTimeStepInterval on every Temporal Interpolator; return their names."""
    names = []
    for key, src in GetSources().items():
        if src.GetXMLName() == 'TemporalInterpolator':
            src.DiscreteTimeStepInterval = dt
            src.UpdatePipelineInformation()  # refreshes TimestepValues and the TimeKeeper
            names.append(key[0])
    if not names:
        raise SystemExit("error: --interp-interval: no Temporal Interpolator in the state")
    return names


def unsuppressed_time_sources():
    """Names of non-interpolator sources that still contribute time steps to the animation."""
    keeper = GetTimeKeeper()
    suppressed = {s.GetGlobalIDAsString() for s in keeper.SuppressedTimeSources}
    by_id = _source_names_by_id()
    names = []
    for src in keeper.TimeSources:
        sid = src.GetGlobalIDAsString()
        if sid in suppressed or src.GetXMLName() == 'TemporalInterpolator':
            continue
        if len(list(getattr(src, 'TimestepValues', None) or [])) > 0:
            names.append(by_id.get(sid, src.GetXMLName()))
    return names


def sequence_frame_times(start_time, end_time, n_frames):
    """Frame times of a 'Sequence' animation: n_frames evenly spaced from start_time to
    end_time (both included), as ParaView 6.1 plays and saves them."""
    if n_frames <= 1:
        return [start_time]
    step = (end_time - start_time) / (n_frames - 1)
    return [start_time + i * step for i in range(n_frames)]


def animation_frame_times(scene):
    """Times of all frames of the animation scene, indexed as SaveAnimation's FrameWindow
    indexes them: the data time steps in 'Snap To TimeSteps' mode (empty for static
    data), otherwise NumberOfFrames frames from StartTime to EndTime."""
    if scene.PlayMode == 'Snap To TimeSteps':
        return list(scene.TimeKeeper.TimestepValues)
    return sequence_frame_times(scene.StartTime, scene.EndTime, scene.NumberOfFrames)


def resolve_frame_window(start, end, stride, n_frames):
    """Return the validated (start, end) frame window; a negative end means the last frame."""
    if end < 0:
        end = n_frames - 1
    if stride < 1:
        raise SystemExit(f"error: --frame-stride must be >= 1, got {stride}")
    if not (0 <= start <= end < n_frames):
        raise SystemExit(
            f"error: frame window [{start}, {end}] invalid; need 0 <= start <= end < {n_frames} "
            f"(the animation has {n_frames} frame{'s' if n_frames != 1 else ''})")
    return start, end


def paraview_version_warning(version):
    """Return a warning message if version (major, minor) is older than 6.1, else None."""
    if tuple(version) < (6, 1):
        return (f"ParaView {version[0]}.{version[1]} detected; pvrender targets ParaView 6.1 "
                f"or newer and may not work correctly")
    return None


def parse_filenames(filenames_str):
    """
    Parse the --filenames argument which is a Dict-formatted string of the form:

        "{'readername1' : '<path1>', 'readername2' : '<path2>', ...}"

    Returns a list of dictionaries of the form:

        [{'name': 'readername1', 'FileName': '<path1>'}, ...]

    See: https://www.paraview.org/paraview-docs/latest/python/paraview.simple.html#paraview.simple.LoadState
    """
    try:
        filenames_dict = ast.literal_eval(filenames_str)
    except (ValueError, SyntaxError) as e:
        raise ValueError(f"Failed to parse --filenames argument: {e}")

    if not isinstance(filenames_dict, dict):
        raise ValueError("--filenames argument must be a dictionary")

    filenames = []
    for name, filepath in filenames_dict.items():
        filenames.append({'name': name, 'FileName': abspath(filepath)})

    return filenames

# ----------------------------------------------------------------
# Data-path checks
# ----------------------------------------------------------------

def parse_pvd_files(pvd_path):
    """Return the absolute paths of every DataSet/@file in a .pvd, resolved relative
    to the .pvd folder."""
    base = dirname(abspath(pvd_path))
    root = ET.parse(pvd_path).getroot()
    return [abspath(os.path.join(base, ds.get('file')))
            for ds in root.iter('DataSet') if ds.get('file')]


def is_inside_dir(path, directory):
    """True if path is directory or lies below it (any subfolder). Case-insensitive on
    Windows, slash-agnostic, relative paths resolved against the cwd."""
    p = os.path.normcase(abspath(path))
    d = os.path.normcase(abspath(directory))
    try:
        return os.path.commonpath([p, d]) == d
    except ValueError:  # different drives
        return False


def check_data_paths(readers, datadir, keep):
    """
    Check the file paths of the used readers.

    readers: [{'name': str, 'paths': [str], 'used': bool}, ...]
    Returns (missing, outside), lists of "name: path" messages:
        missing – paths that don't exist, and files listed in an existing .pvd that don't
        outside – with datadir set, paths not inside datadir (readers in keep are exempt)
    """
    missing, outside = [], []
    for reader in readers:
        if not reader['used']:
            continue
        name = reader['name']
        for path in reader['paths']:
            if not os.path.exists(path):
                missing.append(f"{name}: {path}")
            elif path.lower().endswith('.pvd'):
                try:
                    members = parse_pvd_files(path)
                except (ET.ParseError, OSError) as e:
                    missing.append(f"{name}: {path} (cannot read the .pvd: {e})")
                    members = []
                missing.extend(f"{name}: {m}" for m in members if not os.path.exists(m))
            if datadir is not None and name not in keep and not is_inside_dir(path, datadir):
                outside.append(f"{name}: {path}")
    return missing, outside


def _input_proxies(proxy):
    """Return the upstream proxies connected to any InputProperty of proxy (there may be
    several, e.g. DestinationMesh/SourceDataArrays)."""
    from paraview import servermanager
    out = []
    for name in proxy.ListProperties():
        prop = proxy.GetProperty(name)
        if isinstance(prop, servermanager.InputProperty):
            # items are source proxies (also for output ports > 0)
            out.extend(item for item in prop if item is not None)
    return out


def existing_representation(source, view):
    """Return the representation of source (output port 0) already in view, or None.
    Unlike GetDisplayProperties/GetRepresentation this never creates one."""
    gid = source.GetGlobalIDAsString()
    for rep in view.Representations:
        if 'Input' not in rep.ListProperties():
            continue
        src, port = _rep_source(rep)
        if src is not None and port == 0 and src.GetGlobalIDAsString() == gid:
            return rep
    return None


def _rep_is_drawn(rep):
    """True if a representation actually draws something: Visibility on, and for chart
    representations (which report Visibility 1 for every source) at least one series."""
    props = rep.ListProperties()
    if 'Input' not in props or 'Visibility' not in props or not rep.Visibility:
        return False
    if 'SeriesVisibility' in props and not list(rep.SeriesVisibility):
        return False
    return True


def refresh_chart_representations(views, t):
    """
    Make the drawn chart representations in views draw the series the state saved.

    Right after LoadState a chart representation of composite data (e.g. Plot Data Over
    Time) has not seen its input's block hierarchy yet, so its BlockSelectors read a
    fallback ('/Root' instead of the saved '/Root/id0'). When the input first executes,
    ParaView restores the saved selection on the proxy but leaves it pending: nothing
    under pvbatch pushes it to the VTK representation before the image is rendered, so
    the chart draws none of the saved series. Execute the input at time t, then push the
    pending (saved) values; no setting is changed and no representation is created.
    """
    for view in views:
        for rep in view.Representations:
            props = rep.ListProperties()
            if 'SeriesVisibility' not in props or not _rep_is_drawn(rep):
                continue
            src, _ = _rep_source(rep)
            if src is None:
                continue
            src.UpdatePipeline(t)
            rep.SMProxy.UpdateVTKObjects()


def find_readers(views):
    """
    Return every reader in the pipeline (a source with a FileName or FileNames property):
        [{'name': registration name, 'paths': [str], 'used': bool}, ...]
    used is True when the reader is upstream of a drawn representation in views.
    """
    upstream = set()
    stack = []
    for view in views:
        for rep in view.Representations:
            if _rep_is_drawn(rep):
                stack.extend(_input_proxies(rep))
    while stack:
        proxy = stack.pop()
        gid = proxy.GetGlobalIDAsString()
        if gid in upstream:
            continue
        upstream.add(gid)
        stack.extend(_input_proxies(proxy))

    readers = []
    for key, src in GetSources().items():
        props = src.ListProperties()
        file_props = [p for p in ('FileName', 'FileNames') if p in props]
        if not file_props:
            continue
        name = key[0] if isinstance(key, tuple) and key else None
        if not isinstance(name, str) or not name:
            raise SystemExit(
                f"error: cannot determine the registration name of reader "
                f"{src.GetXMLName()} (key {key!r})")
        paths = []
        for p in file_props:
            value = src.GetPropertyValue(p)
            values = [value] if isinstance(value, str) else list(value or [])
            paths.extend(str(v) for v in values if v)
        readers.append({'name': name, 'paths': paths,
                        'used': src.GetGlobalIDAsString() in upstream})
    return readers


def print_readers(readers):
    """Print a summary table of readers (for --list-readers)."""
    if not readers:
        print("No readers found.")
        return
    name_w = max(30, max(len(r['name']) for r in readers))
    print(f"  {'#':>3}  {'Name':<{name_w}}  {'Used':<4}  Path")
    print(f"  {'---':>3}  {'-'*name_w}  {'-'*4}  {'-'*30}")
    for i, r in enumerate(readers):
        used = 'yes' if r['used'] else 'no'
        paths = r['paths'] or ['(none)']
        print(f"  {i+1:>3}  {r['name']:<{name_w}}  {used:<4}  {paths[0]}")
        for path in paths[1:]:
            print(f"  {'':>3}  {'':<{name_w}}  {'':<4}  {path}")


def check_readers(args, views, datadir):
    """--list-readers, --keep-path validation and the data-path checks (main step 4)."""
    readers = find_readers(views)
    if args.list_readers:
        print_readers(readers)

    names = [r['name'] for r in readers]
    unknown = [n for n in args.keep_path if n not in names]
    if unknown:
        raise SystemExit(
            f"error: --keep-path: no reader named {', '.join(repr(n) for n in unknown)}; "
            f"available: {names} (see --list-readers)")

    missing, outside = check_data_paths(readers, datadir, set(args.keep_path))
    msg_missing = "data files not found:\n  " + "\n  ".join(missing)
    msg_outside = (
        "readers still point outside --datadir (the file was not found there, so ParaView "
        "kept the state's original path):\n  " + "\n  ".join(outside) +
        "\n  Use --keep-path NAME for files that intentionally live elsewhere.")
    if args.allow_missing_data:
        if missing:
            warn(msg_missing)
        if outside:
            warn(msg_outside)
        return
    if missing:
        raise SystemExit("error: " + msg_missing)
    if outside:
        raise SystemExit("error: " + msg_outside)

# ----------------------------------------------------------------
# Colorbar helpers
# ----------------------------------------------------------------

def apply_sym(lo, hi):
    """Expand [lo, hi] symmetrically around zero: [-A, +A] where A = max(|lo|, |hi|)."""
    A = max(abs(lo), abs(hi))
    return -A, A


def enumerate_colorbars(views):
    """
    Return a list of colorbars (unique LUTs) visible across the given views.

    Ordered by view position in the layout, then by representation stacking
    order within each view. Each entry is a dict with keys:
        lut         – the LUT proxy
        array_name  – name of the colored array
        field_assoc – field association string, e.g. 'POINTS' or 'CELLS'
    """
    colorbars = []
    seen = set()
    for view in views:
        if not view.IsA("vtkSMRenderViewProxy"):
            continue
        for source in GetSources().values():
            rep = existing_representation(source, view)
            if rep is None:
                continue
            try:
                visible = rep.Visibility
                lut = rep.LookupTable
                color_array = rep.ColorArrayName
            except AttributeError:
                continue
            if not visible or lut is None or not color_array or not color_array[1]:
                continue
            key = (color_array[1], color_array[0])
            if key in seen:
                continue
            seen.add(key)
            colorbars.append({
                'lut': lut,
                'array_name': color_array[1],
                'field_assoc': color_array[0],
            })
    return colorbars


def print_layouts(layouts):
    """Print a summary table of all layouts (for --list-layouts)."""
    items = list(layouts.items())
    if not items:
        print("No layouts found.")
        return
    print(f"  {'#':>3}  {'Name':<30}  Size")
    print(f"  {'---':>3}  {'-'*30}  {'-'*15}")
    for i, ((name, _), layout) in enumerate(items):
        w, h = layout.GetSize()
        print(f"  {i+1:>3}  {name:<30}  {w} x {h}")


def print_views(layout, views):
    """Print a summary table of views in a layout (for --list-views)."""
    try:
        layout_name = next(
            name for (name, _), lay in GetLayouts().items() if lay is layout
        )
    except StopIteration:
        layout_name = "selected layout"
    w, h = layout.GetSize()
    print(f"Layout '{layout_name}' ({w} x {h}):")
    if not views:
        print("  No views found.")
        return
    print(f"  {'#':>3}  {'Type':<25}  Size")
    print(f"  {'---':>3}  {'-'*25}  {'-'*15}")
    for i, view in enumerate(views):
        vw, vh = view.ViewSize
        print(f"  {i+1:>3}  {view.GetXMLName():<25}  {vw} x {vh}")


def print_colorbars(colorbars):
    """Print a summary table of discovered colorbars (for --list-colorbars)."""
    if not colorbars:
        print("No colorbars found.")
        return
    print(f"  {'#':>3}  {'Array':<30}  {'Field':<8}  Current range")
    print(f"  {'---':>3}  {'-'*30}  {'-'*8}  {'-'*20}")
    for i, cb in enumerate(colorbars):
        try:
            pts = list(cb['lut'].RGBPoints)
            range_str = f"[{pts[0]:.6g}, {pts[-4]:.6g}]" if pts else "(unknown)"
        except Exception:
            range_str = "(unknown)"
        print(f"  {i+1:>3}  {cb['array_name']:<30}  {cb['field_assoc']:<8}  {range_str}")


def print_colormaps():
    """Print a sorted, numbered list of all ParaView colormap preset names (for --list-colormaps)."""
    from paraview import servermanager
    presets = servermanager.vtkSMTransferFunctionPresets.GetInstance()
    names = sorted(presets.GetPresetName(i) for i in range(presets.GetNumberOfPresets()))
    if not names:
        print("No colormap presets found.")
        return
    col_w = max(len(n) for n in names)
    n_cols = max(1, min(3, 120 // (col_w + 8)))
    print(f"Available colormaps ({len(names)} total):")
    for i in range(0, len(names), n_cols):
        row = names[i:i + n_cols]
        parts = [f"  {i + j + 1:>3}  {name:<{col_w}}" for j, name in enumerate(row)]
        print("".join(parts).rstrip())


def _get_data_range_at_time(cb, views, t):
    """Return (min, max) of cb's array at time t across all visible representations,
    or None if no range could be found."""
    GetAnimationScene().TimeKeeper.Time = t
    lo, hi = float('inf'), float('-inf')
    array_name = cb['array_name']
    field_assoc = cb['field_assoc']
    sources = list(GetSources().items())
    for view in views:
        if not view.IsA("vtkSMRenderViewProxy"):
            continue
        for (source_name, _id), source in sources:
            rep = existing_representation(source, view)
            if rep is None:
                continue
            try:
                if not rep.Visibility:
                    continue
                color_array = rep.ColorArrayName
            except AttributeError:
                continue
            if not color_array or color_array[1] != array_name:
                continue
            try:
                source.UpdatePipeline(t)
                info = source.GetDataInformation()
                if field_assoc == 'POINTS':
                    arr_info = info.GetPointDataInformation().GetArrayInformation(array_name)
                elif field_assoc == 'CELLS':
                    arr_info = info.GetCellDataInformation().GetArrayInformation(array_name)
                else:
                    arr_info = None
                if arr_info is not None:
                    r = arr_info.GetComponentRange(-1)
                    lo = min(lo, r[0])
                    hi = max(hi, r[1])
            except Exception as e:
                warn(f"cannot read range of '{array_name}' from '{source_name}': {e}")
    return None if lo == float('inf') else (lo, hi)


def _get_global_data_range(cb, views):
    """Return global (min, max) of cb's array over all animation time steps, or None."""
    scene = GetAnimationScene()
    saved_time = scene.TimeKeeper.Time
    times = list(scene.TimeKeeper.TimestepValues) or [saved_time]
    glo, ghi = float('inf'), float('-inf')
    for t in times:
        r = _get_data_range_at_time(cb, views, t)
        if r is None:
            continue
        glo = min(glo, r[0])
        ghi = max(ghi, r[1])
    scene.TimeKeeper.Time = saved_time
    return None if glo == float('inf') else (glo, ghi)


def apply_colorbar_colormaps(args, colorbars):
    """
    Apply --cb-colormap presets.  Called before limit-setting so that any
    range override (--cb-range / --cb-data-range-*) wins over the preset's
    default scalar range.

    Preset names are matched case-insensitively against the installed ParaView
    presets.
    """
    if not args.cb_colormap:
        return

    # Build a case-insensitive lookup map from the installed presets once.
    from paraview import servermanager
    _presets = servermanager.vtkSMTransferFunctionPresets.GetInstance()
    preset_map = {
        _presets.GetPresetName(i).lower(): _presets.GetPresetName(i)
        for i in range(_presets.GetNumberOfPresets())
    }

    for item in args.cb_colormap:
        n, user_name = int(item[0]), item[1]
        matched = preset_map.get(user_name.lower())
        if matched is None:
            raise SystemExit(
                f"error: --cb-colormap: unknown colormap preset '{user_name}'.\n"
                f"  Use any ParaView preset name (case-insensitive). "
                f"Check the ParaView color map editor for valid names."
            )
        lut = colorbars[n - 1]['lut']
        # rescale=True keeps the current scalar range after applying the preset
        lut.ApplyPreset(matched, True)


def apply_colorbar_discretize(args, colorbars):
    """
    Apply --cb-discretize: enable discrete color banding on the chosen LUTs.

    Sets the LUT's Discretize flag and NumberOfTableValues so the colormap is
    divided into the requested number of uniform color bands.
    """
    if not args.cb_discretize:
        return
    for item in args.cb_discretize:
        n, steps = int(item[0]), int(item[1])
        lut = colorbars[n - 1]['lut']
        lut.Discretize = 1
        lut.NumberOfTableValues = steps


def validate_colorbar_args(args, n_colorbars):
    """Validate all --cb-* argument combinations. Raises SystemExit on error."""
    cb_range_indices = set()
    for item in (args.cb_range or []):
        try:
            cb_range_indices.add(int(item[0]))
        except (ValueError, IndexError):
            raise SystemExit(f"error: --cb-range: N must be an integer, got {item[0]!r}")
        try:
            lo, hi = float(item[1]), float(item[2])
        except (ValueError, IndexError):
            raise SystemExit(
                f"error: --cb-range: MIN and MAX must be numbers, got {item[1:3]!r}")
        if not lo < hi:
            raise SystemExit(f"error: --cb-range: MIN must be less than MAX, got {lo} {hi}")

    data_all   = set(args.cb_data_range_all)
    data_clamp = set(args.cb_data_range_clamp)
    data_grow  = set(args.cb_data_range_grow)
    sym        = set(args.cb_sym)
    all_data   = data_all | data_clamp | data_grow

    # Same index in more than one mode is a conflict
    mode_sets  = [cb_range_indices, data_all, data_clamp, data_grow]
    mode_names = ['--cb-range', '--cb-data-range-all', '--cb-data-range-clamp', '--cb-data-range-grow']
    for i in range(len(mode_sets)):
        for j in range(i + 1, len(mode_sets)):
            overlap = mode_sets[i] & mode_sets[j]
            if overlap:
                raise SystemExit(
                    f"error: colorbar index {sorted(overlap)} appears in both "
                    f"{mode_names[i]} and {mode_names[j]}"
                )

    # --cb-sym requires a data-range mode
    orphan = sym - all_data
    if orphan:
        raise SystemExit(
            f"error: --cb-sym {sorted(orphan)}: each index must also appear in a "
            f"--cb-data-range-* flag"
        )

    # Index bounds (includes --cb-colormap and --cb-discretize indices)
    colormap_indices = set()
    for item in (args.cb_colormap or []):
        try:
            colormap_indices.add(int(item[0]))
        except (ValueError, IndexError):
            raise SystemExit(f"error: --cb-colormap: N must be an integer, got {item[0]!r}")

    discretize_indices = set()
    for item in (args.cb_discretize or []):
        try:
            discretize_indices.add(int(item[0]))
        except (ValueError, IndexError):
            raise SystemExit(f"error: --cb-discretize: N must be an integer, got {item[0]!r}")
        try:
            steps = int(item[1])
        except (ValueError, IndexError):
            raise SystemExit(f"error: --cb-discretize: STEPS must be an integer, got {item[1]!r}")
        if steps < 2:
            raise SystemExit(f"error: --cb-discretize: STEPS must be >= 2, got {steps}")

    title_indices = set()
    for item in (args.cb_title or []):
        try:
            title_indices.add(int(item[0]))
        except (ValueError, IndexError):
            raise SystemExit(f"error: --cb-title: N must be an integer, got {item[0]!r}")

    for n in sorted(cb_range_indices | all_data | sym | colormap_indices | discretize_indices
                    | title_indices):
        if n < 1 or n > n_colorbars:
            raise SystemExit(
                f"error: colorbar index {n} out of range "
                f"(found {n_colorbars} colorbar{'s' if n_colorbars != 1 else ''})"
            )


def _disable_auto_rescale(lut):
    """
    Force the LUT's AutomaticRescaleRangeMode to "Never".

    Without this, a state file that sets the mode to "Clamp"/"Grow and update
    every timestep" causes ParaView to re-rescale the LUT on every timestep
    change, overwriting any range we set via --cb-range / --cb-data-range-*.
    """
    try:
        lut.AutomaticRescaleRangeMode = "Never"
    except (AttributeError, ValueError):
        pass


def apply_static_colorbar_limits(args, colorbars, views):
    """Apply --cb-range and --cb-data-range-all."""
    sym = set(args.cb_sym)

    for item in (args.cb_range or []):
        n, lo, hi = int(item[0]), float(item[1]), float(item[2])
        lut = colorbars[n - 1]['lut']
        _disable_auto_rescale(lut)
        lut.RescaleTransferFunction(lo, hi)

    for n in args.cb_data_range_all:
        r = _get_global_data_range(colorbars[n - 1], views)
        if r is None:
            warn(f"colorbar {n}: no data range found for '{colorbars[n - 1]['array_name']}'; "
                 f"range left as in state")
            continue
        lo, hi = r
        if n in sym:
            lo, hi = apply_sym(lo, hi)
        lut = colorbars[n - 1]['lut']
        _disable_auto_rescale(lut)
        lut.RescaleTransferFunction(lo, hi)


def precompute_dynamic_colorbar_ranges(args, colorbars, views, animation_scene, frame_times,
                                       at_time=None):
    """
    Pre-compute per-frame LUT ranges for --cb-data-range-clamp and --cb-data-range-grow.

    Returns None if no dynamic colorbars are requested; otherwise a dict:
        { array_name: [[t, lo, hi], ...] }   (one entry per frame, sorted by t)

    at_time (a screenshot time outside frame_times): clamp uses only at_time, grow the
    frames before at_time and at_time, so the last entry is the range at at_time.
    """
    clamp   = set(args.cb_data_range_clamp)
    grow    = set(args.cb_data_range_grow)
    sym     = set(args.cb_sym)
    dynamic = clamp | grow
    if not dynamic:
        return None

    saved_time = animation_scene.TimeKeeper.Time
    ranges  = {}   # {array_name: [[t, lo, hi], ...]}
    skipped = {}   # {n: number of frames without a range}

    for n in dynamic:
        _disable_auto_rescale(colorbars[n - 1]['lut'])

    for n in sorted(dynamic):
        cb = colorbars[n - 1]
        entries = []
        for t in _frames_up_to(frame_times, at_time, n in grow):
            r = _get_data_range_at_time(cb, views, t)
            if r is None:
                skipped[n] = skipped.get(n, 0) + 1
                continue
            entries.append([t, r[0], r[1]])
        if n in grow:
            entries = grow_entries(entries)
        if n in sym:
            entries = [[t, *apply_sym(lo, hi)] for t, lo, hi in entries]
        if entries:
            ranges.setdefault(cb['array_name'], []).extend(entries)

    animation_scene.TimeKeeper.Time = saved_time
    for n in sorted(skipped):
        arr = colorbars[n - 1]['array_name']
        if arr not in ranges:
            warn(f"colorbar {n}: no data range found for '{arr}'; range left as in state")
        else:
            warn(f"colorbar {n}: no data range found for '{arr}' in {skipped[n]} frame(s); "
                 f"those frames skipped")
    return ranges


# -- Per-frame ranges shared by colorbars and plots (one animation cue) --

def _frames_up_to(frame_times, at_time, grow):
    """The times a range is computed at: frame_times, or for a screenshot time at_time
    outside them, at_time alone (grow: the frames before at_time, then at_time)."""
    if at_time is None:
        return list(frame_times)
    return [t for t in frame_times if t < at_time] + [at_time] if grow else [at_time]


def grow_entries(entries):
    """For [[t, lo, hi], ...] sorted by t, return the running [[t, min lo, max hi], ...]
    (the range never shrinks). The input is not modified."""
    out = []
    for t, lo, hi in entries:
        if out:
            lo, hi = min(out[-1][1], lo), max(out[-1][2], hi)
        out.append([t, lo, hi])
    return out


def apply_dynamic_ranges_at_time(dynamic, t):
    """
    Apply the precomputed per-frame ranges at time t (nearest-time entry).

    dynamic = {'colorbars': {array_name: [[t, lo, hi], ...]},
               'plots': [{'view': registration name, 'axis': 'Left', 'log': bool,
                          'entries': [[t, lo, hi], ...]}, ...]}

    The source of this function is also embedded in the animation cue script
    (build_dynamic_cue), so it must be self-contained: no module-level names.
    """
    from paraview.simple import FindView, GetColorTransferFunction
    for array_name, entries in dynamic.get('colorbars', {}).items():
        best = min(entries, key=lambda e: abs(e[0] - t))
        GetColorTransferFunction(array_name).RescaleTransferFunction(best[1], best[2])
    for plot in dynamic.get('plots', []):
        view = FindView(plot['view'])
        if view is None:
            continue
        best = min(plot['entries'], key=lambda e: abs(e[0] - t))
        axis = plot['axis']
        setattr(view, axis + 'AxisUseCustomRange', 1)
        setattr(view, axis + 'AxisRangeMinimum', best[1])
        setattr(view, axis + 'AxisRangeMaximum', best[2])


def build_dynamic_cue(dynamic, animation_scene):
    """
    Register one PythonAnimationCue that applies the precomputed per-frame colorbar and
    plot ranges (see apply_dynamic_ranges_at_time) on every tick.
    Returns the cue proxy; remove it from animation_scene.Cues after SaveAnimation.
    """
    # The cue script runs in its own context: embed the data and the apply function.
    cue_script = f"""\
import json as _json
_dynamic = _json.loads({json.dumps(dynamic)!r})

{inspect.getsource(apply_dynamic_ranges_at_time)}

def start_cue(self):
    pass

def tick(self):
    from paraview.simple import GetAnimationScene
    apply_dynamic_ranges_at_time(_dynamic, GetAnimationScene().TimeKeeper.Time)

def end_cue(self):
    pass
"""
    cue = PythonAnimationCue()
    cue.Script = cue_script
    animation_scene.Cues.append(cue)
    return cue


# ----------------------------------------------------------------
# Plots (chart views): axis ranges, log scale, titles
# ----------------------------------------------------------------

_AXIS_ALIASES = {'x': 'Bottom', 'bottom': 'Bottom', 'y': 'Left', 'left': 'Left',
                 'top': 'Top', 'right': 'Right'}
_AXES = ('Bottom', 'Left', 'Right', 'Top')


def normalize_axis(name):
    """Map x/y/bottom/left/top/right (case-insensitive) to the ParaView axis name.
    Raises SystemExit on an unknown name."""
    try:
        return _AXIS_ALIASES[str(name).strip().lower()]
    except KeyError:
        raise SystemExit(f"error: unknown plot axis {name!r} "
                         f"(use one of: x, y, bottom, left, right, top)")


def enumerate_plots(views):
    """Return the chart views (those with axis properties) in the given order."""
    return [v for v in views if 'LeftAxisUseCustomRange' in v.ListProperties()]


def print_plots(plots):
    """Print a summary of the plots (for --list-plots)."""
    if not plots:
        print("No plots found.")
        return
    for i, view in enumerate(plots):
        title = getattr(view, 'ChartTitle', '')
        print(f"  {i+1:>3}  {view.GetXMLName():<20}  title: {title!r}")
        for ax in _AXES:
            custom = bool(getattr(view, ax + 'AxisUseCustomRange', False))
            lo = getattr(view, ax + 'AxisRangeMinimum', 0.0)
            hi = getattr(view, ax + 'AxisRangeMaximum', 0.0)
            log = bool(getattr(view, ax + 'AxisLogScale', False))
            print(f"         {ax:<7} custom {'on' if custom else 'off':<3}  "
                  f"[{lo:.6g}, {hi:.6g}]  log {'on' if log else 'off'}")


def normalize_title(text):
    """A blank (empty or whitespace-only) title text means "clear the title" -> "".
    pvbatch on Windows cannot receive an empty argument, so a single space is the way to
    clear a title there. Non-blank text is returned unchanged."""
    return '' if not text.strip() else text


def _plot_index(flag, text, n_plots):
    try:
        n = int(text)
    except (TypeError, ValueError):
        raise SystemExit(f"error: {flag}: N must be an integer, got {text!r}")
    if n < 1 or n > n_plots:
        raise SystemExit(f"error: {flag}: plot index {n} out of range "
                         f"(found {n_plots} plot{'s' if n_plots != 1 else ''})")
    return n


def _plot_number(flag, text):
    try:
        return float(text)
    except (TypeError, ValueError):
        raise SystemExit(f"error: {flag}: MIN and MAX must be numbers, got {text!r}")


def build_plot_specs(args, n_plots):
    """Validate the --plot-* flags and return {(n, axis): spec}. spec is
    {'mode': 'fixed'|'all'|'grow'|'auto'|None, 'min', 'max', 'sym', 'log', 'title'}.
    Plot-title indices are validated here too (see build_chart_titles)."""
    specs = {}

    def spec(flag, n_text, axis_text):
        n = _plot_index(flag, n_text, n_plots)
        key = (n, normalize_axis(axis_text))
        return key, specs.setdefault(key, {'mode': None, 'min': None, 'max': None,
                                           'sym': False, 'log': None, 'title': None})

    def set_mode(flag, key, s, mode):
        if s['mode'] is not None and s['mode'] != mode:
            raise SystemExit(f"error: plot {key[0]} axis {key[1]}: {flag} conflicts with "
                             f"another range mode ({s['mode']}); use only one per axis")
        s['mode'] = mode

    for item in (args.plot_range or []):
        key, s = spec('--plot-range', item[0], item[1])
        lo = _plot_number('--plot-range', item[2])
        hi = _plot_number('--plot-range', item[3])
        if not lo < hi:
            raise SystemExit(f"error: --plot-range: MIN must be less than MAX, got {lo:g} {hi:g}")
        set_mode('--plot-range', key, s, 'fixed')
        s['min'], s['max'] = lo, hi
    for flag, attr, mode in (('--plot-data-range-all', 'plot_data_range_all', 'all'),
                             ('--plot-data-range-grow', 'plot_data_range_grow', 'grow'),
                             ('--plot-auto', 'plot_auto', 'auto')):
        for item in (getattr(args, attr) or []):
            key, s = spec(flag, item[0], item[1])
            set_mode(flag, key, s, mode)
    for item in (args.plot_sym or []):
        key, s = spec('--plot-sym', item[0], item[1])
        s['sym'] = True
    for item in (args.plot_log or []):
        key, s = spec('--plot-log', item[0], item[1])
        if item[2].lower() not in ('on', 'off'):
            raise SystemExit(f"error: --plot-log: state must be on or off, got {item[2]!r}")
        s['log'] = item[2].lower() == 'on'
    for item in (args.plot_axis_title or []):
        key, s = spec('--plot-axis-title', item[0], item[1])
        s['title'] = normalize_title(item[2])
    for item in (args.plot_title or []):
        _plot_index('--plot-title', item[0], n_plots)

    for key, s in specs.items():
        if s['sym'] and s['mode'] not in ('all', 'grow'):
            raise SystemExit(f"error: --plot-sym {key[0]} {key[1]}: needs "
                             f"--plot-data-range-all or --plot-data-range-grow for the same axis")
        if s['mode'] == 'fixed' and s['log'] and s['min'] <= 0:
            raise SystemExit(f"error: plot {key[0]} axis {key[1]}: a fixed range on a log axis "
                             f"needs MIN > 0, got {s['min']:g}")
    return specs


def build_chart_titles(args):
    """Return {plot number: title} from --plot-title (indices validated by build_plot_specs)."""
    return {int(item[0]): normalize_title(item[1]) for item in (args.plot_title or [])}


def apply_plot_static(specs, plots, chart_titles):
    """Apply the static plot settings: fixed/auto ranges, log scale, axis and chart titles.
    'all'/'grow' ranges are applied separately."""
    for (n, axis), s in sorted(specs.items()):
        view = plots[n - 1]
        if s['log'] is not None:
            setattr(view, axis + 'AxisLogScale', 1 if s['log'] else 0)
        if s['mode'] == 'fixed':
            if s['log'] is None and getattr(view, axis + 'AxisLogScale', 0) and s['min'] <= 0:
                raise SystemExit(f"error: plot {n} axis {axis} is logarithmic: a fixed range "
                                 f"needs MIN > 0, got {s['min']:g}")
            apply_plot_axis_range(view, axis, s['min'], s['max'])
        elif s['mode'] == 'auto':
            setattr(view, axis + 'AxisUseCustomRange', 0)
        if s['title'] is not None:
            setattr(view, axis + 'AxisTitle', s['title'])
    for n, title in chart_titles.items():
        plots[n - 1].ChartTitle = title


def apply_colorbar_titles(args, colorbars, views):
    """Set --cb-title on the scalar bars already shown in views. Never creates one."""
    for item in (args.cb_title or []):
        n, text = int(item[0]), normalize_title(item[1])
        lut = colorbars[n - 1]['lut']
        found = False
        for view in views:
            for rep in view.Representations:
                if rep.GetXMLName() == 'ScalarBarWidgetRepresentation' and rep.LookupTable == lut:
                    rep.Title = text
                    found = True
        if not found:
            warn(f"colorbar {n}: no scalar bar is shown for '{colorbars[n - 1]['array_name']}'; "
                 f"--cb-title ignored")


# -- Plot data ranges (--plot-data-range-all / -grow / --plot-sym) --

def pad_range(lo, hi, frac=0.05, log=False):
    """Add frac of the span on each side of [lo, hi]. With log=True the margin is added in
    log10 space, which needs lo > 0 (ValueError otherwise)."""
    if log:
        if lo <= 0 or hi <= 0:
            raise ValueError(f"pad_range: a log range needs positive bounds, got [{lo}, {hi}]")
        a, b = math.log10(lo), math.log10(hi)
        span = b - a
        return 10 ** (a - frac * span), 10 ** (b + frac * span)
    span = hi - lo
    return lo - frac * span, hi + frac * span


# Series corners follow vtkChart's plot corners. Verified in ParaView 6.1 by setting
# SeriesPlotCorner and reading vtkChartXY.GetPlotCorner(plot) and the plot's X/Y axis
# positions: 0 = bottom-left (X bottom, Y left), 1 = bottom-right (X bottom, Y right),
# 2 = top-right (X top, Y right), 3 = top-left (X top, Y left).
_Y_AXIS_CORNERS = {'Left': ('0', '3'), 'Right': ('1', '2')}
_X_AXIS_CORNERS = {'Bottom': ('0', '1'), 'Top': ('2', '3')}


def _series_corners(plot_corners):
    """{series: corner} from the flat [name, corner, ...] SeriesPlotCorner list."""
    flat = [str(v) for v in plot_corners]
    return dict(zip(flat[0::2], flat[1::2]))


def axis_series(series_visibility, plot_corners, axis):
    """The visible series plotted against Y axis 'Left' or 'Right'. plot_corners is the
    flat [name, corner, ...] SeriesPlotCorner list; unlisted series are on corner '0'.
    'Bottom'/'Top' are X axes, whose range comes from the X array: returns []."""
    if axis not in _Y_AXIS_CORNERS:
        return []
    corners = _series_corners(plot_corners)
    return [s for s in series_visibility if corners.get(s, '0') in _Y_AXIS_CORNERS[axis]]


def x_axis_has_series(series_visibility, plot_corners, axis):
    """True if a visible series is plotted against X axis 'Bottom' (corners 0/1) or 'Top'
    (corners 2/3), i.e. the representation's X array is shown on that axis."""
    corners = _series_corners(plot_corners)
    return any(corners.get(s, '0') in _X_AXIS_CORNERS[axis] for s in series_visibility)


_SERIES_SUFFIX = re.compile(r' \((stats|id=\d+)\)$')
_COMPONENT_SUFFIX = {'X': 0, 'Y': 1, 'Z': 2, 'Magnitude': -1}


def split_series_name(series, array_names):
    """
    Resolve a chart series name to (array name, component) against array_names, or None.
    A trailing " (stats)" or " (id=<n>)" (Plot Data Over Time blocks) is stripped. An exact
    array name gives component -1; otherwise the part after the last '_' must be X, Y, Z,
    Magnitude or an integer (component 0, 1, 2, -1 or that integer). 'Points' may be in
    array_names and then stands for the point coordinates (series Points_X etc.).
    """
    name = _SERIES_SUFFIX.sub('', series)
    if name in array_names:
        return name, -1
    base, sep, suffix = name.rpartition('_')
    if not sep or base not in array_names:
        return None
    if suffix in _COMPONENT_SUFFIX:
        return base, _COMPONENT_SUFFIX[suffix]
    if suffix.isdigit():
        return base, int(suffix)
    return None


_BLOCK_SUFFIX = re.compile(r'^(.*) \(([^()]*)\)$')


def split_block_suffix(series):
    """Split a chart series name of composite data into (name, block label), e.g.
    'z-Displacement [m] (id=0)' -> ('z-Displacement [m]', 'id=0'), 'N (stats)' ->
    ('N', 'stats'), 'X (vtkMultiBlockDataSet)' -> ('X', 'vtkMultiBlockDataSet'). A name
    without a trailing ' (<label>)' gives (series, None). The label is the block's label
    in the data hierarchy (its node name when it has no label)."""
    m = _BLOCK_SUFFIX.match(series)
    return (m.group(1), m.group(2)) if m else (series, None)


def _prop_text(proxy, name):
    """First value of a string property as text ('' if unset)."""
    value = proxy.GetPropertyValue(name)
    if isinstance(value, str):
        return value
    value = list(value or [])
    return str(value[0]) if value else ''


def _subset_info(src, port, selector, assembly='Hierarchy'):
    try:
        return src.SMProxy.GetSubsetDataInformation(port, selector, assembly)
    except Exception:
        return None


def _chart_blocks(rep, src, port):
    """
    The data a chart representation shows. Returns (infos, labels):
        infos  – vtkPVDataInformation of the selected blocks (one per BlockSelectors
                 entry) for composite data, else [whole output]
        labels – None for non-composite data; else {block label: hierarchy path of that
                 block if rep shows it (it is, or lies under, a selected block), else None}.
                 Series of composite data are named '<array> (<block label>)'.
    """
    full = src.GetDataInformation(port).DataInformation
    if not full.IsCompositeDataSet():
        return [full], None
    props = rep.ListProperties()
    selectors = [str(s) for s in rep.BlockSelectors] if 'BlockSelectors' in props else []
    assembly = (_prop_text(rep, 'Assembly') if 'Assembly' in props else '') or 'Hierarchy'
    infos = [i for i in (_subset_info(src, port, s, assembly) for s in selectors) if i]
    hierarchy = full.GetHierarchy()
    if hierarchy is None:
        return infos or [full], {}
    selected = None  # selectors of another assembly can't be mapped: treat all as shown
    if assembly == 'Hierarchy':
        selected = [hierarchy.GetNodePath(n) for n in hierarchy.SelectNodes(selectors or ['/'])]
    labels = {}
    for node in [0] + list(hierarchy.GetChildNodes(0, True)):
        path = hierarchy.GetNodePath(node)
        label = hierarchy.GetAttributeOrDefault(node, 'label', hierarchy.GetNodeName(node))
        shown = selected is None or any(path == p or path.startswith(p + '/') for p in selected)
        if labels.get(label) is None:
            labels[label] = path if shown else None
    return infos or [full], labels


_PDOT_BLOCK = re.compile(r'stats|id=\d+')


def _resolve_series(src, port, infos, labels, attribute, series):
    """Range of one chart series. Returns (range or None, drawn). drawn is False when the
    series names a block that the representation does not show (or that does not exist,
    e.g. a stale '(stats)' series after turning "Only Report Selection Statistics" off):
    such a series draws nothing, so it is skipped without a warning."""
    if labels is not None:
        name, label = split_block_suffix(series)
        if label is not None and label in labels:
            if labels[label] is None:
                return None, False
            info = _subset_info(src, port, labels[label])
            if info is None:
                return None, False
            return _series_range([info], attribute, name), True
        if label is not None:
            # No block has this label: a Plot Data Over Time block missing from the output,
            # or an array name with parentheses, e.g. 'p (bar)'.
            if _PDOT_BLOCK.fullmatch(label):
                return None, False
            r = _series_range(infos, attribute, series)
            return r, r is not None
    return _series_range(infos, attribute, series), True


_ATTRIBUTE_INFO = {'Point Data': 'GetPointDataInformation',
                   'Cell Data': 'GetCellDataInformation',
                   'Row Data': 'GetRowDataInformation'}

_warned_series = set()


def _range_union(a, b):
    if b is None or b[0] > b[1]:
        return a
    return b if a is None else (min(a[0], b[0]), max(a[1], b[1]))


def _array_component_range(attr_info, name, comp):
    arr = attr_info.GetArrayInformation(name)
    if arr is None or comp >= arr.GetNumberOfComponents():
        return None
    return tuple(arr.GetComponentRange(comp))


def _series_range(infos, attribute, series):
    """Union of the data range of one series over infos, or None if unresolvable."""
    getter = _ATTRIBUTE_INFO.get(attribute)
    if getter is None:
        return None
    out = None
    for info in infos:
        attr_info = getattr(info, getter)()
        names = [attr_info.GetArrayInformation(i).GetName()
                 for i in range(attr_info.GetNumberOfArrays())]
        coords = attribute == 'Point Data' and 'Points' not in names
        hit = split_series_name(series, names + (['Points'] if coords else []))
        if hit is None:
            # Plot Data Over Time statistics block (series "<array> (stats)", or plain
            # "<array>" when the output has only that block): the row arrays are
            # min(<array>), max(<array>), avg(...), ...; min .. max bound every drawn curve
            # and band.
            stats = [a[4:-1] for a in names if a.startswith('min(') and a.endswith(')')]
            stat = split_series_name(series, stats)
            if stat is not None:
                for fn in ('min', 'max'):
                    out = _range_union(out, _array_component_range(
                        attr_info, f"{fn}({stat[0]})", stat[1]))
            continue
        name, comp = hit
        if coords and name == 'Points':
            if comp in (0, 1, 2):
                b = info.GetBounds()
                out = _range_union(out, (b[2 * comp], b[2 * comp + 1]))
            else:
                pts = info.GetPointArrayInformation()
                if pts is not None:
                    out = _range_union(out, tuple(pts.GetComponentRange(comp)))
        else:
            out = _range_union(out, _array_component_range(attr_info, name, comp))
    return out


def _index_range(infos, attribute):
    """[0, n - 1] for the largest number of points/cells/rows over infos, or None."""
    getter = {'Point Data': 'GetNumberOfPoints', 'Cell Data': 'GetNumberOfCells',
              'Row Data': 'GetNumberOfRows'}.get(attribute)
    if getter is None:
        return None
    n = max(getattr(info, getter)() for info in infos)
    return (0.0, float(n - 1)) if n > 0 else None


def _get_plot_axis_range_at_time(view, axis, t, label=None):
    """
    Data range (min, max) at time t of what chart view draws against axis, or None.
    Y axes ('Left'/'Right'): the visible series on that axis (SeriesPlotCorner). X axes
    ('Bottom'/'Top'): the X array (or the point/row index with UseIndexForXAxis) of each
    representation with a visible series on that axis. Only representations with a
    non-empty SeriesVisibility count. For composite data (e.g. Plot Data Over Time) a
    series '<array> (<block label>)' uses only that block; a series whose block the
    representation doesn't show (or that doesn't exist) draws nothing and is skipped
    without a warning. Series in a shown block that can't be resolved warn once and are
    skipped. label (e.g. 'plot 1 axis Left') prefixes the warnings.
    """
    label = label or f"plot axis {axis}"
    out = None
    for rep in view.Representations:
        props = rep.ListProperties()
        if 'SeriesVisibility' not in props or not _rep_is_drawn(rep):
            continue
        visible = [str(s) for s in rep.SeriesVisibility]
        corners = list(rep.SeriesPlotCorner) if 'SeriesPlotCorner' in props else []
        if axis in _X_AXIS_CORNERS:
            if not x_axis_has_series(visible, corners, axis):
                continue
            use_index = bool(rep.UseIndexForXAxis) if 'UseIndexForXAxis' in props else False
            series = [] if use_index else [_prop_text(rep, 'XArrayName')]
        else:
            use_index = False
            series = axis_series(visible, corners, axis)
            if not series:
                continue
        src, port = _rep_source(rep)
        if src is None:
            continue
        src.UpdatePipeline(t)
        infos, labels = _chart_blocks(rep, src, port)
        if axis in _X_AXIS_CORNERS and labels:
            # composite data: the X array of the shown blocks with a series on this axis
            corner_of = _series_corners(corners)
            on_axis = [split_block_suffix(v)[1] for v in visible
                       if corner_of.get(v, '0') in _X_AXIS_CORNERS[axis]]
            known = [b for b in on_axis if b in labels]
            if known:
                paths = sorted({labels[b] for b in known if labels[b] is not None})
                if not paths:
                    continue  # none of those series is drawn
                infos = [i for i in (_subset_info(src, port, p) for p in paths) if i]
        attribute = _prop_text(rep, 'AttributeType') if 'AttributeType' in props else ''

        def warn_once(what):
            key = (label, src.GetGlobalIDAsString(), what)
            if key not in _warned_series:
                _warned_series.add(key)
                name = _source_names_by_id().get(src.GetGlobalIDAsString(), src.GetXMLName())
                warn(f"{label}: {what} ({attribute or 'no attribute type'}) not found in the "
                     f"data of '{name}'; ignored for the axis range")

        if use_index:
            r = _index_range(infos, attribute)
            if r is None:
                warn_once("the point/row index")
            out = _range_union(out, r)
        for s in series:
            if axis in _X_AXIS_CORNERS:
                r, drawn = _series_range(infos, attribute, s), True
            else:
                r, drawn = _resolve_series(src, port, infos, labels, attribute, s)
            if r is None and drawn:
                warn_once(f"series {s!r}")
            out = _range_union(out, r)
    return out


def _finish_plot_range(lo, hi, sym, log):
    """sym -> log clip -> margin. Returns ((lo, hi) or None, note); note is None,
    'clipped' (log axis, lo <= 0 raised to hi / 1000), 'nonpositive' or 'degenerate'."""
    if sym:
        lo, hi = apply_sym(lo, hi)
    note = None
    if log and lo <= 0:
        if hi <= 0:
            return None, 'nonpositive'
        lo, note = hi / 1000, 'clipped'
    if not lo < hi:
        return None, 'degenerate'
    return pad_range(lo, hi, log=log), note


def precompute_plot_ranges(specs, plots, frame_times, at_time=None):
    """
    Compute the --plot-data-range-all/-grow axis ranges over frame_times (main step 9).

    Returns (static, dynamic):
        static  – {(n, axis): (lo, hi)} for 'all' axes (union over frame_times)
        dynamic – [{'view': registration name, 'axis': axis, 'log': bool,
                    'entries': [[t, lo, hi], ...]}, ...] for 'grow' axes
    at_time (a screenshot time outside frame_times) is added to the 'all' union; 'grow'
    then uses the frames before at_time and at_time, so its last entry is at at_time.
    Ranges get --plot-sym, then a 5 % margin (in log space on a log axis). On a log axis a
    computed lower bound <= 0 is clipped to hi / 1000 with a warning. An axis without a
    usable range (no series, no data, min == max) warns and is left as in the state.
    """
    from paraview import servermanager
    pm = servermanager.ProxyManager()
    static, dynamic = {}, []
    for (n, axis), s in sorted(specs.items()):
        if s['mode'] not in ('all', 'grow'):
            continue
        view = plots[n - 1]
        label = f"plot {n} axis {axis}"
        log = s['log'] if s['log'] is not None else bool(getattr(view, axis + 'AxisLogScale', 0))
        if s['mode'] == 'all' and at_time is not None:
            times = list(frame_times) + [at_time]
        else:
            times = _frames_up_to(frame_times, at_time, True)
        raw = []
        for t in times:
            r = _get_plot_axis_range_at_time(view, axis, t, label)
            if r is not None:
                raw.append([t, r[0], r[1]])
        if not raw:
            warn(f"{label}: no data range found (no visible series on this axis, or their "
                 f"data could not be read); axis left as in state")
            continue
        if len(raw) < len(times):
            warn(f"{label}: no data range found in {len(times) - len(raw)} frame(s); "
                 f"those frames skipped")
        if s['mode'] == 'all':
            entries = [[None, min(e[1] for e in raw), max(e[2] for e in raw)]]
        else:
            entries = grow_entries(raw)
        finished, notes = [], {}
        for t, lo, hi in entries:
            r, note = _finish_plot_range(lo, hi, s['sym'], log)
            if note:
                notes[note] = notes.get(note, 0) + 1
            if r is not None:
                finished.append([t, r[0], r[1]])
        frames = {k: "" if s['mode'] == 'all' else f" in {v} frame(s)" for k, v in notes.items()}
        rest = "those frames skipped" if finished else "axis left as in state"
        if 'clipped' in notes:
            warn(f"{label}: log axis, but the data range reaches <= 0{frames['clipped']}; "
                 f"lower bound clipped to max / 1000")
        if 'nonpositive' in notes:
            warn(f"{label}: log axis, but the data is all <= 0{frames['nonpositive']}; {rest}")
        if 'degenerate' in notes:
            warn(f"{label}: the data range is a single value (min == max)"
                 f"{frames['degenerate']}; {rest}")
        if not finished:
            continue
        if s['mode'] == 'all':
            static[(n, axis)] = (finished[0][1], finished[0][2])
            continue
        name = pm.GetProxyName('views', view)
        if not name:
            warn(f"{label}: the view has no registration name; per-frame range not applied")
            continue
        dynamic.append({'view': name, 'axis': axis, 'log': log, 'entries': finished})
    return static, dynamic


def apply_plot_axis_range(view, axis, lo, hi):
    """Set a custom range [lo, hi] on axis of a chart view."""
    setattr(view, axis + 'AxisUseCustomRange', 1)
    setattr(view, axis + 'AxisRangeMinimum', lo)
    setattr(view, axis + 'AxisRangeMaximum', hi)


# ----------------------------------------------------------------
# Camera fit
# ----------------------------------------------------------------

def _vsub(a, b):
    return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]


def _vdot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _vscale(a, k):
    return [a[0] * k, a[1] * k, a[2] * k]


def _vunit(a):
    n = math.sqrt(_vdot(a, a))
    return [a[0] / n, a[1] / n, a[2] / n]


def _vcross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def fit_camera(position, focal_point, view_up, view_angle, parallel, parallel_scale, aspect,
               bounds, margin_pct, mode):
    """
    Fit the camera to bounds [xmin, xmax, ymin, ymax, zmin, zmax], keeping the view
    direction and view up. aspect is width / height; margin_pct is the margin on each side
    in percent of the viewport. mode:
        'fit' – center on the bounds and move in or out until the bounds just fit
        'out' – keep the focal point; only move out (or widen the parallel scale) if the
                bounds don't fit; otherwise return the inputs unchanged
    Returns {'position': [x, y, z], 'focal_point': [x, y, z], 'parallel_scale': float}.
    """
    focal_point, position = list(focal_point), list(position)
    to_focal = _vsub(focal_point, position)
    dist0 = math.sqrt(_vdot(to_focal, to_focal))
    d = _vunit(to_focal)
    up = _vsub(view_up, _vscale(d, _vdot(view_up, d)))
    if _vdot(up, up) < 1e-24:  # view up parallel to the view direction: pick any normal
        axis = min(range(3), key=lambda i: abs(d[i]))
        e = [0.0, 0.0, 0.0]
        e[axis] = 1.0
        up = _vsub(e, _vscale(d, d[axis]))
    u = _vunit(up)
    r = _vcross(d, u)

    s = 1 - 2 * margin_pct / 100   # usable fraction of each half-extent
    tv = math.tan(math.radians(view_angle) / 2)
    th = tv * aspect
    if mode == 'fit':
        center = [(bounds[0] + bounds[1]) / 2, (bounds[2] + bounds[3]) / 2,
                  (bounds[4] + bounds[5]) / 2]
    else:
        center = focal_point

    corners = []
    for cx in bounds[0:2]:
        for cy in bounds[2:4]:
            for cz in bounds[4:6]:
                v = _vsub([cx, cy, cz], center)
                corners.append((_vdot(v, r), _vdot(v, u), _vdot(v, d)))

    unchanged = {'position': position, 'focal_point': focal_point,
                 'parallel_scale': parallel_scale}
    if not parallel:
        need = max(max(abs(x) / (th * s), abs(y) / (tv * s)) - z for x, y, z in corners)
        dist = need if mode == 'fit' else max(dist0, need)
        if mode != 'fit' and dist == dist0:
            return unchanged
        scale = parallel_scale
    else:
        need = max(max(abs(x) / (aspect * s), abs(y) / s) for x, y, z in corners)
        scale = need if mode == 'fit' else max(parallel_scale, need)
        # Keep the camera distance unless the nearest corner is closer than 5 % of the
        # bounds diagonal (or behind the camera); then move back to one full diagonal of
        # clearance. VTK's near plane is >= ~0.001 * far, so a tiny clearance would still
        # clip the nearest corner. Moving a parallel camera back doesn't change the image.
        diag = math.sqrt((bounds[1] - bounds[0]) ** 2 + (bounds[3] - bounds[2]) ** 2
                         + (bounds[5] - bounds[4]) ** 2)
        nearest = max(-z for x, y, z in corners)
        dist = nearest + diag if dist0 < nearest + 0.05 * diag else dist0
        if mode != 'fit' and scale == parallel_scale and dist == dist0:
            return unchanged
    return {'position': _vsub(center, _vscale(d, dist)), 'focal_point': list(center),
            'parallel_scale': scale}


def _rep_source(rep):
    """Return (source proxy, output port) feeding rep's Input."""
    from paraview import servermanager
    prop = rep.SMProxy.GetProperty('Input')
    return (servermanager._getPyProxy(prop.GetProxy(0)),
            prop.GetOutputPortForConnection(0))


def _rep_transform_props(rep):
    """Names of rep's Translation/Position, Scale, Orientation, UserTransform properties
    that are not identity."""
    identity = {'Translation': [0.0] * 3, 'Position': [0.0] * 3, 'Scale': [1.0] * 3,
                'Orientation': [0.0] * 3,
                'UserTransform': [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]}
    props = rep.ListProperties()
    out = []
    for name, ident in identity.items():
        if name not in props:
            continue
        try:
            value = [float(v) for v in rep.GetPropertyValue(name)]
        except (TypeError, ValueError):
            continue
        if len(value) == len(ident) and value != ident:
            out.append(name)
    return out


def collect_view_bounds(view, frame_times):
    """
    Return the union over frame_times of the data bounds of the visible representations
    (with an Input) in view, as [xmin, xmax, ymin, ymax, zmin, zmax], or None if nothing
    visible has valid bounds. Warns once per representation with a non-identity
    Translation/Scale/Orientation: the bounds are those of the data, not of the displayed
    geometry.
    """
    names = _source_names_by_id()
    lo, hi = [float('inf')] * 3, [float('-inf')] * 3
    for rep in view.Representations:
        props = rep.ListProperties()
        if 'Input' not in props or 'Visibility' not in props or not rep.Visibility:
            continue
        src, port = _rep_source(rep)
        if src is None:
            continue
        contributed = False
        for t in frame_times:
            src.UpdatePipeline(t)
            b = src.GetDataInformation(port).GetBounds()
            if b[0] > b[1] or b[2] > b[3] or b[4] > b[5]:
                continue
            contributed = True
            for i in range(3):
                lo[i] = min(lo[i], b[2 * i])
                hi[i] = max(hi[i], b[2 * i + 1])
        if contributed:
            transformed = _rep_transform_props(rep)
            if transformed:
                name = names.get(src.GetGlobalIDAsString(), src.GetXMLName())
                warn(f"--fit-camera: the representation of '{name}' has a non-identity "
                     f"transform ({', '.join(transformed)}); the fit uses its untransformed "
                     f"data bounds, so it may be off")
    if lo[0] == float('inf'):
        return None
    return [lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]]


def apply_camera_fit(views, frame_times, mode, margin_pct):
    """--fit-camera: fit the camera of every render view in views (main step 10)."""
    scene = GetAnimationScene()
    saved_time = scene.TimeKeeper.Time
    for i, view in enumerate(views):
        if not view.IsA("vtkSMRenderViewProxy"):
            continue
        Render(view)  # so that ViewSize is current
        w, h = view.ViewSize
        bounds = collect_view_bounds(view, frame_times)
        label = f"view {i + 1} ({view.GetXMLName()})"
        if bounds is None:
            warn(f"--fit-camera: {label}: nothing visible with valid bounds; camera unchanged")
            continue
        if bounds[0] == bounds[1] and bounds[2] == bounds[3] and bounds[4] == bounds[5]:
            warn(f"--fit-camera: {label}: the visible data is a single point; camera unchanged")
            continue
        position = list(view.CameraPosition)
        focal_point = list(view.CameraFocalPoint)
        parallel_scale = float(view.CameraParallelScale)
        cam = fit_camera(position, focal_point, list(view.CameraViewUp),
                         float(view.CameraViewAngle), bool(view.CameraParallelProjection),
                         parallel_scale, w / h, bounds, margin_pct, mode)
        if (cam['position'] == position and cam['focal_point'] == focal_point
                and cam['parallel_scale'] == parallel_scale):
            continue  # 'out' with nothing to do: leave the camera untouched
        view.CameraPosition = cam['position']
        view.CameraFocalPoint = cam['focal_point']
        view.CameraParallelScale = cam['parallel_scale']
        Render(view)  # also resets the clipping range to the visible bounds
    scene.TimeKeeper.Time = saved_time


def save_cameras(views):
    """The camera properties --fit-camera changes, of every render view in views."""
    return [(view, list(view.CameraPosition), list(view.CameraFocalPoint),
             float(view.CameraParallelScale))
            for view in views if view.IsA("vtkSMRenderViewProxy")]


def restore_cameras(saved):
    """Restore cameras saved by save_cameras."""
    for view, position, focal_point, parallel_scale in saved:
        view.CameraPosition = position
        view.CameraFocalPoint = focal_point
        view.CameraParallelScale = parallel_scale
        Render(view)  # also resets the clipping range


# ----------------------------------------------------------------
# Screenshot time
# ----------------------------------------------------------------

def apply_screenshot_time(args, t, frame_times, colorbars, cb_views, plot_specs, plots,
                          views, cameras_before_fit):
    """
    --save-image at a time t outside the frame window (a 'Sequence' scene with
    NumberOfFrames 1, or --time outside --frame-*): apply the ranges and the camera fit
    that include t. Clamp: the range at t; grow: the window frames before t, then t;
    --plot-data-range-all and the --fit-camera bounds: the window plus t. frame_times
    itself is left alone, so --save-animation keeps the window's ranges.
    cameras_before_fit: save_cameras() from before the window's fit (with --fit-camera).
    """
    scene = GetAnimationScene()
    cb_ranges = precompute_dynamic_colorbar_ranges(args, colorbars, cb_views, scene,
                                                   frame_times, at_time=t)
    static, dynamic = precompute_plot_ranges(plot_specs, plots, frame_times, at_time=t)
    for (n, axis), (lo, hi) in static.items():
        apply_plot_axis_range(plots[n - 1], axis, lo, hi)
    apply_dynamic_ranges_at_time({'colorbars': cb_ranges or {}, 'plots': dynamic}, t)
    if args.fit_camera:
        restore_cameras(cameras_before_fit)
        apply_camera_fit(views, list(frame_times) + [t], args.fit_camera, args.fit_margin)


# ----------------------------------------------------------------
# Argument parsing
# ----------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser()

    # -- Positional --
    parser.add_argument('statefile', help="State file to load (.pvsm)")

    # -- Input --
    g_input = parser.add_argument_group('input')
    g_input.add_argument('-d', '--datadir',
        help="Change data file directory where Paraview searches for matching file names.",
        default=None)
    g_input.add_argument('--restrict-to-datadir',
        help="Restrict data file loading to the specified --datadir directory only.",
        action='store_true')
    g_input.add_argument('-f', '--filenames',
        help="Dict-formatted string `{ 'readername1': 'filepath1', ... }` to specify filenames \
            explicitly.",
        default=None)
    g_input.add_argument('--keep-path',
        help="Reader name (see --list-readers) whose file may stay outside --datadir, e.g. a \
            shared reference file. Its file must still exist. Repeatable.",
        metavar='READER', action='append', default=[])
    g_input.add_argument('--allow-missing-data',
        help="Warn instead of failing when data files are missing or readers still point \
            outside --datadir.",
        action='store_true')
    g_input.add_argument('--list-readers',
        help="Print the index, name, used flag, and file path of every reader, then continue.",
        action='store_true')

    # -- Output --
    g_output = parser.add_argument_group('output')
    g_output.add_argument('-o', '--outputname',
        help="Output file name (without extension). All directories will be created if they do \
            not exist. Existing files will be overwritten. Default: './rendered'",
        default="rendered")
    g_output.add_argument('--suffix',
        help="Append datetime suffix to outputname to avoid overwriting existing files.",
        action='store_true')

    # -- Layout and view --
    g_layout = parser.add_argument_group('layout and view')
    g_layout.add_argument('--layout',
        help="Layout name or index (one-based) to render, e.g. 1 or \"Layout #1\". Default: 1",
        default='1')
    g_layout.add_argument('--view',
        help="View index (one-based) in layout to render. If not set or < 1, renders all views \
            in the layout. Default: 0 (all views)",
        default=0, type=int)
    g_layout.add_argument('--time',
        help="Set the time to render, e.g. 10.0. Default: end time",
        default=float('inf'), type=float)
    g_layout.add_argument('--interp-interval',
        help="Set the Discrete Time Step Interval (DT) of every Temporal Interpolator in the state,             giving evenly spaced animation steps. 0 keeps the original time steps.             Error if the state has no Temporal Interpolator. Default: not set",
        metavar='DT', type=float, default=None)
    g_layout.add_argument('--size',
        help="Layout size in pixels. Pass one int for the longest side (other side scaled to preserve aspect ratio) \
            or two ints for exact width and height (aspect ratio not preserved). \
            You can preview a size in the Paraview GUI by clicking \"View -> Preview\". Default: 1920",
        metavar='INT',
        nargs='+', type=int, default=[1920])
    g_layout.add_argument('--fit-camera',
        help="Fit the camera of every rendered 3D view to the visible data, using the data \
            bounds over the frame window (computed once, no per-frame motion); the view \
            direction is kept. 'fit': center on the data and move in or out until it just fits. \
            'out': only move out if the data doesn't fit; otherwise keep the state's camera. \
            Only the data bounds are fitted, not annotations (colorbar, axes grid labels, \
            text): with a colorbar or axes grid shown, use --fit-margin 10 to 20. \
            Default: not set (camera as in the state)",
        choices=['fit', 'out'], default=None)
    g_layout.add_argument('--fit-margin',
        help="Margin for --fit-camera on each side, in percent of the view size \
            (0 <= PCT < 50). Default: 5",
        metavar='PCT', type=float, default=5.0)
    g_layout.add_argument('--palette',
        help="Color palette for rendering. Aliases: white, black, gray/grey (WarmGray), gradient. \
            Default: WarmGrayBackground",
        choices=_PALETTE_CHOICES,
        default='WarmGrayBackground')
    g_layout.add_argument('-i', '--interact',
        help="Interaction with view(s) after loading and rendering.",
        action='store_true')
    g_layout.add_argument('--list-layouts',
        help="Print the index, name, and size of every layout in the state file, then continue.",
        action='store_true')
    g_layout.add_argument('--list-views',
        help="Print the index, type, and size of every view in the selected layout (--layout), "
             "then continue.",
        action='store_true')

    # -- Screenshot (--save-image / --si) --
    g_image = parser.add_argument_group('screenshot (--save-image)')
    g_image.add_argument('--save-image', '--si',
        help="Render and save image.",
        action='store_true')
    g_image.add_argument('--image-format',
        help="File format for saving images. Default: png",
        choices=['png', 'bmp', 'jpg', 'jpeg', 'tif', 'tiff', 'vtk'],
        default='png')
    g_image.add_argument('--image-resolution',
        help="Image resolution for saving rendered files. Pass one int for the longest side (the other \
            side scaled to preserve aspect ratio) or two ints for exact size. If not specified (or 0), use the size \
            of the layout (see --size) or the size of the selected view (see --view).",
        metavar='INT',
        nargs='+', type=int, default=[0])
    g_image.add_argument('--no-font-scaling',
        help="Disable automatic font scaling when saving images and animations.",
        action='store_true')
    g_image.add_argument('--transparent-background',
        help="Enable transparent background when saving images, if supported by the file format.",
        action='store_true')
    g_image.add_argument('--output-palette',
        help="Override color palette when saving images and animations. \
            Aliases: white, black, gray/grey (WarmGray), gradient.",
        choices=_PALETTE_CHOICES,
        default=None)

    # -- Animation (--save-animation / --sa) --
    g_anim = parser.add_argument_group('animation (--save-animation)')
    g_anim.add_argument('--save-animation', '--sa',
        help="Render and save animation.",
        action='store_true')
    g_anim.add_argument('--animation-format',
        help="File format for saving animations.",
        choices=['mp4', 'avi', 'png', 'jpg', 'jpeg', 'ogv', 'tif', 'tiff'],
        default='mp4')
    g_anim.add_argument('--bitrate',
        help="Bitrate for saving mp4 animations (in bps). If not set, estimated from resolution \
            and framerate.",
        default=0, type=int)
    g_anim.add_argument('--framerate',
        help="Framerate for saving animations in frames per second. Default: 30",
        default=30, type=int)
    g_anim.add_argument('--motion-factor',
        help="Motion factor for estimating mp4 bitrate. Recommended between [0.05, 0.2]. Default: 0.1",
        default=0.1, type=float)
    g_anim.add_argument('--frame-start',
        help="Start frame index (zero based) for saving extracts and animations. Default: 0",
        default=0, type=int)
    g_anim.add_argument('--frame-end',
        help="End frame index (zero based, inclusive) for saving extracts and animations. \
            Last frame if negative. Defaults: last frame",
        default=-1, type=int)
    g_anim.add_argument('--frame-stride',
        help="Frame stride for saving extracts and animations. Default: 1",
        default=1, type=int)

    # -- Extracts (--save-extracts / --se) --
    g_extract = parser.add_argument_group('extracts (--save-extracts)')
    g_extract.add_argument('--save-extracts', '--se',
        help="Save extracts.",
        action='store_true')

    # -- State (--save-state / --ss) --
    g_state = parser.add_argument_group('state (--save-state)')
    g_state.add_argument('--save-state', '--ss',
        help="Save the state of the layout as a .pvsm file (including absolute data file paths).",
        action='store_true')

    # -- Colorbars --
    g_cb = parser.add_argument_group('colorbars')
    g_cb.add_argument('--list-colorbars',
        help="Print the index, array name, and current range of each colorbar in the selected "
             "layout/view, then continue.",
        action='store_true')
    g_cb.add_argument('--cb-range',
        help="Set colorbar N's range to [MIN MAX]. N is 1-based. Repeatable for multiple colorbars.",
        nargs=3, metavar=('N', 'MIN', 'MAX'),
        action='append', default=None)
    g_cb.add_argument('--cb-data-range-all',
        help="Set colorbar N's range to the global data range across all time steps. "
             "Accepts one or more 1-based indices.",
        nargs='+', type=int, metavar='N', default=[])
    g_cb.add_argument('--cb-data-range-clamp',
        help="Per-frame: set colorbar N's range to the data range at each time step "
             "(range can go up or down between frames). Accepts one or more 1-based indices.",
        nargs='+', type=int, metavar='N', default=[])
    g_cb.add_argument('--cb-data-range-grow',
        help="Per-frame: grow colorbar N's range monotonically to include each frame's data "
             "(range never shrinks). Accepts one or more 1-based indices.",
        nargs='+', type=int, metavar='N', default=[])
    g_cb.add_argument('--cb-sym',
        help="After any --cb-data-range-* mode, symmetrize colorbar N's range around zero: "
             "[-A, +A] where A = max(|min|, |max|). Accepts one or more 1-based indices.",
        nargs='+', type=int, metavar='N', default=[])
    g_cb.add_argument('--cb-colormap',
        help="Set the colormap of colorbar N to a ParaView preset name (case-insensitive). "
             "N is 1-based. Repeatable. Example preset names: 'Viridis (matplotlib)', "
             "'Cool to Warm', 'Fast', 'Black-Body Radiation', 'Rainbow Desaturated'.",
        nargs=2, metavar=('N', 'COLORMAP'),
        action='append', default=None)
    g_cb.add_argument('--cb-discretize',
        help="Divide colorbar N's colormap into STEPS uniform color bands (integer >= 2). "
             "N is 1-based. Repeatable. Example: --cb-discretize 1 17",
        nargs=2, metavar=('N', 'STEPS'),
        action='append', default=None)
    g_cb.add_argument('--list-colormaps',
        help="Print a sorted, numbered list of all available ParaView colormap preset names "
             "(usable with --cb-colormap), then continue.",
        action='store_true')

    g_cb.add_argument('--cb-title',
        help="Set the title of colorbar N (a blank text clears it). N is 1-based. Repeatable.",
        nargs=2, metavar=('N', 'TEXT'),
        action='append', default=None)

    # -- Plots --
    g_plot = parser.add_argument_group('plots')
    g_plot.add_argument('--list-plots',
        help="Print the index, type, title and axis settings of each plot (chart view) in the "
             "selected layout/view, then continue.",
        action='store_true')
    g_plot.add_argument('--plot-range',
        help="Fix plot N's AXIS (x, y, left, bottom, right, top) to [MIN MAX]. Repeatable.",
        nargs=4, metavar=('N', 'AXIS', 'MIN', 'MAX'), action='append', default=None)
    g_plot.add_argument('--plot-data-range-all',
        help="Set plot N's AXIS range to the data range over all frames of the frame window "
             "(plus a 5%% margin). Repeatable.",
        nargs=2, metavar=('N', 'AXIS'), action='append', default=None)
    g_plot.add_argument('--plot-data-range-grow',
        help="Per-frame: grow plot N's AXIS range to include each frame's data (plus a 5%% "
             "margin). Repeatable.",
        nargs=2, metavar=('N', 'AXIS'), action='append', default=None)
    g_plot.add_argument('--plot-auto',
        help="Use the automatic range for plot N's AXIS (overrides a custom range in the state). "
             "Repeatable.",
        nargs=2, metavar=('N', 'AXIS'), action='append', default=None)
    g_plot.add_argument('--plot-sym',
        help="Symmetrize plot N's AXIS range around zero. Needs --plot-data-range-all or "
             "--plot-data-range-grow for the same axis. Repeatable.",
        nargs=2, metavar=('N', 'AXIS'), action='append', default=None)
    g_plot.add_argument('--plot-log',
        help="Turn the logarithmic scale of plot N's AXIS on or off. Repeatable.",
        nargs=3, metavar=('N', 'AXIS', 'on|off'), action='append', default=None)
    g_plot.add_argument('--plot-title',
        help="Set the title of plot N (a blank text clears it). Repeatable.",
        nargs=2, metavar=('N', 'TEXT'), action='append', default=None)
    g_plot.add_argument('--plot-axis-title',
        help="Set the title of plot N's AXIS (a blank text clears it). Repeatable.",
        nargs=3, metavar=('N', 'AXIS', 'TEXT'), action='append', default=None)

    # -- Parse and validate --
    args = parser.parse_args(argv)

    if len(args.size) > 2:
        parser.error("--size accepts 1 or 2 integers")
    if len(args.image_resolution) > 2:
        parser.error("--image-resolution accepts 1 or 2 integers")
    if args.interp_interval is not None and args.interp_interval < 0:
        parser.error("--interp-interval must be >= 0")
    if not 0 <= args.fit_margin < 50:
        parser.error(f"--fit-margin must be >= 0 and < 50, got {args.fit_margin:g}")
    if args.datadir and args.filenames:
        parser.error("--datadir and --filenames are mutually exclusive")

    # Resolve palette aliases
    args.palette = _PALETTE_ALIASES.get(args.palette, args.palette)
    args.output_palette = _PALETTE_ALIASES.get(args.output_palette, args.output_palette)

    return args

# ----------------------------------------------------------------
# Main
# ----------------------------------------------------------------

def main(argv=None):
    args = parse_args(argv)

    if paraview is not None:
        v = GetParaViewVersion()
        msg = paraview_version_warning((v.major, v.minor))
        if msg:
            warn(msg)

    outputname = strip_output_extension(args.outputname)
    if args.suffix:
        outputname += "_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

    font_scaling = "Do not scale fonts" if args.no_font_scaling else "Scale fonts proportionally"

    if args.list_colormaps:
        print_colormaps()

    # ----------------------------------------------------------------
    # Load state file with modified data file paths
    # ----------------------------------------------------------------

    datadir = abspath(args.datadir) if args.datadir else None
    filenames = parse_filenames(args.filenames) if args.filenames else None

    LoadState(abspath(args.statefile),
        data_directory=datadir,
        filenames=filenames,
        restrict_to_data_directory=args.restrict_to_datadir,
    )

    SetActiveSource(None)

    if args.list_layouts:
        print_layouts(GetLayouts())

    # ----------------------------------------------------------------
    # Pick layout, view, time, etc.
    # ----------------------------------------------------------------

    # Pick the layout by index or name
    layout_items = list(GetLayouts().items())
    layout_names = [key[0] for key, _ in layout_items]
    layout = layout_items[resolve_layout_index(args.layout, layout_names)][1]

    if args.list_views:
        print_views(layout, GetViewsInLayout(layout))

    # Remove all other layouts
    for other in GetLayouts().values():
        if other is not layout:
            RemoveLayout(other)

    # Pick the view in the layout by index (if specified)
    if args.view > 0:
        is_layout = False
        i_view = args.view - 1
        views = GetViewsInLayout(layout)
        try:
            layout_or_view = views[i_view]
        except IndexError:
            raise SystemExit(f"error: View index {args.view} out of range, must be between 1 and {len(views)}")
    else:
        is_layout = True
        layout_or_view = layout

    # Views being rendered: the selected view, or all views in the selected layout
    rendered_views = GetViewsInLayout(layout) if is_layout else [layout_or_view]

    # --list-readers, --keep-path, missing data and template-run fallback checks
    check_readers(args, rendered_views, datadir)

    # --interp-interval (before anything reads TimestepValues)
    if args.interp_interval is not None:
        apply_interp_interval(args.interp_interval)
        # Make the animation follow the new time steps (play mode, frame count, end time)
        GetAnimationScene().UpdateAnimationUsingDataTimeSteps()
        extra = unsuppressed_time_sources()
        if extra:
            warn('these sources still add their own time steps to the animation '
                 '(set "Ignore Time" on them in ParaView): ' + ', '.join(extra))

    if len(args.size) == 1:
        current_w, current_h = layout.GetSize()
        layout.SetSize(*fit_to_box(current_w, current_h, args.size[0]))
    else:
        layout.SetSize(*args.size)
    LoadPalette(args.palette)

    # Get the actual resolution for saving images and animations
    ir = args.image_resolution
    if ir[0] < 1:
        if layout_or_view.IsA("vtkSMViewProxy"):
            image_res = tuple(layout_or_view.ViewSize)
        else:
            image_res = tuple(layout_or_view.GetSize())
    elif len(ir) == 1:
        if layout_or_view.IsA("vtkSMViewProxy"):
            base = layout_or_view.ViewSize
        else:
            base = layout_or_view.GetSize()
        image_res = fit_to_box(base[0], base[1], ir[0])
    else:
        image_res = tuple(ir)

    # Set the time
    animation_scene = GetAnimationScene()
    if args.time == float('inf'):
        animation_scene.TimeKeeper.Time = animation_scene.EndTime
    else:
        animation_scene.TimeKeeper.Time = args.time

    # The frames SaveAnimation's FrameWindow counts: the time steps in 'Snap To TimeSteps'
    # mode (also after --interp-interval), the scene's NumberOfFrames in 'Sequence' mode
    frame_times = animation_frame_times(animation_scene)
    frame_start, frame_end = resolve_frame_window(
        args.frame_start, args.frame_end, args.frame_stride, max(1, len(frame_times)))
    framewindow = [frame_start, frame_end]

    # Charts: push the block selection ParaView restores once the data is read (after the
    # data checks, so missing files fail cleanly first; before the plot ranges)
    refresh_chart_representations(rendered_views, animation_scene.TimeKeeper.Time)

    # ----------------------------------------------------------------
    # Colorbar limits
    # ----------------------------------------------------------------

    views_for_cb = rendered_views
    colorbars = enumerate_colorbars(views_for_cb)

    validate_colorbar_args(args, len(colorbars))

    # Validate the plot arguments too before any colorbar change or per-frame precompute
    plots = enumerate_plots(rendered_views)
    plot_specs = build_plot_specs(args, len(plots))

    if args.list_colorbars:
        print_colorbars(colorbars)

    apply_colorbar_colormaps(args, colorbars)
    apply_colorbar_discretize(args, colorbars)
    apply_colorbar_titles(args, colorbars, views_for_cb)
    apply_static_colorbar_limits(args, colorbars, views_for_cb)

    # Precompute per-frame ranges for --cb-data-range-clamp / --cb-data-range-grow.
    # Always computed over the animation frame window so that grow accumulates from
    # frame_start; --save-image at a time in the window uses the entry at that time.
    anim_frame_times = (
        frame_times[frame_start : frame_end + 1 : args.frame_stride]
        if frame_times else [animation_scene.TimeKeeper.Time]
    )
    dynamic_ranges = precompute_dynamic_colorbar_ranges(
        args, colorbars, views_for_cb, animation_scene, anim_frame_times
    )
    # A screenshot time outside the window gets its own ranges and camera fit
    # (apply_screenshot_time); anim_frame_times stays the window's for --sa/--se
    shot_time = animation_scene.TimeKeeper.Time
    shot_apart = bool(args.save_image) and shot_time not in anim_frame_times

    # ----------------------------------------------------------------
    # Plots: static settings, data ranges, per-frame precompute
    # ----------------------------------------------------------------

    if args.list_plots:
        print_plots(plots)
    apply_plot_static(plot_specs, plots, build_chart_titles(args))

    # --plot-data-range-all (applied now) and -grow (per frame, with the colorbar ranges)
    static_plot_ranges, dynamic_plot_ranges = precompute_plot_ranges(
        plot_specs, plots, anim_frame_times)
    for (n, axis), (lo, hi) in static_plot_ranges.items():
        apply_plot_axis_range(plots[n - 1], axis, lo, hi)

    dynamic = {'colorbars': dynamic_ranges or {}, 'plots': dynamic_plot_ranges}
    has_dynamic = bool(dynamic['colorbars'] or dynamic['plots'])

    # ----------------------------------------------------------------
    # Camera fit (once, from the bounds over the same frame window)
    # ----------------------------------------------------------------

    cameras_before_fit = window_cameras = None
    if args.fit_camera:
        cameras_before_fit = save_cameras(rendered_views)
        apply_camera_fit(rendered_views, anim_frame_times, args.fit_camera, args.fit_margin)
        window_cameras = save_cameras(rendered_views)

    # ----------------------------------------------------------------
    # Postprocessing actions
    # ----------------------------------------------------------------

    # Start interaction
    if args.interact:
        print("Interacting with view. Press 'q' in viewer to continue ...")
        if layout_or_view.IsA("vtkSMViewProxy"):
            Interact(layout_or_view)
        else:
            for view in GetViewsInLayout(layout_or_view):
                Interact(view)

    # Save state
    if args.save_state:
        file_state = abspath(outputname) + '.pvsm'

        if abspath(args.statefile) == abspath(file_state):
            print("Skipped saving state. Source and destination are the same file:", file_state)
        else:
            os.makedirs(dirname(file_state), exist_ok=True)
            print("Saving state to:", file_state)
            SaveState(file_state)

    # Save image
    if args.save_image:
        file_img = abspath(outputname) + '.' + args.image_format
        os.makedirs(dirname(file_img), exist_ok=True)

        if shot_apart:
            apply_screenshot_time(args, shot_time, anim_frame_times, colorbars, views_for_cb,
                                  plot_specs, plots, rendered_views, cameras_before_fit)
        elif has_dynamic:
            apply_dynamic_ranges_at_time(dynamic, shot_time)

        print("Saving screenshot to:", file_img)

        SaveScreenshot(file_img, layout_or_view,
            ImageResolution=image_res,
            FontScaling=font_scaling,
            OverrideColorPalette=args.output_palette,
            TransparentBackground=args.transparent_background,
        )

        if shot_apart and (args.save_animation or args.save_extracts):
            # Back to the window's plot ranges and camera fit (the cue sets the per-frame ranges)
            for (n, axis), (lo, hi) in static_plot_ranges.items():
                apply_plot_axis_range(plots[n - 1], axis, lo, hi)
            if window_cameras is not None:
                restore_cameras(window_cameras)

    # Save animation
    if args.save_animation:
        file_ani = abspath(outputname) + '.' + args.animation_format
        os.makedirs(dirname(file_ani), exist_ok=True)

        is_video = args.animation_format.lower() in _VIDEO_FORMATS

        if is_video:
            bitrate = args.bitrate or estimate_mp4_bitrate(*image_res, args.framerate, args.motion_factor)
            print(f"Saving animation ({image_res[0]} x {image_res[1]}, {args.framerate} fps, {bitrate / 1e6:.1f} Mbps): {file_ani}")
        else:
            print(f"Saving animation ({image_res[0]} x {image_res[1]}, {args.framerate} fps): {file_ani}")

        ani_kwargs = dict(
            scene=animation_scene,
            SaveAllViews=is_layout,
            ImageResolution=image_res,
            FontScaling=font_scaling,
            FrameRate=args.framerate,
            FrameStride=args.frame_stride,
            FrameWindow=framewindow,
            OverrideColorPalette=args.output_palette,
        )
        if is_video:
            ani_kwargs['BitRate'] = bitrate

        dynamic_cue = build_dynamic_cue(dynamic, animation_scene) if has_dynamic else None

        SaveAnimation(file_ani, layout_or_view, **ani_kwargs)

        if dynamic_cue is not None:
            animation_scene.Cues.remove(dynamic_cue)

    # Save extracts
    if args.save_extracts:
        extractsdir = abspath(outputname + '_extracts')

        print(f"Saving extracts: {extractsdir}")

        SaveExtracts(
            ExtractsOutputDirectory=extractsdir,
            FrameRate=args.framerate,  # if the extractor supports it
            FrameStride=args.frame_stride,
            FrameWindow=framewindow,
        )


if __name__ == '__main__':
    main()
