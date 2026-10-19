"""
Tests for pvrender.py

Unit tests (plain pytest, no ParaView required):
  - estimate_mp4_bitrate
  - parse_filenames
  - palette alias resolution

Integration tests (require pvbatch on PATH):
  - save-image / save-animation / save-state
  - --size with 1 or 2 values
  - --image-resolution with 1 or 2 values
  - --output-palette / --palette aliases
  - --frame-start / --frame-end / --frame-stride
  - --suffix

Output is written to test/output/<test_name>/ which is gitignored.

Run:
    pytest test/test_pvrender.py               # unit tests only (fast)
    pytest test/test_pvrender.py -m integration # integration tests (needs pvbatch)
    pytest test/test_pvrender.py               # runs all (integration skipped if no pvbatch)
"""

import itertools
import json
import math
import os
import struct
import subprocess
import sys
import pytest
from os.path import abspath

# ----------------------------------------------------------------
# Paths
# ----------------------------------------------------------------

HERE   = os.path.dirname(os.path.abspath(__file__))
ROOT   = os.path.dirname(HERE)
SCRIPT = os.path.join(ROOT, "pvrender.py")
STATE  = os.path.join(HERE, "radial_wave_state.pvsm")
DATA   = os.path.join(HERE, "data")
OUTDIR = os.path.join(HERE, "output")

# Width used for --size and --image-resolution in integration tests.
# Smaller values run faster; larger values produce more realistic output.
TEST_WIDTH = 1280

INSPECT = os.path.join(HERE, "pv_inspect.py")
MAKE_FIXTURES = os.path.join(HERE, "make_fixtures.py")

if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pvrender
from pvrender import estimate_mp4_bitrate, parse_filenames, apply_sym, fit_to_box, _PALETTE_ALIASES


# ----------------------------------------------------------------
# Integration test helpers
# ----------------------------------------------------------------

def _pvbatch_available():
    try:
        return subprocess.run(
            ["pvbatch", "--version"], capture_output=True, timeout=600
        ).returncode == 0
    except FileNotFoundError:
        return False


def _run(*extra_args, outname):
    """Run pvrender.py via pvbatch and return CompletedProcess."""
    cmd = [
        "pvbatch", SCRIPT, STATE,
        "-d", DATA,
        "-o", outname,
    ] + list(extra_args)
    return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=600)


def _inspect(*extra_args, outname, state=STATE, datadir=DATA):
    """Run pvrender via test/pv_inspect.py under pvbatch.

    Returns (CompletedProcess, report dict or None). The report is parsed only
    when the return code is 0.
    """
    report = outname + "_report.json"
    if os.path.exists(report):
        os.remove(report)
    cmd = ["pvbatch", INSPECT, report, state]
    if datadir is not None:
        cmd += ["-d", datadir]
    cmd += ["-o", outname] + list(extra_args)
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=600)
    rep = None
    if r.returncode == 0:
        with open(report, encoding="utf-8") as f:
            rep = json.load(f)
    return r, rep


def png_size(path):
    """Return (width, height) of a PNG from its IHDR chunk."""
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


@pytest.fixture()
def outdir(request):
    """Create and return a per-test output directory under test/output/."""
    d = os.path.join(OUTDIR, request.node.name)
    os.makedirs(d, exist_ok=True)
    return d


@pytest.fixture(scope="session")
def fixtures():
    """Generate the test fixtures once per session (test/make_fixtures.py under pvbatch).

    Returns the fixture directory. It is deleted and recreated every session.
    """
    d = os.path.join(OUTDIR, "fixtures")
    r = subprocess.run(["pvbatch", MAKE_FIXTURES, d],
                       capture_output=True, text=True, cwd=ROOT, timeout=600)
    assert r.returncode == 0, r.stdout + r.stderr
    for name in ("interp_state.pvsm", "interp_state_unsuppressed.pvsm", "static_state.pvsm",
                 "scaled_rep_state.pvsm", "sequence_state.pvsm", "right_axis_state.pvsm",
                 "stats_chart_state.pvsm",
                 "blocks_chart_state.pvsm",
                 os.path.join("data_big", "radial_wave.pvd"),
                 os.path.join("data_small", "radial_wave.pvd")):
        assert os.path.isfile(os.path.join(d, name)), r.stdout + r.stderr
    return d


# ----------------------------------------------------------------
# Unit tests — estimate_mp4_bitrate
# ----------------------------------------------------------------

def test_pvrender_imports_without_paraview():
    assert pvrender.paraview is None


class TestEstimateMp4Bitrate:

    def test_1080p_typical(self):
        # 1920*1080*30*0.1 = 6,220,800 → rounds to 6.2 Mbps
        assert estimate_mp4_bitrate(1920, 1080, 30, 0.1) == 6_200_000

    def test_720p_typical(self):
        # 1280*720*30*0.1 = 2,764,800 → rounds to 2.8 Mbps
        assert estimate_mp4_bitrate(1280, 720, 30, 0.1) == 2_800_000

    def test_minimum_enforced(self):
        assert estimate_mp4_bitrate(10, 10, 1, 0.1) == 200_000

    def test_maximum_enforced(self):
        assert estimate_mp4_bitrate(10000, 10000, 240, 0.2) == 50_000_000

    def test_result_rounded_to_100k(self):
        br = estimate_mp4_bitrate(1920, 1080, 30, 0.1)
        assert br % 100_000 == 0

    def test_higher_motion_factor_gives_higher_bitrate(self):
        low  = estimate_mp4_bitrate(1920, 1080, 30, 0.05)
        high = estimate_mp4_bitrate(1920, 1080, 30, 0.20)
        assert high > low

    def test_higher_framerate_gives_higher_bitrate(self):
        slow = estimate_mp4_bitrate(1920, 1080, 24)
        fast = estimate_mp4_bitrate(1920, 1080, 60)
        assert fast > slow

    @pytest.mark.parametrize("bad_args", [
        (0, 1080, 30),
        (1920, 0, 30),
        (1920, 1080, 0),
    ])
    def test_non_positive_dimension_raises(self, bad_args):
        with pytest.raises(ValueError):
            estimate_mp4_bitrate(*bad_args)

    def test_zero_motion_factor_raises(self):
        with pytest.raises(ValueError):
            estimate_mp4_bitrate(1920, 1080, 30, motion_factor=0)

    def test_negative_motion_factor_raises(self):
        with pytest.raises(ValueError):
            estimate_mp4_bitrate(1920, 1080, 30, motion_factor=-0.1)


# ----------------------------------------------------------------
# Unit tests — parse_filenames
# ----------------------------------------------------------------

class TestFitToBox:

    @pytest.mark.parametrize("w, h, n, expected", [
        (2145, 777, 1920, (1920, 695)),
        (600, 900, 1920, (1280, 1920)),
        (100, 50, 1920, (1920, 960)),
        (1000, 1000, 500, (500, 500)),
    ])
    def test_fit_to_box(self, w, h, n, expected):
        assert fit_to_box(w, h, n) == expected

    def test_fit_to_box_minimum_one(self):
        assert fit_to_box(10000, 1, 100) == (100, 1)


class TestParseFilenames:

    def test_single_entry(self):
        result = parse_filenames("{'reader.pvd': '/some/path.pvd'}")
        assert len(result) == 1
        assert result[0]["name"] == "reader.pvd"
        assert result[0]["FileName"] == abspath("/some/path.pvd")

    def test_multiple_entries(self):
        result = parse_filenames("{'a.pvd': '/a.pvd', 'b.vtp': '/b.vtp'}")
        assert len(result) == 2
        assert {r["name"] for r in result} == {"a.pvd", "b.vtp"}

    def test_relative_path_becomes_absolute(self):
        result = parse_filenames("{'r.pvd': 'relative/path.pvd'}")
        assert os.path.isabs(result[0]["FileName"])

    def test_invalid_syntax_raises(self):
        with pytest.raises(ValueError, match="Failed to parse"):
            parse_filenames("{not valid python}")

    def test_not_a_dict_raises(self):
        with pytest.raises(ValueError, match="must be a dictionary"):
            parse_filenames("['a', 'b']")

    def test_empty_dict(self):
        assert parse_filenames("{}") == []


# ----------------------------------------------------------------
# Unit tests — palette alias resolution
# ----------------------------------------------------------------

class TestPaletteAliases:

    @pytest.mark.parametrize("alias, expected", list(_PALETTE_ALIASES.items()))
    def test_alias_resolves(self, alias, expected):
        assert _PALETTE_ALIASES.get(alias, alias) == expected

    @pytest.mark.parametrize("full_name", [
        "WarmGrayBackground",
        "DarkGrayBackground",
        "NeutralGrayBackground",
        "LightGrayBackground",
        "WhiteBackground",
        "BlackBackground",
        "GradientBackground",
    ])
    def test_full_name_passes_through(self, full_name):
        assert _PALETTE_ALIASES.get(full_name, full_name) == full_name

    def test_gray_and_grey_map_to_same(self):
        assert _PALETTE_ALIASES["gray"] == _PALETTE_ALIASES["grey"]


# ----------------------------------------------------------------
# Unit tests — argument robustness helpers
# ----------------------------------------------------------------

@pytest.mark.parametrize("name,expected", [
    ("results/run_1.5", "results/run_1.5"), ("out.png", "out"), ("out.MP4", "out"),
    ("a.b/c", "a.b/c"), ("x.pvsm", "x")])
def test_strip_output_extension(name, expected):
    assert pvrender.strip_output_extension(name) == expected


def test_resolve_layout_index():
    names = ["Layout #1", "Layout #2"]
    assert pvrender.resolve_layout_index("1", names) == 0
    assert pvrender.resolve_layout_index("2", names) == 1
    assert pvrender.resolve_layout_index("Layout #2", names) == 1
    for bad in ("0", "-1", "3", "nope"):
        with pytest.raises(SystemExit):
            pvrender.resolve_layout_index(bad, names)


def test_resolve_frame_window():
    assert pvrender.resolve_frame_window(0, -1, 1, 21) == (0, 20)
    assert pvrender.resolve_frame_window(0, -1, 1, 1) == (0, 0)
    for bad in [(50, -1, 1, 21), (5, 3, 1, 21), (0, -1, 0, 21), (0, 5, 0, 21), (0, 21, 1, 21)]:
        with pytest.raises(SystemExit):
            pvrender.resolve_frame_window(*bad)


def test_sequence_frame_times():
    # ParaView 6.1 'Sequence' mode: NumberOfFrames evenly spaced over StartTime..EndTime
    assert pvrender.sequence_frame_times(0.0, 1.0, 10) == pytest.approx(
        [i / 9 for i in range(10)])
    assert pvrender.sequence_frame_times(0.0, 10.0, 41)[20] == pytest.approx(5.0)
    assert pvrender.sequence_frame_times(2.5, 3.5, 1) == [2.5]


def test_version_warning():
    assert isinstance(pvrender.paraview_version_warning((5, 13)), str)
    assert pvrender.paraview_version_warning((6, 1)) is None
    assert pvrender.paraview_version_warning((7, 0)) is None


@pytest.mark.parametrize("cb_range", [
    [['1', 'abc', '5']], [['1', '5', '1']], [['1', '1', '1']]])
def test_validate_cb_range_non_numeric_and_order(cb_range):
    args = pvrender.parse_args(["x.pvsm"])
    args.cb_range = cb_range
    with pytest.raises(SystemExit):
        pvrender.validate_colorbar_args(args, 2)


def test_validate_cb_range_ok():
    args = pvrender.parse_args(["x.pvsm", "--cb-range", "1", "0", "5"])
    pvrender.validate_colorbar_args(args, 2)


# ----------------------------------------------------------------
# Unit tests — data-path checks
# ----------------------------------------------------------------

def test_parse_pvd_files():
    files = pvrender.parse_pvd_files(os.path.join(DATA, "radial_wave.pvd"))
    assert len(files) == 21
    assert files[0].endswith("radial_wave_0_0.vtp")
    assert all(os.path.isabs(f) for f in files)
    assert all(os.path.isfile(f) for f in files)


def test_is_inside_dir(tmp_path, monkeypatch):
    inside = pvrender.is_inside_dir
    run = os.path.join(str(tmp_path), "data", "run")
    assert inside(os.path.join(run, "a.vtp"), run)
    assert inside(os.path.join(run, "sub", "a.vtp"), run)
    assert inside(os.path.join(run, "a.vtp"), run + os.sep)          # trailing separator
    assert not inside(os.path.join(str(tmp_path), "data", "run1", "a.vtp"), run)
    assert not inside(os.path.join(str(tmp_path), "shared.csv"), run)

    # relative directory, resolved against the cwd
    monkeypatch.chdir(tmp_path)
    assert inside(os.path.join(str(tmp_path), "rel", "a.vtp"), "rel")
    assert inside(os.path.join(str(tmp_path), "rel", "a.vtp"), "rel" + os.sep)
    assert not inside(os.path.join(str(tmp_path), "other", "a.vtp"), "rel")

    if os.name == "nt":
        assert inside("C:/data/run/a.vtp", r"C:\data\run")             # forward vs back slashes
        assert inside(r"C:\data\run\a.vtp", "C:/data/run/")
        assert inside(r"C:\data\run\sub/a.vtp", "C:/data\\run\\")
        assert inside(r"c:\DATA\Run\a.vtp", r"C:\data\run")            # case differences
        assert inside(r"C:\data\run\a.vtp", r"c:\Data\RUN")
        assert not inside(r"C:\data\run1\a.vtp", r"C:\data\run")       # prefix is not inside
        assert not inside(r"D:\data\run\a.vtp", r"C:\data\run")        # across drives


def test_check_data_paths(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "a.vtp").write_text("")
    shared = tmp_path / "shared.csv"
    shared.write_text("")
    pvd = run / "r.pvd"
    pvd.write_text(
        '<VTKFile type="Collection"><Collection>'
        '<DataSet timestep="0" file="a.vtp"/>'
        '<DataSet timestep="1" file="sub/gone.vtp"/>'
        '</Collection></VTKFile>')

    readers = [
        {"name": "missing.vtp",      "paths": [str(run / "nope.vtp")],      "used": True},
        {"name": "r.pvd",            "paths": [str(pvd)],                   "used": True},
        {"name": "ok.vtp",           "paths": [str(run / "a.vtp")],         "used": True},
        {"name": "shared.csv",       "paths": [str(shared)],                "used": True},
        {"name": "kept.csv",         "paths": [str(shared)],                "used": True},
        {"name": "kept_missing.csv", "paths": [str(tmp_path / "gone.csv")], "used": True},
        {"name": "unused.vtp",       "paths": [str(tmp_path / "x.vtp")],    "used": False},
    ]
    keep = {"kept.csv", "kept_missing.csv"}

    missing, outside = pvrender.check_data_paths(readers, str(run), keep)
    assert missing == [
        f"missing.vtp: {run / 'nope.vtp'}",
        f"r.pvd: {run / 'sub' / 'gone.vtp'}",
        f"kept_missing.csv: {tmp_path / 'gone.csv'}",
    ]
    assert outside == [f"shared.csv: {shared}"]

    missing, outside = pvrender.check_data_paths(readers, None, set())
    assert len(missing) == 3
    assert outside == []


# ----------------------------------------------------------------
# Unit tests — camera fit
# ----------------------------------------------------------------

def _sub(a, b):
    return [x - y for x, y in zip(a, b)]


def _dot(a, b):
    return sum(x * y for x, y in zip(a, b))


def _unit(a):
    n = math.sqrt(_dot(a, a))
    return [x / n for x in a]


def _cross(a, b):
    return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]]


def _corner_ratios(cam, view_up, view_angle, parallel, aspect, bounds, margin_pct):
    """For each bounds corner: the larger of |x|/half-width and |y|/half-height of the
    margin-shrunk viewport of cam (<= 1 means inside), and its depth in front of the camera."""
    d = _unit(_sub(cam["focal_point"], cam["position"]))
    u = _unit(_sub(view_up, [_dot(view_up, d) * c for c in d]))
    r = _cross(d, u)
    s = 1 - 2 * margin_pct / 100
    tv = math.tan(math.radians(view_angle) / 2)
    out = []
    for c in itertools.product(bounds[0:2], bounds[2:4], bounds[4:6]):
        v = _sub(c, cam["position"])
        x, y, depth = _dot(v, r), _dot(v, u), _dot(v, d)
        if parallel:
            hw, hh = aspect * s * cam["parallel_scale"], s * cam["parallel_scale"]
        else:
            hw, hh = tv * aspect * s * depth, tv * s * depth
        out.append((max(abs(x) / hw, abs(y) / hh), depth))
    return out


class TestFitCamera:

    POS = [3.0, -4.0, 2.0]
    FOCAL = [0.5, 0.25, -0.5]
    UP = [0.1, 0.3, 1.0]       # not orthogonal to the view direction on purpose
    ANGLE = 30.0
    BOUNDS = [-1.0, 1.5, -0.5, 0.75, -0.2, 0.3]
    SMALL = [0.4, 0.6, 0.2, 0.3, -0.5, -0.45]
    BIG = [-5.0, 5.0, -5.0, 5.0, -1.0, 1.0]

    def _fit(self, bounds=None, aspect=1.0, parallel=False, scale=1.0, margin=5.0, mode="fit",
             pos=None, focal=None):
        return pvrender.fit_camera(pos or self.POS, focal or self.FOCAL, self.UP, self.ANGLE,
                                   parallel, scale, aspect,
                                   bounds or self.BOUNDS, margin, mode)

    @staticmethod
    def _dist(cam):
        return math.dist(cam["position"], cam["focal_point"])

    def _same_direction(self, cam):
        d0 = _unit(_sub(self.FOCAL, self.POS))
        d1 = _unit(_sub(cam["focal_point"], cam["position"]))
        return all(abs(a - b) < 1e-12 for a, b in zip(d0, d1))

    @pytest.mark.parametrize("aspect, parallel", [(1.0, False), (2.0, False), (1.5, True)])
    def test_fit_corners_inside_and_tight(self, aspect, parallel):
        cam = self._fit(aspect=aspect, parallel=parallel)
        ratios = _corner_ratios(cam, self.UP, self.ANGLE, parallel, aspect, self.BOUNDS, 5.0)
        assert all(depth > 0 for _, depth in ratios)
        assert all(ratio <= 1 + 1e-9 for ratio, _ in ratios)
        assert abs(max(ratio for ratio, _ in ratios) - 1) < 1e-6      # tight

    @pytest.mark.parametrize("parallel", [False, True])
    def test_fit_keeps_view_direction_and_centers(self, parallel):
        cam = self._fit(parallel=parallel)
        assert self._same_direction(cam)
        b = self.BOUNDS
        center = [(b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2]
        assert all(abs(a - c) < 1e-12 for a, c in zip(cam["focal_point"], center))

    @pytest.mark.parametrize("parallel, scale", [(False, 1.0), (True, 5.0)])
    def test_out_bounds_inside_returns_input(self, parallel, scale):
        cam = self._fit(bounds=self.SMALL, parallel=parallel, scale=scale, mode="out")
        assert cam == {"position": self.POS, "focal_point": self.FOCAL, "parallel_scale": scale}

    def test_out_large_bounds_moves_back(self):
        cam = self._fit(bounds=self.BIG, mode="out")
        assert self._dist(cam) > math.dist(self.POS, self.FOCAL)
        assert cam["focal_point"] == self.FOCAL
        assert self._same_direction(cam)
        ratios = _corner_ratios(cam, self.UP, self.ANGLE, False, 1.0, self.BIG, 5.0)
        assert all(ratio <= 1 + 1e-9 and depth > 0 for ratio, depth in ratios)

    def test_out_large_bounds_parallel_grows_scale(self):
        cam = self._fit(bounds=self.BIG, parallel=True, scale=1.0, mode="out")
        assert cam["parallel_scale"] > 1.0
        assert cam["focal_point"] == self.FOCAL
        assert self._same_direction(cam)
        ratios = _corner_ratios(cam, self.UP, self.ANGLE, True, 1.0, self.BIG, 5.0)
        assert all(ratio <= 1 + 1e-9 and depth > 0 for ratio, depth in ratios)

    def test_fit_small_bounds_moves_in(self):
        cam = self._fit(bounds=self.SMALL)
        assert self._dist(cam) < math.dist(self.POS, self.FOCAL)

    BOX = [-10.0, 10.0, -10.0, 10.0, -10.0, 10.0]
    BOX_DIAG = math.sqrt(3 * 20.0 ** 2)

    @pytest.mark.parametrize("mode", ["fit", "out"])
    def test_parallel_fit_clears_all_corners(self, mode):
        # The camera is 1 unit from the focal point, but the box reaches 10 units towards it.
        # Every corner must be at least one bounds diagonal in front of the camera, a real
        # clearance against the near clipping plane (not just depth > 0).
        cam = self._fit(bounds=self.BOX, parallel=True, scale=100.0, mode=mode,
                        pos=[0.0, 0.0, 1.0], focal=[0.0, 0.0, 0.0])
        ratios = _corner_ratios(cam, self.UP, self.ANGLE, True, 1.0, self.BOX, 5.0)
        assert all(depth >= self.BOX_DIAG - 1e-9 for _, depth in ratios)

    @pytest.mark.parametrize("z", [15.0, 100.0])
    def test_parallel_out_adequate_clearance_unchanged(self, z):
        # Nearest corner is 10 from the focal point; z = 15 clears it by 5 (>= 5 % of the
        # diagonal, < one diagonal), z = 100 by far. The scale fits: inputs returned exactly.
        pos = [0.0, 0.0, z]
        cam = self._fit(bounds=self.BOX, parallel=True, scale=100.0, mode="out",
                        pos=pos, focal=[0.0, 0.0, 0.0])
        assert cam == {"position": pos, "focal_point": [0.0, 0.0, 0.0], "parallel_scale": 100.0}

    def test_parallel_fit_adequate_clearance_keeps_distance(self):
        cam = self._fit(bounds=self.BOX, parallel=True, pos=[0.0, 0.0, 15.0],
                        focal=[0.0, 0.0, 0.0])
        assert abs(self._dist(cam) - 15.0) < 1e-12

    @pytest.mark.parametrize("parallel", [False, True])
    def test_margin_zero_corner_on_edge(self, parallel):
        cam = self._fit(margin=0.0, parallel=parallel, aspect=1.25)
        ratios = _corner_ratios(cam, self.UP, self.ANGLE, parallel, 1.25, self.BOUNDS, 0.0)
        assert all(ratio <= 1 + 1e-9 for ratio, _ in ratios)
        assert abs(max(ratio for ratio, _ in ratios) - 1) < 1e-9

    def test_larger_margin_moves_back(self):
        assert self._dist(self._fit(margin=20.0)) > self._dist(self._fit(margin=5.0))

    @pytest.mark.parametrize("margin", ["-1", "50", "60"])
    def test_fit_margin_out_of_range_parse_error(self, margin):
        with pytest.raises(SystemExit):
            pvrender.parse_args(["x.pvsm", "--fit-camera", "fit", "--fit-margin", margin])

    def test_fit_args_defaults(self):
        args = pvrender.parse_args(["x.pvsm"])
        assert args.fit_camera is None and args.fit_margin == 5.0
        args = pvrender.parse_args(["x.pvsm", "--fit-camera", "out", "--fit-margin", "0"])
        assert args.fit_camera == "out" and args.fit_margin == 0.0



# ----------------------------------------------------------------
# Integration tests — require pvbatch
# ----------------------------------------------------------------

pytestmark_pvbatch = pytest.mark.skipif(
    not _pvbatch_available(),
    reason="pvbatch not available",
)


@pytestmark_pvbatch
@pytest.mark.integration
class TestIntegration:

    # -- basic actions --

    def test_save_image_png(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--time", "1", "--size", str(TEST_WIDTH), outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_save_image_jpg(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--time", "1", "--size", str(TEST_WIDTH),
                 "--image-format", "jpg", outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".jpg")

    def test_save_animation_mp4(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--sa", "--size", str(TEST_WIDTH),
                 "--frame-start", "0", "--frame-end", "2", outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".mp4")

    def test_save_animation_short_mp4(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--sa", "--size", str(TEST_WIDTH),
                 "--frame-start", "0", "--frame-end", "5", outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".mp4")

    def test_save_state_pvsm(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--ss", "--time", "1", "--size", str(TEST_WIDTH), outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".pvsm")

    def test_save_extracts(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--se", "--frame-start", "0", "--frame-end", "2", outname=out)
        assert r.returncode == 0, r.stderr

    def test_save_image_and_animation(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--sa", "--size", str(TEST_WIDTH),
                 "--frame-start", "0", "--frame-end", "2", outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")
        assert os.path.isfile(out + ".mp4")

    # -- --size --

    def test_size_single_value(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--time", "1", "--size", "400", outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_size_two_values(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--time", "1", "--size", str(TEST_WIDTH), "200", outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_size_three_values_is_error(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--time", "1", "--size", str(TEST_WIDTH), "240", "160", outname=out)
        assert r.returncode != 0

    # -- output size box (one value = longest side) --

    def test_size_box_wide(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--time", "1", "--size", "400", outname=out)
        assert r.returncode == 0, r.stderr
        assert png_size(out + ".png") == (400, 145)

    def test_size_box_tall(self, outdir, fixtures):
        out = os.path.join(outdir, "out")
        r, _ = _inspect("--si", "--size", "400", outname=out,
                        state=os.path.join(fixtures, "static_state.pvsm"), datadir=None)
        assert r.returncode == 0, r.stderr
        assert png_size(out + ".png") == (267, 400)

    def test_size_two_values_exact(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--size", "640", "480", "--si", outname=out)
        assert r.returncode == 0, r.stderr
        assert png_size(out + ".png") == (640, 480)

    def test_image_resolution_box(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--view", "1", "--si", "--time", "1", "--size", "400",
                 "--image-resolution", "300", outname=out)
        assert r.returncode == 0, r.stderr
        assert max(png_size(out + ".png")) == 300

    # -- --image-resolution --

    def test_image_resolution_single_value(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--time", "1", "--size", str(TEST_WIDTH),
                 "--image-resolution", "640", outname=out)
        assert r.returncode == 0, r.stderr

    def test_image_resolution_two_values(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--time", "1", "--size", str(TEST_WIDTH),
                 "--image-resolution", "640", "360", outname=out)
        assert r.returncode == 0, r.stderr

    def test_image_resolution_three_values_is_error(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--time", "1",
                 "--image-resolution", "640", "360", "180", outname=out)
        assert r.returncode != 0

    # -- palette aliases --

    # -- palette aliases --

    @pytest.mark.parametrize("alias", ["white", "black"])
    def test_palette_alias(self, alias, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--time", "1", "--size", str(TEST_WIDTH),
                 "--palette", alias, outname=out)
        assert r.returncode == 0, r.stderr

    @pytest.mark.parametrize("alias", ["white", "black"])
    def test_output_palette_alias(self, alias, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--time", "1", "--size", str(TEST_WIDTH),
                 "--output-palette", alias, outname=out)
        assert r.returncode == 0, r.stderr

    # -- animation options --

    def test_frame_stride(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--sa", "--size", str(TEST_WIDTH),
                 "--frame-start", "0", "--frame-end", "4", "--frame-stride", "2",
                 outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".mp4")

    def test_frame_start_nonzero(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--sa", "--size", str(TEST_WIDTH),
                 "--frame-start", "2", "--frame-end", "4", outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".mp4")

    def test_animation_format_png(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--sa", "--size", str(TEST_WIDTH),
                 "--frame-start", "0", "--frame-end", "2",
                 "--animation-format", "png", outname=out)
        assert r.returncode == 0, r.stderr

    def test_framerate(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--sa", "--size", str(TEST_WIDTH),
                 "--frame-start", "0", "--frame-end", "2",
                 "--framerate", "24", outname=out)
        assert r.returncode == 0, r.stderr

    def test_explicit_bitrate(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--sa", "--size", str(TEST_WIDTH),
                 "--frame-start", "0", "--frame-end", "2",
                 "--bitrate", "1000000", outname=out)
        assert r.returncode == 0, r.stderr

    # -- misc options --

    def test_filenames_mapping(self, outdir):
        out = os.path.join(outdir, "out")
        pvd_path = os.path.join(DATA, "radial_wave.pvd").replace("\\", "/")
        csv_path = os.path.join(DATA, "probe_points.csv").replace("\\", "/")
        filenames_arg = "{{'radial_wave.pvd': '{}', 'probe_points.csv': '{}'}}".format(
            pvd_path, csv_path)
        cmd = [
            "pvbatch", SCRIPT, STATE,
            "--filenames", filenames_arg,
            "--si", "--time", "1", "--size", str(TEST_WIDTH),
            "-o", out,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=600)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_no_font_scaling(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--time", "1", "--size", str(TEST_WIDTH),
                 "--no-font-scaling", outname=out)
        assert r.returncode == 0, r.stderr

    def test_suffix_adds_timestamp(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--time", "1", "--size", str(TEST_WIDTH),
                 "--suffix", outname=out)
        assert r.returncode == 0, r.stderr
        files = [f for f in os.listdir(outdir) if f.endswith(".png")]
        assert files[0] != "out.png"  # a timestamp suffix was appended

    def test_layout_index_1(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--time", "1", "--size", str(TEST_WIDTH),
                 "--layout", "1", outname=out)
        assert r.returncode == 0, r.stderr

    def test_invalid_layout_index_fails(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--time", "1", "--layout", "99", outname=out)
        assert r.returncode != 0

    def test_list_layouts(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--list-layouts", "--si", "--time", "1", "--size", str(TEST_WIDTH), outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_list_views(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--list-views", "--si", "--time", "1", "--size", str(TEST_WIDTH), outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    # -- --time --

    def test_time_start(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--size", str(TEST_WIDTH), "--time", "0", outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_time_mid(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--size", str(TEST_WIDTH), "--time", "5", outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_time_end(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--size", str(TEST_WIDTH), "--time", "10", outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_time_default_is_end_time(self, outdir):
        # Without --time the script should use the end time (10.0) and succeed.
        out = os.path.join(outdir, "out")
        r = _run("--si", "--size", str(TEST_WIDTH), outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_time_fractional(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--size", str(TEST_WIDTH), "--time", "2.5", outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    # -- --view --

    def test_view_1(self, outdir):
        # The test state has 3 views; --view 1 should render the first view.
        out = os.path.join(outdir, "out")
        r = _run("--si", "--time", "1", "--size", str(TEST_WIDTH),
                 "--view", "1", outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_view_0_renders_all(self, outdir):
        # --view 0 (default) renders the whole layout.
        out = os.path.join(outdir, "out")
        r = _run("--si", "--time", "1", "--size", str(TEST_WIDTH),
                 "--view", "0", outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_view_with_image_resolution_single_value(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--time", "1", "--view", "2",
                 "--image-resolution", "640", outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_view_out_of_range_fails(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--si", "--time", "1", "--size", str(TEST_WIDTH),
                 "--view", "99", outname=out)
        assert r.returncode != 0

    def test_inspect_harness_reports_defaults(self, outdir):
        r, rep = _inspect("--time", "1", "--size", "320",
                          outname=os.path.join(outdir, "out"))
        assert r.returncode == 0, r.stderr
        assert rep["time"] == 1.0 and len(rep["timesteps"]) == 21
        assert rep["layout_size"][0] == 320
        assert len(rep["colorbars"]) == 1 and len(rep["cameras"]) == 1


# ----------------------------------------------------------------
# Unit tests — apply_sym
# ----------------------------------------------------------------

class TestApplySym:

    def test_positive_range(self):
        assert apply_sym(1.0, 3.0) == (-3.0, 3.0)

    def test_negative_dominant(self):
        assert apply_sym(-4.0, 1.0) == (-4.0, 4.0)

    def test_already_symmetric(self):
        assert apply_sym(-5.0, 5.0) == (-5.0, 5.0)

    def test_zero(self):
        assert apply_sym(0.0, 0.0) == (0.0, 0.0)

    def test_asymmetric_favours_larger_abs(self):
        lo, hi = apply_sym(-2.0, 7.0)
        assert lo == -7.0 and hi == 7.0


# ----------------------------------------------------------------
# Integration tests — colorbars (require pvbatch)
# ----------------------------------------------------------------

@pytestmark_pvbatch
@pytest.mark.integration
class TestColorbars:
    """
    The test state has exactly one colorbar (index 1).
    All tests that should succeed check returncode == 0.
    All tests that should fail check returncode != 0.
    """

    # -- --list-colorbars --

    def test_list_colorbars(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--list-colorbars", "--si", "--time", "1", "--size", str(TEST_WIDTH), outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    # -- --list-colormaps --

    def test_list_colormaps(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--list-colormaps", "--si", "--time", "1", "--size", str(TEST_WIDTH), outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")
        # Verify the header and at least one known preset name appear in stdout
        assert "Available colormaps" in r.stdout
        assert "Viridis" in r.stdout

    # -- --cb-discretize --

    def test_cb_discretize(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-discretize", "1", "17",
                 "--si", "--time", "1", "--size", str(TEST_WIDTH), outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_cb_discretize_256(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-discretize", "1", "256",
                 "--si", "--time", "1", "--size", str(TEST_WIDTH), outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_cb_discretize_with_colormap(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-colormap", "1", "Viridis", "--cb-discretize", "1", "8",
                 "--si", "--time", "1", "--size", str(TEST_WIDTH), outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_cb_discretize_steps_too_small_fails(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-discretize", "1", "1",
                 "--si", "--time", "1", "--size", str(TEST_WIDTH), outname=out)
        assert r.returncode != 0

    def test_cb_discretize_invalid_index_fails(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-discretize", "99", "17",
                 "--si", "--time", "1", "--size", str(TEST_WIDTH), outname=out)
        assert r.returncode != 0

    # -- --cb-range --

    def test_cb_range_explicit(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-range", "1", "0", "1",
                 "--si", "--time", "1", "--size", str(TEST_WIDTH), outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_cb_range_negative_values(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-range", "1", "-1", "1",
                 "--si", "--time", "1", "--size", str(TEST_WIDTH), outname=out)
        assert r.returncode == 0, r.stderr

    def test_cb_range_out_of_bounds_fails(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-range", "99", "0", "1",
                 "--si", "--time", "1", outname=out)
        assert r.returncode != 0

    # -- --cb-data-range-all --

    def test_cb_data_range_all_image(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-data-range-all", "1",
                 "--si", "--time", "1", "--size", str(TEST_WIDTH), outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_cb_data_range_all_sym_image(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-data-range-all", "1", "--cb-sym", "1",
                 "--si", "--time", "1", "--size", str(TEST_WIDTH), outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    # -- --cb-data-range-clamp --

    def test_cb_data_range_clamp_image(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-data-range-clamp", "1",
                 "--si", "--time", "1", "--size", str(TEST_WIDTH), outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_cb_data_range_clamp_animation(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-data-range-clamp", "1",
                 "--sa", "--size", str(TEST_WIDTH), "--frame-start", "0", "--frame-end", "2",
                 outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".mp4")

    def test_cb_data_range_clamp_sym_animation(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-data-range-clamp", "1", "--cb-sym", "1",
                 "--sa", "--size", str(TEST_WIDTH), "--frame-start", "0", "--frame-end", "2",
                 outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".mp4")

    # -- --cb-data-range-grow --

    def test_cb_data_range_grow_image(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-data-range-grow", "1",
                 "--si", "--time", "1", "--size", str(TEST_WIDTH), outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_cb_data_range_grow_animation(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-data-range-grow", "1",
                 "--sa", "--size", str(TEST_WIDTH), "--frame-start", "0", "--frame-end", "2",
                 outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".mp4")

    def test_cb_data_range_grow_sym_animation(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-data-range-grow", "1", "--cb-sym", "1",
                 "--sa", "--size", str(TEST_WIDTH), "--frame-start", "0", "--frame-end", "2",
                 outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".mp4")

    # -- Conflict / error cases --

    def test_cb_sym_without_data_range_fails(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-sym", "1", "--si", "--time", "1", outname=out)
        assert r.returncode != 0

    def test_cb_range_and_data_range_all_conflict_fails(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-range", "1", "0", "1", "--cb-data-range-all", "1",
                 "--si", "--time", "1", outname=out)
        assert r.returncode != 0

    def test_cb_data_range_all_and_clamp_conflict_fails(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-data-range-all", "1", "--cb-data-range-clamp", "1",
                 "--si", "--time", "1", outname=out)
        assert r.returncode != 0

    # -- --cb-colormap --

    def test_cb_colormap_cool_to_warm(self, outdir):
        # Also exercises case-insensitive matching ("cool to warm" vs "Cool to Warm")
        out = os.path.join(outdir, "out")
        r = _run("--cb-colormap", "1", "cool to warm",
                 "--si", "--time", "1", "--size", str(TEST_WIDTH), outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_cb_colormap_with_data_range_all(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-colormap", "1", "Cool to Warm", "--cb-data-range-all", "1",
                 "--si", "--time", "1", "--size", str(TEST_WIDTH), outname=out)
        assert r.returncode == 0, r.stderr

    def test_cb_colormap_unknown_fails(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-colormap", "1", "does_not_exist_xyz",
                 "--si", "--time", "1", outname=out)
        assert r.returncode != 0

    def test_cb_colormap_out_of_bounds_fails(self, outdir):
        out = os.path.join(outdir, "out")
        r = _run("--cb-colormap", "99", "Cool to Warm",
                 "--si", "--time", "1", outname=out)
        assert r.returncode != 0

    # -- argument robustness --

    def test_layout_zero_fails(self, outdir):
        r = _run("--layout", "0", "--size", "320", outname=os.path.join(outdir, "out"))
        assert r.returncode != 0
        assert "error:" in r.stderr

    def test_frame_start_beyond_end_fails(self, outdir):
        r = _run("--sa", "--frame-start", "50", "--animation-format", "png",
                 "--size", "320", outname=os.path.join(outdir, "out"))
        assert r.returncode != 0
        assert "error:" in r.stderr
        assert r.returncode != 139

    def test_dotted_outname_kept(self, outdir):
        out = os.path.join(outdir, "run_1.5")
        r = _run("--si", "--size", "320", outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_cb_range_non_numeric_fails(self, outdir):
        r = _run("--si", "--cb-range", "1", "abc", "5", "--size", "320",
                 outname=os.path.join(outdir, "out"))
        assert r.returncode != 0
        assert "Traceback" not in r.stderr


# ----------------------------------------------------------------
# Integration tests — data-path checks and generated states (require pvbatch)
# ----------------------------------------------------------------

@pytestmark_pvbatch
@pytest.mark.integration
class TestDataPaths:
    """Missing data files and the template-run fallback (reader left outside --datadir)."""

    def test_missing_datadir_file_fails(self, outdir, fixtures):
        r, _ = _inspect("--si", "--size", "320", outname=os.path.join(outdir, "out"),
                        state=os.path.join(fixtures, "interp_state.pvsm"),
                        datadir=os.path.join(fixtures, "data_missing_step"))
        assert r.returncode != 0
        assert "radial_wave_0_7.vtp" in r.stderr
        assert "Traceback" not in r.stderr

    def test_fallback_outside_datadir_fails(self, outdir, fixtures):
        r, _ = _inspect("--si", "--size", "320", outname=os.path.join(outdir, "out"),
                        state=os.path.join(fixtures, "interp_state.pvsm"),
                        datadir=os.path.join(fixtures, "data_partial"))
        assert r.returncode != 0
        assert "probe_points.csv" in r.stderr
        assert "--keep-path" in r.stderr
        assert "Traceback" not in r.stderr

    def test_keep_path_allows_shared_file(self, outdir, fixtures):
        out = os.path.join(outdir, "out")
        r, _ = _inspect("--keep-path", "probe_points.csv", "--si", "--size", "320",
                        outname=out,
                        state=os.path.join(fixtures, "interp_state.pvsm"),
                        datadir=os.path.join(fixtures, "data_partial"))
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")

    def test_keep_path_unknown_reader_fails(self, outdir):
        r = _run("--keep-path", "nope.csv", "--si", "--size", "320",
                 outname=os.path.join(outdir, "out"))
        assert r.returncode != 0
        assert "nope.csv" in r.stderr
        assert "Traceback" not in r.stderr

    def test_keep_path_unused_reader_ok(self, outdir):
        # Review Focus 5: view 1 (XY chart of PlotOverLine) is fed only by the PVD, so the
        # CSV reader exists but is unused; naming it in --keep-path is accepted silently.
        out = os.path.join(outdir, "out")
        r = _run("--view", "1", "--keep-path", "probe_points.csv", "--si", "--size", "320",
                 outname=out)
        assert r.returncode == 0, r.stderr
        assert "error:" not in r.stderr
        assert os.path.isfile(out + ".png")

    def test_list_readers_used_flags(self, outdir):
        # Scoping: only readers upstream of a drawn representation in the rendered view
        # count as used. View 1 uses the PVD only; view 2 (quartile chart of
        # PlotDataOverTime <- ResampleWithDataset <- TableToPoints/PVD) uses both.
        def used_flags(view):
            r = _run("--view", view, "--list-readers", "--size", "320",
                     outname=os.path.join(outdir, "out"))
            assert r.returncode == 0, r.stderr
            flags = {}
            for line in r.stdout.splitlines():
                fields = line.split()
                if len(fields) >= 3 and fields[1] in ("radial_wave.pvd", "probe_points.csv"):
                    flags[fields[1]] = fields[2]
            return flags

        assert used_flags("1") == {"radial_wave.pvd": "yes", "probe_points.csv": "no"}
        assert used_flags("2") == {"radial_wave.pvd": "yes", "probe_points.csv": "yes"}

    def test_list_readers_chart_rule(self, outdir, fixtures):
        # Chart rule: the CSV's chart representation is visible but has no series, so it
        # draws nothing and its reader is unused.
        r, _ = _inspect("--list-readers", "--size", "320", outname=os.path.join(outdir, "out"),
                        state=os.path.join(fixtures, "chart_state.pvsm"), datadir=None)
        assert r.returncode == 0, r.stderr
        flags = {f[1]: f[2] for f in (line.split() for line in r.stdout.splitlines())
                 if len(f) >= 3 and f[1] in ("radial_wave.pvd", "probe_points.csv")}
        assert flags == {"radial_wave.pvd": "yes", "probe_points.csv": "no"}

    def test_filenames_missing_unused_csv_ok(self, outdir):
        # Missing-data scope: the state's CSV path doesn't exist, but view 1 doesn't use it.
        out = os.path.join(outdir, "out")
        pvd_path = os.path.join(DATA, "radial_wave.pvd").replace("\\", "/")
        cmd = ["pvbatch", SCRIPT, STATE,
               "--filenames", "{{'radial_wave.pvd': '{}'}}".format(pvd_path),
               "--view", "1", "--si", "--size", "320", "-o", out]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=600)
        assert r.returncode == 0, r.stderr
        assert "error:" not in r.stderr
        assert os.path.isfile(out + ".png")

    def test_allow_missing_data_warns(self, outdir, fixtures):
        out = os.path.join(outdir, "out")
        r, _ = _inspect("--allow-missing-data", "--si", "--size", "320", outname=out,
                        state=os.path.join(fixtures, "interp_state.pvsm"),
                        datadir=os.path.join(fixtures, "data_missing_step"))
        assert r.returncode == 0, r.stderr
        assert "warning:" in r.stderr
        assert "radial_wave_0_7.vtp" in r.stderr

    def test_filenames_unmapped_missing_csv_fails(self, outdir):
        # Only the PVD is mapped; the state's CSV path does not exist.
        pvd_path = os.path.join(DATA, "radial_wave.pvd").replace("\\", "/")
        cmd = ["pvbatch", SCRIPT, STATE,
               "--filenames", "{{'radial_wave.pvd': '{}'}}".format(pvd_path),
               "--si", "--size", "320", "-o", os.path.join(outdir, "out")]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=600)
        assert r.returncode != 0
        assert "probe_points.csv" in r.stderr
        assert "Traceback" not in r.stderr

    def test_list_readers(self, outdir):
        r = _run("--list-readers", "--size", "320", outname=os.path.join(outdir, "out"))
        assert r.returncode == 0, r.stderr
        assert "radial_wave.pvd" in r.stdout
        assert "probe_points.csv" in r.stdout

    def test_static_state_renders(self, outdir, fixtures):
        # Review Focus 3: a static data set (no time steps) renders an image and an
        # animation, and --cb-data-range-all works on it.
        out = os.path.join(outdir, "out")
        r, rep = _inspect("--si", "--sa", "--animation-format", "png",
                          "--cb-data-range-all", "1", "--size", "320", outname=out,
                          state=os.path.join(fixtures, "static_state.pvsm"), datadir=None)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")
        assert rep["timesteps"] == []
        lo, hi = rep["colorbars"][0]["range"]
        assert lo < hi



@pytestmark_pvbatch
@pytest.mark.integration
class TestSequenceScene:
    """A state whose animation scene is in PlayMode 'Sequence' (static data, 10 frames):
    the frame window counts the scene's frames, not the data time steps."""

    def _sa(self, outdir, fixtures, *extra):
        out = os.path.join(outdir, "out")
        r = subprocess.run(
            ["pvbatch", SCRIPT, os.path.join(fixtures, "sequence_state.pvsm"), "-o", out,
             "--sa", "--animation-format", "png", "--size", "160"] + list(extra),
            capture_output=True, text=True, cwd=ROOT, timeout=600)
        pngs = sorted(f for f in os.listdir(outdir) if f.lower().endswith(".png"))
        return r, pngs

    def test_sequence_no_flags_writes_all_frames(self, outdir, fixtures):
        r, pngs = self._sa(outdir, fixtures)
        assert r.returncode == 0, r.stderr
        assert len(pngs) == 10, pngs

    def test_sequence_frame_end_last(self, outdir, fixtures):
        r, pngs = self._sa(outdir, fixtures, "--frame-end", "9")
        assert r.returncode == 0, r.stderr
        assert len(pngs) == 10, pngs

    def test_sequence_frame_end_beyond_fails(self, outdir, fixtures):
        r, pngs = self._sa(outdir, fixtures, "--frame-end", "10")
        assert r.returncode != 0
        assert "error:" in r.stderr
        assert pngs == []

    def test_sequence_frame_window_from_zero(self, outdir, fixtures):
        r, pngs = self._sa(outdir, fixtures, "--frame-start", "0", "--frame-end", "4")
        assert r.returncode == 0, r.stderr
        assert pngs == [f"out.{i:04d}.png" for i in range(5)]

    def test_sequence_frame_window_inner(self, outdir, fixtures):
        # The window is accepted and passed to SaveAnimation. ParaView 6.1 itself writes
        # one frame fewer for a 'Sequence' window that starts after frame 0 (it skips
        # frame start + 1; pvrender before this branch did the same), so only the file
        # names are checked: they start at the window start and stay inside the window.
        r, pngs = self._sa(outdir, fixtures, "--frame-start", "2", "--frame-end", "5")
        assert r.returncode == 0, r.stderr
        assert pngs and pngs[0] == "out.0002.png", pngs
        assert set(pngs) <= {f"out.{i:04d}.png" for i in range(2, 6)}, pngs


@pytestmark_pvbatch
@pytest.mark.integration
class TestInterpInterval:
    """--interp-interval on states with Temporal Interpolators."""

    def _args(self, fixtures, name="interp_state.pvsm"):
        # R2: probe_points.csv lives in test/data, outside the adaptive data dir.
        return dict(state=os.path.join(fixtures, name),
                    datadir=os.path.join(fixtures, "data_adaptive"))

    def test_interp_interval_sets_all(self, outdir, fixtures):
        r, rep = _inspect("--interp-interval", "0.5", "--keep-path", "probe_points.csv",
                          "--si", "--size", "320", outname=os.path.join(outdir, "out"),
                          **self._args(fixtures))
        assert r.returncode == 0, r.stderr
        assert rep["interpolators"] == [0.5]
        exp = [0.5 * i for i in range(21)]
        assert len(rep["timesteps"]) == len(exp)
        assert all(abs(a - b) < 1e-9 for a, b in zip(rep["timesteps"], exp))

    def test_interp_interval_zero_original_steps(self, outdir, fixtures):
        r, rep = _inspect("--interp-interval", "0", "--keep-path", "probe_points.csv",
                          "--si", "--size", "320", outname=os.path.join(outdir, "out"),
                          **self._args(fixtures))
        assert r.returncode == 0, r.stderr
        exp = [10 * (i / 20) ** 2 for i in range(21)]
        assert len(rep["timesteps"]) == len(exp)
        assert all(abs(a - b) < 1e-9 for a, b in zip(rep["timesteps"], exp))

    def test_interp_interval_frame_window_counts_new_steps(self, outdir, fixtures):
        out = os.path.join(outdir, "out")
        a = self._args(fixtures)
        r = subprocess.run(
            ["pvbatch", SCRIPT, a["state"], "-d", a["datadir"], "-o", out,
             "--interp-interval", "0.25", "--keep-path", "probe_points.csv",
             "--sa", "--animation-format", "png", "--frame-end", "40", "--size", "160"],
            capture_output=True, text=True, cwd=ROOT, timeout=600)
        assert r.returncode == 0, r.stderr
        pngs = [f for f in os.listdir(outdir) if f.lower().endswith(".png")]
        assert len(pngs) == 41, pngs

    def test_interp_interval_no_interpolator_fails(self, outdir):
        r = _run("--interp-interval", "0.5", "--si", "--size", "320",
                 outname=os.path.join(outdir, "out"))
        assert r.returncode != 0
        assert "Temporal Interpolator" in r.stderr
        assert "Traceback" not in r.stderr

    def test_interp_interval_negative_fails(self, outdir):
        r = _run("--interp-interval", "-1", "--si", "--size", "320",
                 outname=os.path.join(outdir, "out"))
        assert r.returncode != 0
        assert "--interp-interval" in r.stderr
        assert "Traceback" not in r.stderr

    def test_interp_unsuppressed_warns(self, outdir, fixtures):
        out = os.path.join(outdir, "out")
        r, _ = _inspect("--interp-interval", "0.5", "--keep-path", "probe_points.csv",
                        "--si", "--size", "320", outname=out,
                        **self._args(fixtures, "interp_state_unsuppressed.pvsm"))
        assert r.returncode == 0, r.stderr
        assert "warning: these sources still add their own time steps" in r.stderr
        assert "radial_wave.pvd" in r.stderr


@pytestmark_pvbatch
@pytest.mark.integration
class TestFitCameraIntegration:
    """--fit-camera on the main state with the radial wave scaled x3 (data_big) and x0.3
    (data_small); the state's camera was set up for the unscaled data."""

    def _cam(self, outdir, fixtures, *extra, data=None, name="out"):
        datadir = DATA if data is None else os.path.join(fixtures, data)
        r, rep = _inspect("--size", "320", *extra, outname=os.path.join(outdir, name),
                          datadir=datadir)
        assert r.returncode == 0, r.stderr
        assert len(rep["cameras"]) == 1
        return rep["cameras"][0]

    @staticmethod
    def _dist(cam):
        return math.dist(cam["position"], cam["focal_point"])

    def test_no_fit_camera_unchanged(self, outdir, fixtures):
        default = self._cam(outdir, fixtures, name="default")
        big = self._cam(outdir, fixtures, data="data_big", name="big")
        assert big == default

    def test_fit_out_big_moves_back(self, outdir, fixtures):
        default = self._cam(outdir, fixtures, name="default")
        cam = self._cam(outdir, fixtures, "--fit-camera", "out", data="data_big")
        assert self._dist(cam) > self._dist(default) + 1e-6
        assert all(abs(a - b) < 1e-9 for a, b in zip(cam["focal_point"], default["focal_point"]))

    def test_fit_out_small_unchanged(self, outdir, fixtures):
        default = self._cam(outdir, fixtures, name="default")
        cam = self._cam(outdir, fixtures, "--fit-camera", "out", data="data_small")
        assert cam == default

    def test_fit_fit_small_moves_in(self, outdir, fixtures):
        default = self._cam(outdir, fixtures, name="default")
        cam = self._cam(outdir, fixtures, "--fit-camera", "fit", data="data_small")
        assert self._dist(cam) < self._dist(default) - 1e-6

    def test_fit_same_for_image_and_animation(self, outdir, fixtures):
        # Same frame window for both, so the bounds (and the fit) come from the same frames;
        # saving the animation must not move the camera per frame. The screenshot time
        # (frame 3) is inside the window: a time outside it adds its bounds to the fit.
        img = self._cam(outdir, fixtures, "--fit-camera", "fit", "--si", "--frame-end", "3",
                        "--time", "1.5", data="data_big", name="img")
        ani = self._cam(outdir, fixtures, "--fit-camera", "fit", "--sa",
                        "--animation-format", "png", "--frame-end", "3",
                        data="data_big", name="ani")
        for key in ("position", "focal_point", "view_up"):
            assert all(abs(a - b) < 1e-9 for a, b in zip(img[key], ani[key])), key
        assert abs(img["parallel_scale"] - ani["parallel_scale"]) < 1e-9

    def test_fit_static_state(self, outdir, fixtures):
        # Review Focus 3: static data set (no time steps).
        out = os.path.join(outdir, "out")
        r, rep = _inspect("--fit-camera", "fit", "--si", "--size", "320", outname=out,
                          state=os.path.join(fixtures, "static_state.pvsm"), datadir=None)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")
        assert "warning:" not in r.stderr

    def test_fit_scaled_rep_warns(self, outdir, fixtures):
        # Review Focus 1: the representation's Scale is [2, 1, 1]; the fit uses the data
        # bounds, so it warns (naming the representation's source) but still runs.
        r, _ = _inspect("--fit-camera", "fit", "--size", "320",
                        outname=os.path.join(outdir, "out"),
                        state=os.path.join(fixtures, "scaled_rep_state.pvsm"), datadir=None)
        assert r.returncode == 0, r.stderr
        warnings = [line for line in r.stderr.splitlines() if line.startswith("warning:")]
        assert any("Scale" in w or "transform" in w for w in warnings), r.stderr
        assert any("radial_wave_0_5.vtp" in w for w in warnings), r.stderr

    def test_fit_margin_out_of_range_fails(self, outdir):
        r = _run("--fit-camera", "fit", "--fit-margin", "60", "--size", "320",
                 outname=os.path.join(outdir, "out"))
        assert r.returncode != 0
        assert "--fit-margin" in r.stderr
        assert "Traceback" not in r.stderr


@pytestmark_pvbatch
@pytest.mark.integration
class TestScreenshotTime:
    """--save-image renders at the screenshot time T (--time, default EndTime), which can
    lie outside the frame window: a 'Sequence' scene with NumberOfFrames 1 (states written
    by pvpython scripts; the window is [StartTime]) or --time outside --frame-*. The
    screenshot's ranges and camera fit then include T; --save-animation keeps the window's.

    On the main state, frame 1 is t = 0.5 and frame 20 is t = 10 (= EndTime), so the
    window [1, 1] with T = 10 must match the window {1, 20} (--frame-stride 19)."""

    WINDOW_1 = ("--frame-start", "1", "--frame-end", "1")
    WINDOW_1_20 = ("--frame-start", "1", "--frame-end", "20", "--frame-stride", "19")
    SA = ("--sa", "--animation-format", "png")

    def _interp(self, outdir, fixtures, *extra, name="o"):
        r, rep = _inspect("--keep-path", "probe_points.csv", "--si", "--size", "160", *extra,
                          outname=os.path.join(outdir, name),
                          state=os.path.join(fixtures, "interp_state.pvsm"),
                          datadir=os.path.join(fixtures, "data_adaptive"))
        assert r.returncode == 0, r.stderr
        return rep

    def _main(self, outdir, *extra, name, datadir=DATA):
        r, rep = _inspect("--size", "160", *extra, outname=os.path.join(outdir, name),
                          datadir=datadir)
        assert r.returncode == 0, r.stderr
        return rep

    def test_sequence_scene_clamp_at_screenshot_time(self, outdir, fixtures):
        # interp_state: 'Sequence', NumberOfFrames 1, so the window is [t = 0]; T = 10
        rep = self._interp(outdir, fixtures, "--cb-data-range-clamp", "1")
        assert rep["time"] == pytest.approx(10.0)
        assert rep["colorbars"][0]["range"] == pytest.approx([-0.9967, 0.9996], abs=1e-4)

    def test_sequence_scene_grow_includes_screenshot_time(self, outdir, fixtures):
        # union of t = 0 ([-0.9455, 1.0]) and t = 10 ([-0.9967, 0.9996])
        rep = self._interp(outdir, fixtures, "--cb-data-range-grow", "1")
        assert rep["colorbars"][0]["range"] == pytest.approx([-0.9967, 1.0], abs=1e-4)

    @pytest.mark.parametrize("mode", ["all", "grow"])
    def test_plot_range_includes_screenshot_time(self, outdir, mode):
        # Line chart y: t = 0.5 reaches 0.969, t = 10 reaches 0.9996
        flags = (f"--plot-data-range-{mode}", "1", "y")
        img, ref, ani, both = (
            self._main(outdir, *flags, *extra, name=name)["plots"][0]["axes"]["Left"]
            for name, extra in (("img", ("--si",) + self.WINDOW_1),
                                ("ref", self.SA + self.WINDOW_1_20),
                                ("ani", self.SA + self.WINDOW_1),
                                ("both", ("--si",) + self.SA + self.WINDOW_1)))
        assert img["custom"] is True
        assert img["range"] == pytest.approx(ref["range"], abs=1e-9)
        assert img["range"][1] > ani["range"][1] + 1e-3
        # --save-animation keeps the window's range, also after a screenshot outside it
        assert both["range"] == pytest.approx(ani["range"], abs=1e-9)

    def test_fit_camera_includes_screenshot_time(self, outdir, fixtures):
        big = os.path.join(fixtures, "data_big")
        flags = ("--fit-camera", "fit")
        img = self._main(outdir, *flags, "--si", *self.WINDOW_1, name="img", datadir=big)
        ref = self._main(outdir, *flags, *self.SA, *self.WINDOW_1_20, name="ref", datadir=big)
        ani = self._main(outdir, *flags, *self.SA, *self.WINDOW_1, name="ani", datadir=big)
        both = self._main(outdir, *flags, "--si", *self.SA, *self.WINDOW_1, name="both",
                          datadir=big)
        img, ref, ani, both = (rep["cameras"][0] for rep in (img, ref, ani, both))
        assert img["focal_point"] != pytest.approx(ani["focal_point"], abs=1e-6)
        for key in ("position", "focal_point", "view_up"):
            assert img[key] == pytest.approx(ref[key], abs=1e-9), key
            assert both[key] == pytest.approx(ani[key], abs=1e-9), key
        assert img["parallel_scale"] == pytest.approx(ref["parallel_scale"], abs=1e-9)
        assert both["parallel_scale"] == pytest.approx(ani["parallel_scale"], abs=1e-9)


@pytestmark_pvbatch
@pytest.mark.integration
class TestNoStrayRepresentations:
    """Inspecting the pipeline must not create representations: the render view shows
    exactly what the saved state shows (probed straight after LoadState)."""

    STATE_VISIBLE = ["AnnotateTimeFilter1", "TimeStepProgressBar1", "WarpByScalar1"]

    def _check(self, rep):
        assert len(rep["cameras"]) == 1
        visible = rep["cameras"][0]["visible_sources"]
        for stray in ("PlotOverLine1", "PlotDataOverTime1", "ResampleWithDataset1"):
            assert stray not in visible
        assert visible == self.STATE_VISIBLE

    def test_render_view_shows_only_state_sources(self, outdir):
        r, rep = _inspect("--si", "--time", "1", "--size", "320",
                          outname=os.path.join(outdir, "out"))
        assert r.returncode == 0, r.stderr
        self._check(rep)

    def test_dynamic_range_does_not_create_reps(self, outdir):
        r, rep = _inspect("--cb-data-range-clamp", "1", "--sa", "--animation-format", "png",
                          "--frame-end", "2", "--size", "160",
                          outname=os.path.join(outdir, "out"))
        assert r.returncode == 0, r.stderr
        self._check(rep)


# ----------------------------------------------------------------
# Plots: axes, titles, --list-plots, --cb-title
# ----------------------------------------------------------------

def _plot_args(*extra):
    return pvrender.parse_args(["x.pvsm"] + list(extra))


def test_normalize_axis():
    assert pvrender.normalize_axis("x") == "Bottom"
    assert pvrender.normalize_axis("Y") == "Left"
    assert pvrender.normalize_axis("right") == "Right"
    assert pvrender.normalize_axis("TOP") == "Top"
    assert pvrender.normalize_axis("bottom") == "Bottom"
    with pytest.raises(SystemExit):
        pvrender.normalize_axis("z")


def test_build_plot_specs_fixed_auto_log_title():
    args = _plot_args("--plot-range", "1", "y", "-2", "2",
                      "--plot-auto", "1", "x",
                      "--plot-log", "2", "x", "on",
                      "--plot-axis-title", "1", "y", "w [m]")
    specs = pvrender.build_plot_specs(args, 2)
    assert specs[(1, "Left")]["mode"] == "fixed"
    assert (specs[(1, "Left")]["min"], specs[(1, "Left")]["max"]) == (-2.0, 2.0)
    assert specs[(1, "Left")]["title"] == "w [m]"
    assert specs[(1, "Bottom")]["mode"] == "auto"
    assert specs[(2, "Bottom")]["log"] is True
    assert specs[(2, "Bottom")]["mode"] is None


def test_build_plot_specs_empty_when_no_flags():
    assert pvrender.build_plot_specs(_plot_args(), 2) == {}


def test_build_plot_specs_x_and_bottom_merge():
    args = _plot_args("--plot-range", "1", "x", "0", "1",
                      "--plot-log", "1", "bottom", "off")
    specs = pvrender.build_plot_specs(args, 1)
    assert list(specs) == [(1, "Bottom")]
    assert specs[(1, "Bottom")]["mode"] == "fixed"
    assert specs[(1, "Bottom")]["log"] is False


def test_build_plot_specs_all_grow_sym_parsed():
    args = _plot_args("--plot-data-range-all", "1", "y", "--plot-sym", "1", "y",
                      "--plot-data-range-grow", "2", "x")
    specs = pvrender.build_plot_specs(args, 2)
    assert specs[(1, "Left")]["mode"] == "all" and specs[(1, "Left")]["sym"] is True
    assert specs[(2, "Bottom")]["mode"] == "grow" and specs[(2, "Bottom")]["sym"] is False


@pytest.mark.parametrize("flags", [
    ["--plot-range", "1", "y", "0", "1", "--plot-data-range-all", "1", "y"],
    ["--plot-data-range-all", "1", "y", "--plot-data-range-grow", "1", "left"],
    ["--plot-range", "1", "y", "0", "1", "--plot-auto", "1", "y"],
    ["--plot-sym", "1", "y"],
    ["--plot-range", "1", "y", "0", "1", "--plot-sym", "1", "y"],
    ["--plot-range", "1", "y", "1", "1"],
    ["--plot-range", "1", "y", "2", "1"],
    ["--plot-range", "1", "y", "abc", "1"],
    ["--plot-range", "0", "y", "0", "1"],
    ["--plot-range", "3", "y", "0", "1"],
    ["--plot-range", "x", "y", "0", "1"],
    ["--plot-range", "1", "z", "0", "1"],
    ["--plot-log", "1", "x", "maybe"],
    ["--plot-range", "1", "x", "0", "1", "--plot-log", "1", "x", "on"],
    ["--plot-range", "1", "x", "-1", "1", "--plot-log", "1", "x", "on"],
    ["--plot-title", "3", "T"],
    ["--plot-axis-title", "1", "q", "T"],
])
def test_build_plot_specs_errors(flags):
    with pytest.raises(SystemExit):
        pvrender.build_plot_specs(_plot_args(*flags), 2)


def test_build_plot_specs_log_on_positive_fixed_ok():
    args = _plot_args("--plot-range", "1", "x", "0.1", "1", "--plot-log", "1", "x", "on")
    assert pvrender.build_plot_specs(args, 1)[(1, "Bottom")]["log"] is True


def test_validate_cb_title_index():
    args = _plot_args("--cb-title", "1", "T")
    pvrender.validate_colorbar_args(args, 1)
    for bad in (["--cb-title", "0", "T"], ["--cb-title", "2", "T"], ["--cb-title", "a", "T"]):
        with pytest.raises(SystemExit):
            pvrender.validate_colorbar_args(_plot_args(*bad), 1)


def test_normalize_title():
    assert pvrender.normalize_title("") == ""
    assert pvrender.normalize_title(" ") == ""
    assert pvrender.normalize_title("   ") == ""
    assert pvrender.normalize_title(" A ") == " A "
    assert pvrender.normalize_title("Run A") == "Run A"
    args = _plot_args("--plot-title", "1", " ", "--plot-axis-title", "1", "y", "  ")
    assert pvrender.build_chart_titles(args) == {1: ""}
    assert pvrender.build_plot_specs(args, 1)[(1, "Left")]["title"] == ""


def test_enumerate_plots_filters_by_property():
    class V:
        def __init__(self, has):
            self.has = has
        def ListProperties(self):
            return ["LeftAxisUseCustomRange"] if self.has else ["Other"]
    a, b, c = V(True), V(False), V(True)
    assert pvrender.enumerate_plots([a, b, c]) == [a, c]


@pytestmark_pvbatch
@pytest.mark.integration
class TestPlots:

    def test_list_plots(self, outdir):
        r = _run("--list-plots", "--size", "320", outname=os.path.join(outdir, "o"))
        assert r.returncode == 0, r.stderr
        assert "XYChartView" in r.stdout and "QuartileChartView" in r.stdout

    def test_bad_plot_index_fails_before_colorbar_work(self, outdir):
        # Plot arguments are validated right after the colorbar arguments, before any
        # colorbar change (here an unknown colormap preset, which would fail when applied)
        # and before the per-frame colorbar precompute (--cb-data-range-clamp).
        r = _run("--cb-colormap", "1", "no such preset", "--cb-data-range-clamp", "1",
                 "--plot-range", "9", "y", "0", "1", "--si", "--size", "320",
                 outname=os.path.join(outdir, "o"))
        assert r.returncode != 0
        assert "error: --plot-range: plot index 9 out of range" in r.stderr, r.stderr
        assert "--cb-colormap" not in r.stderr, r.stderr
        assert "warning:" not in r.stderr, r.stderr
        assert "Traceback" not in r.stderr

    def test_plot_range_fixed_x_and_y(self, outdir):
        r, rep = _inspect("--plot-range", "1", "x", "-0.2", "0.3",
                          "--plot-range", "1", "y", "-2", "2", "--size", "320",
                          outname=os.path.join(outdir, "o"))
        assert r.returncode == 0, r.stderr
        axes = rep["plots"][0]["axes"]
        assert axes["Bottom"]["custom"] is True
        assert axes["Bottom"]["range"] == [-0.2, 0.3]
        assert axes["Left"]["custom"] is True
        assert axes["Left"]["range"] == [-2, 2]

    def test_plot_auto(self, outdir):
        r, rep = _inspect("--plot-range", "1", "y", "-2", "2", "--plot-auto", "1", "x",
                          "--size", "320", outname=os.path.join(outdir, "o"))
        assert r.returncode == 0, r.stderr
        assert rep["plots"][0]["axes"]["Bottom"]["custom"] is False
        assert rep["plots"][0]["axes"]["Left"]["custom"] is True

    def test_plot_log(self, outdir):
        r, rep = _inspect("--plot-log", "2", "x", "on", "--size", "320",
                          outname=os.path.join(outdir, "o"))
        assert r.returncode == 0, r.stderr
        assert rep["plots"][1]["axes"]["Bottom"]["log"] is True
        assert rep["plots"][0]["axes"]["Bottom"]["log"] is False

    def test_plot_titles(self, outdir):
        r, rep = _inspect("--plot-title", "1", "Run A", "--plot-axis-title", "1", "y", "w [m]",
                          "--size", "320", outname=os.path.join(outdir, "o"))
        assert r.returncode == 0, r.stderr
        assert rep["plots"][0]["title"] == "Run A"
        assert rep["plots"][0]["axes"]["Left"]["title"] == "w [m]"

    def test_plot_title_empty_clears(self, outdir):
        r, rep = _inspect("--plot-title", "1", " ", "--size", "320",
                          outname=os.path.join(outdir, "o"))
        assert r.returncode == 0, r.stderr
        assert rep["plots"][0]["title"] == ""

    def test_cb_title_blank_clears(self, outdir):
        r, rep = _inspect("--cb-title", "1", " ", "--size", "320",
                          outname=os.path.join(outdir, "o"))
        assert r.returncode == 0, r.stderr
        assert rep["colorbars"][0]["titles"] == [""]

    def test_cb_title(self, outdir):
        r, rep = _inspect("--cb-title", "1", "Displacement", "--size", "320",
                          outname=os.path.join(outdir, "o"))
        assert r.returncode == 0, r.stderr
        assert rep["colorbars"][0]["titles"] == ["Displacement"]

    def test_plot_index_out_of_range_fails(self, outdir):
        r = _run("--plot-range", "3", "y", "0", "1", "--size", "320",
                 outname=os.path.join(outdir, "o"))
        assert r.returncode != 0
        assert "plot" in (r.stderr + r.stdout).lower()


# ----------------------------------------------------------------
# Plot data ranges (all/grow/sym), margin, shared per-frame cue
# ----------------------------------------------------------------

def test_pad_range():
    assert pvrender.pad_range(0, 10) == pytest.approx((-0.5, 10.5))
    lo, hi = pvrender.pad_range(1, 100, log=True)
    assert lo == pytest.approx(10 ** -0.1) and hi == pytest.approx(10 ** 2.1)
    with pytest.raises(ValueError):
        pvrender.pad_range(0, 100, log=True)


def test_grow_entries():
    entries = [[0, -1, 1], [1, -0.5, 2], [2, -3, 0]]
    assert pvrender.grow_entries(entries) == [[0, -1, 1], [1, -1, 2], [2, -3, 2]]
    assert entries == [[0, -1, 1], [1, -0.5, 2], [2, -3, 0]]  # input unchanged
    assert pvrender.grow_entries([]) == []


def test_axis_series():
    # Review Focus 2: series on the right axis belong to Right only, not to y/Left.
    visible, corners = ["a", "b"], ["b", "1"]
    assert pvrender.axis_series(visible, corners, "Left") == ["a"]
    assert pvrender.axis_series(visible, corners, "Right") == ["b"]
    assert pvrender.axis_series(visible, corners, "Bottom") == []
    assert pvrender.axis_series(visible, corners, "Top") == []
    # corner 3 (top-left) plots on the left axis, corner 2 (top-right) on the right axis
    assert pvrender.axis_series(["a", "b", "c"], ["a", "3", "b", "2"], "Left") == ["a", "c"]
    assert pvrender.axis_series(["a", "b", "c"], ["a", "3", "b", "2"], "Right") == ["b"]


def test_x_axis_has_series():
    # The X array of a series on corner 0/1 is on the bottom axis, on corner 2/3 on the top.
    assert pvrender.x_axis_has_series(["a"], [], "Bottom") is True
    assert pvrender.x_axis_has_series(["a"], [], "Top") is False
    assert pvrender.x_axis_has_series(["a"], ["a", "2"], "Top") is True
    assert pvrender.x_axis_has_series(["a"], ["a", "2"], "Bottom") is False
    assert pvrender.x_axis_has_series([], [], "Bottom") is False


def test_split_series_name():
    arrays = ["z-Displacement [m]", "Points", "U"]
    split = pvrender.split_series_name
    assert split("z-Displacement [m] (stats)", arrays) == ("z-Displacement [m]", -1)
    assert split("z-Displacement [m] (id=0)", arrays) == ("z-Displacement [m]", -1)
    assert split("z-Displacement [m]", arrays) == ("z-Displacement [m]", -1)
    assert split("U_X", arrays) == ("U", 0)
    assert split("U_Y", arrays) == ("U", 1)
    assert split("U_Z", arrays) == ("U", 2)
    assert split("U_Magnitude", arrays) == ("U", -1)
    assert split("U_2", arrays) == ("U", 2)
    assert split("Points_X", arrays) == ("Points", 0)
    assert split("U_X (id=12)", arrays) == ("U", 0)
    assert split("nope", arrays) is None
    assert split("U_W", arrays) is None
    assert split("V_X", arrays) is None


def test_split_block_suffix():
    split = pvrender.split_block_suffix
    assert split("z-Displacement [m] (id=0)") == ("z-Displacement [m]", "id=0")
    assert split("z-Displacement [m] (stats)") == ("z-Displacement [m]", "stats")
    assert split("N (vtkMultiBlockDataSet)") == ("N", "vtkMultiBlockDataSet")
    assert split("Point Coordinates_X (id=12)") == ("Point Coordinates_X", "id=12")
    assert split("p (bar) (block 1)") == ("p (bar)", "block 1")
    assert split("z-Displacement [m]") == ("z-Displacement [m]", None)
    assert split("min(z-Displacement [m])") == ("min(z-Displacement [m])", None)
    assert split("U_X") == ("U_X", None)


def test_finish_plot_range():
    finish = pvrender._finish_plot_range
    r, note = finish(-1, 3, False, False)
    assert r == pytest.approx((-1.2, 3.2)) and note is None
    r, note = finish(-1, 3, True, False)  # sym first, then the margin
    assert r == pytest.approx((-3.3, 3.3)) and note is None
    # Ruling R4: on a log axis a lower bound <= 0 is clipped to hi / 1000
    r, note = finish(-1, 100, False, True)
    assert note == "clipped"
    assert r == pytest.approx(pvrender.pad_range(0.1, 100, log=True))
    assert finish(-5, 0, False, True) == (None, "nonpositive")
    assert finish(2, 2, False, False) == (None, "degenerate")


def _right_axis_state(fixtures):
    return os.path.join(fixtures, "right_axis_state.pvsm")


@pytestmark_pvbatch
@pytest.mark.integration
class TestPlotRanges:
    """--plot-data-range-all/grow and --plot-sym on the main state's Line Chart (plot 1,
    PlotOverLine over x = -0.5 .. 0.5) and Plot Data Over Time (plot 2, time 0 .. 10)."""

    def test_plot_all_y_line_chart(self, outdir):
        r, rep = _inspect("--plot-data-range-all", "1", "y", "--size", "320",
                          outname=os.path.join(outdir, "all"))
        assert r.returncode == 0, r.stderr
        left = rep["plots"][0]["axes"]["Left"]
        assert left["custom"] is True
        lo, hi = left["range"]
        assert lo < 0 < hi
        r, rep = _inspect("--plot-data-range-grow", "1", "y", "--sa", "--animation-format", "png",
                          "--size", "160", outname=os.path.join(outdir, "grow"))
        assert r.returncode == 0, r.stderr
        glo, ghi = rep["plots"][0]["axes"]["Left"]["range"]
        assert rep["plots"][0]["axes"]["Left"]["custom"] is True
        assert lo <= glo + 1e-9 and ghi <= hi + 1e-9
        # grow ends at the union over all frames, which is the 'all' range
        assert glo == pytest.approx(lo, abs=1e-9) and ghi == pytest.approx(hi, abs=1e-9)

    def test_plot_all_x_line_chart(self, outdir):
        r, rep = _inspect("--plot-data-range-all", "1", "x", "--size", "320",
                          outname=os.path.join(outdir, "o"))
        assert r.returncode == 0, r.stderr
        bottom = rep["plots"][0]["axes"]["Bottom"]
        assert bottom["custom"] is True
        assert bottom["range"] == pytest.approx([-0.55, 0.55], abs=1e-6)

    def test_plot_all_x_quartile_time(self, outdir):
        r, rep = _inspect("--plot-data-range-all", "2", "x", "--size", "320",
                          outname=os.path.join(outdir, "o"))
        assert r.returncode == 0, r.stderr
        bottom = rep["plots"][1]["axes"]["Bottom"]
        assert bottom["custom"] is True
        assert bottom["range"] == pytest.approx([-0.5, 10.5], abs=1e-6)

    def test_plot_sym(self, outdir):
        r, rep = _inspect("--plot-data-range-all", "1", "y", "--plot-sym", "1", "y",
                          "--size", "320", outname=os.path.join(outdir, "o"))
        assert r.returncode == 0, r.stderr
        left = rep["plots"][0]["axes"]["Left"]
        assert left["custom"] is True
        lo, hi = left["range"]
        assert hi > 1  # data max ~1 plus the 5 % margin (the state's range is [-1, 1])
        assert lo == pytest.approx(-hi, abs=1e-12)

    def test_plot_all_quartile(self, outdir):
        r, rep = _inspect("--plot-data-range-all", "2", "y", "--size", "320",
                          outname=os.path.join(outdir, "o"))
        assert r.returncode == 0, r.stderr
        left = rep["plots"][1]["axes"]["Left"]
        assert left["custom"] is True
        lo, hi = left["range"]
        assert lo < 0 < hi

    def test_plot_grow_animation(self, outdir):
        out = os.path.join(outdir, "o")
        r, rep = _inspect("--plot-data-range-grow", "1", "y", "--sa", "--animation-format",
                          "png", "--frame-end", "3", "--size", "160", outname=out)
        assert r.returncode == 0, r.stderr
        assert rep["plots"][0]["axes"]["Left"]["custom"] is True
        lo, hi = rep["plots"][0]["axes"]["Left"]["range"]
        assert lo < 0 < hi

    def test_plot_grow_and_cb_grow_share_cue(self, outdir):
        # one cue carries both colorbar and plot ranges
        r, rep = _inspect("--plot-data-range-grow", "2", "y", "--cb-data-range-grow", "1",
                          "--sa", "--animation-format", "png", "--frame-end", "2",
                          "--size", "160", outname=os.path.join(outdir, "o"))
        assert r.returncode == 0, r.stderr
        assert rep["plots"][1]["axes"]["Left"]["custom"] is True
        lo, hi = rep["colorbars"][0]["range"]
        assert lo < hi

    def test_plot_grow_image(self, outdir):
        out = os.path.join(outdir, "o")
        r, rep = _inspect("--plot-data-range-grow", "1", "x", "--si", "--size", "160",
                          outname=out)
        assert r.returncode == 0, r.stderr
        assert os.path.isfile(out + ".png")
        bottom = rep["plots"][0]["axes"]["Bottom"]
        assert bottom["custom"] is True
        assert bottom["range"] == pytest.approx([-0.55, 0.55], abs=1e-6)

    def test_plot_right_axis_separate(self, outdir, fixtures):
        # Review Focus 2: arc_length is on the right axis; y/Left uses z-Displacement only.
        r, rep = _inspect("--plot-data-range-all", "1", "y", "--plot-data-range-all", "1", "right",
                          "--size", "320", outname=os.path.join(outdir, "o"),
                          state=_right_axis_state(fixtures), datadir=None)
        assert r.returncode == 0, r.stderr
        axes = rep["plots"][0]["axes"]
        assert axes["Left"]["custom"] is True and axes["Right"]["custom"] is True
        llo, lhi = axes["Left"]["range"]
        rlo, rhi = axes["Right"]["range"]
        # arc_length runs 0 .. sqrt(2) along the diagonal line
        assert rlo <= 0 and rhi >= math.sqrt(2) - 1e-6
        assert llo < 0 < lhi
        assert lhi < rhi

    def test_plot_all_log_clips_and_warns(self, outdir):
        # x runs -0.5 .. 0.5: on a log axis the lower bound is clipped to 0.5 / 1000
        r, rep = _inspect("--plot-data-range-all", "1", "x", "--plot-log", "1", "x", "on",
                          "--size", "320", outname=os.path.join(outdir, "o"))
        assert r.returncode == 0, r.stderr
        assert "clipped" in r.stderr
        bottom = rep["plots"][0]["axes"]["Bottom"]
        assert bottom["custom"] is True and bottom["log"] is True
        assert bottom["range"] == pytest.approx(list(pvrender.pad_range(0.0005, 0.5, log=True)),
                                                rel=1e-6)

    def test_plot_all_quartile_stats_block(self, outdir, fixtures):
        # Plot Data Over Time statistics: the range is min(z) .. max(z) over all points
        # and times, i.e. the global data range (-0.99987 .. 1.0), plus the 5 % margin.
        r, rep = _inspect("--plot-data-range-all", "1", "y", "--size", "320",
                          outname=os.path.join(outdir, "o"),
                          state=os.path.join(fixtures, "stats_chart_state.pvsm"))
        assert r.returncode == 0, r.stderr
        assert "not found" not in r.stderr
        left = rep["plots"][0]["axes"]["Left"]
        assert left["custom"] is True
        assert left["range"] == pytest.approx(list(pvrender.pad_range(-0.99987, 1.0)), abs=1e-4)

    def test_plot_all_quartile_stale_stats_series_silent(self, outdir):
        # The main state's Plot Data Over Time shows block id=0 and keeps a stale visible
        # '(stats)' series (statistics are off, so no stats block exists): no warning, and
        # the range is exactly block id=0's range (-0.99413 .. 1.0) plus the margin.
        r, rep = _inspect("--plot-data-range-all", "2", "y", "--size", "320",
                          outname=os.path.join(outdir, "o"))
        assert r.returncode == 0, r.stderr
        assert "warning" not in r.stderr, r.stderr
        left = rep["plots"][1]["axes"]["Left"]
        assert left["custom"] is True
        assert left["range"] == pytest.approx(list(pvrender.pad_range(-0.99412966, 1.0)),
                                              abs=1e-6)

    # blocks_chart_state: block id=0 (corner point) spans -0.858216 .. 0.994743, block id=1
    # (center) -0.994130 .. 1.0; the union would be -0.994130 .. 1.0.
    ID0 = (-0.8582162261009216, 0.9947432279586792)

    def test_plot_hidden_block_series_excluded(self, outdir, fixtures):
        # plot 1 selects both blocks but shows only the id=0 series; plot 2 selects only
        # block id=0, so its visible '(id=1)' series draws nothing.
        r, rep = _inspect("--plot-data-range-all", "1", "y", "--plot-data-range-all", "2", "y",
                          "--plot-data-range-all", "1", "x", "--size", "320",
                          outname=os.path.join(outdir, "o"),
                          state=os.path.join(fixtures, "blocks_chart_state.pvsm"))
        assert r.returncode == 0, r.stderr
        assert "warning" not in r.stderr, r.stderr
        expected = list(pvrender.pad_range(*self.ID0))
        for plot in rep["plots"]:
            assert plot["axes"]["Left"]["custom"] is True
            assert plot["axes"]["Left"]["range"] == pytest.approx(expected, abs=1e-6)
        assert rep["plots"][0]["axes"]["Bottom"]["range"] == pytest.approx([-0.5, 10.5],
                                                                           abs=1e-6)

    def test_plot_no_visible_series_warns(self, outdir, fixtures):
        r, rep = _inspect("--plot-data-range-all", "1", "top", "--size", "320",
                          outname=os.path.join(outdir, "o"),
                          state=_right_axis_state(fixtures), datadir=None)
        assert r.returncode == 0, r.stderr
        assert "warning:" in r.stderr and "Top" in r.stderr
        assert rep["plots"][0]["axes"]["Top"]["custom"] is False


@pytestmark_pvbatch
@pytest.mark.integration
class TestChartsDrawSavedSeries:
    """Charts draw the series the saved state shows (n_plotted counts the series the VTK
    chart actually plots)."""

    def test_quartile_chart_draws_saved_series(self, outdir):
        # Plot Data Over Time: 'z-Displacement [m] (id=0)' is visible in the state, but the
        # saved block selection (/Root/id0), restored by ParaView once the data is read,
        # never reached the VTK chart before the image was rendered: an empty chart.
        r, rep = _inspect("--si", "--time", "1", "--size", "320",
                          outname=os.path.join(outdir, "o"))
        assert r.returncode == 0, r.stderr
        assert rep["plots"][1]["type"] == "QuartileChartView"
        assert rep["plots"][1]["n_plotted"] >= 1

    def test_line_chart_draws_saved_series(self, outdir):
        r, rep = _inspect("--si", "--time", "1", "--size", "320",
                          outname=os.path.join(outdir, "o"))
        assert r.returncode == 0, r.stderr
        assert rep["plots"][0]["type"] == "XYChartView"
        assert rep["plots"][0]["n_plotted"] >= 1
