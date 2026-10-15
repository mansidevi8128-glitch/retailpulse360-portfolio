"""Report helpers and checks on the generated deliverables."""

import json
import re

import pandas as pd
import pytest

from retailpulse360 import reporting
from retailpulse360.config import PROJECT_ROOT, REPORTS_DIR


def test_markdown_table():
    table = reporting.markdown_table(pd.DataFrame({"a": [1.5], "b": ["x"]}), {"a": "{:.1f}%"})
    assert table.splitlines() == ["| a | b |", "|---|---|", "| 1.5% | x |"]


def test_value_range_collapses_equal_values():
    assert reporting.value_range(11.4, 11.46, suffix="×") == "about 11×"
    assert reporting.value_range(2, 5) == "2–5"


def test_update_marked_section(tmp_path):
    path = tmp_path / "doc.md"
    path.write_text("before\n<!-- X:START -->\nold\n<!-- X:END -->\nafter\n")
    reporting.update_marked_section(path, "X", "new")
    assert path.read_text() == "before\n<!-- X:START -->\nnew\n<!-- X:END -->\nafter\n"
    with pytest.raises(ValueError):
        reporting.update_marked_section(path, "MISSING", "x")


GENERATED = ["data_quality_report.md", "business_recommendations.md"]


@pytest.mark.parametrize("name", GENERATED)
def test_generated_reports_exist_and_disclose_synthetic_data(name):
    text = (REPORTS_DIR / name).read_text(encoding="utf-8")
    assert "synthetic" in text.lower()
    assert not re.search(r"\bTODO\b|\bTBD\b|nan%|\$nan", text)


def test_model_metrics_match_saved_tables():
    metrics = json.loads((REPORTS_DIR / "model_metrics.json").read_text())
    test_results = pd.read_csv(REPORTS_DIR / "tables" / "churn_test_results.csv").set_index("model")
    chosen = metrics["churn"]["chosen_model"]
    assert metrics["churn"]["test_metrics_at_threshold"]["roc_auc"] == pytest.approx(test_results.loc[chosen, "roc_auc"], abs=1e-4)


def test_readme_findings_block_is_generated():
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    block = readme.split("<!-- KEY-FINDINGS:START -->")[1].split("<!-- KEY-FINDINGS:END -->")[0]
    summary = json.loads((REPORTS_DIR / "model_metrics.json").read_text())["executive_summary"]
    assert f"{summary['completed_orders']:,}" in block


def test_interview_guide_quotes_current_metrics():
    """Numbers quoted by hand in the interview guide must match the generated metrics."""
    metrics = json.loads((REPORTS_DIR / "model_metrics.json").read_text())
    churn = metrics["churn"]["test_metrics_at_threshold"]
    text = (PROJECT_ROOT / "docs" / "interview_walkthrough.md").read_text(encoding="utf-8")
    expected = [
        f"{metrics['executive_summary']['completed_orders']:,}",
        f"${metrics['executive_summary']['aov_usd']:,.2f}",
        f"{churn['roc_auc']:.3f}",
        f"{churn['pr_auc']:.3f}",
        f"{metrics['churn']['threshold']:.2f}",
        f"{100 * metrics['churn']['base_rate_test']:.1f}%",
        f"{metrics['headline']['ytd_revenue_growth_2026_vs_2025_pct']:.1f}%",
    ]
    missing = [value for value in expected if value not in text]
    assert not missing, f"Interview guide is out of date: {missing}"
