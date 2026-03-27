"""Panel matching — link pre/post surveys via pseudonymisation keys.

Produces THREE analysis datasets:
  1. pre_all:    All pre-survey respondents (N=304) — baseline analysis
  2. post_all:   All post-survey respondents (N=147) — outcome analysis
  3. matched:    Only respondents in BOTH surveys — individual change analysis

This ensures NO data is lost from dropouts. Someone who only completed
the pre-survey still contributes to baseline statistics.
"""

from __future__ import annotations
import logging, re
from typing import Dict, Tuple
from collections import Counter

import pandas as pd

log = logging.getLogger("bc4d_intel.core.panel_matcher")


def build_pseudokey(row, street_col: str, birthday_col: str) -> str:
    """Build pseudonymisation key: first 4 letters of street + zero-padded birthday day.

    Examples: "KASS20", "KRAF31", "BURG05"
    """
    street = str(row.get(street_col, "")).strip().upper()
    # Take first 4 alpha characters (skip numbers, spaces)
    alpha_chars = [c for c in street if c.isalpha()]
    street_key = "".join(alpha_chars[:4])

    birthday = str(row.get(birthday_col, "")).strip()
    try:
        day = int(re.sub(r'\D', '', birthday))
        birthday_key = f"{day:02d}"
    except (ValueError, TypeError):
        birthday_key = "00"

    key = f"{street_key}{birthday_key}"
    return key if len(street_key) >= 3 else ""  # reject keys that are too short


def find_key_columns(roles: Dict[str, str]) -> Tuple[str, str]:
    """Find the pseudokey street and birthday columns from detected roles."""
    street_col = next((c for c, r in roles.items() if r == "pseudokey_street"), "")
    birthday_col = next((c for c, r in roles.items() if r == "pseudokey_birthday"), "")
    return street_col, birthday_col


def match_panels(
    pre_df: pd.DataFrame,
    pre_roles: Dict[str, str],
    post_df: pd.DataFrame,
    post_roles: Dict[str, str],
) -> Dict:
    """Match pre/post surveys and produce three analysis datasets.

    Returns dict with:
        pre_all:      DataFrame — all pre-survey respondents
        post_all:     DataFrame — all post-survey respondents
        matched:      DataFrame — merged pre+post for matched respondents
        stats:        dict — matching statistics
        pre_keys:     Series — pseudokeys for pre-survey
        post_keys:    Series — pseudokeys for post-survey
    """
    # Find pseudokey columns
    pre_street, pre_bday = find_key_columns(pre_roles)
    post_street, post_bday = find_key_columns(post_roles)

    if not pre_street or not pre_bday:
        log.warning("Pre-survey missing pseudokey columns")
        return _empty_result(pre_df, post_df, "Pre-survey missing pseudokey columns")
    if not post_street or not post_bday:
        log.warning("Post-survey missing pseudokey columns")
        return _empty_result(pre_df, post_df, "Post-survey missing pseudokey columns")

    # Build pseudokeys
    pre_df = pre_df.copy()
    post_df = post_df.copy()
    pre_df["_pseudokey"] = pre_df.apply(
        lambda r: build_pseudokey(r, pre_street, pre_bday), axis=1)
    post_df["_pseudokey"] = post_df.apply(
        lambda r: build_pseudokey(r, post_street, post_bday), axis=1)

    # Remove empty/invalid keys
    pre_valid = pre_df[pre_df["_pseudokey"] != ""]
    post_valid = post_df[post_df["_pseudokey"] != ""]

    pre_invalid = len(pre_df) - len(pre_valid)
    post_invalid = len(post_df) - len(post_valid)

    # Find matches
    pre_keys = set(pre_valid["_pseudokey"])
    post_keys = set(post_valid["_pseudokey"])
    matched_keys = pre_keys & post_keys

    # Handle duplicates: if a key appears multiple times, take the first occurrence
    pre_dedup = pre_valid.drop_duplicates(subset="_pseudokey", keep="first")
    post_dedup = post_valid.drop_duplicates(subset="_pseudokey", keep="first")

    pre_dupes = len(pre_valid) - len(pre_dedup)
    post_dupes = len(post_valid) - len(post_dedup)

    # Merge matched pairs (suffixes: _pre, _post)
    matched_df = pd.merge(
        pre_dedup, post_dedup,
        on="_pseudokey",
        how="inner",
        suffixes=("_pre", "_post"),
    )

    # Statistics
    stats = {
        "n_pre_total": len(pre_df),
        "n_post_total": len(post_df),
        "n_pre_valid_keys": len(pre_valid),
        "n_post_valid_keys": len(post_valid),
        "n_pre_invalid_keys": pre_invalid,
        "n_post_invalid_keys": post_invalid,
        "n_pre_duplicates": pre_dupes,
        "n_post_duplicates": post_dupes,
        "n_matched": len(matched_df),
        "n_pre_only": len(pre_keys - post_keys),
        "n_post_only": len(post_keys - pre_keys),
        "match_rate_pre": round(len(matched_df) / max(len(pre_dedup), 1) * 100, 1),
        "match_rate_post": round(len(matched_df) / max(len(post_dedup), 1) * 100, 1),
        "error": "",
    }

    log.info("Panel matching: %d pre × %d post → %d matched (%.1f%% of post)",
             stats["n_pre_total"], stats["n_post_total"],
             stats["n_matched"], stats["match_rate_post"])

    return {
        "pre_all": pre_df,       # ALL pre respondents (including unmatched)
        "post_all": post_df,     # ALL post respondents (including unmatched)
        "matched": matched_df,   # Only matched pairs (for pre/post comparison)
        "stats": stats,
        "pre_keys": pre_df["_pseudokey"],
        "post_keys": post_df["_pseudokey"],
    }


def _empty_result(pre_df, post_df, error_msg):
    """Return result with no matching when keys can't be built."""
    return {
        "pre_all": pre_df,
        "post_all": post_df,
        "matched": pd.DataFrame(),
        "stats": {
            "n_pre_total": len(pre_df),
            "n_post_total": len(post_df),
            "n_matched": 0,
            "match_rate_pre": 0,
            "match_rate_post": 0,
            "error": error_msg,
        },
        "pre_keys": pd.Series(dtype=str),
        "post_keys": pd.Series(dtype=str),
    }
