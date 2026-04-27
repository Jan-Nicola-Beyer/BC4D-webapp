"""Statistical analysis engine — descriptive stats, paired tests, effect sizes.

All calculations in pure pandas/scipy. No LLM needed.
Handles three analysis levels:
  1. Pre-all (baseline): descriptive stats for all pre-survey respondents
  2. Post-all (outcomes): descriptive stats for all post-survey respondents
  3. Matched panel: paired comparisons, individual-level change, effect sizes

Improvement #4: Added Cronbach's alpha, confidence intervals, Bonferroni correction.
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
        return {"n": 0, "mean": None, "sd": None, "median": None,
                "ci_lower": None, "ci_upper": None, "distribution": {},
                "pct_agree": None, "pct_disagree": None}

    n = int(len(clean))
    mean = float(clean.mean())
    sd = float(clean.std())

    # 95% confidence interval for the mean
    from scipy.stats import t as t_dist
    se = sd / np.sqrt(n) if n > 1 else 0
    ci_margin = t_dist.ppf(0.975, n - 1) * se if n > 1 else 0
    ci_lower = round(mean - ci_margin, 2)
    ci_upper = round(mean + ci_margin, 2)

    dist = {v: int((clean == v).sum()) for v in range(1, 6)}

    # Percentage who agree (4-5) vs disagree (1-2)
    pct_agree = round((dist.get(4, 0) + dist.get(5, 0)) / n * 100, 1)
    pct_disagree = round((dist.get(1, 0) + dist.get(2, 0)) / n * 100, 1)

    return {
        "n": n,
        "mean": round(mean, 2),
        "sd": round(sd, 2),
        "median": round(float(clean.median()), 1),
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "distribution": dist,
        "pct_agree": pct_agree,
        "pct_disagree": pct_disagree,
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


def cronbachs_alpha(df: pd.DataFrame, columns: List[str]) -> Optional[float]:
    """Compute Cronbach's alpha for internal consistency of a Likert scale.

    Args:
        df: DataFrame with numeric Likert columns
        columns: list of column names to include

    Returns alpha (0-1) or None if computation fails.
    """
    from bc4d_intel.core.data_loader import normalize_likert_column

    items = pd.DataFrame()
    for col in columns:
        if col in df.columns:
            items[col] = normalize_likert_column(df[col])

    items = items.dropna()
    n_items = len(items.columns)
    if n_items < 2 or len(items) < 5:
        return None

    item_vars = items.var(axis=0, ddof=1)
    total_var = items.sum(axis=1).var(ddof=1)

    if total_var == 0:
        return None

    alpha = (n_items / (n_items - 1)) * (1 - item_vars.sum() / total_var)
    return round(float(alpha), 3)


def paired_comparison(pre_series: pd.Series, post_series: pd.Series,
                      bonferroni_n: int = 1) -> Dict:
    """Paired comparison for matched panel data.

    Uses Wilcoxon signed-rank test (non-parametric, appropriate for Likert data).
    Supports Bonferroni correction via bonferroni_n (number of simultaneous tests).
    """
    pre = pd.to_numeric(pre_series, errors="coerce")
    post = pd.to_numeric(post_series, errors="coerce")

    combined = pd.DataFrame({"pre": pre, "post": post}).dropna()
    if len(combined) < 5:
        return {"n_pairs": len(combined), "error": "Too few pairs (<5)"}

    diff = combined["post"] - combined["pre"]
    n = len(combined)
    mean_change = float(diff.mean())
    sd_change = float(diff.std()) if n > 1 else 0

    # 95% CI for mean change
    from scipy.stats import t as t_dist
    se = sd_change / np.sqrt(n) if n > 1 else 0
    ci_margin = t_dist.ppf(0.975, n - 1) * se if n > 1 else 0
    ci_lower = round(mean_change - ci_margin, 2)
    ci_upper = round(mean_change + ci_margin, 2)

    # Cohen's d (paired)
    pooled_sd = float(np.sqrt((combined["pre"].var() + combined["post"].var()) / 2))
    cohens_d = mean_change / pooled_sd if pooled_sd > 0 else 0

    # Wilcoxon signed-rank test
    p_value = None
    try:
        from scipy.stats import wilcoxon
        non_zero = diff[diff != 0]
        if len(non_zero) >= 5:
            stat, p_value = wilcoxon(non_zero)
            p_value = round(float(p_value), 4)
    except Exception:
        pass

    # Bonferroni correction
    p_corrected = round(p_value * bonferroni_n, 4) if p_value is not None else None
    if p_corrected is not None:
        p_corrected = min(p_corrected, 1.0)

    # Direction & effect size
    if mean_change > 0.1:
        direction = "improvement"
    elif mean_change < -0.1:
        direction = "decline"
    else:
        direction = "stable"

    if abs(cohens_d) >= 0.8:
        effect_label = "large"
    elif abs(cohens_d) >= 0.5:
        effect_label = "medium"
    elif abs(cohens_d) >= 0.2:
        effect_label = "small"
    else:
        effect_label = "negligible"

    return {
        "n_pairs": int(n),
        "pre_mean": round(float(combined["pre"].mean()), 2),
        "post_mean": round(float(combined["post"].mean()), 2),
        "mean_change": round(mean_change, 2),
        "sd_change": round(sd_change, 2),
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "cohens_d": round(cohens_d, 2),
        "effect_label": effect_label,
        "p_value": p_value,
        "p_corrected": p_corrected,
        "significant": p_corrected < 0.05 if p_corrected is not None else None,
        "direction": direction,
        "improved_pct": round(float((diff > 0).sum() / n * 100), 1),
        "declined_pct": round(float((diff < 0).sum() / n * 100), 1),
        "unchanged_pct": round(float((diff == 0).sum() / n * 100), 1),
    }


def practical_transfer_stats(df: pd.DataFrame, roles: Dict[str, str]) -> List[Dict]:
    """Aggregate frequency-scale items for practical transfer analysis.

    Combines "manchmal" + "regelmäßig" as "applied" percentage.
    """
    from bc4d_intel.core.data_loader import normalize_likert_column

    results = []
    freq_cols = [c for c, r in roles.items() if r == "frequency"]
    for col in freq_cols:
        series = normalize_likert_column(df[col])
        clean = series.dropna()
        n = len(clean)
        if n == 0:
            continue
        # 3+ = "manchmal" or better = "applied"
        n_applied = int((clean >= 3).sum())
        pct_applied = round(n_applied / n * 100, 1)
        results.append({
            "column": col,
            "label": col,
            "n": n,
            "n_applied": n_applied,
            "pct_applied": pct_applied,
            "mean": round(float(clean.mean()), 2),
        })
    return results


def analyze_all_likert(df: pd.DataFrame, roles: Dict[str, str]) -> List[Dict]:
    """Analyze all Likert columns in a DataFrame."""
    from bc4d_intel.core.data_loader import normalize_likert_column

    results = []
    for col, role in roles.items():
        if role in ("likert", "frequency", "relevance"):
            series = normalize_likert_column(df[col])
            stats = descriptive_stats(series)
            results.append({"column": col, "label": col, "role": role, "stats": stats})
    return results


def analyze_matched_likert(
    matched_df: pd.DataFrame,
    pre_roles: Dict[str, str],
    post_roles: Dict[str, str],
) -> List[Dict]:
    """Find matching Likert columns between pre/post and run paired comparisons.

    Applies Bonferroni correction based on number of simultaneous tests.
    """
    from bc4d_intel.core.data_loader import normalize_likert_column
    from difflib import SequenceMatcher

    pre_likert = [c for c, r in pre_roles.items() if r in ("likert", "frequency", "relevance")]
    post_likert = [c for c, r in post_roles.items() if r in ("likert", "frequency", "relevance")]

    # First pass: find all matches
    matches = []
    used_post = set()
    for pre_col in pre_likert:
        best_match, best_ratio = None, 0
        for post_col in post_likert:
            if post_col in used_post:
                continue
            pre_norm = " ".join(pre_col.lower().split())
            post_norm = " ".join(post_col.lower().split())
            ratio = SequenceMatcher(None, pre_norm, post_norm).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_match = post_col
        if best_match and best_ratio > 0.6:
            used_post.add(best_match)
            matches.append((pre_col, best_match, best_ratio))

    # Second pass: run comparisons with Bonferroni correction
    n_tests = len(matches)
    results = []
    for pre_col, post_col, ratio in matches:
        pre_merged = pre_col + "_pre" if pre_col + "_pre" in matched_df.columns else pre_col
        post_merged = post_col + "_post" if post_col + "_post" in matched_df.columns else post_col

        if pre_merged in matched_df.columns and post_merged in matched_df.columns:
            pre_series = normalize_likert_column(matched_df[pre_merged])
            post_series = normalize_likert_column(matched_df[post_merged])
            comparison = paired_comparison(pre_series, post_series, bonferroni_n=n_tests)
            results.append({
                "pre_column": pre_col, "post_column": post_col,
                "label": pre_col, "match_ratio": round(ratio, 2),
                "comparison": comparison,
            })

    return results


def analyze_demographics(df: pd.DataFrame, roles: Dict[str, str]) -> List[Dict]:
    """Analyze all demographic columns in a DataFrame."""
    results = []
    for col, role in roles.items():
        if role == "demographic":
            stats = frequency_stats(df[col])
            results.append({"column": col, "label": col, "role": role, "stats": stats})
    return results
