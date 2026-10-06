"""Read and validate the weekly Excel workbook."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from .config import COLUMN_ALIASES, LIMIT_ALIASES, REQUIRED


@dataclass
class LoadResult:
    df: pd.DataFrame
    sheet: str
    warnings: list[str] = field(default_factory=list)
    limits: dict = field(default_factory=dict)


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(s).strip().lower()).strip("_")


def _map_columns(columns, aliases_map=COLUMN_ALIASES) -> dict[str, str]:
    normed = {c: _norm(c) for c in columns}
    mapping: dict[str, str] = {}
    for canon, aliases in aliases_map.items():
        for alias in aliases:  # alias order = priority
            hit = next((c for c, n in normed.items() if n == alias and c not in mapping), None)
            if hit is not None:
                mapping[hit] = canon
                break
    return mapping


def load_workbook(path: str, sheet: str | None = None) -> LoadResult:
    xl = pd.ExcelFile(path)
    candidates = [sheet] if sheet else xl.sheet_names
    best = None
    for name in candidates:
        if name not in xl.sheet_names:
            raise ValueError(f"Sheet '{name}' not found. Available: {xl.sheet_names}")
        raw = xl.parse(name)
        mapping = _map_columns(raw.columns)
        found = set(mapping.values())
        if all(r in found for r in REQUIRED):
            best = (name, raw, mapping)
            break
    if best is None:
        raise ValueError(
            f"No sheet contains the required columns {REQUIRED}. "
            f"Sheets checked: {candidates}. See README for accepted header names."
        )
    name, raw, mapping = best
    df = raw.rename(columns=mapping)[list(mapping.values())].copy()
    warnings: list[str] = []
    n0 = len(df)

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for c in ("measured", "certified"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["element"] = df["element"].astype(str).str.strip()
    for c, default in (("instrument", "XRF-1"), ("standard", "QC"), ("operator", "n/a")):
        if c not in df:
            df[c] = default
        df[c] = df[c].fillna(default).astype(str).str.strip()

    bad = df[["date", "measured", "certified"]].isna().any(axis=1) | (df["certified"] <= 0)
    if bad.any():
        warnings.append(f"{int(bad.sum())} of {n0} rows dropped (missing/invalid date, measured or certified value).")
    df = df[~bad & df["element"].ne("") & df["element"].ne("nan")].copy()
    if df.empty:
        raise ValueError("No valid rows left after cleaning.")

    dups = df.duplicated(["date", "instrument", "element", "standard", "measured"])
    if dups.any():
        warnings.append(f"{int(dups.sum())} exact duplicate rows removed.")
        df = df[~dups]

    df["recovery"] = df["measured"] / df["certified"] * 100.0
    df["bias_pct"] = df["recovery"] - 100.0
    df["week"] = df["date"].dt.normalize() - pd.to_timedelta(df["date"].dt.weekday, unit="D")
    df = df.sort_values("date").reset_index(drop=True)
    return LoadResult(df, name, warnings, _load_limits(xl, exclude=name))


def _load_limits(xl: pd.ExcelFile, exclude: str) -> dict:
    """Optional sheet named like 'Limits' / 'Thresholds' with per-element limits."""
    for name in xl.sheet_names:
        if name == exclude or _norm(name) not in ("limits", "thresholds", "qc_limits", "specs", "specifications"):
            continue
        raw = xl.parse(name)
        m = _map_columns(raw.columns, LIMIT_ALIASES)
        if "element" not in m.values():
            continue
        t = raw.rename(columns=m)[list(m.values())]
        out = {}
        for _, r in t.iterrows():
            vals = {k: float(v) for k, v in r.items() if k != "element" and pd.notna(pd.to_numeric(v, errors="coerce"))}
            if vals and pd.notna(r["element"]):
                out[str(r["element"]).strip()] = vals
        return out
    return {}
