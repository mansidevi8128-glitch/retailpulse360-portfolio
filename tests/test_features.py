"""Feature engineering: snapshot reproduction and leakage safeguards."""

import pandas as pd
import pytest

from retailpulse360 import features, quality
from retailpulse360.config import SNAPSHOT_DATE


def test_rebuilt_features_match_provided_snapshot(tables, snapshot):
    rebuilt = features.build_customer_features(tables)
    check = quality.snapshot_reproduction_check(snapshot, rebuilt, features.SNAPSHOT_NUMERIC_FEATURES)
    assert (check["match_rate"] == 1.0).all(), check[check["match_rate"] < 1]


def test_categorical_attributes_match_snapshot(tables, snapshot):
    rebuilt = features.build_customer_features(tables).set_index("customer_id")
    provided = snapshot.set_index("customer_id")
    for column in features.CATEGORICAL_FEATURES:
        assert (rebuilt.loc[provided.index, column] == provided[column]).all()


def test_events_after_snapshot_do_not_change_features(tables):
    """Adding a future order, session and ticket must not change any feature."""
    baseline = features.build_customer_features(tables)
    future = SNAPSHOT_DATE + pd.Timedelta(days=10)
    customer = tables["customers"]["customer_id"].iloc[0]
    altered = dict(tables)
    order = tables["orders"].iloc[[0]].assign(order_id="FUTURE", customer_id=customer, order_date=future, order_status="Completed")
    altered["orders"] = pd.concat([tables["orders"], order], ignore_index=True)
    session = tables["web_sessions"].iloc[[0]].assign(session_id="FUTURE", customer_id=customer, session_date=future)
    altered["web_sessions"] = pd.concat([tables["web_sessions"], session], ignore_index=True)
    ticket = tables["support_tickets"].iloc[[0]].assign(ticket_id="FUTURE", customer_id=customer, opened_date=future)
    altered["support_tickets"] = pd.concat([tables["support_tickets"], ticket], ignore_index=True)
    pd.testing.assert_frame_equal(baseline, features.build_customer_features(altered))


def test_recency_sentinel_is_documented_correctly(model_frame):
    no_purchase = model_frame[model_frame["frequency_12m"] == 0]
    assert len(no_purchase) == 606
    assert (no_purchase["recency_days"] == no_purchase["days_since_signup"] + 30).all()


def test_corrected_recency(model_frame, tables):
    assert model_frame["never_purchased"].sum() == 317
    buyers = model_frame[model_frame["never_purchased"] == 0]
    completed = tables["orders"][tables["orders"]["order_status"] == "Completed"]
    last = completed.groupby("customer_id")["order_date"].max()
    expected = (SNAPSHOT_DATE - buyers["customer_id"].map(last)).dt.days
    assert (buyers["days_since_last_purchase"].to_numpy() == expected.to_numpy()).all()
    # Customers with recent purchases keep the same recency under both definitions.
    recent = model_frame[model_frame["frequency_12m"] > 0]
    assert (recent["recency_days"] == recent["days_since_last_purchase"]).all()


@pytest.mark.parametrize("column", ["customer_id", "churned_next_90d", "snapshot_date"])
def test_leakage_guard_rejects_non_features(column):
    with pytest.raises(ValueError):
        features.assert_no_leakage(["frequency_12m", column])


def test_model_feature_lists_are_clean():
    features.assert_no_leakage(features.MODEL_NUMERIC_FEATURES + features.CATEGORICAL_FEATURES)
    assert "recency_days" not in features.MODEL_NUMERIC_FEATURES  # sentinel replaced
