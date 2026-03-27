"""Excel data loading + automated column role detection.

Handles the key challenge: pre-survey uses TEXT Likert labels
("teils/teils", "Stimme eher nicht zu") while post-survey uses
NUMERIC values (1-5) or mixed ("5 = sehr sicher"). This module
normalizes everything to numeric 1-5 for analysis.
"""

from __future__ import annotations
import logging, re
from typing import Dict, List, Tuple, Optional

import pandas as pd

log = logging.getLogger("bc4d_intel.core.data_loader")


# ── Likert text → numeric mappings ───────────────────────────────

# Agreement scale (Stimme ... zu / trifft ... zu)
AGREEMENT_MAP = {
    "stimme voll und ganz zu": 5, "trifft voll und ganz zu": 5,
    "stimme eher zu": 4, "trifft eher zu": 4,
    "teils/teils": 3, "teils / teils": 3, "teil/teils": 3,
    "stimme eher nicht zu": 4, "trifft eher nicht zu": 2,
    "stimme überhaupt nicht zu": 1, "trifft gar nicht zu": 1,
    "stimme eher nicht zu": 2,
}

# Confidence scale (sicher)
CONFIDENCE_MAP = {
    "sehr sicher": 5, "5 = sehr sicher": 5,
    "eher sicher": 4, "4 = eher sicher": 4,
    "teils/teils": 3, "3 = teils/teils": 3,
    "eher nicht sicher": 2, "2 = eher nicht sicher": 2,
    "überhaupt nicht sicher": 1, "1 = überhaupt nicht sicher": 1,
}

# Frequency scale
FREQUENCY_MAP = {
    "regelmäßig": 4, "regelm\u00e4\u00dfig": 4,
    "manchmal": 3, "manchmal.": 3,
    "selten": 2, "selten.": 2,
    "nie": 1,
}

# Relevance scale
RELEVANCE_MAP = {
    "sehr relevant": 5, "5 = sehr relevant": 5,
    "eher relevant": 4, "4 = eher relevant": 4,
    "teils/teils": 3, "3 = teils/teils": 3,
    "eher nicht relevant": 2, "2 = eher nicht relevant": 2,
    "überhaupt nicht relevant": 1, "1 = überhaupt nicht relevant": 1,
    "gar nicht relevant": 1, "1 = gar nicht relevant": 1,
}

# Combined: try all maps
ALL_LIKERT_MAPS = [AGREEMENT_MAP, CONFIDENCE_MAP, FREQUENCY_MAP, RELEVANCE_MAP]


def _text_to_numeric(value) -> Optional[float]:
    """Convert a text Likert label to numeric 1-5."""
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        if 1 <= value <= 5:
            return float(value)
        return None

    text = str(value).strip().lower()

    # Try extracting leading number ("5 = sehr sicher" → 5)
    m = re.match(r'^(\d)\s*=', text)
    if m:
        return float(m.group(1))

    # Try all Likert maps
    for mapping in ALL_LIKERT_MAPS:
        if text in mapping:
            return float(mapping[text])

    return None


# ── Column role detection ────────────────────────────────────────

def detect_column_roles(df: pd.DataFrame) -> Dict[str, str]:
    """Auto-detect column roles from data patterns.

    Returns {col_name: role} where role is one of:
    - "metadata": ID, timestamps, email, name
    - "pseudokey": street letters or birthday day
    - "demographic": gender, age, education
    - "likert": Likert-scale items (1-5, text or numeric)
    - "frequency": behavioral frequency items
    - "free_text": open-ended text responses
    - "ignore": empty or irrelevant columns
    """
    roles = {}

    for col in df.columns:
        col_lower = col.lower()
        series = df[col]
        n_unique = series.nunique()
        n_valid = series.notna().sum()

        # Skip empty columns
        if n_valid == 0:
            roles[col] = "ignore"
            continue

        # Metadata: IDs, timestamps, email, name
        if col_lower in ("id", "name", "e-mail", "email"):
            roles[col] = "metadata"
            continue
        if "zeit" in col_lower or "time" in col_lower or "änderung" in col_lower:
            roles[col] = "metadata"
            continue

        # Pseudokey: street letters
        if "buchstaben" in col_lower and "straße" in col_lower or "stra\u00dfe" in col_lower:
            roles[col] = "pseudokey_street"
            continue
        if "tag des monats" in col_lower or "geburtstag" in col_lower:
            roles[col] = "pseudokey_birthday"
            continue

        # Demographics
        if any(w in col_lower for w in ["identifizieren", "geschlecht", "gender"]):
            roles[col] = "demographic"
            continue
        if "wie alt" in col_lower or "alter" == col_lower:
            roles[col] = "demographic"
            continue
        if "bildungsabschluss" in col_lower or "education" in col_lower:
            roles[col] = "demographic"
            continue

        # Try Likert detection: can most values be mapped to 1-5?
        if n_unique <= 7:
            numeric_count = sum(1 for v in series.dropna()
                                if _text_to_numeric(v) is not None)
            ratio = numeric_count / max(n_valid, 1)
            if ratio >= 0.7:
                # Distinguish frequency from agreement/confidence
                sample_vals = [str(v).lower() for v in series.dropna().head(20)]
                if any(w in " ".join(sample_vals) for w in ["nie", "selten", "manchmal", "regelmäßig"]):
                    roles[col] = "frequency"
                elif any(w in " ".join(sample_vals) for w in ["relevant", "nicht relevant"]):
                    roles[col] = "relevance"
                else:
                    roles[col] = "likert"
                continue

        # Free text: long strings, many unique values
        if series.dtype == object:
            avg_len = series.dropna().astype(str).str.len().mean()
            if avg_len > 30 and n_unique > 10:
                roles[col] = "free_text"
                continue

        # Default: check if it looks like a categorical with few values
        if n_unique <= 6 and series.dtype == object:
            roles[col] = "categorical"
            continue

        roles[col] = "other"

    return roles


def normalize_likert_column(series: pd.Series) -> pd.Series:
    """Convert a Likert column (text or numeric) to numeric 1-5."""
    return series.apply(_text_to_numeric)


# ── Main loading function ────────────────────────────────────────

def _clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Clean common data issues in survey exports.

    - Strip trailing semicolons from categorical values
      (e.g., "Weiblich;" → "Weiblich")
    - Strip whitespace from string values
    - Normalize unicode whitespace
    """
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = (df[col].astype(str)
                       .str.strip()
                       .str.rstrip(";")
                       .str.strip()
                       .replace("nan", pd.NA))
    return df


def load_survey(path: str) -> Tuple[pd.DataFrame, Dict[str, str]]:
    """Load an Excel survey file, clean it, and detect column roles.

    Returns (DataFrame, {col_name: role})
    """
    df = pd.read_excel(path)
    df = _clean_dataframe(df)
    log.info("Loaded %s: %d rows, %d columns", path.split("/")[-1].split("\\")[-1],
             len(df), len(df.columns))

    roles = detect_column_roles(df)

    # Count by role
    role_counts = {}
    for r in roles.values():
        role_counts[r] = role_counts.get(r, 0) + 1
    log.info("Column roles: %s", role_counts)

    return df, roles


def get_pseudokey(row, street_col: str, birthday_col: str) -> str:
    """Build pseudonymisation key: first 4 letters of street + zero-padded birthday day."""
    street = str(row.get(street_col, "")).strip().upper()[:4]
    birthday = str(row.get(birthday_col, "")).strip()
    # Zero-pad birthday day
    try:
        day = int(re.sub(r'\D', '', birthday))
        birthday = f"{day:02d}"
    except (ValueError, TypeError):
        birthday = birthday[:2]
    return f"{street}{birthday}"
