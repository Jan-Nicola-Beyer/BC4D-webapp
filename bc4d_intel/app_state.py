"""Central application state — all data flows through this object.

No globals. Every screen reads/writes through AppState.
Persists to sessions/latest.bc4d as JSON after every major action.
"""

from __future__ import annotations
import json, os, logging
from dataclasses import dataclass, field, asdict
from typing import Optional, List, Dict, Any

from bc4d_intel.constants import SESSION_DIR

log = logging.getLogger("bc4d_intel.state")


@dataclass
class AppState:
    """Single source of truth for the current analysis session."""

    # ── File paths ──
    pre_survey_path: str = ""
    post_survey_path: str = ""

    # ── Raw data (DataFrames serialized as list-of-dicts for JSON) ──
    pre_data: Optional[List[Dict]] = None
    post_data: Optional[List[Dict]] = None

    # ── Column roles (detected or manually assigned) ──
    # {col_name: "likert" | "free_text" | "demographic" | "metadata" | "pseudokey" | "ignore"}
    pre_columns: Dict[str, str] = field(default_factory=dict)
    post_columns: Dict[str, str] = field(default_factory=dict)

    # ── Panel matching ──
    matched_pairs: int = 0
    unmatched_pre: int = 0
    unmatched_post: int = 0
    merged_data: Optional[List[Dict]] = None

    # ── Staffel (cohort) info ──
    staffel_name: str = ""
    staffel_date: str = ""
    n_pre: int = 0
    n_post: int = 0

    # ── AI tagging results ──
    tagged_responses: Dict[str, List[Dict]] = field(default_factory=dict)
    # {question_col: [{text, tag, confidence, human_override}, ...]}

    # ── Report sections ──
    report_sections: Dict[str, str] = field(default_factory=dict)
    # {section_name: markdown_text}

    # ── Settings ──
    api_key: str = ""
    theme: str = "dark"

    def save(self, path: str = ""):
        """Persist state to JSON file."""
        if not path:
            path = os.path.join(SESSION_DIR, "latest.bc4d")
        try:
            data = asdict(self)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)
            log.info("Session saved to %s", path)
        except Exception as e:
            log.warning("Failed to save session: %s", e)

    @classmethod
    def load(cls, path: str = "") -> "AppState":
        """Load state from JSON file."""
        if not path:
            path = os.path.join(SESSION_DIR, "latest.bc4d")
        if not os.path.exists(path):
            return cls()
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            state = cls(**{k: v for k, v in data.items()
                          if k in cls.__dataclass_fields__})
            log.info("Session loaded from %s", path)
            return state
        except Exception as e:
            log.warning("Failed to load session: %s", e)
            return cls()
