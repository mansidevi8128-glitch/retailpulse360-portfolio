"""Consistent matplotlib chart helpers used by the notebooks and report pipeline.

Style rules: one y-axis per chart (no dual axes), a single blue for single
series, a fixed categorical colour order, recessive grid, direct labels only
where they help.
"""

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

from .config import FIGURES_DIR, GRID_COLOR, INK, INK_MUTED, INK_SECONDARY, NEGATIVE_COLOR, PALETTE, PRIMARY_COLOR, SURFACE


def apply_style() -> None:
    plt.rcParams.update(
        {
            "figure.facecolor": SURFACE,
            "axes.facecolor": SURFACE,
            "axes.edgecolor": "#c3c2b7",
            "axes.labelcolor": INK_SECONDARY,
            "axes.titlecolor": INK,
            "axes.titlesize": 12,
            "axes.titleweight": "bold",
            "axes.titlelocation": "left",
            "axes.labelsize": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "axes.grid": True,
            "axes.axisbelow": True,
            "grid.color": GRID_COLOR,
            "grid.linewidth": 0.8,
            "xtick.color": INK_MUTED,
            "ytick.color": INK_MUTED,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.frameon": False,
            "legend.fontsize": 9,
            "lines.linewidth": 2,
            "font.family": "sans-serif",
            "figure.dpi": 100,
            "savefig.dpi": 130,
            "savefig.bbox": "tight",
        }
    )


def money(ax, axis: str = "y", decimals: int = 0) -> None:
    """Format an axis as US dollars with K/M suffixes."""

    def fmt(value, _):
        if abs(value) >= 1e6:
            return f"${value / 1e6:.1f}M"
        if abs(value) >= 1e4:
            return f"${value / 1e3:.0f}K"
        if abs(value) >= 1e3:
            return f"${value / 1e3:.1f}K"
        return f"${value:,.{decimals}f}"

    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(mticker.FuncFormatter(fmt))


def percent(ax, axis: str = "y", decimals: int = 0) -> None:
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.{decimals}f}%"))


def save(fig, name: str, directory: Path = FIGURES_DIR) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{name}.png"
    fig.savefig(path)
    return path


def _date_axis(ax, x_values) -> None:
    if pd.api.types.is_datetime64_any_dtype(x_values):
        locator = mdates.AutoDateLocator(minticks=4, maxticks=8)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))


def line_chart(df: pd.DataFrame, x: str, y: str, title: str, ylabel: str = "", color: str = PRIMARY_COLOR, ax=None, label=None, zero_baseline: bool = True):
    if ax is None:
        _, ax = plt.subplots(figsize=(9, 3.6))
    ax.plot(df[x], df[y], color=color, label=label)
    _date_axis(ax, df[x])
    if zero_baseline and df[y].min() >= 0:
        ax.set_ylim(bottom=0, top=df[y].max() * 1.1)
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.set_xlabel("")
    ax.grid(axis="x", visible=False)
    return ax


def multi_line_chart(df: pd.DataFrame, x: str, series: str, y: str, title: str, ylabel: str = "", ax=None):
    """One line per category in fixed palette order, with a legend."""
    if ax is None:
        _, ax = plt.subplots(figsize=(9, 3.8))
    for color, (name, group) in zip(PALETTE, df.groupby(series, sort=True)):
        ax.plot(group[x], group[y], color=color, label=name)
    _date_axis(ax, df[x])
    ax.set_title(title)
    ax.set_ylabel(ylabel)
    ax.grid(axis="x", visible=False)
    ax.legend(loc="upper left", ncol=3)
    return ax


def barh_chart(df: pd.DataFrame, category: str, value: str, title: str, xlabel: str = "", fmt: str = "{:,.0f}", color: str = PRIMARY_COLOR, ax=None, sort: bool = True):
    """Horizontal bar chart with value labels; negative values drawn in red."""
    data = df.sort_values(value) if sort else df.iloc[::-1]
    if ax is None:
        _, ax = plt.subplots(figsize=(8, 0.45 * len(data) + 1.2))
    colors = [NEGATIVE_COLOR if v < 0 else color for v in data[value]]
    bars = ax.barh(data[category].astype(str), data[value], color=colors, height=0.65)
    span = data[value].abs().max()
    for bar, v in zip(bars, data[value]):
        ax.text(bar.get_width() + (0.01 * span if v >= 0 else -0.01 * span), bar.get_y() + bar.get_height() / 2, fmt.format(v), va="center", ha="left" if v >= 0 else "right", fontsize=8.5, color=INK_SECONDARY)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.grid(axis="y", visible=False)
    ax.margins(x=0.15)
    return ax


def heatmap(matrix: pd.DataFrame, title: str, fmt: str = "{:.0f}", cmap: str = "Blues", ax=None, xlabel: str = "", ylabel: str = "", norm=None):
    """Annotated heatmap. Pass a matplotlib ``norm`` for diverging scales."""
    if ax is None:
        _, ax = plt.subplots(figsize=(11, 0.32 * len(matrix) + 1.5))
    values = matrix.to_numpy(dtype=float)
    image = ax.imshow(values, aspect="auto", cmap=cmap, norm=norm)
    ax.set_xticks(range(matrix.shape[1]), [str(c) for c in matrix.columns])
    ax.set_yticks(range(matrix.shape[0]), [str(i) for i in matrix.index])
    for i in range(values.shape[0]):
        for j in range(values.shape[1]):
            if not np.isnan(values[i, j]):
                rgba = image.cmap(image.norm(values[i, j]))
                luminance = 0.299 * rgba[0] + 0.587 * rgba[1] + 0.114 * rgba[2]
                ax.text(j, i, fmt.format(values[i, j]), ha="center", va="center", fontsize=7, color="white" if luminance < 0.5 else INK)
    ax.grid(False)
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    return ax


def indexed_profile_heatmap(indexed: pd.DataFrame, title: str, ax=None):
    """Diverging heatmap for values indexed to 100 = average (blue below, red above).

    The colour scale is clipped at 0-300 so one extreme value cannot wash out
    the rest; the printed numbers keep the true values.
    """
    from matplotlib.colors import TwoSlopeNorm

    return heatmap(indexed, title, cmap="RdBu_r", norm=TwoSlopeNorm(vmin=0, vcenter=100, vmax=300), ax=ax)


def roc_pr_curves(curves: dict, base_rate: float):
    """ROC and precision-recall curves for several models side by side."""
    from sklearn.metrics import precision_recall_curve, roc_curve

    fig, (ax_roc, ax_pr) = plt.subplots(1, 2, figsize=(11, 4.2))
    for color, (name, (y_true, proba)) in zip(PALETTE, curves.items()):
        fpr, tpr, _ = roc_curve(y_true, proba)
        precision, recall, _ = precision_recall_curve(y_true, proba)
        ax_roc.plot(fpr, tpr, color=color, label=name)
        ax_pr.plot(recall, precision, color=color, label=name)
    ax_roc.plot([0, 1], [0, 1], color=INK_MUTED, linestyle="--", linewidth=1, label="Random")
    ax_pr.axhline(base_rate, color=INK_MUTED, linestyle="--", linewidth=1, label=f"Base rate ({base_rate:.0%})")
    ax_roc.set(title="ROC curve (test set)", xlabel="False positive rate", ylabel="True positive rate")
    ax_pr.set(title="Precision-recall curve (test set)", xlabel="Recall", ylabel="Precision")
    ax_roc.legend(loc="lower right")
    ax_pr.legend(loc="upper right")
    return fig


def confusion_matrix_plot(metrics: dict, title: str):
    matrix = pd.DataFrame(
        [[metrics["true_negatives"], metrics["false_positives"]], [metrics["false_negatives"], metrics["true_positives"]]],
        index=["Actual: retained", "Actual: churned"],
        columns=["Predicted: retained", "Predicted: churned"],
    )
    fig, ax = plt.subplots(figsize=(5.2, 3.6))
    heatmap(matrix, title, fmt="{:,.0f}", ax=ax)
    return fig


def threshold_plot(table: pd.DataFrame, chosen: float | None = None):
    fig, ax = plt.subplots(figsize=(8, 3.8))
    for color, metric in zip(PALETTE, ["precision", "recall", "f1"]):
        ax.plot(table["threshold"], table[metric], color=color, label=metric.upper() if metric == "f1" else metric.capitalize())
    if chosen is not None:
        ax.axvline(chosen, color=INK_MUTED, linestyle="--", linewidth=1)
        ax.text(chosen + 0.01, 0.05, f"chosen = {chosen:.2f}", color=INK_SECONDARY, fontsize=8.5)
    ax.set(title="Precision / recall trade-off by threshold (test set)", xlabel="Probability threshold", ylabel="Score", ylim=(0, 1.02))
    ax.legend(loc="center right")
    return fig


def k_selection_plot(evaluation: pd.DataFrame, chosen_k: int):
    fig, (ax_elbow, ax_sil) = plt.subplots(1, 2, figsize=(11, 3.8))
    ax_elbow.plot(evaluation["k"], evaluation["inertia"], color=PRIMARY_COLOR, marker="o")
    ax_sil.plot(evaluation["k"], evaluation["silhouette"], color=PRIMARY_COLOR, marker="o")
    for ax in (ax_elbow, ax_sil):
        ax.axvline(chosen_k, color=INK_MUTED, linestyle="--", linewidth=1)
        ax.set_xlabel("Number of clusters (k)")
    ax_elbow.set(title="Elbow curve (inertia)", ylabel="Within-cluster sum of squares")
    ax_sil.set(title="Silhouette score", ylabel="Silhouette")
    return fig
