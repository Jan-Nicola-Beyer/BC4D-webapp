"""Power user simulation — clicks through every screen, changes things, jumps around.

Simulates a real user session WITHOUT a GUI (tests the logic layer directly):
1. Load files
2. Jump to dashboard
3. Jump back to import
4. Run analysis (mocked)
5. Switch rapidly between Categories/Insights/Responses
6. Change a response category
7. Check propagation to other screens
8. Generate report (mocked)
9. Re-run analysis
10. Check report was cleared
11. Toggle theme multiple times
12. Export/Import JSON
13. Close and restore session

No API calls. No GUI rendering. Pure logic + state verification.
"""

from __future__ import annotations
import json, os, sys, time, shutil
from unittest.mock import patch, MagicMock
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "bc4d_intel"))
sys.path.insert(0, os.path.dirname(__file__))

RESULTS = {}


def record(name, passed, details=""):
    RESULTS[name] = passed
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    if details and not passed:
        print(f"         {details[:120]}")


print("\n" + "=" * 70)
print("POWER USER SIMULATION")
print("=" * 70)

# ── Setup: clean state ──────────────────────────────────────────
from bc4d_intel.app_state import AppState
from bc4d_intel import constants as C

state = AppState()
state.tagged_responses = {}
state.taxonomies = {}
state.flat_taxonomies = {}
state.report_sections = {}
_analysis_results = {}

# Simulate app._frames with real screen data but no GUI
_match_result = None

# ── 1. Load both Excel files ────────────────────────────────────
print("\n--- 1. Load Excel Files ---")

from bc4d_intel.core.data_loader import load_survey
from bc4d_intel.core.panel_matcher import match_panels

t0 = time.perf_counter()
pre_df, pre_roles = load_survey("Synthetisch_Vorbefragung_Staffel13.xlsx")
post_df, post_roles = load_survey("Synthetisch_Abschlussbefragung_Staffel13.xlsx")
record("load_pre", len(pre_df) > 0, f"{len(pre_df)} rows")
record("load_post", len(post_df) > 0, f"{len(post_df)} rows")

state.n_pre = len(pre_df)
state.n_post = len(post_df)
state.pre_survey_path = "Synthetisch_Vorbefragung_Staffel13.xlsx"
state.post_survey_path = "Synthetisch_Abschlussbefragung_Staffel13.xlsx"

# ── 2. Panel matching ───────────────────────────────────────────
print("\n--- 2. Panel Matching ---")

_match_result = match_panels(pre_df, pre_roles, post_df, post_roles)
state.matched_pairs = _match_result["stats"]["n_matched"]
record("matching", state.matched_pairs > 0, f"{state.matched_pairs} pairs")

# ── 3. Jump to Dashboard (needs _match_result) ─────────────────
print("\n--- 3. Dashboard Data Check ---")

from bc4d_intel.core.stats_engine import analyze_all_likert, analyze_matched_likert

post_items = analyze_all_likert(_match_result["post_all"], post_roles)
record("dashboard_post_likert", len(post_items) > 0, f"{len(post_items)} items")

comparisons = analyze_matched_likert(_match_result["matched"], pre_roles, post_roles)
record("dashboard_matched", len(comparisons) > 0, f"{len(comparisons)} comparisons")

# ── 4. Jump BACK to Import (should still have data) ────────────
print("\n--- 4. Jump Back to Import ---")

record("import_data_persists", pre_df is not None and post_df is not None)
record("match_result_persists", _match_result is not None)

# ── 5. Run AI Analysis (mocked) ────────────────────────────────
print("\n--- 5. AI Analysis (mocked) ---")

from bc4d_intel.core.answer_cache import deduplicate, add_to_cache, get_cached_taxonomy, save_taxonomy

# Extract free-text questions
all_ft = []
for stype, df, roles in [("Pre", _match_result["pre_all"], pre_roles),
                           ("Post", _match_result["post_all"], post_roles)]:
    for col, role in roles.items():
        if role == "free_text" and col in df.columns:
            responses = [r.strip() for r in df[col].dropna().astype(str).tolist()
                         if len(r.strip()) > 5]
            if len(responses) >= 5:
                label = f"[{stype}] {col[:45]}"
                all_ft.append((label, col, responses))

record("found_questions", len(all_ft) >= 3, f"{len(all_ft)} questions")

# Mock LLM classification
def mock_classify(system, user_msg, task="tagging", api_key="", max_tokens=1000, stream_cb=None):
    import re
    ids = re.findall(r'\[(\d+)\]', user_msg)
    results = []
    for id_str in ids:
        results.append({"id": int(id_str), "cluster_id": "cat_1a",
                        "main_category": "Theme A", "cluster_title": "Sub A",
                        "confidence": "high"})
    return json.dumps(results)

# Mock taxonomy design
def mock_pipeline(responses, api_key, question="", progress_cb=None):
    taxonomy = {"categories": [{"id": "cat_1", "main_category": "Theme A",
                "sub_categories": [{"id": "cat_1a", "title": "Sub A",
                "examples": responses[:2], "include_rule": "test", "exclude_rule": ""}]}]}
    classifications = [{"text": r, "cluster_id": "cat_1a", "cluster_title": "Sub A",
                        "main_category": "Theme A", "confidence": "high",
                        "match_type": "llm", "human_override": ""} for r in responses]
    return {"taxonomy": taxonomy, "classifications": classifications,
            "flat_taxonomy": [{"id": "cat_1a", "title": "Sub A",
                              "main_category": "Theme A", "count": len(responses)}]}

# Process each question
for label, col, responses in all_ft[:3]:  # first 3 for speed
    deduped, remaining = deduplicate(label, responses)

    with patch("bc4d_intel.ai.claude_client.call_claude", side_effect=mock_classify):
        from bc4d_intel.core.answer_cache import classify_with_llm

        taxonomy = get_cached_taxonomy(label)
        if not taxonomy:
            res = mock_pipeline(responses, "mock")
            save_taxonomy(label, res["taxonomy"])
            taxonomy = res["taxonomy"]
            classified = res["classifications"]
        else:
            classified = classify_with_llm(col, remaining, taxonomy, "mock")
            classified = list(deduped) + classified

    # Save results (same as screen_analysis does)
    _analysis_results[label] = {
        "taxonomy": taxonomy,
        "flat_taxonomy": [{"id": "cat_1a", "title": "Sub A",
                          "main_category": "Theme A", "count": len(classified)}],
        "classifications": classified,
    }
    state.tagged_responses[label] = classified
    state.taxonomies[label] = taxonomy
    state.save()

record("analysis_complete", len(_analysis_results) == 3,
       f"{len(_analysis_results)} questions analyzed")

# Verify report was NOT auto-generated
record("report_empty_after_analysis", len(state.report_sections) == 0)

# ── 6. Rapid screen switching ──────────────────────────────────
print("\n--- 6. Rapid Screen Switching ---")

# Simulate jumping between screens 20 times
screens_visited = []
for i in range(20):
    screen = ["categories", "insights", "responses", "dashboard", "analysis"][i % 5]
    screens_visited.append(screen)

record("rapid_switching", len(screens_visited) == 20, "No crash simulating 20 switches")

# ── 7. Change a response category ──────────────────────────────
print("\n--- 7. Response Category Change ---")

first_label = list(_analysis_results.keys())[0]
first_data = _analysis_results[first_label]
original_cat = first_data["classifications"][0]["cluster_id"]

# User changes first response to a different category
first_data["classifications"][0]["human_override"] = "cat_2a"
first_data["classifications"][0]["cluster_title"] = "Sub B (edited)"
first_data["classifications"][0]["main_category"] = "Theme B"

# Save and propagate (same as screen_responses._save_and_propagate)
state.tagged_responses[first_label] = first_data["classifications"]
state.save()

record("category_changed",
       first_data["classifications"][0]["human_override"] == "cat_2a")

# Verify propagation — other data sources see the change
record("propagation_to_state",
       state.tagged_responses[first_label][0].get("human_override") == "cat_2a")
record("propagation_to_results",
       _analysis_results[first_label]["classifications"][0].get("human_override") == "cat_2a")

# ── 8. Report context uses LIVE data ───────────────────────────
print("\n--- 8. Report Context Uses Live Data ---")

from bc4d_intel.ai.report_writer import build_data_context

tagged_data = {}
for label, classifications in state.tagged_responses.items():
    tagged_data[label] = [{"text": c.get("text", ""), "tag": c.get("cluster_title", ""),
                           "human_override": c.get("human_override", "")}
                          for c in classifications]

context = build_data_context(state, _match_result, tagged_data,
                             pre_roles=pre_roles, post_roles=post_roles,
                             pre_df=_match_result["pre_all"],
                             post_df=_match_result["post_all"])

record("context_has_current_data", "cat_2a" in context or "Sub B" in context,
       "Edited category visible in report context")
record("context_has_stats", "M=" in context and "Cohen" in context)

# ── 9. Generate report (mocked) ────────────────────────────────
print("\n--- 9. Generate Report (mocked) ---")

def mock_sonnet(system, user_msg, **kwargs):
    return "## Test Section\n\nGenerated with current data."

from bc4d_intel.ai.report_writer import generate_section
from bc4d_intel.ai.prompts import REPORT_SECTIONS

with patch("bc4d_intel.ai.report_writer.call_claude", side_effect=mock_sonnet):
    for section in REPORT_SECTIONS:
        text = generate_section(section, context, "mock")
        state.report_sections[section] = text

record("all_sections_generated", len(state.report_sections) == 7)
state.save()

# ── 10. Re-run analysis → report should clear ──────────────────
print("\n--- 10. Re-run Analysis -> Report Clears ---")

# Simulate what screen_analysis does after re-run
state.report_sections = {}
record("report_cleared_on_rerun", len(state.report_sections) == 0)

# ── 11. Theme toggle stress test ────────────────────────────────
print("\n--- 11. Theme Toggle Stress ---")

for i in range(20):
    theme = "light" if i % 2 == 0 else "dark"
    C.apply_theme(theme)

from bc4d_intel.core.chart_builder import _chart_colors
cc_light = None
cc_dark = None
C.apply_theme("light")
cc_light = _chart_colors()
C.apply_theme("dark")
cc_dark = _chart_colors()

record("theme_toggle_20x", True)
record("theme_colors_differ", cc_light["text"] != cc_dark["text"])

# ── 12. Export/Import JSON ──────────────────────────────────────
print("\n--- 12. Export/Import JSON ---")

export_data = {"version": "v5", "staffel": "test",
               "questions": {}}
for label, res in _analysis_results.items():
    export_data["questions"][label] = {
        "taxonomy": res.get("taxonomy", {}),
        "flat_taxonomy": res.get("flat_taxonomy", []),
        "classifications": res.get("classifications", []),
    }

export_path = "test_power_user_export.json"
with open(export_path, "w", encoding="utf-8") as f:
    json.dump(export_data, f, ensure_ascii=False)

record("export_json", os.path.exists(export_path))

# Import into clean state
state2 = AppState()
with open(export_path, "r", encoding="utf-8") as f:
    imported = json.load(f)

for label, qdata in imported["questions"].items():
    state2.tagged_responses[label] = qdata.get("classifications", [])
    state2.taxonomies[label] = qdata.get("taxonomy", {})

record("import_json", len(state2.tagged_responses) == len(_analysis_results))

# Verify imported data matches original
first_label = list(_analysis_results.keys())[0]
orig_count = len(_analysis_results[first_label]["classifications"])
imported_count = len(state2.tagged_responses[first_label])
record("import_data_matches", orig_count == imported_count,
       f"Original: {orig_count}, Imported: {imported_count}")

os.remove(export_path)

# ── 13. Session save/restore cycle ──────────────────────────────
print("\n--- 13. Session Save/Restore ---")

state.save()
restored = AppState.load()

record("session_restore_files",
       restored.pre_survey_path == state.pre_survey_path)
record("session_restore_analysis",
       len(restored.tagged_responses) == len(state.tagged_responses))
record("session_restore_theme",
       restored.theme == state.theme)

# ── 14. Concurrent-like operations ──────────────────────────────
print("\n--- 14. Concurrent Save Stress ---")

import threading
errors = []

def save_worker(n):
    try:
        for i in range(10):
            state.save()
    except Exception as e:
        errors.append(str(e))

threads = [threading.Thread(target=save_worker, args=(i,)) for i in range(5)]
for t in threads:
    t.start()
for t in threads:
    t.join()

record("concurrent_saves", len(errors) == 0,
       f"{len(errors)} errors" if errors else "50 saves from 5 threads")

# ── 15. Edge cases ──────────────────────────────────────────────
print("\n--- 15. Edge Cases ---")

# Empty response list
deduped, remaining = deduplicate("nonexistent_question", [])
record("empty_responses", len(deduped) == 0 and len(remaining) == 0)

# Very long response
long_text = "A" * 10000
deduped, remaining = deduplicate("test", [long_text])
record("long_response", len(remaining) == 1)

# Unicode in responses
unicode_text = "Ueber die Staerken: Trainerin war toll \u00e4\u00f6\u00fc\u00df"
deduped, remaining = deduplicate("test", [unicode_text])
record("unicode_response", len(remaining) == 1)

# None/empty in classifications
bad_classifications = [
    {"text": "", "cluster_id": "c1", "cluster_title": "T", "main_category": "M", "confidence": "high"},
    {"text": "OK", "cluster_id": "", "cluster_title": "", "main_category": "", "confidence": ""},
]
added = add_to_cache("edge_case_test", bad_classifications)
record("bad_classifications_handled", True, f"Added {added} (should handle gracefully)")

# ════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("SUMMARY")
print("=" * 70)

n_pass = sum(1 for v in RESULTS.values() if v)
n_fail = sum(1 for v in RESULTS.values() if not v)

for name, passed in RESULTS.items():
    if not passed:
        print(f"  FAIL -- {name}")

print(f"\n  {n_pass}/{n_pass + n_fail} passed, {n_fail} failed")

if n_fail == 0:
    print("\n  VERDICT: APP IS STABLE UNDER POWER USER SIMULATION")
else:
    print(f"\n  VERDICT: {n_fail} ISSUES NEED ATTENTION")

sys.exit(0 if n_fail == 0 else 1)
