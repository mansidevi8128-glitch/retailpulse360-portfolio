"""Smoke test: the dashboard script runs on the real data without errors."""

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from retailpulse360.config import PROJECT_ROOT  # noqa: E402

APP = str(PROJECT_ROOT / "dashboard" / "app.py")


def test_dashboard_runs_and_shows_real_kpis(tables):
    app = AppTest.from_file(APP, default_timeout=180).run()
    assert not app.exception
    values = {m.label: m.value for m in app.metric}
    assert values["Completed orders"] == f"{(tables['orders']['order_status'] == 'Completed').sum():,}"
    assert any("synthetic" in c.value.lower() for c in app.caption)


def test_dashboard_filters_recompute_kpis():
    app = AppTest.from_file(APP, default_timeout=180).run()
    total = {m.label: m.value for m in app.metric}["Net revenue"]
    app.sidebar.multiselect[0].select("West").run()
    assert not app.exception
    assert {m.label: m.value for m in app.metric}["Net revenue"] != total
