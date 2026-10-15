"""Customer segmentation with K-Means.

The churn target is never used as a clustering input; it is only joined
afterwards to describe the segments.
"""

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from .config import RANDOM_STATE
from .features import TARGET, assert_no_leakage

# RFM + engagement + profitability/discount/refund/support behaviour.
SEGMENT_FEATURES = [
    "days_since_last_purchase",
    "frequency_12m",
    "monetary_value_12m",
    "gross_margin_pct_12m",
    "avg_discount_pct_12m",
    "refund_rate_12m",
    "web_sessions_90d",
    "support_tickets_12m",
]
# Right-skewed counts/amounts get log1p before scaling.
LOG_FEATURES = ["days_since_last_purchase", "frequency_12m", "monetary_value_12m", "avg_discount_pct_12m", "web_sessions_90d", "support_tickets_12m"]

PROFILE_COLUMNS = [
    "days_since_last_purchase",
    "frequency_12m",
    "monetary_value_12m",
    "profit_12m",
    "avg_order_value_12m",
    "gross_margin_pct_12m",
    "avg_discount_pct_12m",
    "refund_rate_12m",
    "category_diversity_12m",
    "web_sessions_90d",
    "conversion_rate_90d",
    "support_tickets_12m",
    "never_purchased",
]


def _log_selected(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in LOG_FEATURES:
        if column in out:
            out[column] = np.log1p(out[column].clip(lower=0))
    return out


def build_transformer() -> Pipeline:
    return Pipeline([("log", FunctionTransformer(_log_selected)), ("scale", StandardScaler())])


def segment_matrix(df: pd.DataFrame, features=SEGMENT_FEATURES) -> np.ndarray:
    """Transformed, scaled feature matrix. Refuses to cluster on the target."""
    if TARGET in features:
        raise ValueError("The churn target must not be used as a segmentation feature.")
    assert_no_leakage(list(features))
    return build_transformer().fit_transform(df[list(features)])


def skew_table(df: pd.DataFrame, features=SEGMENT_FEATURES) -> pd.DataFrame:
    raw = df[list(features)]
    logged = _log_selected(raw)
    return pd.DataFrame({"skew_raw": raw.skew(), "skew_after_transform": logged.skew(), "log_transformed": [f in LOG_FEATURES for f in features]})


def evaluate_k(matrix: np.ndarray, k_values=range(2, 9), sample_size: int | None = None) -> pd.DataFrame:
    rows = []
    for k in k_values:
        model = KMeans(n_clusters=k, n_init=20, random_state=RANDOM_STATE).fit(matrix)
        score = silhouette_score(matrix, model.labels_, sample_size=sample_size, random_state=RANDOM_STATE)
        sizes = np.bincount(model.labels_)
        rows.append({"k": k, "inertia": model.inertia_, "silhouette": score, "smallest_cluster_pct": 100 * sizes.min() / len(matrix)})
    return pd.DataFrame(rows)


def choose_k(k_evaluation: pd.DataFrame, min_k: int = 3, min_cluster_pct: float = 5.0) -> int:
    """Highest-silhouette k among solutions with >= min_k clusters and no tiny cluster.

    k=2 is excluded by default because it only separates customers without a
    recent purchase from everyone else, which is already known without
    clustering. Clusters under 5% of customers are too small to act on.
    """
    eligible = k_evaluation[(k_evaluation["k"] >= min_k) & (k_evaluation["smallest_cluster_pct"] >= min_cluster_pct)]
    if eligible.empty:
        raise ValueError("No k satisfies the selection constraints.")
    return int(eligible.loc[eligible["silhouette"].idxmax(), "k"])


def fit_kmeans(matrix: np.ndarray, k: int, seed: int = RANDOM_STATE) -> KMeans:
    return KMeans(n_clusters=k, n_init=20, random_state=seed).fit(matrix)


def stability(matrix: np.ndarray, k: int, seeds=(1, 7, 21, 99, 2024), bootstrap_rounds: int = 10) -> dict:
    """Adjusted Rand index of labels across random seeds and bootstrap refits."""
    reference = fit_kmeans(matrix, k).labels_
    seed_ari = [adjusted_rand_score(reference, fit_kmeans(matrix, k, seed).labels_) for seed in seeds]
    rng = np.random.default_rng(RANDOM_STATE)
    boot_ari = []
    for _ in range(bootstrap_rounds):
        idx = rng.choice(len(matrix), size=len(matrix), replace=True)
        model = KMeans(n_clusters=k, n_init=10, random_state=RANDOM_STATE).fit(matrix[idx])
        boot_ari.append(adjusted_rand_score(reference, model.predict(matrix)))
    return {"seed_ari_min": float(np.min(seed_ari)), "seed_ari_mean": float(np.mean(seed_ari)), "bootstrap_ari_mean": float(np.mean(boot_ari)), "bootstrap_ari_min": float(np.min(boot_ari))}


def profile_segments(df: pd.DataFrame, labels, segment_col: str = "cluster") -> pd.DataFrame:
    """Mean business metrics per cluster plus size and (post-hoc) churn rate."""
    frame = df.assign(**{segment_col: labels})
    profile = frame.groupby(segment_col)[PROFILE_COLUMNS].mean()
    profile.insert(0, "customers", frame.groupby(segment_col).size())
    profile.insert(1, "share_pct", 100 * profile["customers"] / len(frame))
    profile["total_profit_12m"] = frame.groupby(segment_col)["profit_12m"].sum()
    profile["profit_share_pct"] = 100 * profile["total_profit_12m"] / frame["profit_12m"].sum()
    if TARGET in frame:
        profile["churn_rate_pct"] = 100 * frame.groupby(segment_col)[TARGET].mean()
    return profile


def name_segments(profile: pd.DataFrame) -> dict:
    """Assign business names from cluster profiles using transparent rules.

    Rules are applied in order; each cluster gets the first rule it matches,
    judged relative to the overall customer-weighted average.
    """
    weights = profile["customers"]
    overall = {c: np.average(profile[c], weights=weights) for c in profile.columns if c not in ("customers", "share_pct")}
    names = {}
    for cluster, row in profile.iterrows():
        if row["frequency_12m"] < 0.5:
            name = "Lapsed / No Recent Purchase"
        elif row["refund_rate_12m"] > 2 * overall["refund_rate_12m"] and row["refund_rate_12m"] > 0.10:
            name = "Refund-Prone Buyers"
        elif row["monetary_value_12m"] > 1.5 * overall["monetary_value_12m"]:
            name = "High-Value Loyalists"
        elif row["avg_discount_pct_12m"] > 1.5 * overall["avg_discount_pct_12m"]:
            name = "Promotion-Driven Frequent Buyers" if row["frequency_12m"] > overall["frequency_12m"] else "Promotion-Driven Buyers"
        elif row["avg_discount_pct_12m"] < 0.25 * overall["avg_discount_pct_12m"]:
            name = "Full-Price Regulars"
        elif row["support_tickets_12m"] > 2 * overall["support_tickets_12m"]:
            name = "Support-Heavy Customers"
        elif row["days_since_last_purchase"] > overall["days_since_last_purchase"]:
            name = "Cooling Occasional Buyers"
        else:
            name = "Steady Core Buyers"
        names[cluster] = name
    # Disambiguate if two clusters land on the same rule.
    seen = {}
    for cluster in sorted(names, key=lambda c: -profile.loc[c, "monetary_value_12m"]):
        base = names[cluster]
        seen[base] = seen.get(base, 0) + 1
        if seen[base] > 1:
            names[cluster] = f"{base} ({seen[base]})"
    return names
