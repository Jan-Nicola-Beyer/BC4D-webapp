"""Chart generation — matplotlib/seaborn charts for BC4D evaluation.

All charts return a matplotlib Figure object that can be embedded
in customtkinter via FigureCanvasTkAgg.

Chart types:
  1. Likert stacked bar (horizontal, diverging from center)
  2. Pre/post grouped bar comparison
  3. Change histogram (distribution of individual changes)
  4. Demographic pie/donut
  5. Frequency grouped bar
  6. Summary overview (key metrics as big numbers)
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional

import pandas as pd
import numpy as np

log = logging.getLogger("bc4d_intel.core.charts")

# Lazy matplotlib import
_mpl_ready = False


def _ensure_mpl():
    global _mpl_ready
    if _mpl_ready:
        return
    import matplotlib
    matplotlib.use("Agg")  # non-interactive backend
    _mpl_ready = True


def _apply_style(fig, ax):
    """Apply consistent dark-mode-friendly style with readable font sizes."""
    fig.patch.set_facecolor("#0d1117")
    ax.set_facecolor("#161b22")
    ax.tick_params(colors="#9ca3af", labelsize=11)
    ax.xaxis.label.set_color("#9ca3af")
    ax.xaxis.label.set_fontsize(11)
    ax.yaxis.label.set_color("#9ca3af")
    ax.yaxis.label.set_fontsize(11)
    ax.title.set_color("#e6edf3")
    ax.title.set_fontsize(14)
    for spine in ax.spines.values():
        spine.set_color("#30363d")


LIKERT_COLORS = ["#dc2626", "#f97316", "#facc15", "#84cc16", "#22c55e"]
LIKERT_LABELS = ["1 (gar nicht)", "2", "3 (teils)", "4", "5 (voll)"]


def likert_stacked_bar(items: List[Dict], title: str = "Likert Scale Distribution"):
    """Horizontal stacked bar chart for Likert items.

    Args:
        items: list of {label, stats: {distribution: {1:n, 2:n, ...}, n}}
    """
    _ensure_mpl()
    import matplotlib.pyplot as plt

    n_items = len(items)
    if n_items == 0:
        return _empty_chart("No Likert items to display")

    fig, ax = plt.subplots(figsize=(10, max(3, n_items * 0.5 + 1)))
    _apply_style(fig, ax)

    labels = [item["label"][:50] for item in items]
    y_pos = range(n_items)

    for val in range(1, 6):
        widths = []
        lefts = []
        for item in items:
            dist = item["stats"]["distribution"]
            total = item["stats"]["n"]
            pct = dist.get(val, 0) / max(total, 1) * 100
            widths.append(pct)
            left = sum(dist.get(v, 0) / max(total, 1) * 100 for v in range(1, val))
            lefts.append(left)

        ax.barh(y_pos, widths, left=lefts, height=0.6,
                color=LIKERT_COLORS[val - 1], label=LIKERT_LABELS[val - 1],
                edgecolor="#0d1117", linewidth=0.5)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xlabel("Percentage (%)", fontsize=11)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    ax.legend(loc="upper right", fontsize=10, facecolor="#161b22", edgecolor="#30363d",
              labelcolor="#9ca3af")
    ax.invert_yaxis()

    # Add mean + n labels on right
    for i, item in enumerate(items):
        mean = item["stats"].get("mean")
        n = item["stats"].get("n", 0)
        if mean:
            ax.text(102, i, f"M={mean} (n={n})", va="center", fontsize=10, color="#e6edf3")

    fig.tight_layout()
    return fig


def pre_post_grouped_bar(comparisons: List[Dict], title: str = "Pre/Post Comparison"):
    """Grouped bar chart comparing pre and post means for matched items."""
    _ensure_mpl()
    import matplotlib.pyplot as plt

    valid = [c for c in comparisons if "error" not in c.get("comparison", {})]
    if not valid:
        return _empty_chart("No matched comparisons available")

    n = len(valid)
    fig, ax = plt.subplots(figsize=(10, max(3, n * 0.6 + 1)))
    _apply_style(fig, ax)

    labels = [c["label"][:45] for c in valid]
    y = np.arange(n)
    height = 0.35

    pre_means = [c["comparison"]["pre_mean"] for c in valid]
    post_means = [c["comparison"]["post_mean"] for c in valid]

    ax.barh(y - height / 2, pre_means, height, label="Pre",
            color="#6366f1", edgecolor="#0d1117")
    ax.barh(y + height / 2, post_means, height, label="Post",
            color="#22c55e", edgecolor="#0d1117")

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xlabel("Mean (1-5)", fontsize=11)
    ax.set_xlim(0, 5.8)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    ax.legend(fontsize=11, facecolor="#161b22", edgecolor="#30363d", labelcolor="#9ca3af")
    ax.invert_yaxis()

    # Add change indicators with effect size
    for i, c in enumerate(valid):
        change = c["comparison"]["mean_change"]
        effect = c["comparison"].get("effect_label", "")
        color = "#22c55e" if change > 0 else ("#dc2626" if change < 0 else "#9ca3af")
        sign = "+" if change > 0 else ""
        ax.text(5.3, i, f"{sign}{change} ({effect})", va="center", fontsize=10,
                color=color, fontweight="bold")

    fig.tight_layout()
    return fig


def change_histogram(comparisons: List[Dict], title: str = "Distribution of Change"):
    """Bar chart showing % improved / unchanged / declined per item."""
    _ensure_mpl()
    import matplotlib.pyplot as plt

    valid = [c for c in comparisons if "error" not in c.get("comparison", {})]
    if not valid:
        return _empty_chart("No matched comparisons available")

    n = len(valid)
    fig, ax = plt.subplots(figsize=(10, max(3, n * 0.5 + 1)))
    _apply_style(fig, ax)

    labels = [c["label"][:45] for c in valid]
    y = np.arange(n)

    improved = [c["comparison"]["improved_pct"] for c in valid]
    unchanged = [c["comparison"]["unchanged_pct"] for c in valid]
    declined = [c["comparison"]["declined_pct"] for c in valid]

    ax.barh(y, improved, height=0.6, label="Improved", color="#22c55e")
    ax.barh(y, unchanged, height=0.6, left=improved, label="Unchanged", color="#facc15")
    ax.barh(y, declined, height=0.6,
            left=[i + u for i, u in zip(improved, unchanged)],
            label="Declined", color="#dc2626")

    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=10)
    ax.set_xlabel("Percentage (%)", fontsize=11)
    ax.set_title(title, fontsize=14, fontweight="bold", pad=12)
    ax.legend(fontsize=11, facecolor="#161b22", edgecolor="#30363d", labelcolor="#9ca3af")
    ax.invert_yaxis()

    fig.tight_layout()
    return fig


def demographic_pie(series: pd.Series, title: str = "Demographics"):
    """Pie/donut chart for demographic distribution."""
    _ensure_mpl()
    import matplotlib.pyplot as plt

    counts = series.value_counts(dropna=True)
    if len(counts) == 0:
        return _empty_chart("No demographic data")

    fig, ax = plt.subplots(figsize=(6, 5))
    fig.patch.set_facecolor("#0d1117")

    colors = ["#C8175D", "#0077B6", "#059669", "#d97706", "#6366f1",
              "#ec4899", "#14b8a6", "#f59e0b"]

    # Format labels with count: "Weiblich (191)"
    pie_labels = [f"{k} ({v})" for k, v in zip(counts.index, counts.values)]

    wedges, texts, autotexts = ax.pie(
        counts.values, labels=pie_labels, autopct="%1.0f%%",
        colors=colors[:len(counts)], startangle=90,
        wedgeprops=dict(width=0.65, edgecolor="#0d1117"),
        textprops=dict(color="#e6edf3", fontsize=11),
    )
    for t in autotexts:
        t.set_fontsize(10)
        t.set_color("#ffffff")
        t.set_fontweight("bold")

    ax.set_title(title, fontsize=14, fontweight="bold", color="#e6edf3", pad=12)
    fig.tight_layout()
    return fig


def _empty_chart(message: str):
    """Return a placeholder chart with a message."""
    _ensure_mpl()
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 3))
    _apply_style(fig, ax)
    ax.text(0.5, 0.5, message, ha="center", va="center",
            fontsize=12, color="#6b7280", transform=ax.transAxes)
    ax.set_xticks([])
    ax.set_yticks([])
    return fig
