# XRF Analytical Performance Monitor

Turns the weekly XRF QC workbook (Excel) into a self-contained interactive report and an Excel summary. Each report has:

- **Executive summary.** A health score, the share of results within spec, mean absolute bias and control-rule violations, each with the change since last week.
- **Key findings & actions.** Plain-language findings generated from the data, most severe first: out-of-control elements, drift, instrument disagreement, operator effects and the largest weekly shifts.
- **Status matrix.** An instrument × element heat map showing Green / Amber / Red.
- **Scorecard.** A sortable, filterable table of recovery, bias, precision, % in spec, week-on-week change, drift and the reason for each status.
- **Weekly trends.** Small multiples covering up to 26 weeks, with warning and action bands.
- **Levey-Jennings control charts.** One per instrument/element, with Westgard multi-rule flags (1-3s, 2-2s, R-4s, 4-1s, 10-x).
- **Accuracy & precision.** Bias with ±1 SD whiskers, SD against each element's limit, recovery vs concentration level, recovery distributions, and QC workload.
- **Violation log.** Every result that broke a rule this week: who, when, which CRM and which rule.

The HTML file works offline (plotly.js is embedded), prints cleanly to PDF (Ctrl+P), and charts can be zoomed, hovered and saved as PNG.

## Install

```bash
pip install -r requirements.txt        # Python 3.10+
```

## Weekly use

```bash
python -m xrf_report path/to/week_40.xlsx --history data/history.csv -o reports
```

Outputs:

- `reports/XRF_Performance_2026-W40.html`
- `reports/XRF_Performance_2026-W40_summary.xlsx`

`--history` matters if each weekly file only holds that week's data. Every upload is appended (de-duplicated) to `data/history.csv`, so control limits, drift detection and trends build up over time. If your file already holds the full history, you can leave it out.

**One-click option:** drop the new workbook into `inbox/` and run `run_weekly.bat` (Windows) or `./run_weekly.sh`. The newest file is processed and the report opens. To make it fully automatic, schedule that script with Windows Task Scheduler or cron.

**Try it with demo data:**

```bash
python generate_sample.py sample/xrf_qc_sample.xlsx
python -m xrf_report sample/xrf_qc_sample.xlsx -o reports
```

The demo has four planted problems: a sudden Na₂O shift, a slow Fe₂O₃ drift on XRF-02, an operator effect on SO₃, and a precision loss on K₂O.

### Options

| Option | Meaning |
|---|---|
| `--week 2026-09-30` | Report a specific week (any date inside it). The default is the latest week in the data. |
| `--sheet QC_Data` | Use this sheet. The default is the first sheet that has the required columns. |
| `--history FILE` | Accumulate uploads in a CSV history. |
| `--cdn` | Load plotly.js from a CDN. The file is about 0.2 MB instead of 5 MB, but viewing it needs internet. |
| `--no-excel` | Skip the Excel summary. |
| `--recovery-warn 5 --recovery-action 10 --precision-limit 3` | Override the default limits. All fields in `xrf_report/config.py` can be overridden this way. |

## Input format

One row per QC measurement of a reference material (CRM / in-house standard). Header names are matched flexibly: case, spaces and punctuation are ignored, and common synonyms are accepted.

| Column | Required | Accepted headers (examples) |
|---|---|---|
| Date | ✔ | Date, Analysis Date, Timestamp, Run Date |
| Element | ✔ | Element, Analyte, Oxide, Parameter |
| Measured | ✔ | Measured Value, Result, Value, Found |
| Certified | ✔ | Certified Value, Reference Value, Expected, Target, Assigned Value |
| Instrument | | Instrument, Analyzer, Spectrometer (default `XRF-1`) |
| Standard | | Standard, CRM, Reference Material, Sample ID |
| Operator | | Operator, Analyst, Technician |

Rows with a missing or invalid date or value are dropped, exact duplicates are removed, and both are reported at the top of the report.

**Optional `Limits` sheet** with per-element limits (useful because trace oxides are noisier than majors):

| Element | Warning limit | Action limit | Precision limit |
|---|---|---|---|
| Na2O | 8 | 12 | 6 |

## How the status is decided

- **Recovery** = measured / certified × 100. **Bias** = recovery − 100.
- **Precision** is the SD of recovery within the week.
- **Control limits** are the mean and SD of recovery for each instrument/element over the previous 12 weeks. With fewer than 10 points, all available data is used and the report says so.
- **Red** if any of these hold:
  - |bias| is above the action limit (default 10%)
  - a 2-2s or R-4s violation, or a 1-3s that is repeated or comes with another rule
  - SD is above twice the precision limit
- **Amber** if any of these hold:
  - |bias| is above the warning limit (default 5%)
  - one isolated 1-3s outlier, or a 4-1s or 10-x violation
  - SD is above the precision limit
  - significant drift: a linear trend over 12 weeks with |slope| ≥ 0.4 pts/week and R² ≥ 0.2
  - fewer than 90% of results are within the warning limit
- **Instrument and operator effects** are flagged when two groups differ by more than 2 recovery points over the last 4 weeks and the gap is statistically clear (> 3 standard errors, n ≥ 5 each).

All thresholds are in `xrf_report/config.py`.

## Project layout

```
xrf_report/
  config.py      thresholds and column aliases
  loader.py      reads and validates the workbook (plus the optional Limits sheet)
  analysis.py    KPIs, Westgard rules, drift, status logic, auto-generated findings
  charts.py      Plotly figures
  render.py      HTML report (templates/report.html.j2) and Excel summary
  cli.py         command line and history store
generate_sample.py   realistic demo workbook
tests/               pytest suite (python -m pytest tests)
```
