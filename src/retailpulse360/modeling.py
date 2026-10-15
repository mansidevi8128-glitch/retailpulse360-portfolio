"""Churn-model training and evaluation helpers.

All preprocessing lives inside scikit-learn Pipelines, so scalers and encoders
are fitted on training folds only (no test-set information leaks into them).
"""

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, cross_validate, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .config import RANDOM_STATE
from .features import CATEGORICAL_FEATURES, MODEL_NUMERIC_FEATURES, TARGET, assert_no_leakage

TEST_SIZE = 0.25


def feature_matrix(df: pd.DataFrame, numeric=MODEL_NUMERIC_FEATURES, categorical=CATEGORICAL_FEATURES):
    """Return (X, y) after verifying no ID/target column is used as a predictor."""
    columns = list(numeric) + list(categorical)
    assert_no_leakage(columns)
    return df[columns].copy(), df[TARGET].astype(int).copy()


def split_data(X: pd.DataFrame, y: pd.Series, test_size: float = TEST_SIZE):
    """Stratified hold-out split so both sets keep the same churn rate."""
    return train_test_split(X, y, test_size=test_size, stratify=y, random_state=RANDOM_STATE)


def build_preprocessor(numeric=MODEL_NUMERIC_FEATURES, categorical=CATEGORICAL_FEATURES, scale: bool = True) -> ColumnTransformer:
    numeric_step = StandardScaler() if scale else "passthrough"
    return ColumnTransformer(
        [
            ("numeric", numeric_step, list(numeric)),
            ("categorical", OneHotEncoder(handle_unknown="ignore", sparse_output=False), list(categorical)),
        ],
        verbose_feature_names_out=False,
    )


def build_models(numeric=MODEL_NUMERIC_FEATURES, categorical=CATEGORICAL_FEATURES) -> dict[str, Pipeline]:
    """Candidate models: an interpretable baseline and two tree ensembles."""
    return {
        "Logistic Regression": Pipeline(
            [
                ("preprocess", build_preprocessor(numeric, categorical, scale=True)),
                ("model", LogisticRegression(max_iter=2000, C=1.0, random_state=RANDOM_STATE)),
            ]
        ),
        "Random Forest": Pipeline(
            [
                ("preprocess", build_preprocessor(numeric, categorical, scale=False)),
                ("model", RandomForestClassifier(n_estimators=400, min_samples_leaf=10, max_features="sqrt", n_jobs=-1, random_state=RANDOM_STATE)),
            ]
        ),
        "Gradient Boosting": Pipeline(
            [
                ("preprocess", build_preprocessor(numeric, categorical, scale=False)),
                ("model", HistGradientBoostingClassifier(learning_rate=0.05, max_iter=300, max_leaf_nodes=15, min_samples_leaf=40, l2_regularization=1.0, random_state=RANDOM_STATE)),
            ]
        ),
    }


def cross_validate_models(models: dict[str, Pipeline], X_train, y_train, folds: int = 5) -> pd.DataFrame:
    """Stratified k-fold CV on the training set only."""
    cv = StratifiedKFold(n_splits=folds, shuffle=True, random_state=RANDOM_STATE)
    rows = []
    for name, model in models.items():
        scores = cross_validate(model, X_train, y_train, cv=cv, scoring={"roc_auc": "roc_auc", "pr_auc": "average_precision"}, n_jobs=1)
        rows.append(
            {
                "model": name,
                "cv_roc_auc_mean": scores["test_roc_auc"].mean(),
                "cv_roc_auc_std": scores["test_roc_auc"].std(),
                "cv_pr_auc_mean": scores["test_pr_auc"].mean(),
                "cv_pr_auc_std": scores["test_pr_auc"].std(),
            }
        )
    return pd.DataFrame(rows)


def classification_metrics(y_true, probabilities, threshold: float = 0.5) -> dict:
    predictions = (np.asarray(probabilities) >= threshold).astype(int)
    tn, fp, fn, tp = confusion_matrix(y_true, predictions, labels=[0, 1]).ravel()
    return {
        "threshold": threshold,
        "roc_auc": roc_auc_score(y_true, probabilities),
        "pr_auc": average_precision_score(y_true, probabilities),
        "brier_score": brier_score_loss(y_true, probabilities),
        "accuracy": (tp + tn) / len(predictions),
        "precision": precision_score(y_true, predictions, zero_division=0),
        "recall": recall_score(y_true, predictions, zero_division=0),
        "f1": f1_score(y_true, predictions, zero_division=0),
        "true_negatives": int(tn),
        "false_positives": int(fp),
        "false_negatives": int(fn),
        "true_positives": int(tp),
        "flagged_customers": int(tp + fp),
    }


def threshold_table(y_true, probabilities, thresholds=None) -> pd.DataFrame:
    """Precision/recall/F1 and contact volume at each probability threshold."""
    thresholds = np.round(np.arange(0.1, 0.91, 0.05), 2) if thresholds is None else thresholds
    y_true = np.asarray(y_true)
    probabilities = np.asarray(probabilities)
    rows = []
    for t in thresholds:
        pred = probabilities >= t
        rows.append(
            {
                "threshold": float(t),
                "flagged_pct": 100 * pred.mean(),
                "precision": precision_score(y_true, pred, zero_division=0),
                "recall": recall_score(y_true, pred, zero_division=0),
                "f1": f1_score(y_true, pred, zero_division=0),
            }
        )
    return pd.DataFrame(rows)


def capacity_table(y_true, probabilities, contact_shares=(0.05, 0.10, 0.15, 0.20, 0.30, 0.40)) -> pd.DataFrame:
    """Precision and recall if the team can only contact the top X% riskiest customers.

    Contact capacity is an *assumption* for illustration; the data contains no
    information about retention-team capacity or campaign costs.
    """
    y_true = np.asarray(y_true)
    order = np.argsort(-np.asarray(probabilities), kind="stable")
    base_rate = y_true.mean()
    rows = []
    for share in contact_shares:
        n = int(round(share * len(y_true)))
        top = y_true[order[:n]]
        rows.append(
            {
                "contact_share_pct": 100 * share,
                "customers_contacted": n,
                "churners_reached": int(top.sum()),
                "precision": top.mean(),
                "recall": top.sum() / y_true.sum(),
                "lift_vs_random": top.mean() / base_rate,
            }
        )
    return pd.DataFrame(rows)


def best_f1_threshold(y_true, probabilities) -> float:
    table = threshold_table(y_true, probabilities, thresholds=np.round(np.arange(0.05, 0.951, 0.01), 2))
    return float(table.loc[table["f1"].idxmax(), "threshold"])


def logistic_coefficients(fitted_pipeline: Pipeline) -> pd.DataFrame:
    """Standardised logistic-regression coefficients (log-odds per 1 SD / per category)."""
    names = fitted_pipeline.named_steps["preprocess"].get_feature_names_out()
    coefs = fitted_pipeline.named_steps["model"].coef_[0]
    table = pd.DataFrame({"feature": names, "coefficient": coefs, "odds_ratio": np.exp(coefs)})
    return table.reindex(table["coefficient"].abs().sort_values(ascending=False).index).reset_index(drop=True)


def permutation_importance_table(fitted_pipeline: Pipeline, X, y, repeats: int = 10) -> pd.DataFrame:
    """Drop in test ROC-AUC when each original input column is shuffled."""
    result = permutation_importance(fitted_pipeline, X, y, scoring="roc_auc", n_repeats=repeats, random_state=RANDOM_STATE, n_jobs=1)
    return (
        pd.DataFrame({"feature": X.columns, "importance_mean": result.importances_mean, "importance_std": result.importances_std})
        .sort_values("importance_mean", ascending=False)
        .reset_index(drop=True)
    )


def risk_band(probabilities, bands=(0.0, 0.3, 0.6, 1.0001), labels=("Low", "Medium", "High")) -> pd.Series:
    return pd.cut(pd.Series(probabilities), bins=list(bands), labels=list(labels), right=False)
