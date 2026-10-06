import numpy as np
import pandas as pd
import pytest

from generate_sample import make
from xrf_report.analysis import analyse, westgard_flags
from xrf_report.cli import main
from xrf_report.loader import load_workbook


@pytest.fixture(scope="module")
def sample_xlsx(tmp_path_factory):
    p = tmp_path_factory.mktemp("d") / "qc.xlsx"
    make(16).to_excel(p, sheet_name="QC_Data", index=False)
    return p


def test_westgard_rules():
    assert westgard_flags(np.array([0, 3.5]))[1] == ["1-3s"]
    assert "2-2s" in westgard_flags(np.array([2.1, 2.2]))[1]
    assert "R-4s" in westgard_flags(np.array([2.1, -2.1]))[1]
    assert "4-1s" in westgard_flags(np.array([1.2, 1.1, 1.5, 1.3]))[3]
    assert "10-x" in westgard_flags(np.full(10, 0.3))[9]
    assert westgard_flags(np.array([0.1, -0.2, 0.5])) == [[], [], []]


def test_loader_maps_header_aliases(tmp_path):
    p = tmp_path / "x.xlsx"
    pd.DataFrame({"Analysis Date": ["2026-01-05", "2026-01-06", None],
                  "Analyte": ["SiO2", "SiO2", "SiO2"], "Result": [20.5, "bad", 20.0],
                  "Certified Value": [20.8, 20.8, 20.8]}).to_excel(p, index=False)
    lr = load_workbook(str(p))
    assert len(lr.df) == 1 and lr.df.instrument.iloc[0] == "XRF-1"
    assert lr.df.recovery.iloc[0] == pytest.approx(20.5 / 20.8 * 100)
    assert "2 of 3 rows dropped" in lr.warnings[0]


def test_loader_rejects_missing_columns(tmp_path):
    p = tmp_path / "x.xlsx"
    pd.DataFrame({"foo": [1]}).to_excel(p, index=False)
    with pytest.raises(ValueError, match="required columns"):
        load_workbook(str(p))


def test_analysis_detects_planted_problems(sample_xlsx):
    a = analyse(load_workbook(str(sample_xlsx)).df)
    st = a.groups.set_index(["instrument", "element"])["status"]
    assert st[("XRF-01", "Na2O")] == "Red"          # sudden shift
    assert st[("XRF-02", "Fe2O3")] == "Red"         # accumulated drift
    assert a.groups.set_index(["instrument", "element"]).loc[("XRF-02", "Fe2O3"), "drift"]
    assert st[("XRF-01", "CaO")] == "Green"
    titles = " ".join(i["title"] for i in a.insights)
    assert "Operator effect on SO3 (XRF-02)" in titles
    assert "Instruments disagree on Fe2O3" in titles


def test_cli_end_to_end_with_history(sample_xlsx, tmp_path):
    hist = tmp_path / "history.csv"
    assert main([str(sample_xlsx), "-o", str(tmp_path / "out"), "--history", str(hist), "--cdn"]) == 0
    assert main([str(sample_xlsx), "-o", str(tmp_path / "out"), "--history", str(hist), "--cdn"]) == 0
    assert len(pd.read_csv(hist)) == len(load_workbook(str(sample_xlsx)).df)   # re-upload is deduplicated
    html = next((tmp_path / "out").glob("*.html")).read_text()
    assert "Levey-Jennings" in html and "Na2O" in html
    assert next((tmp_path / "out").glob("*_summary.xlsx")).exists()
