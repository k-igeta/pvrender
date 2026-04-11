"""
pvrender.py

Render ParaView .pvsm state files from the command line using `pvpython` or `pvbatch`,
with many customizable options.

Documentation: https://github.com/k-igeta/pvrender

# Usage

    pvpython pvrender.py <statefile.pvsm> [options]
    pvbatch  pvrender.py <statefile.pvsm> [options]

    pvpython pvrender.py statefile.pvsm --help
    pvpython pvrender.py statefile.pvsm --save-image --suffix
    pvpython pvrender.py statefile.pvsm --time 1.0 --interact
    pvpython pvrender.py statefile.pvsm -d /pathto/data/ -o output --save-image --save-animation
    pvpython pvrender.py statefile.pvsm --filenames "{'reader.pvd': 'pathto/file.pvd'}"

Loads a ParaView statefile.pvsm and optionally sets data file paths
(-d / --filenames), then performs any combination of the following actions:

- Save a screenshot:            --save-image  (--si)
- Save an animation:            --save-animation (--sa)
- Save pipeline extracts:       --save-extracts  (--se)
- Save a relocated state file:  --save-state  (--ss)
- Preview interactively:        --interact (-i)

The layout, view, timestep, output size, colorbars, color palettes, and file format are all
configurable. Use --list-colormaps to browse all available colormap preset names.
See --help for the full list of options.

Use `pvbatch` for fully headless/offscreen rendering (e.g. on a server).
To suppress the render window with `pvpython`, pass `--force-offscreen-rendering` before
the script name.

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
import paraview
paraview.compatibility.major = 6
paraview.compatibility.minor = 1

from paraview.simple import *
paraview.simple._DisableFirstRenderCameraReset()

import ast
import argparse
import datetime
import json
import os
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
            rep = GetDisplayProperties(source, view)
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
    """Return (min, max) of cb's array at time t across all visible representations."""
    GetAnimationScene().TimeKeeper.Time = t
    lo, hi = float('inf'), float('-inf')
    array_name = cb['array_name']
    field_assoc = cb['field_assoc']
    sources = list(GetSources().values())
    for view in views:
        if not view.IsA("vtkSMRenderViewProxy"):
            continue
        for source in sources:
            rep = GetDisplayProperties(source, view)
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
            except Exception:
                pass
    return (0.0, 1.0) if lo == float('inf') else (lo, hi)


def _get_global_data_range(cb, views):
    """Return global (min, max) of cb's array over all animation time steps."""
    scene = GetAnimationScene()
    saved_time = scene.TimeKeeper.Time
    times = list(scene.TimeKeeper.TimestepValues) or [saved_time]
    glo, ghi = float('inf'), float('-inf')
    for t in times:
        lo, hi = _get_data_range_at_time(cb, views, t)
        glo = min(glo, lo)
        ghi = max(ghi, hi)
    scene.TimeKeeper.Time = saved_time
    return glo, ghi


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


def validate_colorbar_args(args, n_colorbars):
    """Validate all --cb-* argument combinations. Raises SystemExit on error."""
    cb_range_indices = set()
    for item in (args.cb_range or []):
        try:
            cb_range_indices.add(int(item[0]))
        except (ValueError, IndexError):
            raise SystemExit(f"error: --cb-range: N must be an integer, got {item[0]!r}")

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

    # Index bounds (includes --cb-colormap indices)
    colormap_indices = set()
    for item in (args.cb_colormap or []):
        try:
            colormap_indices.add(int(item[0]))
        except (ValueError, IndexError):
            raise SystemExit(f"error: --cb-colormap: N must be an integer, got {item[0]!r}")

    for n in sorted(cb_range_indices | all_data | sym | colormap_indices):
        if n < 1 or n > n_colorbars:
            raise SystemExit(
                f"error: colorbar index {n} out of range "
                f"(found {n_colorbars} colorbar{'s' if n_colorbars != 1 else ''})"
            )


def apply_static_colorbar_limits(args, colorbars, views):
    """Apply --cb-range and --cb-data-range-all."""
    sym = set(args.cb_sym)

    for item in (args.cb_range or []):
        n, lo, hi = int(item[0]), float(item[1]), float(item[2])
        colorbars[n - 1]['lut'].RescaleTransferFunction(lo, hi)

    for n in args.cb_data_range_all:
        lo, hi = _get_global_data_range(colorbars[n - 1], views)
        if n in sym:
            lo, hi = apply_sym(lo, hi)
        colorbars[n - 1]['lut'].RescaleTransferFunction(lo, hi)


def precompute_dynamic_colorbar_ranges(args, colorbars, views, animation_scene, frame_times):
    """
    Pre-compute per-frame LUT ranges for --cb-data-range-clamp and --cb-data-range-grow.

    Returns None if no dynamic colorbars are requested; otherwise a dict:
        { array_name: [[t, lo, hi], ...] }   (one entry per frame, sorted by t)
    """
    clamp   = set(args.cb_data_range_clamp)
    grow    = set(args.cb_data_range_grow)
    sym     = set(args.cb_sym)
    dynamic = clamp | grow
    if not dynamic:
        return None

    saved_time = animation_scene.TimeKeeper.Time
    ranges  = {}   # {array_name: [[t, lo, hi], ...]}
    running = {}   # for grow: {array_name: (lo, hi)}

    for t in frame_times:
        for n in dynamic:
            cb  = colorbars[n - 1]
            arr = cb['array_name']
            lo, hi = _get_data_range_at_time(cb, views, t)

            if n in grow:
                if arr not in running:
                    running[arr] = (lo, hi)
                else:
                    rlo, rhi = running[arr]
                    running[arr] = (min(rlo, lo), max(rhi, hi))
                lo, hi = running[arr]

            if n in sym:
                lo, hi = apply_sym(lo, hi)

            ranges.setdefault(arr, []).append([t, lo, hi])

    animation_scene.TimeKeeper.Time = saved_time
    return ranges


def apply_dynamic_colorbar_ranges_at_time(dynamic_ranges, t):
    """Apply precomputed dynamic ranges at time t (nearest-time lookup)."""
    for array_name, entries in dynamic_ranges.items():
        best = min(entries, key=lambda e: abs(e[0] - t))
        GetColorTransferFunction(array_name).RescaleTransferFunction(best[1], best[2])


def build_dynamic_colorbar_cue(dynamic_ranges, animation_scene):
    """
    Register a PythonAnimationCue that applies precomputed per-frame LUT ranges.
    Returns the cue proxy; remove it from animation_scene.Cues after SaveAnimation.
    """
    ranges_json = json.dumps(dynamic_ranges)
    cue_script = f"""\
import json as _json
_ranges = _json.loads({repr(ranges_json)})

def start_cue(self):
    pass

def tick(self):
    from paraview.simple import GetAnimationScene, GetColorTransferFunction
    t = GetAnimationScene().TimeKeeper.Time
    for array_name, entries in _ranges.items():
        best = min(entries, key=lambda e: abs(e[0] - t))
        GetColorTransferFunction(array_name).RescaleTransferFunction(best[1], best[2])

def end_cue(self):
    pass
"""
    cue = PythonAnimationCue()
    cue.Script = cue_script
    animation_scene.Cues.append(cue)
    return cue


# ----------------------------------------------------------------
# Argument parsing
# ----------------------------------------------------------------

def parse_args():
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
    g_layout.add_argument('--size',
        help="Layout size in pixels. Pass one int for width (height scaled to preserve aspect ratio) \
            or two ints for exact width and height (aspect ratio not preserved). \
            You can preview a size in the Paraview GUI by clicking \"View -> Preview\". Default: 1920",
        metavar='INT',
        nargs='+', type=int, default=[1920])
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
        help="Image resolution for saving rendered files. Pass one int for width (height scaled to \
            preserve aspect ratio) or two ints for exact size. If not specified (or 0), use the size \
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
    g_cb.add_argument('--list-colormaps',
        help="Print a sorted, numbered list of all available ParaView colormap preset names "
             "(usable with --cb-colormap), then continue.",
        action='store_true')

    # -- Parse and validate --
    args = parser.parse_args()

    if len(args.size) > 2:
        parser.error("--size accepts 1 or 2 integers")
    if len(args.image_resolution) > 2:
        parser.error("--image-resolution accepts 1 or 2 integers")
    if args.datadir and args.filenames:
        parser.error("--datadir and --filenames are mutually exclusive")

    # Resolve palette aliases
    args.palette = _PALETTE_ALIASES.get(args.palette, args.palette)
    args.output_palette = _PALETTE_ALIASES.get(args.output_palette, args.output_palette)

    return args

# ----------------------------------------------------------------
# Main
# ----------------------------------------------------------------

def main():
    args = parse_args()

    outputname = os.path.splitext(args.outputname)[0]
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
    try:
        i_layout = int(args.layout) - 1
        layouts = GetLayouts()
        layout = list(layouts.values())[i_layout]
    except ValueError:
        layout = GetLayoutByName(str(args.layout))
        if layout is None:
            raise SystemExit(f"error: Layout '{args.layout}' not found by name")
    except IndexError:
        raise SystemExit(f"error: Layout index {args.layout} out of range, must be between 1 and {len(layouts)}")

    if args.list_views:
        print_views(layout, GetViewsInLayout(layout))

    # Remove all other layouts
    for other in GetLayouts().values():
        if other is not layout:
            RemoveLayout(other)

    if len(args.size) == 1:
        width = args.size[0]
        current_w, current_h = layout.GetSize()
        height = round(width * current_h / current_w)
        layout.SetSize(width, height)
    else:
        layout.SetSize(*args.size)
    LoadPalette(args.palette)

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
        image_res = (ir[0], round(ir[0] * base[1] / base[0]))
    else:
        image_res = tuple(ir)

    # Set the time
    animation_scene = GetAnimationScene()
    if args.time == float('inf'):
        animation_scene.TimeKeeper.Time = animation_scene.EndTime
    else:
        animation_scene.TimeKeeper.Time = args.time

    n_timesteps = len(animation_scene.TimeKeeper.TimestepValues)
    frame_end = n_timesteps - 1 if args.frame_end < 0 else args.frame_end
    framewindow = [args.frame_start, frame_end]

    # ----------------------------------------------------------------
    # Colorbar limits
    # ----------------------------------------------------------------

    views_for_cb = GetViewsInLayout(layout) if is_layout else [layout_or_view]
    colorbars = enumerate_colorbars(views_for_cb)

    validate_colorbar_args(args, len(colorbars))

    if args.list_colorbars:
        print_colorbars(colorbars)

    apply_colorbar_colormaps(args, colorbars)
    apply_static_colorbar_limits(args, colorbars, views_for_cb)

    # Precompute per-frame ranges for --cb-data-range-clamp / --cb-data-range-grow.
    # Always computed over the animation frame window so that grow accumulates from
    # frame_start and the nearest-time lookup is consistent for --save-image too.
    timestep_values = list(animation_scene.TimeKeeper.TimestepValues)
    anim_frame_times = (
        timestep_values[args.frame_start : frame_end + 1 : args.frame_stride]
        if timestep_values else [animation_scene.TimeKeeper.Time]
    )
    dynamic_ranges = precompute_dynamic_colorbar_ranges(
        args, colorbars, views_for_cb, animation_scene, anim_frame_times
    )

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

        if dynamic_ranges:
            apply_dynamic_colorbar_ranges_at_time(dynamic_ranges, animation_scene.TimeKeeper.Time)

        print("Saving screenshot to:", file_img)

        SaveScreenshot(file_img, layout_or_view,
            ImageResolution=image_res,
            FontScaling=font_scaling,
            OverrideColorPalette=args.output_palette,
            TransparentBackground=args.transparent_background,
        )

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

        dynamic_cue = build_dynamic_colorbar_cue(dynamic_ranges, animation_scene) \
            if dynamic_ranges else None

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
