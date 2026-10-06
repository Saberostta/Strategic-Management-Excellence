"""Assemble the HTML report and the companion Excel summary."""
from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import __version__, charts
from .analysis import RULE_TEXT, Analysis


def _fmt(v, spec=".1f", suffix="", signed=False):
    if v is None or (isinstance(v, float) and not np.isfinite(v)):
        return "–"
    return f"{v:{'+' if signed else ''}{spec}}{suffix}"


def _delta(cur, prev, lower_is_better=False, spec=".1f", suffix=""):
    if prev is None or not np.isfinite(prev) or not np.isfinite(cur):
        return dict(text="no prior week", cls="flat")
    d = cur - prev
    if abs(d) < 1e-9:
        return dict(text="unchanged vs last week", cls="flat")
    good = (d < 0) if lower_is_better else (d > 0)
    return dict(text=f"{'▲' if d > 0 else '▼'} {abs(d):{spec}}{suffix} vs last week", cls="up" if good else "down")


def build_html(a: Analysis, source_name: str, warnings: list[str], plotly_mode: str = "inline") -> str:
    from plotly.offline import get_plotlyjs, get_plotlyjs_version

    k = a.kpis
    env = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"),
                      autoescape=select_autoescape(["html", "j2"]))
    env.filters["f"] = _fmt
    iso = a.week.isocalendar()
    scorecard = []
    for _, r in a.groups.iterrows():
        scorecard.append(dict(
            instrument=r.instrument, element=r.element, n=r.n, status=r.status,
            recovery=_fmt(r.mean_recovery, ".2f", "%"), bias=_fmt(r.bias, ".2f", "%", True),
            sd=_fmt(r.sd, ".2f", "%"), in_spec=_fmt(r.in_spec, ".0f", "%"),
            delta=_fmt(r.delta_recovery, ".2f", "", True),
            trend=("—" if not np.isfinite(r.slope) else f"{r.slope:+.2f}/wk") + (" ⚠" if r.drift else ""),
            rules=", ".join(r.rules) or "—", reasons="; ".join(r.reasons) or "All checks passed"))
    events = [dict(date=e.date.strftime("%a %d %b %H:%M"), instrument=e.instrument, element=e.element,
                   standard=e.standard, operator=e.operator, measured=f"{e.measured:.4g}",
                   certified=f"{e.certified:.4g}", recovery=f"{e.recovery:.2f}%", z=f"{e.z:+.2f}", rules=e.rules)
              for e in a.events.itertuples()]
    tpl = env.get_template("report.html.j2")
    return tpl.render(
        title=f"XRF Analytical Performance — Week {iso.week}, {iso.year}",
        week_label=f"Week {iso.week} · {a.week:%d %b} – {(a.week + pd.Timedelta(days=6)):%d %b %Y}",
        generated=datetime.now().strftime("%d %b %Y %H:%M"), source=source_name, version=__version__,
        k=k, th=a.th,
        d_inspec=_delta(k["in_spec"], k["prev_in_spec"], spec=".1f", suffix=" pts"),
        d_bias=_delta(k["mean_abs_bias"], k["prev_mean_abs_bias"], lower_is_better=True, spec=".2f", suffix=" pts"),
        d_n=_delta(k["n_results"], k["n_prev"] or np.nan, spec=".0f"),
        insights=a.insights, scorecard=scorecard, events=events, rule_text=RULE_TEXT, warnings=warnings,
        fig_status=charts.status_matrix(a), fig_trends=charts.weekly_trends(a),
        lj=charts.levey_jennings(a), fig_biasprec=charts.bias_precision(a),
        fig_scatter=charts.recovery_vs_level(a), fig_dist=charts.recovery_distribution(a),
        fig_volume=charts.volume_chart(a),
        plotly_inline=get_plotlyjs() if plotly_mode == "inline" else None,
        plotly_version=get_plotlyjs_version(),
        n_weeks=a.df.week.nunique(), first_date=a.df.date.min(), last_date=a.df.date.max(),
    )


def build_excel(a: Analysis, path: Path) -> None:
    g = a.groups.copy()
    g["rules"] = g["rules"].map(", ".join)
    g["reasons"] = g["reasons"].map("; ".join)
    cols = ["status", "instrument", "element", "n", "mean_recovery", "bias", "sd", "in_spec", "worst_bias",
            "prev_recovery", "delta_recovery", "slope", "r2", "drift", "rules", "reasons",
            "base_mean", "base_sd", "limits_source"]
    insights = pd.DataFrame(a.insights)[["severity", "title", "text", "action"]]
    with pd.ExcelWriter(path, engine="xlsxwriter") as xw:
        wb = xw.book
        insights.to_excel(xw, sheet_name="Summary", index=False)
        g[cols].round(3).to_excel(xw, sheet_name="Scorecard", index=False)
        a.events.round({"recovery": 3, "z": 3}).to_excel(xw, sheet_name="Rule violations", index=False)
        tr = a.weekly.copy(); tr["week"] = tr["week"].dt.date
        tr.round(3).to_excel(xw, sheet_name="Weekly trend", index=False)
        cur = a.cur.drop(columns=["rules"]).assign(rules=a.cur["rules"].map(", ".join))
        cur.round({c: 4 for c in ("measured", "certified", "recovery", "bias_pct", "z")}).to_excel(xw, sheet_name="Report week data", index=False)
        fills = {s: wb.add_format({"bg_color": c, "font_color": "#0b0b0b"})
                 for s, c in (("Green", "#c8ecc8"), ("Amber", "#fde7b5"), ("Red", "#f5c4c4"))}
        hdr = wb.add_format({"bold": True, "bg_color": "#eef3fb", "border": 0})
        for name, df in (("Summary", insights), ("Scorecard", g[cols])):
            ws = xw.sheets[name]
            for j, c in enumerate(df.columns):
                ws.write(0, j, c, hdr)
                width = df[c].astype(str).str.len().quantile(0.9) if len(df) else 0
                ws.set_column(j, j, min(60, max(10, int(np.nan_to_num(width)) + 2)))
            ws.freeze_panes(1, 0)
            for s, f in fills.items():
                ws.conditional_format(1, 0, len(df), 0, {"type": "cell", "criteria": "==", "value": f'"{s}"', "format": f})
