"""BC4D Intel — theme, colors, navigation, and app-wide constants."""

# ── Brand colors ─────────────────────────────────────────────────
BC4D_PINK = "#C8175D"   # primary brand
BC4D_BLUE = "#0077B6"   # reports / data
BC4D_TEAL = "#059669"   # success / matched
BC4D_AMBER = "#d97706"  # warnings
BC4D_CORAL = "#e74c3c"  # errors / danger

# ── Dark theme (default) ────────────────────────────────────────
_DARK = dict(
    BG="#0d1117", PANEL="#111827", CARD="#161b22", BORDER="#21262d",
    ACCENT=BC4D_PINK, SELECT="#3d0f28",
    SUCCESS="#059669", WARN="#d97706", DANGER="#dc2626",
    TEXT="#e6edf3", MUTED="#6b7280", DIM="#374151", BTN="#374151",
    ENTRY_BG="#1c2333", ENTRY_BORDER="#30363d",
)

# ── Light theme ──────────────────────────────────────────────────
_LIGHT = dict(
    BG="#ffffff", PANEL="#f3f4f6", CARD="#f9fafb", BORDER="#e5e7eb",
    ACCENT=BC4D_PINK, SELECT="#fce4ec",
    SUCCESS="#059669", WARN="#d97706", DANGER="#dc2626",
    TEXT="#1f2937", MUTED="#4b5563", DIM="#d1d5db", BTN="#e5e7eb",
    ENTRY_BG="#ffffff", ENTRY_BORDER="#d1d5db",
)

# ── Module-level tokens (mutated by apply_theme) ────────────────
BG = _DARK["BG"]
PANEL = _DARK["PANEL"]
CARD = _DARK["CARD"]
BORDER = _DARK["BORDER"]
ACCENT = _DARK["ACCENT"]
SELECT = _DARK["SELECT"]
SUCCESS = _DARK["SUCCESS"]
WARN = _DARK["WARN"]
DANGER = _DARK["DANGER"]
TEXT = _DARK["TEXT"]
MUTED = _DARK["MUTED"]
DIM = _DARK["DIM"]
BTN = _DARK["BTN"]
ENTRY_BG = _DARK["ENTRY_BG"]
ENTRY_BORDER = _DARK["ENTRY_BORDER"]

_current_theme = "dark"


def apply_theme(name: str):
    d = _DARK if name == "dark" else _LIGHT
    global BG, PANEL, CARD, BORDER, ACCENT, SELECT
    global SUCCESS, WARN, DANGER, TEXT, MUTED, DIM, BTN
    global ENTRY_BG, ENTRY_BORDER, _current_theme
    _current_theme = name
    BG      = d["BG"];      PANEL  = d["PANEL"];  CARD   = d["CARD"]
    BORDER  = d["BORDER"];  ACCENT = d["ACCENT"]; SELECT = d["SELECT"]
    SUCCESS = d["SUCCESS"]; WARN   = d["WARN"];   DANGER = d["DANGER"]
    TEXT    = d["TEXT"];      MUTED  = d["MUTED"];  DIM    = d["DIM"]
    BTN     = d["BTN"]
    ENTRY_BG = d["ENTRY_BG"]; ENTRY_BORDER = d["ENTRY_BORDER"]


def current_theme() -> str:
    return _current_theme


# ── Navigation ───────────────────────────────────────────────────
NAV_ITEMS = [
    ("Import",       "import",      "\U0001F4C2"),  # folder
    ("Dashboard",    "dashboard",   "\U0001F4CA"),  # chart
    ("Reliability",  "reliability", "\U0001F50D"),  # magnifier
    ("AI Analysis",  "analysis",    "\U0001F916"),  # robot
    ("Clusters",     "clusters",    "\U0001F3AF"),  # target
    ("Responses",    "responses",   "\U0001F4DD"),  # memo
    ("Insights",     "insights",    "\U0001F4C8"),  # chart up
    ("Report",       "report",      "\U0001F4C4"),  # document
    ("Settings",     "settings",    "\u2699"),       # gear
]

# ── Likert scale config ─────────────────────────────────────────
LIKERT_LABELS = {
    1: "Trifft gar nicht zu",
    2: "Trifft eher nicht zu",
    3: "Teils/Teils",
    4: "Trifft eher zu",
    5: "Trifft voll und ganz zu",
}

LIKERT_COLORS = {
    1: "#dc2626",  # red
    2: "#f97316",  # orange
    3: "#facc15",  # yellow
    4: "#84cc16",  # lime
    5: "#22c55e",  # green
}

# ── AI model config ──────────────────────────────────────────────
AI_MODELS = {
    "tagging": "claude-haiku-4-5-20251001",    # edge case review (simple pick-from-list)
    "report":  "claude-sonnet-4-6",            # taxonomy design + report sections
    # Taxonomy design uses "report" (Sonnet) — needs reasoning about themes.
    # Edge case review uses "tagging" (Haiku) — just picks from existing categories.
    # Report writing uses "report" (Sonnet) — needs quality German prose.
    # Saves ~40% on edge case costs without quality loss.
}

# ── Session / paths ──────────────────────────────────────────────
import os
APP_DIR = os.path.dirname(os.path.abspath(__file__))
SESSION_DIR = os.path.join(APP_DIR, "sessions")
os.makedirs(SESSION_DIR, exist_ok=True)
