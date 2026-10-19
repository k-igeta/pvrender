"""
Inspection harness for the integration tests.

Run under pvbatch:

    pvbatch test/pv_inspect.py REPORT_JSON STATE [pvrender args...]

Runs pvrender.main() with the given arguments, then writes a JSON report of
the resulting ParaView state (time, layout size, colorbars, plots, cameras,
temporal interpolators) to REPORT_JSON. The report is only written when
main() returns normally.
"""

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pvrender
from paraview.simple import (GetAnimationScene, GetLayouts, GetSources,
                             GetViewsInLayout)

_AXES = ("Bottom", "Left", "Right", "Top")


def _colorbar_report(views):
    out = []
    for cb in pvrender.enumerate_colorbars(views):
        lut = cb["lut"]
        pts = list(lut.RGBPoints)
        titles = []
        for view in views:
            for rep in view.Representations:
                if (rep.GetXMLName() == "ScalarBarWidgetRepresentation"
                        and rep.LookupTable == lut):
                    titles.append(rep.Title)
        out.append({"array": cb["array_name"],
                    "range": [pts[0], pts[-4]],
                    "titles": titles})
    return out


def _plot_report(views):
    enumerate_plots = getattr(pvrender, "enumerate_plots", None)
    if enumerate_plots is None:
        return []
    out = []
    for plot in enumerate_plots(views):
        view = plot["view"] if isinstance(plot, dict) else plot
        axes = {}
        for ax in _AXES:
            axes[ax] = {
                "custom": bool(getattr(view, ax + "AxisUseCustomRange", False)),
                "range": [getattr(view, ax + "AxisRangeMinimum", 0.0),
                          getattr(view, ax + "AxisRangeMaximum", 0.0)],
                "log": bool(getattr(view, ax + "AxisLogScale", False)),
                "title": getattr(view, ax + "AxisTitle", ""),
            }
        out.append({"type": view.GetXMLName(),
                    "title": getattr(view, "ChartTitle", ""),
                    "axes": axes,
                    "n_plotted": _n_plotted(view)})
    return out


def _n_plotted(view):
    """Number of series the chart drew in its last render (the saved image): visible
    plots of the view's VTK chart with input data, not counting the time marker
    (vtkPVPlotTime). The view is deliberately not rendered again: SaveScreenshot pushes
    pending representation properties to VTK on its way out, so a fresh render could
    draw what the saved image did not. A view never rendered reports 0."""
    chart = view.GetContextItem()
    n = 0
    for i in range(chart.GetNumberOfPlots()):
        plot = chart.GetPlot(i)
        if plot.GetClassName() == "vtkPVPlotTime" or not plot.GetVisible():
            continue
        table = plot.GetInput()
        if table is not None and table.GetNumberOfRows() > 0:
            n += 1
    return n


def _visible_sources(view):
    """Sorted registration names of sources with a visible representation in view (read
    from view.Representations, so nothing is created)."""
    from paraview import servermanager
    by_id = {src.GetGlobalIDAsString(): key[0] for key, src in GetSources().items()}
    names = set()
    for rep in view.Representations:
        props = rep.ListProperties()
        if 'Input' not in props or 'Visibility' not in props or not rep.Visibility:
            continue
        src = servermanager._getPyProxy(rep.SMProxy.GetProperty('Input').GetProxy(0))
        if src is not None and src.GetGlobalIDAsString() in by_id:
            names.add(by_id[src.GetGlobalIDAsString()])
    return sorted(names)


def _camera_report(views):
    out = []
    for view in views:
        if not view.IsA("vtkSMRenderViewProxy"):
            continue
        out.append({
            "position": list(view.CameraPosition),
            "focal_point": list(view.CameraFocalPoint),
            "view_up": list(view.CameraViewUp),
            "view_angle": float(view.CameraViewAngle),
            "parallel": bool(view.CameraParallelProjection),
            "parallel_scale": float(view.CameraParallelScale),
            "visible_sources": _visible_sources(view),
        })
    return out


def main():
    report_path, pv_args = sys.argv[1], sys.argv[2:]
    pvrender.main(pv_args)

    scene = GetAnimationScene()
    layouts = list(GetLayouts().values())
    layout = layouts[0]
    views = list(GetViewsInLayout(layout))

    interpolators = [float(src.DiscreteTimeStepInterval)
                     for src in GetSources().values()
                     if src.GetXMLName() == "TemporalInterpolator"]

    report = {
        "time": float(scene.TimeKeeper.Time),
        "timesteps": [float(t) for t in scene.TimeKeeper.TimestepValues],
        "layout_size": list(layout.GetSize()),
        "colorbars": _colorbar_report(views),
        "plots": _plot_report(views),
        "cameras": _camera_report(views),
        "interpolators": interpolators,
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


main()
