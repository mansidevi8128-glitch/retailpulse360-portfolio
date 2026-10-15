import pandas as pd
import pytest

from retailpulse360 import data, features


@pytest.fixture(scope="session")
def tables():
    return data.load_raw_tables()


@pytest.fixture(scope="session")
def snapshot():
    return data.load_snapshot()


@pytest.fixture(scope="session")
def model_frame(tables, snapshot):
    return features.add_corrected_features(snapshot, tables["orders"])


@pytest.fixture
def toy_orders():
    """Five orders for two customers covering every status."""
    return pd.DataFrame(
        {
            "order_id": ["O1", "O2", "O3", "O4", "O5"],
            "customer_id": ["C1", "C1", "C2", "C2", "C2"],
            "order_date": pd.to_datetime(["2024-01-05", "2024-02-10", "2024-01-20", "2024-02-15", "2024-02-20"]),
            "order_status": ["Completed", "Completed", "Completed", "Refunded", "Cancelled"],
            "gross_merchandise_value_usd": [100.0, 50.0, 200.0, 80.0, 40.0],
            "shipping_fee_usd": [5.0, 0.0, 0.0, 5.0, 0.0],
            "net_revenue_usd": [105.0, 50.0, 200.0, 0.0, 0.0],
            "total_cost_usd": [60.0, 30.0, 120.0, 48.0, 0.0],
            "profit_usd": [45.0, 20.0, 80.0, -48.0, 0.0],
            "discount_pct": [0.0, 10.0, 0.0, 0.0, 0.0],
            "sales_channel": ["Website", "Website", "Mobile App", "Mobile App", "Website"],
        }
    )


@pytest.fixture
def toy_items():
    return pd.DataFrame(
        {
            "order_item_id": ["L1", "L2", "L3", "L4", "L5", "L6"],
            "order_id": ["O1", "O1", "O2", "O3", "O4", "O5"],
            "product_id": ["P1", "P2", "P1", "P2", "P1", "P2"],
            "quantity": [1, 1, 1, 2, 1, 1],
            "unit_price_usd": [60.0, 40.0, 50.0, 100.0, 80.0, 40.0],
            "discount_pct": [0.0, 0.0, 10.0, 0.0, 0.0, 0.0],
            "line_revenue_usd": [60.0, 40.0, 50.0, 200.0, 80.0, 40.0],
            "line_cost_usd": [36.0, 24.0, 30.0, 120.0, 48.0, 24.0],
        }
    )


@pytest.fixture
def toy_products():
    return pd.DataFrame({"product_id": ["P1", "P2"], "category": ["Office", "Beauty"]})
