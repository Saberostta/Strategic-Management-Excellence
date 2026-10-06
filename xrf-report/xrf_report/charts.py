"""Plotly figures. Each function returns an HTML <div> fragment (plotly.js loaded once by the page)."""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from .analysis import Analysis, for_element

# validated categorical order (identity) + reserved status colours (state)
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
STATUS = {"Green": "#0ca30c", "Amber": "#fab219", "Red": "#d03b3b"}
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#8a8984", "#e6e5e0", "#fcfcfb"
BAND_WARN, BAND_ACT = "rgba(42,120,214,0.08)", "rgba(208,59,59,0.06)"
FONT = "Inter, 'Segoe UI', system-ui, -apple-system, sans-serif"
CONFIG = {"displaylogo": False, "responsive": True,
          "modeBarButtonsToRemove": ["lasso2d", "select2d", "autoScale2d"],
          "toImageButtonOptions": {"format": "png", "scale": 2}}


def _layout(fig: go.Figure, height=380, **kw):
    fig.update_layout(
        height=height, font=dict(family=FONT, size=12, color=INK2),
        paper_bgcolor=SURFACE, plot_bgcolor=SURFACE, margin=dict(l=56, r=20, t=30, b=44),
        hoverlabel=dict(bgcolor="white", bordercolor=GRID, font=dict(family=FONT, color=INK)),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, x=0, title=None),
        **kw)
    fig.update_xaxes(showgrid=False, linecolor=GRID, ticks="outside", tickcolor=GRID, zeroline=False)
    fig.update_yaxes(gridcolor=GRID, linecolor=GRID, zeroline=False)
    return fig


def _html(fig, div_id):
    return fig.to_html(full_html=False, include_plotlyjs=False, config=CONFIG, div_id=div_id)


def inst_colors(instruments):
    return {inst: SERIES[i % 3] if len(instruments) <= 3 else SERIES[i % len(SERIES)]
            for i, inst in enumerate(sorted(instruments))}


# ---------------------------------------------------------------- 1. status matrix
def status_matrix(a: Analysis) -> str:
    g = a.groups
    els = sorted(g.element.unique())
    insts = sorted(g.instrument.unique())
    code = {"Green": 0, "Amber": 1, "Red": 2}
    z = np.full((len(insts), len(els)), np.nan)
    text = [["" for _ in els] for _ in insts]
    hover = [["no data" for _ in els] for _ in insts]
    for _, r in g.iterrows():
        i, j = insts.index(r.instrument), els.index(r.element)
        z[i, j] = code[r.status]
        icon = {"Green": "✓", "Amber": "!", "Red": "✕"}[r.status]
        text[i][j] = f"{icon} {r.mean_recovery:.1f}%"
        hover[i][j] = (f"<b>{r.element} · {r.instrument}</b><br>Status: {r.status}<br>"
                       f"Mean recovery: {r.mean_recovery:.2f}%<br>SD: {r.sd:.2f}%<br>n = {r.n}<br>"
                       + ("<br>".join(r.reasons) if r.reasons else "All checks passed"))
    scale = [[0, STATUS["Green"]], [0.333, STATUS["Green"]], [0.334, STATUS["Amber"]],
             [0.666, STATUS["Amber"]], [0.667, STATUS["Red"]], [1, STATUS["Red"]]]
    fig = go.Figure(go.Heatmap(
        z=z, x=els, y=insts, zmin=0, zmax=2, colorscale=scale, showscale=False, xgap=3, ygap=3,
        text=text, texttemplate="%{text}", textfont=dict(color=INK, size=12),
        customdata=hover, hovertemplate="%{customdata}<extra></extra>"))
    _layout(fig, height=max(170, 70 * len(insts) + 80))
    fig.update_yaxes(showgrid=False, autorange="reversed")
    fig.update_xaxes(side="top")
    fig.update_layout(margin=dict(l=90, r=20, t=40, b=20))
    return _html(fig, "fig-status")


# ---------------------------------------------------------------- 2. weekly trends (small multiples)
def weekly_trends(a: Analysis) -> str:
    th, w = a.th, a.weekly
    w = w[w["week"] > a.week - pd.Timedelta(weeks=26)]
    els = sorted(a.groups.element.unique())
    cols = min(3, len(els))
    rows = math.ceil(len(els) / cols)
    fig = make_subplots(rows=rows, cols=cols, subplot_titles=els, shared_xaxes=True,
                        vertical_spacing=0.12 / max(rows - 1, 1) * 1.5 if rows > 1 else 0.1,
                        horizontal_spacing=0.06)
    colors = inst_colors(a.df.instrument.unique())
    shown = set()
    allv = w["mean"]
    act = max(for_element(th, el).recovery_action for el in els)
    lo = min(100 - act - 2, allv.min() - 1)
    hi = max(100 + act + 2, allv.max() + 1)
    for k, el in enumerate(els):
        r, c = k // cols + 1, k % cols + 1
        te = for_element(th, el)
        fig.add_hrect(y0=100 - te.recovery_warn, y1=100 + te.recovery_warn, fillcolor=BAND_WARN,
                      line_width=0, row=r, col=c)
        for y in (100 - te.recovery_action, 100 + te.recovery_action):
            fig.add_hline(y=y, line=dict(color=STATUS["Red"], width=1, dash="dot"), row=r, col=c)
        fig.add_hline(y=100, line=dict(color=MUTED, width=1), row=r, col=c)
        for inst, gg in w[w.element == el].groupby("instrument"):
            gg = gg.sort_values("week")
            fig.add_trace(go.Scatter(
                x=gg["week"], y=gg["mean"], mode="lines+markers", name=inst, legendgroup=inst,
                showlegend=inst not in shown, line=dict(color=colors[inst], width=2),
                marker=dict(size=7, line=dict(color=SURFACE, width=1.5)),
                customdata=np.c_[gg["sd"].fillna(0), gg["n"]],
                hovertemplate=f"<b>{el} · {inst}</b><br>Week of %{{x|%d %b %Y}}<br>"
                              "Mean recovery %{y:.2f}%<br>SD %{customdata[0]:.2f}% · n=%{customdata[1]}<extra></extra>"),
                row=r, col=c)
            shown.add(inst)
        fig.add_vline(x=a.week, line=dict(color=INK2, width=1, dash="dash"), row=r, col=c)
    _layout(fig, height=230 * rows + 80, hovermode="closest")
    fig.update_layout(margin=dict(l=56, r=20, t=70, b=44), legend=dict(y=0.995, yanchor="top", yref="container"))
    fig.update_yaxes(range=[lo, hi], ticksuffix="%")
    fig.update_annotations(font=dict(size=13, color=INK))
    return _html(fig, "fig-trends")


# ---------------------------------------------------------------- 3. Levey-Jennings per group
def levey_jennings(a: Analysis) -> list[dict]:
    out = []
    start = a.week - pd.Timedelta(weeks=a.th.trend_weeks)
    for k, r in a.groups.sort_values(["element", "instrument"]).reset_index(drop=True).iterrows():
        d = a.df[(a.df.instrument == r.instrument) & (a.df.element == r.element) & (a.df.week > start)].sort_values("date")
        fig = go.Figure()
        for s, col in ((3, BAND_ACT), (2, BAND_WARN)):
            fig.add_hrect(y0=-s, y1=s, fillcolor=col, line_width=0)
        for s, dash, color in ((1, "dot", MUTED), (2, "dash", "#eda100"), (3, "solid", STATUS["Red"])):
            for sign in (1, -1):
                fig.add_hline(y=s * sign, line=dict(color=color, width=1, dash=dash),
                              annotation_text=f"{'+' if sign > 0 else '−'}{s}SD", annotation_position="right",
                              annotation_font=dict(size=10, color=MUTED))
        fig.add_hline(y=0, line=dict(color=INK2, width=1))
        cur = d.week == a.week
        viol = d["rules"].map(len) > 0
        hov = ("<b>%{customdata[0]}</b> · %{x|%d %b %H:%M}<br>Measured %{customdata[1]:.4g} / certified %{customdata[2]:.4g}"
               "<br>Recovery %{customdata[3]:.2f}% · z = %{y:.2f}<br>Operator %{customdata[4]}<br>%{customdata[5]}<extra></extra>")
        cd = np.c_[d["standard"], d["measured"], d["certified"], d["recovery"], d["operator"],
                   d["rules"].map(lambda x: "Rule: " + ", ".join(x) if x else "")]
        fig.add_trace(go.Scatter(x=d["date"], y=d["z"], mode="lines", line=dict(color=GRID, width=1.5),
                                 hoverinfo="skip", showlegend=False))
        for mask, name, color, size in ((~cur & ~viol, "Previous weeks", "#9cc0ec", 7),
                                        (cur & ~viol, "Report week", SERIES[0], 9),
                                        (viol, "Rule violation", STATUS["Red"], 11)):
            if mask.any():
                fig.add_trace(go.Scatter(
                    x=d["date"][mask], y=d["z"][mask], mode="markers", name=name, customdata=cd[mask.to_numpy()],
                    marker=dict(color=color, size=size, symbol="x" if name == "Rule violation" else "circle",
                                line=dict(color=SURFACE, width=1.5)), hovertemplate=hov))
        wk_start = a.week
        fig.add_vrect(x0=wk_start, x1=wk_start + pd.Timedelta(days=7), fillcolor="rgba(11,11,11,0.035)", line_width=0,
                      annotation_text="report week", annotation_position="top left",
                      annotation_font=dict(size=10, color=MUTED))
        m = float(np.nanmax(np.abs(d["z"]))) if len(d) else 3
        _layout(fig, height=360)
        fig.update_yaxes(range=[-max(3.6, m + 0.4), max(3.6, m + 0.4)], title_text="z-score (SD from baseline mean)")
        fig.update_layout(margin=dict(l=60, r=50, t=30, b=40))
        out.append(dict(key=f"lj-{k}", label=f"{r.element} · {r.instrument}", status=r.status,
                        mean=r.base_mean, sd=r.base_sd, source=r.limits_source,
                        html=_html(fig, f"fig-lj-{k}")))
    return out


# ---------------------------------------------------------------- 4. bias & precision
def bias_precision(a: Analysis) -> str:
    th = a.th
    g = a.groups.sort_values(["element", "instrument"]).reset_index(drop=True)
    labels = g.element + " · " + g.instrument
    fig = make_subplots(rows=1, cols=2, shared_yaxes=True, horizontal_spacing=0.04,
                        subplot_titles=("Accuracy — mean bias vs certified (%)", "Precision — SD of recovery (%)"))
    fig.add_vrect(x0=-th.recovery_warn, x1=th.recovery_warn, fillcolor=BAND_WARN, line_width=0, row=1, col=1)
    for x in (-th.recovery_action, th.recovery_action):
        fig.add_vline(x=x, line=dict(color=STATUS["Red"], width=1, dash="dot"), row=1, col=1)
    fig.add_vline(x=0, line=dict(color=INK2, width=1), row=1, col=1)
    fig.add_trace(go.Bar(
        y=labels, x=g.bias, orientation="h", marker=dict(color=SERIES[0], cornerradius=4),
        error_x=dict(type="data", array=g.sd.fillna(0), color=MUTED, thickness=1, width=3),
        customdata=np.c_[g.status, g.n, g.worst_bias],
        hovertemplate="<b>%{y}</b><br>Bias %{x:+.2f}% (±1 SD bar)<br>Worst single result %{customdata[2]:+.2f}%"
                      "<br>n=%{customdata[1]} · %{customdata[0]}<extra></extra>", showlegend=False), row=1, col=1)
    fig.add_trace(go.Bar(
        y=labels, x=g.sd, orientation="h",
        marker=dict(color=[SERIES[1] if v > lim else "#9cc0ec" for v, lim in zip(g.sd.fillna(0), g.precision_limit)],
                    cornerradius=4),
        customdata=g.precision_limit,
        hovertemplate="<b>%{y}</b><br>SD %{x:.2f}% (limit %{customdata:g}%)<extra></extra>", showlegend=False), row=1, col=2)
    fig.add_trace(go.Scatter(y=labels, x=g.precision_limit, mode="markers", name="limit",
                             marker=dict(symbol="line-ns", size=16, line=dict(width=2, color=STATUS["Red"])),
                             hovertemplate="<b>%{y}</b><br>limit %{x:g}%<extra></extra>", showlegend=False), row=1, col=2)
    _layout(fig, height=max(320, 26 * len(g) + 110), bargap=0.35)
    fig.update_yaxes(autorange="reversed", gridcolor="rgba(0,0,0,0)")
    fig.update_xaxes(showgrid=True, gridcolor=GRID, ticksuffix="%")
    fig.update_annotations(font=dict(size=13, color=INK))
    fig.update_layout(margin=dict(l=130, r=20, t=40, b=40))
    return _html(fig, "fig-biasprec")


# ---------------------------------------------------------------- 5. recovery vs concentration
def recovery_vs_level(a: Analysis) -> str:
    """Recovery against certified concentration: exposes level-dependent bias (e.g. poor trace-level accuracy)."""
    c = a.cur
    colors = inst_colors(a.df.instrument.unique())
    fig = go.Figure()
    fig.add_hrect(y0=100 - a.th.recovery_warn, y1=100 + a.th.recovery_warn, fillcolor=BAND_WARN, line_width=0)
    fig.add_hline(y=100, line=dict(color=MUTED, width=1))
    for inst, d in c.groupby("instrument"):
        fig.add_trace(go.Scatter(
            x=d.certified, y=d.recovery, mode="markers", name=inst,
            marker=dict(color=colors[inst], size=9, opacity=0.85, line=dict(color=SURFACE, width=1.5)),
            customdata=np.c_[d.element, d.standard, d.measured],
            hovertemplate="<b>%{customdata[0]}</b> · %{customdata[1]}<br>Certified %{x:.4g} · measured %{customdata[2]:.4g}"
                          "<br>Recovery %{y:.2f}%<extra>" + inst + "</extra>"))
    # label each element once at its median position
    for el, d in c.groupby("element"):
        fig.add_annotation(x=np.log10(d.certified.median()), y=d.recovery.max(), text=el, showarrow=False,
                           yshift=12, font=dict(size=10, color=INK2))
    _layout(fig, height=420)
    fig.update_xaxes(type="log", title_text="Certified concentration (log scale)", showgrid=True, gridcolor=GRID)
    fig.update_yaxes(title_text="Recovery", ticksuffix="%")
    return _html(fig, "fig-scatter")


# ---------------------------------------------------------------- 6. recovery distribution
def recovery_distribution(a: Analysis) -> str:
    start = a.week - pd.Timedelta(weeks=4)
    d = a.df[a.df.week > start]
    fig = go.Figure()
    for name, mask, color in (("Previous 3 weeks", d.week < a.week, "#9cc0ec"), ("Report week", d.week == a.week, SERIES[0])):
        dd = d[mask]
        fig.add_trace(go.Box(x=dd.element, y=dd.recovery, name=name, marker=dict(color=color, size=4),
                             line=dict(width=1.5), boxpoints="outliers",
                             hovertemplate="%{x}<br>Recovery %{y:.2f}%<extra>" + name + "</extra>"))
    fig.add_hrect(y0=100 - a.th.recovery_warn, y1=100 + a.th.recovery_warn, fillcolor=BAND_WARN, line_width=0)
    fig.add_hline(y=100, line=dict(color=MUTED, width=1))
    _layout(fig, height=380, boxmode="group", boxgap=0.3, boxgroupgap=0.15)
    fig.update_xaxes(categoryorder="array", categoryarray=sorted(d.element.unique()))
    fig.update_yaxes(ticksuffix="%", title_text="Recovery")
    return _html(fig, "fig-dist")


# ---------------------------------------------------------------- 7. volume
def volume_chart(a: Analysis) -> str:
    v = a.df[a.df.week > a.week - pd.Timedelta(weeks=12)].groupby(["week", "instrument"]).size().reset_index(name="n")
    colors = inst_colors(a.df.instrument.unique())
    fig = go.Figure()
    for inst, d in v.groupby("instrument"):
        fig.add_trace(go.Bar(x=d.week, y=d.n, name=inst, marker=dict(color=colors[inst], cornerradius=3),
                             hovertemplate="Week of %{x|%d %b}<br>%{y} QC results<extra>" + inst + "</extra>"))
    _layout(fig, height=280, barmode="group", bargap=0.3, bargroupgap=0.08)
    fig.update_yaxes(title_text="QC results")
    return _html(fig, "fig-volume")
