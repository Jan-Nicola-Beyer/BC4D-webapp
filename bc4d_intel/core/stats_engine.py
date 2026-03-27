"""Statistical analysis engine — descriptive stats, paired tests, effect sizes.

All calculations in pure pandas/scipy. No LLM needed.
Handles three analysis levels:
  1. Pre-all (baseline): descriptive stats for all pre-survey respondents
  2. Post-all (outcomes): descriptive stats for all post-survey respondents
  3. Matched panel: paired comparisons, individual-level change, effect sizes
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

log = logging.getLogger("bc4d_intel.core.stats")


def descriptive_stats(series: pd.Series) -> Dict:
    """Compute descriptive statistics for a numeric Likert series."""
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean) == 0:
        return {"n": 0, "mean": None, "sd": None, "median": None, "distribution": {}}

    dist = {}
    for v in range(1, 6):
        count = int((clean == v).sum())
        dist[v] = count

    return {
        "n": int(len(clean)),
        "mean": round(float(clean.mean()), 2),
        "sd": round(float(clean.std()), 2),
        "median": round(float(clean.median()), 1),
        "distribution": dist,
    }


def frequency_stats(series: pd.Series) -> Dict:
    """Compute frequency distribution for a categorical column."""
    counts = series.value_counts(dropna=True)
    total = int(counts.sum())
    return {
        "n": total,
        "categories": {str(k): int(v) for k, v in counts.items()},
        "percentages": {str(k): round(v / max(total, 1) * 100, 1)
                        for k, v in counts.items()},
    }


def paired_comparison(pre_series: pd.Series, post_series: pd.Series) -> Dict:
    """Paired comparison for matched panel data.

    Uses Wilcoxon signed-rank test (non-parametric, appropriate for Likert data).
    Returns: mean change, effect size (Cohen's d), p-value, direction.
    """
    pre = pd.to_numeric(pre_series, errors="coerce")
    post = pd.to_numeric(post_series, errors="coerce")

    # Align on index and drop pairs with missing values
    combined = pd.DataFrame({"pre": pre, "post": post}).dropna()
    if len(combined) < 5:
        return {"n_pairs": len(combined), "error": "Too few pairs (<5)"}

    diff = combined["post"] - combined["pre"]
    mean_change = float(diff.mean())
    sd_change = float(diff.std()) if len(diff) > 1 else 0

    # Cohen's d (paired)
    pooled_sd = float(np.sqrt((combined["pre"].var() + combined["post"].var()) / 2))
    cohens_d = mean_change / pooled_sd if pooled_sd > 0 else 0

    # Wilcoxon signed-rank test
    p_value = None
    try:
        from scipy.stats import wilcoxon
        # Only test if there are non-zero differences
        non_zero = diff[diff != 0]
        if len(non_zero) >= 5:
            stat, p_value = wilcoxon(non_zero)
            p_value = round(float(p_value), 4)
    except Exception:
        pass

    # Direction
    if mean_change > 0.1:
        direction = "improvement"
    elif mean_change < -0.1:
        direction = "decline"
    else:
        direction = "stable"

    # Effect size interpretation
    if abs(cohens_d) >= 0.8:
        effect_label = "large"
    elif abs(cohens_d) >= 0.5:
        effect_label = "medium"
    elif abs(cohens_d) >= 0.2:
        effect_label = "small"
    else:
        effect_label = "negligible"

    return {
        "n_pairs": int(len(combined)),
        "pre_mean": round(float(combined["pre"].mean()), 2),
        "post_mean": round(float(combined["post"].mean()), 2),
        "mean_change": round(mean_change, 2),
        "sd_change": round(sd_change, 2),
        "cohens_d": round(cohens_d, 2),
        "effect_label": effect_label,
        "p_value": p_value,
        "significant": p_value < 0.05 if p_value is not None else None,
        "direction": direction,
        "improved_pct": round(float((diff > 0).sum() / len(diff) * 100), 1),
        "declined_pct": round(float((diff < 0).sum() / len(diff) * 100), 1),
        "unchanged_pct": round(float((diff == 0).sum() / len(diff) * 100), 1),
    }


def analyze_all_likert(
    df: pd.DataFrame,
    roles: Dict[str, str],
    normalize_fn=None,
) -> List[Dict]:
    """Analyze all Likert columns in a DataFrame.

    Returns list of {column, label, stats} dicts.
    """
    from bc4d_intel.core.data_loader import normalize_likert_column

    results = []
    for col, role in roles.items():
        if role in ("likert", "frequency", "relevance"):
            series = normalize_likert_column(df[col]) if normalize_fn is None else normalize_fn(df[col])
            stats = descriptive_stats(series)
            # Truncate column name for display
            label = col[:60] if len(col) <= 60 else col[:57] + "..."
            results.append({
                "column": col,
                "label": label,
                "role": role,
                "stats": stats,
            })
    return results


def analyze_matched_likert(
    matched_df: pd.DataFrame,
    pre_roles: Dict[str, str],
    post_roles: Dict[str, str],
) -> List[Dict]:
    """Find matching Likert columns between pre/post and run paired comparisons.

    Matches columns by similar names (fuzzy) since pre/post may have
    slightly different column names for the same construct.
    """
    from bc4d_intel.core.data_loader import normalize_likert_column
    from difflib import SequenceMatcher

    pre_likert = [c for c, r in pre_roles.items() if r in ("likert", "frequency", "relevance")]
    post_likert = [c for c, r in post_roles.items() if r in ("likert", "frequency", "relevance")]

    results = []
    used_post = set()

    for pre_col in pre_likert:
        # Find best matching post column
        best_match = None
        best_ratio = 0
        for post_col in post_likert:
            if post_col in used_post:
                continue
            # Compare column names (normalize whitespace)
            pre_norm = " ".join(pre_col.lower().split())
            post_norm = " ".join(post_col.lower().split())
            ratio = SequenceMatcher(None, pre_norm, post_norm).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = post_col

        if best_match and best_ratio > 0.6:
            used_post.add(best_match)

            # Get pre/post columns from merged DataFrame
            pre_col_merged = pre_col + "_pre" if pre_col + "_pre" in matched_df.columns else pre_col
            post_col_merged = best_match + "_post" if best_match + "_post" in matched_df.columns else best_match

            if pre_col_merged in matched_df.columns and post_col_merged in matched_df.columns:
                pre_series = normalize_likert_column(matched_df[pre_col_merged])
                post_series = normalize_likert_column(matched_df[post_col_merged])

                comparison = paired_comparison(pre_series, post_series)
                label = pre_col[:55] if len(pre_col) <= 55 else pre_col[:52] + "..."

                results.append({
                    "pre_column": pre_col,
                    "post_column": best_match,
                    "label": label,
                    "match_ratio": round(best_ratio, 2),
                    "comparison": comparison,
                })

    return results
