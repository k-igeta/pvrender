"""
Generate test fixtures for test_pvrender.py.

Run under pvbatch:

    pvbatch test/make_fixtures.py OUT_DIR

OUT_DIR is deleted and recreated. Everything is generated with paraview.simple
(no hand-edited XML):

  data_adaptive/       radial_wave.pvd + radial_wave/*.vtp with non-uniform time
                       steps 10*(i/20)**2, i = 0..20, plus probe_points.csv
  data_partial/        same .pvd/.vtp as data_adaptive, no CSV
  data_missing_step/   like data_adaptive, without radial_wave_0_7.vtp
  data_big/            the repo radial wave scaled x3 (Transform), same time steps
                       0..10 step 0.5, plus probe_points.csv (unscaled copy)
  data_small/          the same, scaled x0.3
  interp_state.pvsm    PVD -> TemporalInterpolator (interval 0), colored by
                       z-Displacement [m] with a scalar bar; CSV (repo
                       test/data) -> TableToPoints; PVD reader suppressed in
                       the time keeper
  interp_state_unsuppressed.pvsm   same pipeline, without the suppression
  static_state.pvsm    XMLPolyDataReader(test/data/radial_wave/radial_wave_0_5.vtp)
                       in one render view, colored by z-Displacement [m];
                       no time steps; layout 600 x 900
  scaled_rep_state.pvsm  like static_state.pvsm, with the representation's
                       Scale = [2, 1, 1]
  sequence_state.pvsm  like static_state.pvsm (static data, no time steps), with the
                       animation scene in PlayMode 'Sequence', StartTime 0, EndTime 1,
                       NumberOfFrames 10
  chart_state.pvsm     one line chart: PVD (test/data) -> PlotOverLine with a visible
                       series; CSV (test/data) -> TableToPoints shown (Visibility 1)
                       but with no series selected
  right_axis_state.pvsm  one line chart: XMLPolyDataReader (the static_state data) ->
                       PlotOverLine along the diagonal (-0.5,-0.5,0)..(0.5,0.5,0), two
                       visible series: z-Displacement [m] on corner 0 (left axis) and
                       arc_length (0 .. sqrt 2) on corner 1 (right axis)
  stats_chart_state.pvsm  one quartile chart: PVD (test/data) -> PlotDataOverTime with
                       no selection (statistics block only), series z-Displacement [m]
  blocks_chart_state.pvsm  two quartile charts of PVD -> PlotOverLine (2 points) ->
                       PlotDataOverTime per point (blocks id=0, id=1): plot 1 selects both
                       blocks but shows only id=0; plot 2 selects only id=0
"""

import os
import shutil
import sys

from paraview.simple import *

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
SRC_PVD = os.path.join(DATA, "radial_wave.pvd")
SRC_CSV = os.path.join(DATA, "probe_points.csv")
ARRAY = "z-Displacement [m]"

N_STEPS = 21
ADAPTIVE_TIMES = [10 * (i / 20) ** 2 for i in range(N_STEPS)]
SOURCE_TIMES = [0.5 * i for i in range(N_STEPS)]

# ProgrammableFilter scripts that relabel the 21 source steps (0, 0.5, ..., 10)
# with the non-uniform ADAPTIVE_TIMES; step i stays step i.
_INFO_SCRIPT = f"""
from vtkmodules.vtkCommonExecutionModel import vtkStreamingDemandDrivenPipeline as sddp
times = {ADAPTIVE_TIMES!r}
info = self.GetOutputInformation(0)
info.Set(sddp.TIME_STEPS(), times, len(times))
info.Set(sddp.TIME_RANGE(), [times[0], times[-1]], 2)
"""

_UPDATE_SCRIPT = f"""
from vtkmodules.vtkCommonExecutionModel import vtkStreamingDemandDrivenPipeline as sddp
times = {ADAPTIVE_TIMES!r}
src_times = {SOURCE_TIMES!r}
out_info = self.GetOutputInformation(0)
t = out_info.Get(sddp.UPDATE_TIME_STEP()) if out_info.Has(sddp.UPDATE_TIME_STEP()) else times[-1]
i = 0
for k in range(len(times)):  # nearest step (builtin min is shadowed here)
    if abs(times[k] - t) < abs(times[i] - t):
        i = k
self.GetInputInformation(0, 0).Set(sddp.UPDATE_TIME_STEP(), src_times[i])
"""

_COPY_SCRIPT = """
self.GetOutput().ShallowCopy(self.GetInput())
"""


def make_adaptive_data(out_dir):
    """Write data_adaptive/: the radial wave relabelled with non-uniform time steps."""
    d = os.path.join(out_dir, "data_adaptive")
    os.makedirs(d)
    reader = PVDReader(FileName=SRC_PVD)
    relabel = ProgrammableFilter(Input=reader)
    relabel.OutputDataSetType = "Same as Input"
    relabel.Script = _COPY_SCRIPT
    relabel.RequestInformationScript = _INFO_SCRIPT
    relabel.RequestUpdateExtentScript = _UPDATE_SCRIPT
    SaveData(os.path.join(d, "radial_wave.pvd"), proxy=relabel, WriteTimeSteps=1)
    shutil.copy(SRC_CSV, d)
    Delete(relabel)
    Delete(reader)

    # A failing ProgrammableFilter script only logs; pvbatch would still exit 0.
    check = PVDReader(FileName=os.path.join(d, "radial_wave.pvd"))
    times = list(check.TimestepValues)
    Delete(check)
    # (no any()/abs(): the paraview.simple star import shadows them with VTK numpy versions)
    ok = len(times) == N_STEPS
    for a, b in zip(times, ADAPTIVE_TIMES):
        if not -1e-9 < a - b < 1e-9:
            ok = False
    if not ok:
        raise SystemExit(f"make_fixtures: unexpected time steps in data_adaptive: {times}")
    return d


def make_scaled_data(out_dir, name, factor):
    """Write <name>/: the repo radial wave scaled by factor, same time steps."""
    d = os.path.join(out_dir, name)
    os.makedirs(d)
    reader = PVDReader(FileName=SRC_PVD)
    scaled = Transform(Input=reader)
    scaled.Transform = "Transform"
    scaled.Transform.Scale = [factor, factor, factor]
    SaveData(os.path.join(d, "radial_wave.pvd"), proxy=scaled, WriteTimeSteps=1)
    shutil.copy(SRC_CSV, d)
    Delete(scaled)
    Delete(reader)

    check = PVDReader(FileName=os.path.join(d, "radial_wave.pvd"))
    times = list(check.TimestepValues)
    check.UpdatePipeline(times[-1])
    xmax = check.GetDataInformation().GetBounds()[1]
    Delete(check)
    ok = len(times) == N_STEPS and -1e-6 < xmax - 0.5 * factor < 1e-6
    for a, b in zip(times, SOURCE_TIMES):
        if not -1e-9 < a - b < 1e-9:
            ok = False
    if not ok:
        raise SystemExit(f"make_fixtures: unexpected {name}: times {times}, x max {xmax}")


def make_data_variants(out_dir, adaptive):
    partial = os.path.join(out_dir, "data_partial")
    shutil.copytree(adaptive, partial)
    os.remove(os.path.join(partial, "probe_points.csv"))

    missing = os.path.join(out_dir, "data_missing_step")
    shutil.copytree(adaptive, missing)
    os.remove(os.path.join(missing, "radial_wave", "radial_wave_0_7.vtp"))


def new_render_layout(size):
    view = CreateRenderView()
    layout = CreateLayout("Layout #1")
    AssignViewToLayout(view=view, layout=layout, hint=0)
    layout.SetSize(*size)
    SetActiveView(view)
    return view, layout


def make_interp_states(out_dir, adaptive):
    view, _ = new_render_layout((800, 600))

    pvd = PVDReader(registrationName="radial_wave.pvd",
                    FileName=os.path.join(adaptive, "radial_wave.pvd"))
    interp = TemporalInterpolator(registrationName="TemporalInterpolator1", Input=pvd)
    interp.DiscreteTimeStepInterval = 0.0
    rep = Show(interp, view)
    ColorBy(rep, ("POINTS", ARRAY))
    rep.RescaleTransferFunctionToDataRange(True, False)
    rep.SetScalarBarVisibility(view, True)

    csv = CSVReader(registrationName="probe_points.csv", FileName=[SRC_CSV])
    points = TableToPoints(registrationName="TableToPoints1", Input=csv)
    points.XColumn = "x"
    points.YColumn = "y"
    points.ZColumn = "z"
    Show(points, view)

    view.ResetCamera(False)

    tk = GetTimeKeeper()
    tk.SuppressedTimeSources = [pvd]
    SaveState(os.path.join(out_dir, "interp_state.pvsm"))

    tk.SuppressedTimeSources = []
    SaveState(os.path.join(out_dir, "interp_state_unsuppressed.pvsm"))


def make_static_state(out_dir, name="static_state.pvsm", scale=None, sequence_frames=None):
    view, _ = new_render_layout((600, 900))
    reader = XMLPolyDataReader(
        registrationName="radial_wave_0_5.vtp",
        FileName=[os.path.join(DATA, "radial_wave", "radial_wave_0_5.vtp")])
    reader.TimeArray = "None"  # ignore the TimeValue field: no time steps at all
    rep = Show(reader, view)
    ColorBy(rep, ("POINTS", ARRAY))
    rep.RescaleTransferFunctionToDataRange(True, False)
    rep.SetScalarBarVisibility(view, True)
    if scale is not None:
        rep.Scale = scale
    view.ResetCamera(False)
    if sequence_frames is not None:
        scene = GetAnimationScene()
        scene.PlayMode = "Sequence"
        scene.StartTime = 0.0
        scene.EndTime = 1.0
        scene.NumberOfFrames = sequence_frames
    SaveState(os.path.join(out_dir, name))


def make_chart_state(out_dir):
    """One line chart: PVD -> PlotOverLine draws a series; CSV -> TableToPoints is shown
    (Visibility 1) but with no series selected, so it draws nothing."""
    view = CreateView("XYChartView")
    layout = CreateLayout("Layout #1")
    AssignViewToLayout(view=view, layout=layout, hint=0)
    layout.SetSize(800, 600)
    SetActiveView(view)

    pvd = PVDReader(registrationName="radial_wave.pvd", FileName=SRC_PVD)
    line = PlotOverLine(registrationName="PlotOverLine1", Input=pvd)
    line_rep = Show(line, view)
    line_rep.SeriesVisibility = [ARRAY]

    csv = CSVReader(registrationName="probe_points.csv", FileName=[SRC_CSV])
    points = TableToPoints(registrationName="TableToPoints1", Input=csv)
    points.XColumn = "x"
    points.YColumn = "y"
    points.ZColumn = "z"
    points_rep = Show(points, view)
    points_rep.SeriesVisibility = []
    SaveState(os.path.join(out_dir, "chart_state.pvsm"))


def make_right_axis_state(out_dir):
    """Line chart with one series on the left axis and one on the right axis."""
    view = CreateView("XYChartView")
    layout = CreateLayout("Layout #1")
    AssignViewToLayout(view=view, layout=layout, hint=0)
    layout.SetSize(800, 600)
    SetActiveView(view)

    reader = XMLPolyDataReader(
        registrationName="radial_wave_0_5.vtp",
        FileName=[os.path.join(DATA, "radial_wave", "radial_wave_0_5.vtp")])
    reader.TimeArray = "None"
    line = PlotOverLine(registrationName="PlotOverLine1", Input=reader)
    line.Point1 = [-0.5, -0.5, 0.0]
    line.Point2 = [0.5, 0.5, 0.0]
    rep = Show(line, view)
    rep.SeriesVisibility = [ARRAY, "arc_length"]
    rep.SeriesPlotCorner = ["arc_length", "1"]  # vtkChart corner 1 = bottom-right
    SaveState(os.path.join(out_dir, "right_axis_state.pvsm"))


def make_stats_chart_state(out_dir):
    """Plot Data Over Time without a selection: the output holds only the statistics
    block (row arrays min(...), max(...), avg(...), ...), and the series is the plain
    array name."""
    view = CreateView("QuartileChartView")
    layout = CreateLayout("Layout #1")
    AssignViewToLayout(view=view, layout=layout, hint=0)
    layout.SetSize(800, 600)
    SetActiveView(view)

    pvd = PVDReader(registrationName="radial_wave.pvd", FileName=SRC_PVD)
    over_time = PlotDataOverTime(registrationName="PlotDataOverTime1", Input=pvd)
    rep = Show(over_time, view)
    rep.SeriesVisibility = [ARRAY]
    SaveState(os.path.join(out_dir, "stats_chart_state.pvsm"))


def make_blocks_chart_state(out_dir):
    """Two quartile charts of Plot Data Over Time per point (no statistics): the input is
    a 2-point PlotOverLine, so the output has blocks id=0 (corner point) and id=1 (center)
    with different ranges.
      plot 1: both blocks selected, only the id=0 series visible (plus a stale
              '(stats)' series, as GUI states keep after turning statistics off)
      plot 2: only block id=0 selected, series of id=0 and id=1 visible"""
    layout = CreateLayout("Layout #1")
    layout.SplitHorizontal(0, 0.5)
    layout.SetSize(800, 400)

    pvd = PVDReader(registrationName="radial_wave.pvd", FileName=SRC_PVD)
    two = PlotOverLine(registrationName="TwoPoints", Input=pvd)
    two.Point1 = [-0.5, -0.5, 0.0]
    two.Point2 = [0.0, 0.0, 0.0]
    two.Resolution = 1
    over_time = PlotDataOverTime(registrationName="PlotDataOverTime1", Input=two)
    over_time.OnlyReportSelectionStatistics = 0

    for hint, selectors, visible in (
            (1, ["/Root/id0", "/Root/id1"], [f"{ARRAY} (id=0)", f"{ARRAY} (stats)"]),
            (2, ["/Root/id0"], [f"{ARRAY} (id=0)", f"{ARRAY} (id=1)"])):
        view = CreateView("QuartileChartView")
        AssignViewToLayout(view=view, layout=layout, hint=hint)
        rep = Show(over_time, view)
        rep.BlockSelectors = selectors
        rep.SeriesVisibility = visible
    SaveState(os.path.join(out_dir, "blocks_chart_state.pvsm"))


def main():
    out_dir = os.path.abspath(sys.argv[1])
    if os.path.exists(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir)

    adaptive = make_adaptive_data(out_dir)
    make_data_variants(out_dir, adaptive)
    make_scaled_data(out_dir, "data_big", 3.0)
    make_scaled_data(out_dir, "data_small", 0.3)

    make_interp_states(out_dir, adaptive)
    ResetSession()
    make_static_state(out_dir)
    ResetSession()
    make_static_state(out_dir, "scaled_rep_state.pvsm", scale=[2, 1, 1])
    ResetSession()
    make_static_state(out_dir, "sequence_state.pvsm", sequence_frames=10)
    ResetSession()
    make_chart_state(out_dir)
    ResetSession()
    make_right_axis_state(out_dir)
    ResetSession()
    make_stats_chart_state(out_dir)
    ResetSession()
    make_blocks_chart_state(out_dir)


main()
