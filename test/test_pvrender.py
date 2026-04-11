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

import ast
import os
import subprocess
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


# ----------------------------------------------------------------
# Inline copies of pure functions from pvrender.py
# (cannot import pvrender.py directly — it calls paraview at import time)
# ----------------------------------------------------------------

def estimate_mp4_bitrate(width, height, framerate=30, motion_factor=0.1,
        min_bitrate=200e3, max_bitrate=50e6):
    if width <= 0 or height <= 0 or framerate <= 0:
        raise ValueError("width, height and framerate must be positive")
    elif motion_factor <= 0:
        raise ValueError("motion_factor must be positive")
    pixels = width * height
    bitrate = pixels * framerate * motion_factor
    bitrate = max(bitrate, min_bitrate)
    bitrate = min(bitrate, max_bitrate)
    bitrate = int(round(bitrate / 1e6, 1) * 1e6)
    return bitrate


def parse_filenames(filenames_str):
    try:
        filenames_dict = ast.literal_eval(filenames_str)
    except Exception as e:
        raise ValueError("Failed to parse --filenames argument: " + str(e))
    if not isinstance(filenames_dict, dict):
        raise ValueError("--filenames argument must be a dictionary")
    filenames = []
    for name, filepath in filenames_dict.items():
        filenames.append({"name": name, "FileName": abspath(filepath)})
    return filenames


_PALETTE_ALIASES = {
    "white":    "WhiteBackground",
    "black":    "BlackBackground",
    "gray":     "WarmGrayBackground",
    "grey":     "WarmGrayBackground",
    "gradient": "GradientBackground",
}


# ----------------------------------------------------------------
# Integration test helpers
# ----------------------------------------------------------------

def _pvbatch_available():
    try:
        return subprocess.run(
            ["pvbatch", "--version"], capture_output=True
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
    return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)


@pytest.fixture()
def outdir(request):
    """Create and return a per-test output directory under test/output/."""
    d = os.path.join(OUTDIR, request.node.name)
    os.makedirs(d, exist_ok=True)
    return d


# ----------------------------------------------------------------
# Unit tests — estimate_mp4_bitrate
# ----------------------------------------------------------------

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
        filenames_arg = "{{'radial_wave.pvd': '{}'}}".format(pvd_path)
        cmd = [
            "pvbatch", SCRIPT, STATE,
            "--filenames", filenames_arg,
            "--si", "--time", "1", "--size", str(TEST_WIDTH),
            "-o", out,
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT)
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


# ----------------------------------------------------------------
# Unit tests — apply_sym
# ----------------------------------------------------------------

def apply_sym(lo, hi):
    A = max(abs(lo), abs(hi))
    return -A, A


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
