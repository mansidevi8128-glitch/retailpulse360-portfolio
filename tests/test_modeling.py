"""Modeling safeguards and evaluation helpers."""

import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score

from retailpulse360 import modeling, pipeline
from retailpulse360.features import TARGET


def test_feature_matrix_excludes_ids_and_target(model_frame):
    X, y = modeling.feature_matrix(model_frame)
    assert "customer_id" not in X.columns and TARGET not in X.columns and "snapshot_date" not in X.columns
    assert len(X) == len(y) == len(model_frame)


def test_split_is_stratified_and_reproducible(model_frame):
    X, y = modeling.feature_matrix(model_frame)
    X_train, X_test, y_train, y_test = modeling.split_data(X, y)
    assert abs(y_train.mean() - y_test.mean()) < 0.01
    again = modeling.split_data(X, y)
    assert X_test.index.equals(again[1].index)
    assert set(X_train.index).isdisjoint(X_test.index)


def test_preprocessing_fitted_on_training_data_only(model_frame):
    X, y = modeling.feature_matrix(model_frame)
    X_train, X_test, y_train, _ = modeling.split_data(X, y)
    model = modeling.build_models()["Logistic Regression"].fit(X_train, y_train)
    scaler = model.named_steps["preprocess"].named_transformers_["numeric"]
    numeric = list(scaler.feature_names_in_)
    np.testing.assert_allclose(scaler.mean_, X_train[numeric].mean().to_numpy())
    assert not np.allclose(scaler.mean_, X[numeric].mean().to_numpy())


def test_baseline_model_beats_random(model_frame):
    X, y = modeling.feature_matrix(model_frame)
    X_train, X_test, y_train, y_test = modeling.split_data(X, y)
    model = modeling.build_models()["Logistic Regression"].fit(X_train, y_train)
    assert roc_auc_score(y_test, model.predict_proba(X_test)[:, 1]) > 0.7


def test_classification_metrics_confusion_counts():
    y_true = np.array([0, 0, 1, 1])
    proba = np.array([0.1, 0.6, 0.4, 0.9])
    result = modeling.classification_metrics(y_true, proba, threshold=0.5)
    assert (result["true_negatives"], result["false_positives"], result["false_negatives"], result["true_positives"]) == (1, 1, 1, 1)
    assert result["precision"] == 0.5 and result["recall"] == 0.5


def test_threshold_table_recall_never_increases_with_threshold():
    rng = np.random.default_rng(0)
    y = rng.integers(0, 2, 500)
    proba = np.clip(y * 0.3 + rng.random(500) * 0.7, 0, 1)
    table = modeling.threshold_table(y, proba)
    assert (np.diff(table["recall"].to_numpy()) <= 1e-12).all()


def test_capacity_table_contacting_everyone_reaches_all_churners():
    y = np.array([0, 1, 0, 1, 1, 0, 0, 0, 0, 1])
    proba = np.linspace(0, 1, 10)
    table = modeling.capacity_table(y, proba, contact_shares=(1.0,))
    assert table.loc[0, "recall"] == 1.0
    assert table.loc[0, "lift_vs_random"] == pytest.approx(1.0)


def test_select_model_prefers_simpler_model_when_close():
    cv = pd.DataFrame({"model": ["Logistic Regression", "Random Forest"], "cv_pr_auc_mean": [0.600, 0.605]})
    assert pipeline.select_model(cv) == "Logistic Regression"
    cv.loc[1, "cv_pr_auc_mean"] = 0.65
    assert pipeline.select_model(cv) == "Random Forest"


def test_risk_band_edges():
    bands = modeling.risk_band(np.array([0.0, 0.29, 0.3, 0.59, 0.6, 1.0]))
    assert list(bands.astype(str)) == ["Low", "Low", "Medium", "Medium", "High", "High"]
