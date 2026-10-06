"""Thresholds and column aliases. Edit here to match your lab's QC policy."""
from dataclasses import dataclass, field

# canonical name -> accepted header spellings (after lower-casing / non-alnum -> "_")
COLUMN_ALIASES = {
    "date": ["date", "datetime", "analysis_date", "measurement_date", "run_date", "timestamp"],
    "instrument": ["instrument", "instrument_id", "analyzer", "spectrometer", "xrf", "unit_id", "machine"],
    "element": ["element", "analyte", "oxide", "parameter", "component"],
    "standard": ["standard", "standard_id", "crm", "crm_id", "reference", "reference_material", "sample_id", "sample"],
    "measured": ["measured", "measured_value", "result", "value", "xrf_value", "found", "xrf"],
    "certified": ["certified", "certified_value", "reference_value", "expected", "true_value", "target", "assigned_value"],
    "operator": ["operator", "analyst", "technician", "user"],
}
REQUIRED = ["date", "element", "measured", "certified"]


@dataclass
class Thresholds:
    recovery_warn: float = 5.0      # |bias| % beyond which a group is Amber
    recovery_action: float = 10.0   # |bias| % beyond which a group is Red
    precision_limit: float = 3.0    # SD of recovery (%) acceptable
    in_spec_min_pct: float = 90.0   # % of results inside warn band expected
    baseline_weeks: int = 12        # history used for control limits
    min_baseline_n: int = 10        # fewer points -> fall back to all data
    trend_weeks: int = 12           # window for drift detection
    drift_slope_pts_per_week: float = 0.4   # recovery points / week
    drift_min_r2: float = 0.2
    drift_min_n: int = 10
    group_diff_pts: float = 2.0     # instrument / operator mean-recovery gap worth flagging
    # per-element overrides of recovery_warn / recovery_action / precision_limit,
    # e.g. {"Na2O": {"precision_limit": 6.0, "recovery_warn": 8.0}}. A "Limits" sheet in the workbook fills this too.
    per_element: dict = field(default_factory=dict)


LIMIT_ALIASES = {
    "element": ["element", "analyte", "oxide", "parameter"],
    "recovery_warn": ["recovery_warn", "warning_limit", "warn_limit", "warning", "warn_pct", "warning_limit_pct"],
    "recovery_action": ["recovery_action", "action_limit", "action", "action_pct", "action_limit_pct"],
    "precision_limit": ["precision_limit", "precision", "max_sd", "sd_limit", "rsd_limit", "max_rsd"],
}
