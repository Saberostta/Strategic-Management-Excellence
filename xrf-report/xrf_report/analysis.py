"""Statistical analysis: weekly KPIs, control-chart rules, drift, insights."""
from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from .config import Thresholds

SEVERITY_ORDER = {"Red": 0, "Amber": 1, "Green": 2}


@dataclass
class Analysis:
    df: pd.DataFrame                 # all data with z-scores & flags
    week: pd.Timestamp
    prev_week: pd.Timestamp | None
    cur: pd.DataFrame                # report-week rows
    groups: pd.DataFrame             # per instrument x element scorecard
    weekly: pd.DataFrame             # per week x group trend
    events: pd.DataFrame             # rule violations in report week
    insights: list[dict] = field(default_factory=list)
    kpis: dict = field(default_factory=dict)
    th: Thresholds = field(default_factory=Thresholds)


# ---------------------------------------------------------------- control rules
def westgard_flags(z: np.ndarray) -> list[list[str]]:
    """Return, per point, the Westgard rules violated at that point (sequence order)."""
    out: list[list[str]] = [[] for _ in z]
    for i, v in enumerate(z):
        if abs(v) > 3:
            out[i].append("1-3s")
        if i >= 1 and ((z[i] > 2 and z[i - 1] > 2) or (z[i] < -2 and z[i - 1] < -2)):
            out[i].append("2-2s")
        if i >= 1 and ((z[i] > 2 and z[i - 1] < -2) or (z[i] < -2 and z[i - 1] > 2)):
            out[i].append("R-4s")
        if i >= 3 and (all(z[i - 3:i + 1] > 1) or all(z[i - 3:i + 1] < -1)):
            out[i].append("4-1s")
        if i >= 9 and (all(z[i - 9:i + 1] > 0) or all(z[i - 9:i + 1] < 0)):
            out[i].append("10-x")
    return out


RULE_TEXT = {
    "1-3s": "single result beyond ±3 SD (random error or gross failure)",
    "2-2s": "two consecutive results beyond 2 SD on the same side (systematic shift)",
    "R-4s": "consecutive results beyond 2 SD on opposite sides (imprecision)",
    "4-1s": "four consecutive results beyond 1 SD on the same side (early bias)",
    "10-x": "ten consecutive results on the same side of the mean (persistent bias)",
}
SERIOUS_RULES = {"1-3s", "2-2s", "R-4s"}


def for_element(th: Thresholds, element: str) -> Thresholds:
    """Global thresholds with any per-element overrides applied."""
    ov = th.per_element.get(element) or th.per_element.get(element.lower()) or {}
    return replace(th, **{k: v for k, v in ov.items() if v is not None and np.isfinite(v)}) if ov else th


def _slope_per_week(g: pd.DataFrame):
    if len(g) < 3 or g["date"].nunique() < 3:
        return np.nan, np.nan
    x = (g["date"] - g["date"].min()).dt.total_seconds().to_numpy() / 86400 / 7
    y = g["recovery"].to_numpy()
    if np.ptp(x) == 0:
        return np.nan, np.nan
    slope, intercept = np.polyfit(x, y, 1)
    ss_res = ((y - (slope * x + intercept)) ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    return float(slope), float(1 - ss_res / ss_tot) if ss_tot > 0 else 0.0


def _add_control_stats(df: pd.DataFrame, week: pd.Timestamp, th: Thresholds):
    """z-scores against baseline (history before report week) + Westgard flags."""
    df = df.copy()
    df["z"] = np.nan
    df["rules"] = [[] for _ in range(len(df))]
    limits = {}
    start = week - pd.Timedelta(weeks=th.baseline_weeks)
    for key, g in df.groupby(["instrument", "element"], sort=False):
        base = g[(g["week"] < week) & (g["week"] >= start)]
        source = f"previous {th.baseline_weeks} weeks"
        if len(base) < th.min_baseline_n:
            base = g[g["week"] <= week]
            source = "all available data (short history)"
        mu, sd = base["recovery"].mean(), base["recovery"].std(ddof=1)
        if not np.isfinite(sd) or sd < 0.05:
            sd = max(th.precision_limit / 2, 0.05)
            source += "; SD floored"
        gi = g[g["week"] <= week].sort_values("date")
        z = ((gi["recovery"] - mu) / sd).to_numpy()
        df.loc[gi.index, "z"] = z
        for idx, r in zip(gi.index, westgard_flags(z)):
            df.at[idx, "rules"] = r
        limits[key] = (mu, sd, source, len(base))
    return df, limits


# ---------------------------------------------------------------- main entry
def analyse(df: pd.DataFrame, week: pd.Timestamp | None = None, th: Thresholds | None = None) -> Analysis:
    th = th or Thresholds()
    weeks = sorted(df["week"].unique())
    week = pd.Timestamp(week) if week is not None else pd.Timestamp(weeks[-1])
    week = week - pd.Timedelta(days=week.weekday())
    if week not in set(weeks):
        raise ValueError(f"No data for week starting {week.date()}. Available: {[str(pd.Timestamp(w).date()) for w in weeks[-6:]]}")
    df = df[df["week"] <= week]
    prev = max((w for w in weeks if w < week), default=None)
    prev = pd.Timestamp(prev) if prev is not None else None

    df, limits = _add_control_stats(df, week, th)
    cur = df[df["week"] == week]
    pre = df[df["week"] == prev] if prev is not None else df.iloc[0:0]

    rows = []
    th_global = th
    for (inst, el), g in cur.groupby(["instrument", "element"], sort=True):
        th = for_element(th_global, el)
        mu, sd, src, nbase = limits[(inst, el)]
        hist = df[(df["instrument"] == inst) & (df["element"] == el) &
                  (df["week"] > week - pd.Timedelta(weeks=th.trend_weeks))]
        slope, r2 = _slope_per_week(hist)
        p = pre[(pre["instrument"] == inst) & (pre["element"] == el)]
        rules = sorted({r for rs in g["rules"] for r in rs})
        sd_rec = g["recovery"].std(ddof=1) if len(g) > 1 else np.nan
        row = dict(
            instrument=inst, element=el, n=len(g),
            mean_recovery=g["recovery"].mean(), bias=g["recovery"].mean() - 100,
            sd=sd_rec, in_spec=(g["bias_pct"].abs() <= th.recovery_warn).mean() * 100,
            worst_bias=g.loc[g["bias_pct"].abs().idxmax(), "bias_pct"],
            prev_recovery=p["recovery"].mean() if len(p) else np.nan,
            prev_sd=p["recovery"].std(ddof=1) if len(p) > 1 else np.nan,
            base_mean=mu, base_sd=sd, limits_source=src, base_n=nbase,
            slope=slope, r2=r2, rules=rules,
            drift=bool(len(hist) >= th.drift_min_n and r2 >= th.drift_min_r2
                       and abs(slope) >= th.drift_slope_pts_per_week),
        )
        row["delta_recovery"] = row["mean_recovery"] - row["prev_recovery"]
        reasons, status = [], "Green"
        ab = abs(row["bias"])
        if ab > th.recovery_action:
            status = "Red"; reasons.append(f"mean bias {row['bias']:+.1f}% exceeds ±{th.recovery_action:g}% action limit")
        elif ab > th.recovery_warn:
            status = "Amber"; reasons.append(f"mean bias {row['bias']:+.1f}% exceeds ±{th.recovery_warn:g}% warning limit")
        n13 = sum("1-3s" in rs for rs in g["rules"])
        serious = set(rules) & SERIOUS_RULES
        if serious == {"1-3s"} and n13 == 1 and len(rules) == 1:
            status = "Amber" if status == "Green" else status
            reasons.append("one isolated 1-3s outlier; confirm with a re-run")
        elif serious:
            status = "Red"; reasons.append("control rule " + ", ".join(sorted(serious)) + " violated")
        elif rules:
            status = "Amber" if status == "Green" else status
            reasons.append("control rule " + ", ".join(rules) + " violated")
        if np.isfinite(sd_rec) and sd_rec > th.precision_limit * 2:
            status = "Red"; reasons.append(f"precision SD {sd_rec:.1f}% is over twice the {th.precision_limit:g}% limit")
        elif np.isfinite(sd_rec) and sd_rec > th.precision_limit:
            status = "Amber" if status == "Green" else status
            reasons.append(f"precision SD {sd_rec:.1f}% above {th.precision_limit:g}% limit")
        if row["drift"]:
            status = "Amber" if status == "Green" else status
            reasons.append(f"drift of {slope:+.2f} pts/week over {th.trend_weeks} weeks (R²={r2:.2f})")
        if row["in_spec"] < th.in_spec_min_pct and len(g) >= 3:
            status = "Amber" if status == "Green" else status
            reasons.append(f"only {row['in_spec']:.0f}% of results within ±{th.recovery_warn:g}%")
        row["status"], row["reasons"] = status, reasons
        row["warn"], row["action"], row["precision_limit"] = th.recovery_warn, th.recovery_action, th.precision_limit
        rows.append(row)
    th = th_global
    groups = pd.DataFrame(rows)
    groups["_o"] = groups["status"].map(SEVERITY_ORDER)
    groups = groups.sort_values(["_o", "instrument", "element"]).drop(columns="_o").reset_index(drop=True)

    weekly = (df.groupby(["week", "instrument", "element"])["recovery"]
                .agg(mean="mean", sd="std", n="count").reset_index())

    ev = cur[cur["rules"].map(len) > 0][["date", "instrument", "element", "standard", "operator",
                                         "measured", "certified", "recovery", "z", "rules"]].copy()
    ev["rules"] = ev["rules"].map(", ".join)

    a = Analysis(df=df, week=week, prev_week=prev, cur=cur, groups=groups, weekly=weekly, events=ev, th=th)
    a.kpis = _kpis(a)
    a.insights = _insights(a)
    return a


def _kpis(a: Analysis) -> dict:
    g, c, th = a.groups, a.cur, a.th
    pw = a.df[a.df["week"] == a.prev_week] if a.prev_week is not None else None
    def spec(d):
        warn = d["element"].map(lambda e: for_element(th, e).recovery_warn)
        return (d["bias_pct"].abs() <= warn).mean() * 100
    in_spec = spec(c)
    prev_in_spec = spec(pw) if pw is not None and len(pw) else np.nan
    return dict(
        n_results=len(c), n_prev=0 if pw is None else len(pw),
        n_groups=len(g), n_green=int((g.status == "Green").sum()),
        n_amber=int((g.status == "Amber").sum()), n_red=int((g.status == "Red").sum()),
        in_spec=in_spec, prev_in_spec=prev_in_spec,
        mean_abs_bias=c["bias_pct"].abs().mean(),
        prev_mean_abs_bias=pw["bias_pct"].abs().mean() if pw is not None and len(pw) else np.nan,
        health=100 * (g.status == "Green").mean() + 50 * (g.status == "Amber").mean() if len(g) else np.nan,
        n_events=len(a.events),
        instruments=sorted(c["instrument"].unique()), elements=sorted(c["element"].unique()),
    )


def _sentence(parts: list[str]) -> str:
    t = "; ".join(parts)
    return (t[:1].upper() + t[1:] + ".") if t else ""


def _compare(gg: pd.DataFrame, by: str, th: Thresholds):
    """Highest vs lowest mean recovery across levels of `by`; returns (hi, lo, gap) if material and significant."""
    m = gg.groupby(by)["recovery"].agg(["mean", "std", "count"])
    m = m[m["count"] >= 5]
    if len(m) < 2:
        return None
    hi, lo = m["mean"].idxmax(), m["mean"].idxmin()
    gap = m.loc[hi, "mean"] - m.loc[lo, "mean"]
    se = np.sqrt(m.loc[hi, "std"] ** 2 / m.loc[hi, "count"] + m.loc[lo, "std"] ** 2 / m.loc[lo, "count"])
    if gap > th.group_diff_pts and (not np.isfinite(se) or se == 0 or gap / se > 3):
        return hi, lo, gap, m
    return None


def _insights(a: Analysis) -> list[dict]:
    th, g, out = a.th, a.groups, []
    add = lambda sev, title, text, action="": out.append(dict(severity=sev, title=title, text=text, action=action))

    for _, r in g[g.status == "Red"].iterrows():
        add("Red", f"{r.element} on {r.instrument} is out of control", _sentence(r.reasons),
            "Stop reporting this element until a fresh CRM passes; check calibration, sample preparation, "
            "cup film and tube condition." + (" A drift correction / recalibration is due." if r.drift else ""))
    for _, r in g[(g.status == "Amber") & ~g.drift].iterrows():
        add("Amber", f"{r.element} on {r.instrument} needs attention", _sentence(r.reasons),
            "Schedule a recheck with a CRM and review the weekly trend before the next batch.")
    for _, r in g[g.drift & (g.status != "Red")].iterrows():
        direction = "upward" if r.slope > 0 else "downward"
        add("Amber", f"Drift detected: {r.element} on {r.instrument}",
            f"Recovery is moving {direction} by {abs(r.slope):.2f} points per week (R²={r.r2:.2f}); "
            f"over a quarter that is roughly {abs(r.slope) * 13:.1f} points.",
            "Plan a drift correction / recalibration (monitor monitor-sample intensity, tube age, temperature).")

    # instrument comparison on elements measured on >1 instrument (last 4 weeks)
    recent = a.df[a.df["week"] > a.week - pd.Timedelta(weeks=4)]
    for el, gg in recent.groupby("element"):
        res = _compare(gg, "instrument", th)
        if res:
            hi, lo, gap, m = res
            add("Amber", f"Instruments disagree on {el}",
                f"{hi} reads {gap:.1f} points higher than {lo} over the last 4 weeks "
                f"({m.loc[hi, 'mean']:.1f}% vs {m.loc[lo, 'mean']:.1f}% recovery).",
                "Cross-calibrate the instruments against the same CRM set.")
    # operator effect within each instrument/element (excluding report-week shifts already flagged)
    ops = recent[recent["operator"] != "n/a"]
    if ops["operator"].nunique() >= 2:
        for (inst, el), gg in ops.groupby(["instrument", "element"]):
            res = _compare(gg, "operator", th)
            if res:
                hi, lo, gap, m = res
                add("Amber", f"Operator effect on {el} ({inst})",
                    f"Results by {hi} average {gap:.1f} points above those by {lo} over the last 4 weeks "
                    f"(n={int(m.loc[hi, 'count'])} vs {int(m.loc[lo, 'count'])}).",
                    "Review sample preparation and loading practice with both analysts; refresh SOP training.")

    # week-on-week movement
    k = a.kpis
    if np.isfinite(k["prev_mean_abs_bias"]):
        d = k["mean_abs_bias"] - k["prev_mean_abs_bias"]
        if abs(d) >= 0.3:
            add("Green" if d < 0 else "Amber", "Accuracy " + ("improved" if d < 0 else "worsened") + " versus last week",
                f"Mean absolute bias moved from {k['prev_mean_abs_bias']:.2f}% to {k['mean_abs_bias']:.2f}%.")
    m = g.dropna(subset=["delta_recovery"])
    if len(m):
        w = m.loc[m["delta_recovery"].abs().idxmax()]
        if abs(w.delta_recovery) >= 1.5:
            add("Amber", f"Largest weekly shift: {w.element} on {w.instrument}",
                f"Mean recovery moved {w.delta_recovery:+.1f} points ({w.prev_recovery:.1f}% to {w.mean_recovery:.1f}%).")
    if not out or all(i["severity"] == "Green" for i in out):
        add("Green", "All monitored elements are in control",
            f"{k['n_green']} of {k['n_groups']} instrument/element combinations passed every check this week.")
    out.sort(key=lambda i: SEVERITY_ORDER[i["severity"]])
    return out
