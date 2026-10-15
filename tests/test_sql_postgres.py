"""Run the SQL scripts against PostgreSQL and compare results with pandas.

Skipped automatically when no PostgreSQL server is reachable. Connection
settings come from the standard PG* environment variables. A throwaway
database named ``retailpulse360_test`` is created and dropped.
"""

import os
import shutil
import subprocess

import pandas as pd
import pytest

from retailpulse360 import metrics
from retailpulse360.config import PROJECT_ROOT

TEST_DB = "retailpulse360_test"
psycopg2 = pytest.importorskip("psycopg2")


def _connect(dbname):
    return psycopg2.connect(dbname=dbname, connect_timeout=3)


def _server_available() -> bool:
    if shutil.which("psql") is None:
        return False
    try:
        _connect(os.environ.get("PGDATABASE", "postgres")).close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _server_available(), reason="PostgreSQL server not reachable")


@pytest.fixture(scope="module")
def sql_db():
    admin = _connect(os.environ.get("PGDATABASE", "postgres"))
    admin.autocommit = True
    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
        cur.execute(f"CREATE DATABASE {TEST_DB}")
    scripts = sorted((PROJECT_ROOT / "sql").glob("[0-9][0-9]_*.sql"))
    for script in scripts:
        subprocess.run(
            ["psql", "-d", TEST_DB, "-v", "ON_ERROR_STOP=1", "-q", "-f", str(script.relative_to(PROJECT_ROOT))],
            cwd=PROJECT_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
    conn = _connect(TEST_DB)
    yield conn
    conn.close()
    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
    admin.close()


def query(conn, sql: str) -> pd.DataFrame:
    with conn.cursor() as cur:
        cur.execute("SET search_path TO retailpulse")
        cur.execute(sql)
        columns = [d[0] for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=columns)


def test_all_tables_loaded(sql_db):
    counts = query(sql_db, "SELECT (SELECT COUNT(*) FROM orders) AS orders, (SELECT COUNT(*) FROM order_items) AS items")
    assert counts.loc[0, "orders"] == 30054 and counts.loc[0, "items"] == 56183


def test_monthly_kpis_match_pandas(sql_db, tables):
    sql = query(sql_db, "SELECT order_month, net_revenue_usd, profit_usd, active_customers FROM monthly_kpis_v ORDER BY order_month")
    py = metrics.monthly_kpis(tables["orders"])
    assert len(sql) == len(py)
    pd.testing.assert_series_equal(sql["net_revenue_usd"].astype(float), py["net_revenue_usd"], check_names=False, atol=0.01)
    pd.testing.assert_series_equal(sql["profit_usd"].astype(float), py["profit_usd"], check_names=False, atol=0.01)
    assert (sql["active_customers"].to_numpy() == py["active_customers"].to_numpy()).all()


def test_category_profit_matches_pandas(sql_db, tables):
    sql = query(sql_db, "SELECT category, SUM(revenue_usd) - SUM(cost_usd) AS profit_usd FROM line_financials_v GROUP BY category").set_index("category")
    py = metrics.category_performance(tables["orders"], tables["order_items"], tables["products"]).set_index("category")
    for category in py.index:
        assert float(sql.loc[category, "profit_usd"]) == pytest.approx(py.loc[category, "profit_usd"], abs=0.05)


def test_first_year_value_matches_pandas(sql_db, tables):
    sql = query(sql_db, "SELECT * FROM first_year_value_v").set_index("acquisition_channel")
    py = metrics.first_year_value_by_channel(tables["orders"], tables["customers"]).set_index("acquisition_channel")
    for channel in py.index:
        assert int(sql.loc[channel, "cohort_customers"]) == py.loc[channel, "cohort_customers"]
        assert float(sql.loc[channel, "first_year_profit_per_customer_usd"]) == pytest.approx(py.loc[channel, "first_year_profit_per_customer_usd"], abs=0.01)


def test_cohort_retention_matches_pandas(sql_db, tables):
    sql = query(sql_db, "SELECT cohort_month, months_since_first, retention_pct FROM cohort_retention_v WHERE months_since_first BETWEEN 1 AND 12")
    py = metrics.cohort_retention(tables["orders"])
    for row in sql.itertuples():
        assert float(row.retention_pct) == pytest.approx(py.loc[pd.Timestamp(row.cohort_month), row.months_since_first], abs=0.01)


def test_sql_feature_view_reproduces_snapshot(sql_db):
    result = query(
        sql_db,
        """
        SELECT COUNT(*) FILTER (WHERE f.recency_days <> s.recency_days
                                   OR f.frequency_12m <> s.frequency_12m
                                   OR ABS(f.monetary_value_12m - s.monetary_value_12m) > 0.01
                                   OR ABS(f.refund_rate_12m - s.refund_rate_12m) > 0.01
                                   OR f.web_sessions_90d <> s.web_sessions_90d
                                   OR ABS(f.avg_csat_12m - s.avg_csat_12m) > 0.01) AS mismatches
        FROM customer_features_v f JOIN customer_modeling_snapshot s USING (customer_id)
        """,
    )
    assert result.loc[0, "mismatches"] == 0
