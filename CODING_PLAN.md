# BC4D Intel — Coding Plan

## Overview

Python desktop app for the ISD Deutschland BC4D evaluation pipeline.
Covers the full workflow: raw Excel import → quantitative charts → AI-assisted qualitative coding → validated report draft.

**Three files to read before starting:**
- This file (`CODING_PLAN.md`) — full spec
- `CLAUDE.md` — auto-loaded context summary
- Ask the user: "Show me your existing GUI apps so I can match the framework and reuse shared code."

---

## Stack & Dependencies

```
customtkinter>=5.2    # or match user's existing framework
pandas>=2.0
openpyxl>=3.1
matplotlib>=3.8
seaborn>=0.13
scipy>=1.11
anthropic>=0.40
python-docx>=1.1
weasyprint>=61
keyring>=25
pyyaml>=6.0
```

---

## File Structure

Create all files as stubs in Phase 1. No logic until Phase 2+.

```
bc4d_intel/
├── main.py                     # Entry point — loads AppState, launches MainWindow
├── app_state.py                # AppState dataclass + save/load session as JSON
├── CLAUDE.md                   # Auto-read by Claude Code (already exists)
├── CODING_PLAN.md              # This file
├── requirements.txt
│
├── screens/
│   ├── screen_import.py        # Screen 1: file loading, column detection, panel match
│   ├── screen_dashboard.py     # Screen 2: chart builder
│   ├── screen_validation.py    # Screen 3: AI tagging + human review
│   ├── screen_report.py        # Screen 4: report draft + export
│   └── screen_settings.py      # Screen 5: API config, model selection, preferences
│
├── core/
│   ├── data_loader.py          # Excel ingestion, column role detection, normalisation
│   ├── panel_matcher.py        # Pseudokey matching between pre- and post-survey
│   ├── chart_builder.py        # All matplotlib/seaborn chart functions
│   ├── stats_engine.py         # Likert aggregation, Cohen's d, Cronbach's alpha, t-tests
│   └── export_engine.py        # DOCX + PDF export (reuse user's existing export code)
│
├── ai/
│   ├── claude_client.py        # Anthropic API wrapper with retry, cost tracking, error handling
│   ├── tagger.py               # Batch free-text tagging via Haiku
│   ├── report_writer.py        # Report section generation via Sonnet
│   └── prompts.py              # All system prompts as string constants — never hardcode elsewhere
│
├── ui/
│   ├── components.py           # Reusable widgets: TagRow, ChartPanel, StepHeader, MatchBadge
│   ├── theme.py                # Colors, fonts — inherits from user's existing apps
│   └── icons.py                # Inline base64 icons (no external image files)
│
├── config/
│   └── defaults.yaml           # Default column mappings, tag labels, model names, report structure
│
└── sessions/                   # Auto-saved .bc4d session files (JSON)
```

---

## AppState Schema

Defined in `app_state.py`. Passed by reference to every screen — never duplicated.

```python
@dataclass
class AppState:
    # Data
    pre_df: pd.DataFrame | None = None        # Vorabfragebogen raw data
    post_df: pd.DataFrame | None = None       # Abschlussbefragung raw data
    matched_df: pd.DataFrame | None = None    # Panel-matched rows (pre + post columns)
    column_roles: dict = field(default_factory=dict)  # {col: "likert"|"freetext"|"key"|"demographic"|"meta"}

    # Validation
    tags: dict = field(default_factory=dict)
    # Structure: { col_name: [ {id, text, ai_tag, confidence, override, confirmed, note} ] }

    # Output
    charts: dict = field(default_factory=dict)    # {chart_key: matplotlib Figure}
    report_draft: dict = field(default_factory=dict)  # {section_key: str}

    # Config
    settings: dict = field(default_factory=dict)

def save_session(state: AppState, path="sessions/latest.bc4d"):
    # Serialise to JSON — exclude non-serialisable objects (DataFrames saved as parquet sidecar)

def load_session(path="sessions/latest.bc4d") -> AppState:
    # Restore from JSON + parquet sidecar
```

---

## Phase 1 — Scaffold

**Goal:** All files exist as stubs. App launches. Navigation between all 5 screens works.

- Create every file listed in the file structure above
- Each screen is a class with an empty `render()` method and a placeholder label
- `main.py` launches `MainWindow` which hosts all screens in a tabbed or sidebar nav
- Match the user's existing framework and base window class exactly
- Confirm app launches with no errors before moving to Phase 2

**Do not write any data logic, API calls, or chart code in this phase.**

---

## Phase 2 — Import Screen + Data Loading

### screen_import.py

UI elements:
- File drop zone with "Browse" fallback — accepts up to 3 `.xlsx` files (pre-survey, post-survey, optional comparison staffel)
- Auto-detection panel showing detected column roles with colour-coded badges
- Column mapper: dropdown to manually reassign any column if auto-detection is wrong
- Panel match summary widget (built in Phase 3, placeholder here)
- Scrollable data preview table, filterable by matched/unmatched
- "Continue →" button — disabled until at least one file is loaded and validated

### core/data_loader.py

```python
# Column role detection heuristics
LIKERT_KEYWORDS  = ["kenne", "weiß", "traue", "stimme", "wichtig", "sicher", "zuversicht"]
KEY_KEYWORDS     = ["buchstaben", "straße", "geburtstag", "tag des monats"]
META_KEYWORDS    = ["startzeit", "fertigstellung", "e-mail", "name", "id"]
FREETEXT_MIN_LEN = 40   # mean character length threshold to classify as free-text

def detect_column_roles(df: pd.DataFrame) -> dict:
    """
    Returns dict mapping column name to role string.
    Role options: "likert", "freetext", "key", "demographic", "meta"
    Demographic columns: Alter, Geschlecht, Bildung, etc.
    """

def normalise_likert(series: pd.Series) -> pd.Series:
    """
    Converts German text responses to integers 1-5.
    Handles: "Stimme voll und ganz zu" → 5
             "Stimme eher zu" → 4
             "teils/teils" → 3
             "Stimme eher nicht zu" → 2
             "Stimme überhaupt nicht zu" → 1
    Also handles legacy binary responses (Ja/Nein) for cross-staffel comparison.
    """
```

---

## Phase 3 — Panel Matcher

### core/panel_matcher.py

Both Excel files contain two columns that together form a pseudonymisation key:
- First 4 letters of street name (e.g. "KARL" for Karlsruher Straße)
- Birthday day-of-month, zero-padded (e.g. "05" for the 5th)
- Combined key example: "KARL05"

This key appears in both the pre-survey (Vorabfragebogen) and post-survey (Abschlussbefragung), making individual-level matching possible.

```python
def build_pseudo_key(df: pd.DataFrame, street_col: str, bday_col: str) -> pd.Series:
    """
    Produces the combined key. Handles:
    - Inconsistent capitalisation
    - Leading/trailing whitespace
    - Numeric vs string birthday values
    - Keys shorter than 4 chars (pad with underscore)
    """
    street = df[street_col].astype(str).str.upper().str.strip().str[:4].str.ljust(4, "_")
    bday   = pd.to_numeric(df[bday_col], errors="coerce").fillna(0).astype(int).astype(str).str.zfill(2)
    return street + bday

def match_panel(pre_df, post_df, pre_cols: dict, post_cols: dict) -> dict:
    """
    Args:
        pre_cols:  {"street": col_name, "bday": col_name}
        post_cols: {"street": col_name, "bday": col_name}

    Returns dict with keys:
        matched         — merged DataFrame, one row per matched person, suffixes _pre / _post
        unmatched_pre   — pre rows with no post match
        unmatched_post  — post rows with no pre match
        stats           — {n_pre, n_post, n_matched, match_rate, n_unmatched_pre, n_unmatched_post}
        quality         — "good" (>70%), "acceptable" (50-70%), "poor" (<50%)
    """
    # Drop duplicate keys before merging (keep first occurrence)
    # Inner merge on _key
    # Return all four outputs
```

### screen_import.py — match results widget

After matching, show a clearly visible summary:
- "✅ 87 of 147 respondents matched (59%) — individual-level analysis available"
- Or: "⚠️ Match rate 34% — only group-level analysis available. Check column mapping."
- "Review unmatched" button opens a modal showing unmatched rows from both files
- User can manually link rows in the modal (drag-and-drop or dropdown)

### What panel matching enables in stats_engine.py

```python
def paired_comparison(matched_df: pd.DataFrame, pre_col: str, post_col: str) -> dict:
    """
    Paired t-test or Wilcoxon signed-rank test (Wilcoxon if n<30 or non-normal).
    Returns: {t_stat, p_value, effect_size_d, n, mean_pre, mean_post, mean_delta,
              pct_improved, pct_unchanged, pct_declined, test_used}
    """

def change_score_distribution(matched_df, pre_col, post_col) -> pd.Series:
    """Returns series of individual delta scores (post - pre) for histogram."""
```

---

## Phase 4 — Dashboard & Charts

### core/chart_builder.py

All functions return a `matplotlib.figure.Figure` object. Never display directly — the screen handles rendering.

**Chart 1 — Likert distribution (horizontal stacked bar)**
```python
def chart_likert_stacked(df, columns: list[str], title: str, n: int) -> Figure:
    """
    Shows 5 response categories as stacked horizontal bars.
    Colors: strongly agree #C8175D, agree #e8799b, neutral #cccccc, 
            disagree #a0a0a0, strongly disagree #707070
    Includes % labels inside bars (if segment > 5%), n shown in subtitle.
    """
```

**Chart 2 — Pre/post grouped bar**
```python
def chart_prepost_grouped(pre_vals: dict, post_vals: dict, title: str, 
                           panel_data: bool = False) -> Figure:
    """
    Paired bars. If panel_data=True, adds individual change lines (spaghetti plot overlay).
    Shows delta as annotation above each pair.
    """
```

**Chart 3 — Change score histogram (panel data only)**
```python
def chart_change_histogram(delta_series: pd.Series, item_label: str, 
                            stats: dict) -> Figure:
    """
    Histogram of individual delta scores.
    Color: improved=green, unchanged=grey, declined=red.
    Subtitle: p-value and Cohen's d from stats dict.
    """
```

**Chart 4 — Staffel trend line**
```python
def chart_staffel_trend(data: dict, metrics: list[str]) -> Figure:
    """
    Line chart across staffeln. data = {staffel_label: {metric: value}}.
    Each metric is a separate line. Annotated data points.
    """
```

**Chart 5 — Practical transfer (horizontal bar)**
```python
def chart_practical_transfer(df, columns: list[str], title: str) -> Figure:
    """
    Horizontal bars showing % "manchmal" + "regelmäßig" combined.
    Dual annotation: % and absolute n.
    Matches style of existing BC4D Zusammenfassung report.
    """
```

**Chart 6 — Pie / donut**
```python
def chart_pie(counts: pd.Series, title: str, donut: bool = False) -> Figure:
    """ISD pink palette. Shows absolute counts as labels."""
```

### screen_dashboard.py

Two-panel layout:
- Left panel (280px): chart type selector, configuration options (which columns, title override, n display toggle, colour scheme)
- Right panel: live chart canvas using `matplotlib FigureCanvasTkAgg`
- Below canvas: "Export PNG", "Export SVG", "Add to Report" buttons
- Top bar: "Generate All Charts" button — runs all charts in sequence, saves to `charts/` folder

---

## Phase 5 — AI Tagging & Validation

### ai/claude_client.py

```python
class ClaudeClient:
    def __init__(self, api_key: str, settings: dict):
        self.client = anthropic.Anthropic(api_key=api_key)
        self.session_cost = 0.0
        self.settings = settings

    def complete(self, model: str, system: str, user: str, max_tokens: int = 1000) -> str:
        """Single completion with retry (max 3 attempts, exponential backoff)."""

    def complete_batch(self, model: str, system: str, user_messages: list[str], 
                       max_tokens: int = 500, on_progress=None) -> list[str]:
        """
        Sends messages sequentially with progress callback.
        Updates self.session_cost after each call.
        on_progress(completed, total) called after each response.
        """

    def estimate_cost(self, model: str, input_tokens: int, output_tokens: int) -> float:
        """Returns estimated USD cost."""
```

### ai/tagger.py

```python
BATCH_SIZE = 50  # responses per API call

def tag_column(df: pd.DataFrame, text_col: str, client: ClaudeClient, 
               settings: dict, on_progress=None) -> list[dict]:
    """
    Tags all non-null responses in text_col.
    Sends in batches of BATCH_SIZE.
    Returns list of {id, text, ai_tag, confidence} dicts.
    Deduplicates tag labels (normalises capitalisation and spacing).
    """

def normalise_tag_schema(tags: list[dict]) -> tuple[list[dict], dict]:
    """
    After tagging, finds near-duplicate tag labels and merges them.
    Returns (normalised_tags, merge_map).
    Uses simple string distance — no API call needed.
    """
```

### ui/components.py — TagRow widget

```python
class TagRow(ctk.CTkFrame):
    """
    Single row in the validation table.

    Displays:
        [row_id] [response text, truncated to 80 chars, expandable] 
        [AI tag badge] [confidence bar] [override dropdown] [status icon]

    Confidence bar color:
        >= 0.8: green
        >= 0.5: amber  
        <  0.5: red

    Override dropdown lists all current tags + "➕ New tag..." option.
    Status icons: ⬜ unreviewed, ✅ confirmed, ✏️ overridden, 🚫 excluded

    on_change_callback(row_id, new_tag) called on any change.
    """
```

### screen_validation.py

Layout:
- Top bar: column selector dropdown, "Tag this column" button, progress bar (hidden until running), cost estimate label
- Left panel (220px): tag schema panel showing all tags with counts, "Rename", "Merge", "Split" buttons (Level 1)
- Right panel: scrollable list of TagRow widgets, filterable by: All / Low confidence / Unreviewed / Overridden
- Bottom bar: "Confirm all reviewed", "Next column →", overall progress ("3 of 7 columns validated")

Three-level override system:
1. **Schema level** (left panel): rename/merge/split tags — propagates to all rows instantly
2. **Batch level**: select a tag in left panel → "Reassign all to..." dropdown appears
3. **Row level**: click any TagRow → override dropdown, note field, exclude toggle

### core/stats_engine.py — validation metrics

```python
def cronbach_alpha(df: pd.DataFrame, columns: list[str]) -> float:
    """Cronbach's alpha for a set of Likert items. Flag if < 0.7."""

def ai_agreement_rate(tags: list[dict]) -> float:
    """Proportion of AI tags accepted without override. Report as inter-rater proxy."""

def cohen_d_paired(pre: pd.Series, post: pd.Series) -> float:
    """Effect size for paired pre/post comparison."""

def run_paired_test(pre: pd.Series, post: pd.Series) -> dict:
    """
    Chooses between paired t-test and Wilcoxon signed-rank based on n and normality.
    Returns {test, statistic, p_value, effect_size_d, interpretation}
    where interpretation is a plain German sentence for the report.
    """
```

---

## Phase 6 — Report Screen

### ai/prompts.py

```python
TAGGER_SYSTEM = """
You are a qualitative research coder for ISD (Institute for Strategic Dialogue).
Your task: assign exactly ONE thematic tag to each survey response.

Rules:
- Infer tags inductively from the data — do not impose a fixed schema upfront
- Use short, descriptive German labels (3-6 words maximum)
- Be consistent: use the exact same label string for the same concept across all responses
- Assign a confidence score between 0.0 and 1.0
- If a response is too vague, blank, or off-topic, tag it as "nicht auswertbar"

Return ONLY valid JSON — no prose, no markdown fences:
[{"id": 1, "tag": "Demokratieschutz", "confidence": 0.92}, ...]
"""

REPORT_SYSTEM = """
You are writing an evaluation report for {org_name}'s {program_name} programme.
Audience: corporate partner organisations that funded the training.
Language: {language}
Tone: {tone}

Rules:
- Write in flowing prose — no bullet points
- Every quantitative claim must reference the n in brackets, e.g. (n=147)
- Where panel data is available, reference individual-level findings with effect sizes
- Include one methodological footnote per section where scientifically warranted
- Do not over-interpret — stay close to what the data shows
- Do not duplicate content across sections
- End each section with one transition sentence pointing to the next section
"""

REPORT_SECTION_USER = """
Write the "{section}" section of the evaluation report.

Data for this section:
{data}

Target length: 150-250 words.
"""
```

### ai/report_writer.py

```python
SECTION_DATA_BUILDERS = {
    "ueberblick":          _build_ueberblick_payload,
    "problembewusstsein":  _build_qualitative_payload,
    "kompetenzzuwachs":    _build_prepost_payload,
    "handlungssicherheit": _build_likert_payload,
    "praxistransfer":      _build_transfer_payload,
    "schulungsfeedback":   _build_feedback_payload,
    "methodische_hinweise": _build_methods_payload,
}

def generate_section(section_key: str, app_state: AppState, settings: dict) -> str:
    """
    Assembles structured data payload for the section.
    Calls Claude Sonnet with system + user prompt.
    Returns plain text (no markdown formatting).
    """

def _build_prepost_payload(app_state: AppState) -> dict:
    """
    If panel data available: includes individual-level stats (paired test results, effect sizes).
    Always includes group-level stats for context.
    Includes match_rate and methodological note if panel was used.
    """
```

### screen_report.py

Layout:
- Left panel (240px): section list — each section has name, status icon (⬜/🔄/✅/✏️), "Generate" button, "Regenerate" button
- Top of left panel: "Generate All Sections" master button
- Right panel: editable text area for selected section (rich text or plain textarea)
- Bottom bar: "Export DOCX", "Export PDF", "Export Data Appendix (XLSX)", "Copy Section" buttons

Section status:
- ⬜ Not generated
- 🔄 Generating (spinner)
- ✅ Generated, not edited
- ✏️ Manually edited

---

## Phase 7 — Settings & Polish

### screen_settings.py

Sections:
1. **API Configuration** — API key input (masked, stored in OS keychain via `keyring`), "Test connection" button, session cost display
2. **Model Selection** — dropdown per task (tagging, report writing), shows model names and estimated cost per use
3. **Report Preferences** — language toggle (DE/EN), tone preset (3 options: evidenzbasiert/zugänglich/kompakt), org name, programme name, which sections to include
4. **Data Configuration** — save/load column mapping presets, Likert scale direction, match threshold warning level
5. **Export Paths** — default output folder for exports and chart saves

### app_state.py — session persistence

```python
def save_session(state: AppState, path: str = "sessions/latest.bc4d"):
    """
    Saves AppState to JSON. DataFrames saved as parquet sidecars.
    Charts saved as PNG sidecars and referenced by filename.
    """

def load_session(path: str = "sessions/latest.bc4d") -> AppState:
    """Restores AppState. Offers "Resume last session?" dialog on app launch."""
```

### Final polish checklist
- [ ] Consistent padding, font sizes, and button styles across all screens (match existing apps)
- [ ] All API calls run in background threads — UI never freezes
- [ ] Progress indicators on all long-running operations (tagging, chart generation, report writing)
- [ ] Error messages shown in UI (not just console) — especially for API failures
- [ ] "Help" tooltip on every non-obvious UI element
- [ ] Test with real BC4D Staffel 13 files before declaring done

---

## Model Routing Reference

| Task | Model | Rationale | Est. cost / staffel |
|------|-------|-----------|---------------------|
| Bulk free-text tagging (~700 responses) | `claude-haiku-4-5-20251001` | Fast, cheap, excellent at classification | $0.05–0.15 |
| Report section writing (7 sections) | `claude-sonnet-4-6` | Nuance, tone, data interpretation | $0.15–0.40 |
| Single section regeneration | `claude-sonnet-4-6` | Short context, fast | $0.02–0.05 |
| Optional full-report coherence pass | `claude-sonnet-4-6` (Opus in settings) | Only for high-stakes reports | $0.50–1.50 |
| Column detection, stats, charts | No API | Local Python — deterministic, free | $0.00 |

**Total typical cost per staffel evaluation: $0.20–0.55**

---

## Panel Matching — Methodological Note

The pseudonymisation key combines:
- First 4 uppercase letters of street name (self-reported)
- Birthday day-of-month, zero-padded (self-reported)

Expected match rate: 50–75% (typos, format variation, late sign-ups reduce it).

The app must:
1. Display match rate prominently on the Import screen
2. Warn if match rate < 50% ("only group-level analysis recommended")
3. Add an automatic footnote in the report's Methodische Hinweise section stating the match rate and its limitations
4. Never claim individual-level findings in the report if match rate < 50%

---

## First Claude Code Prompt (copy-paste)

```
I am building a Python desktop app called BC4D Intel.

Before writing any code:
1. Read CODING_PLAN.md and CLAUDE.md in the project root
2. Ask me: what framework are my existing two GUIs built with?
3. Ask me: what is the path to my existing base window class and shared components?

Then start Phase 1 only: create all files as empty stubs, set up navigation between 
all 5 screens, confirm it launches cleanly. Do not write any logic yet.
```
