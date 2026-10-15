"""Data-quality expectations on the real files plus unit tests of the checks."""

import pandas as pd

from retailpulse360 import quality
from retailpulse360.config import RAW_DIR

EXPECTED_ROWS = {
    "customers": 6000,
    "products": 120,
    "orders": 30054,
    "order_items": 56183,
    "web_sessions": 76327,
    "support_tickets": 4662,
    "marketing_spend": 174,
}


def test_row_counts_match_documentation(tables):
    for name, expected in EXPECTED_ROWS.items():
        assert len(tables[name]) == expected, name


def test_no_missing_values_or_duplicate_rows(tables):
    overview = quality.table_overview(tables)
    assert overview["missing_cells"].sum() == 0
    assert overview["duplicate_rows"].sum() == 0


def test_primary_keys_unique(tables):
    assert quality.check_primary_keys(tables)["passed"].all()


def test_foreign_keys_have_no_orphans(tables):
    assert quality.check_foreign_keys(tables)["orphan_rows"].sum() == 0


def test_order_financials_reconcile_with_line_items(tables):
    result = quality.reconcile_order_financials(tables["orders"], tables["order_items"])
    assert result["violations"].sum() == 0, result


def test_no_events_after_snapshot_date(tables):
    rules = quality.business_rule_checks(tables).set_index("check")["rows_flagged"]
    assert rules["Order dated after snapshot date"] == 0
    assert rules["Order dated before customer signup"] == 0


def test_known_findings_are_detected(tables):
    """The audit's documented findings stay reproducible."""
    rules = quality.business_rule_checks(tables).set_index("check")["rows_flagged"]
    assert rules["coupon_used = 1 but discount_pct = 0"] == 4079
    assert rules["Completed order with negative profit"] == 2


def test_primary_key_check_detects_duplicates():
    df = pd.DataFrame({"id": [1, 1, 2]})
    result = quality.check_primary_key(df, "id")
    assert result["duplicate_keys"] == 1 and not result["passed"]


def test_composite_key_allows_repeated_parts():
    """month repeats across channels and channel repeats across months: not duplicates."""
    df = pd.DataFrame({"month": ["2024-01", "2024-01", "2024-02"], "channel": ["Email", "Affiliate", "Email"]})
    assert quality.check_primary_key(df, ["month", "channel"])["passed"]


def test_foreign_key_check_detects_orphans():
    parent = pd.DataFrame({"customer_id": ["C1"]})
    child = pd.DataFrame({"customer_id": ["C1", "C9"]})
    assert quality.check_foreign_key(child, "customer_id", parent, "customer_id") == 1


def test_raw_files_are_not_modified_by_loading(tables):
    """Loading parses types in memory only; the CSV header row stays the source schema."""
    header = (RAW_DIR / "orders.csv").read_text(encoding="utf-8").splitlines()[0].split(",")
    assert header == list(tables["orders"].columns)
