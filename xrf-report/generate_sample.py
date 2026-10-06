"""Create a realistic demo workbook so the report can be tried without real data.

    python generate_sample.py sample/xrf_qc_sample.xlsx --weeks 16
"""
import argparse

import numpy as np
import pandas as pd

CRMS = {  # certified values, wt %
    "CRM-Cement-A": dict(SiO2=20.80, Al2O3=5.12, Fe2O3=3.41, CaO=63.40, MgO=1.62, SO3=2.71, K2O=0.82, Na2O=0.21, TiO2=0.26),
    "CRM-Clinker-B": dict(SiO2=21.65, Al2O3=5.40, Fe2O3=3.62, CaO=65.80, MgO=1.95, SO3=0.85, K2O=0.64, Na2O=0.18, TiO2=0.29),
    "CRM-Raw-Meal-C": dict(SiO2=13.40, Al2O3=3.22, Fe2O3=2.05, CaO=43.10, MgO=1.31, SO3=0.42, K2O=0.51, Na2O=0.12, TiO2=0.17),
}
RSD = dict(SiO2=0.6, Al2O3=1.0, Fe2O3=1.0, CaO=0.4, MgO=1.6, SO3=1.4, K2O=1.5, Na2O=3.5, TiO2=2.0)
# optional per-element limits (trace oxides are noisier than majors)
LIMITS = pd.DataFrame([
    {"Element": "Na2O", "Warning limit": 8, "Action limit": 12, "Precision limit": 6},
    {"Element": "K2O", "Warning limit": 6, "Action limit": 10, "Precision limit": 4},
    {"Element": "TiO2", "Warning limit": 6, "Action limit": 10, "Precision limit": 4},
])
OPERATORS = ["A. Hassan", "M. Saleh", "R. Omar"]


def make(weeks: int, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    today = pd.Timestamp.today().normalize()
    end = today - pd.Timedelta(days=today.weekday() + 1)  # last complete week (Sunday)
    start = end - pd.Timedelta(days=end.weekday()) - pd.Timedelta(weeks=weeks - 1)
    rows = []
    for day in pd.date_range(start, end):
        if day.weekday() >= 5:
            continue
        wk = (day - start).days / 7
        last = wk >= weeks - 1
        for inst in ("XRF-01", "XRF-02"):
            for shift_h in (8, 15):
                crm = list(CRMS)[rng.integers(len(CRMS))]
                op = OPERATORS[rng.integers(len(OPERATORS))]
                t = day + pd.Timedelta(hours=shift_h, minutes=int(rng.integers(0, 50)))
                for el, cert in CRMS[crm].items():
                    rec = 100 + rng.normal(0, RSD[el])
                    if inst == "XRF-02" and el == "Fe2O3":
                        rec += 0.45 * wk                        # slow upward drift
                    if inst == "XRF-01" and el == "Na2O" and last:
                        rec -= 8 + rng.normal(0, 1)             # sudden shift this week
                    if inst == "XRF-02" and el == "SO3" and op == "R. Omar":
                        rec += 2.8                              # operator / prep effect
                    if inst == "XRF-01" and el == "MgO" and last and shift_h == 15 and day.weekday() == 2:
                        rec += 7                                # gross outlier
                    if inst == "XRF-02" and el == "K2O" and last:
                        rec += rng.normal(0, 4)                 # precision loss
                    rows.append({"Date": t, "Instrument": inst, "Standard": crm, "Element": el,
                                 "Certified Value": cert, "Measured Value": round(cert * rec / 100, 4),
                                 "Unit": "wt%", "Operator": op})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("out", nargs="?", default="sample/xrf_qc_sample.xlsx")
    ap.add_argument("--weeks", type=int, default=16)
    a = ap.parse_args()
    df = make(a.weeks)
    with pd.ExcelWriter(a.out, engine="xlsxwriter") as xw:
        df.to_excel(xw, sheet_name="QC_Data", index=False)
        LIMITS.to_excel(xw, sheet_name="Limits", index=False)
    print(f"wrote {len(df)} rows to {a.out}")
