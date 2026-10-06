"""Command line: python -m xrf_report <weekly.xlsx> [options]"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

from .analysis import analyse
from .config import Thresholds
from .loader import load_workbook
from .render import build_excel, build_html

HIST_COLS = ["date", "instrument", "element", "standard", "operator", "measured", "certified"]


def merge_history(df: pd.DataFrame, history: Path) -> pd.DataFrame:
    """Append this week's rows to a CSV history store (deduplicated) and return the full history."""
    if history.exists():
        old = pd.read_csv(history, parse_dates=["date"], dtype={c: str for c in ("instrument", "element", "standard", "operator")})
        full = pd.concat([old[HIST_COLS], df[HIST_COLS]], ignore_index=True)
    else:
        full = df[HIST_COLS].copy()
    full = full.drop_duplicates(["date", "instrument", "element", "standard", "measured"], keep="last").sort_values("date")
    history.parent.mkdir(parents=True, exist_ok=True)
    full.to_csv(history, index=False)
    full["recovery"] = full["measured"] / full["certified"] * 100
    full["bias_pct"] = full["recovery"] - 100
    full["week"] = full["date"].dt.normalize() - pd.to_timedelta(full["date"].dt.weekday, unit="D")
    return full.reset_index(drop=True)


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="xrf_report", description="Turn the weekly XRF QC workbook into a monitoring report.")
    p.add_argument("excel", help="weekly Excel workbook (.xlsx/.xls)")
    p.add_argument("-o", "--out-dir", default="reports", help="output folder (default: reports)")
    p.add_argument("--sheet", help="sheet name (default: first sheet with the required columns)")
    p.add_argument("--week", help="report week, any date inside it (default: latest week in data)")
    p.add_argument("--history", help="CSV file that accumulates every weekly upload, for long-term trends")
    p.add_argument("--no-excel", action="store_true", help="skip the Excel summary workbook")
    p.add_argument("--cdn", action="store_true", help="load plotly.js from CDN (smaller file, needs internet to view)")
    for name, default in vars(Thresholds()).items():
        if isinstance(default, dict):
            continue
        p.add_argument(f"--{name.replace('_', '-')}", type=type(default), default=default, help=argparse.SUPPRESS)
    args = p.parse_args(argv)

    th = Thresholds(**{n: getattr(args, n) for n, d in vars(Thresholds()).items() if not isinstance(d, dict)})
    try:
        lr = load_workbook(args.excel, args.sheet)
        th.per_element = {**th.per_element, **lr.limits}
        df = merge_history(lr.df, Path(args.history)) if args.history else lr.df
        a = analyse(df, pd.Timestamp(args.week) if args.week else None, th)
    except (ValueError, FileNotFoundError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    if a.df.week.nunique() < 4:
        lr.warnings.append(f"Only {a.df.week.nunique()} week(s) of data: control limits and trends are provisional. "
                           "Use --history so every weekly upload builds up the baseline.")
    out = Path(args.out_dir); out.mkdir(parents=True, exist_ok=True)
    iso = a.week.isocalendar()
    stem = f"XRF_Performance_{iso.year}-W{iso.week:02d}"
    html_path = out / f"{stem}.html"
    html_path.write_text(build_html(a, Path(args.excel).name, lr.warnings, "cdn" if args.cdn else "inline"), encoding="utf-8")
    print(f"report : {html_path}")
    if not args.no_excel:
        build_excel(a, out / f"{stem}_summary.xlsx")
        print(f"excel  : {out / (stem + '_summary.xlsx')}")
    k = a.kpis
    print(f"week {iso.week}: {k['n_results']} results · {k['n_green']} green / {k['n_amber']} amber / {k['n_red']} red"
          f" · {k['in_spec']:.1f}% of results within spec")
    for w in lr.warnings:
        print(f"warning: {w}")
    return 0
