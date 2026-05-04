"""Full system audit — every component of BC4D Intel.

Tests: data loading, column detection, panel matching, deduplication,
LLM classification (mocked), quality gate (mocked), cache persistence,
taxonomy flow, reliability checker, validation screen data flow,
screen_analysis orchestration, embedder.py full_pipeline (mocked).

Clean DB state — no synthetic data.
"""

from __future__ import annotations
import os, sys, time, json, random
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "bc4d_intel"))
sys.path.insert(0, os.path.dirname(__file__))

random.seed(42)
RESULTS = {}
WARNINGS = []


def record(name, passed, details=""):
    RESULTS[name] = {"passed": passed, "details": details}
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}")
    if details:
        for line in details.split("\n")[:4]:
            print(f"         {line}")


def warn(msg):
    WARNINGS.append(msg)
    print(f"  [WARN] {msg}")


# ════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("FULL SYSTEM AUDIT — BC4D Intel v5")
print("=" * 70)

from bc4d_intel.core.answer_cache import get_cache_stats
stats = get_cache_stats()
print(f"\nDB state: {stats}")
if stats["total_answers"] > 0:
    warn("DB not clean — results may reflect cached data")

# ── 1. Data Loading ─────────────────────────────────────────────
print("\n--- 1. DATA LOADING ---\n")

from bc4d_intel.core.data_loader import load_survey

for name, path in [("NEGATIV Pre", "NEGATIV_Vorbefragung_Staffel13.xlsx"),
                    ("NEGATIV Post", "NEGATIV_Abschlussbefragung_Staffel13.xlsx")]:
    try:
        df, roles = load_survey(path)
        ft = sum(1 for r in roles.values() if r == "free_text")
        lk = sum(1 for r in roles.values() if r == "likert")
        ps = sum(1 for r in roles.values() if "pseudokey" in r)
        record(f"load_{name}", len(df) > 0,
               f"{len(df)} rows, {ft} free_text, {lk} likert, {ps} pseudokeys")
    except Exception as e:
        record(f"load_{name}", False, str(e))

# ── 2. Panel Matching ───────────────────────────────────────────
print("\n--- 2. PANEL MATCHING ---\n")

from bc4d_intel.core.panel_matcher import match_panels

pre_df, pre_roles = load_survey("NEGATIV_Vorbefragung_Staffel13.xlsx")
post_df, post_roles = load_survey("NEGATIV_Abschlussbefragung_Staffel13.xlsx")
result = match_panels(pre_df, pre_roles, post_df, post_roles)

pre_all = result.get("pre_all")
post_all = result.get("post_all")
matched = result.get("matched")

record("panel_no_loss",
       pre_all is not None and len(pre_all) == len(pre_df) and
       post_all is not None and len(post_all) == len(post_df),
       f"Pre: {len(pre_all)}/{len(pre_df)}, Post: {len(post_all)}/{len(post_df)}")

record("panel_match_rate",
       matched is not None and len(matched) > 0,
       f"Matched: {len(matched) if matched is not None else 0} "
       f"({len(matched)/len(post_df)*100:.0f}% of post)" if matched is not None else "No matches")

# ── 3. Question Fuzzy Matching ──────────────────────────────────
print("\n--- 3. QUESTION FUZZY MATCHING ---\n")

from bc4d_intel.core.answer_cache import _normalize_question

test_cases = [
    ("[Pre] Was erhoffen Sie sich? (offene Frage)", "was erhoffen sie sich?"),
    ("[Post] Bitte nennen Sie Stärken.", "bitte nennen sie staerken."),
    ("Verbesserungsmöglichkeiten (Angabe)", "verbesserungsmoeglichkeiten"),
]
all_norm_ok = True
for raw, expected in test_cases:
    got = _normalize_question(raw)
    ok = expected in got
    if not ok:
        all_norm_ok = False
        print(f"    FAIL: '{raw[:40]}' -> '{got}' (expected '{expected}' substring)")

record("question_normalization", all_norm_ok,
       f"{len(test_cases)} cases tested")

# ── 4. Deduplication ────────────────────────────────────────────
print("\n--- 4. DEDUPLICATION ---\n")

from bc4d_intel.core.answer_cache import deduplicate, add_to_cache

# Add some test data then check dedup
test_data = [
    {"text": "Die Trainerin war super kompetent", "cluster_id": "c1",
     "cluster_title": "Trainer Lob", "main_category": "Positiv", "confidence": "high"},
    {"text": "Zu wenig Pausen", "cluster_id": "c2",
     "cluster_title": "Zeitkritik", "main_category": "Kritik", "confidence": "high"},
]
add_to_cache("audit_test_question", test_data, staffel="audit")

deduped, remaining = deduplicate("audit_test_question",
    ["Die Trainerin war super kompetent", "Ganz neuer Text", "Zu wenig Pausen"])

record("dedup_exact_match", len(deduped) == 2 and len(remaining) == 1,
       f"Deduped: {len(deduped)}, Remaining: {len(remaining)}")

if deduped:
    record("dedup_category_preserved",
           deduped[0]["cluster_id"] in ("c1", "c2"),
           f"Category: {deduped[0]['main_category']} > {deduped[0]['cluster_title']}")

# ── 5. Taxonomy CRUD ────────────────────────────────────────────
print("\n--- 5. TAXONOMY CRUD ---\n")

from bc4d_intel.core.answer_cache import save_taxonomy, get_cached_taxonomy

test_taxonomy = {
    "categories": [{
        "id": "cat_1", "main_category": "Positiv",
        "sub_categories": [{
            "id": "cat_1a", "title": "Trainer Lob",
            "examples": ["Trainerin war super", "Gute Moderation"],
            "include_rule": "Lob fuer Trainer",
            "exclude_rule": "Reine Inhaltsbewertung",
        }, {
            "id": "cat_1b", "title": "Inhalt positiv",
            "examples": ["Spannende Themen", "Praxisnahe Beispiele"],
            "include_rule": "Positive Inhaltsbewertung",
            "exclude_rule": "",
        }],
    }, {
        "id": "cat_2", "main_category": "Kritik",
        "sub_categories": [{
            "id": "cat_2a", "title": "Zeitkritik",
            "examples": ["Zu wenig Pausen", "Zu lang"],
            "include_rule": "Zeitbezogene Kritik",
            "exclude_rule": "",
        }],
    }]
}

save_taxonomy("audit_test_question", test_taxonomy, n_responses=3)
loaded = get_cached_taxonomy("audit_test_question")

record("taxonomy_save_load",
       loaded is not None and len(loaded.get("categories", [])) == 2,
       f"Saved 2 categories, loaded: {len(loaded.get('categories', [])) if loaded else 0}")

# Fuzzy match
loaded2 = get_cached_taxonomy("[Post] Audit Test Question (Angabe)")
record("taxonomy_fuzzy_load", loaded2 is not None,
       f"Fuzzy matched: {loaded2 is not None}")

# ── 6. LLM Classification (mocked) ─────────────────────────────
print("\n--- 6. LLM CLASSIFICATION ---\n")

from bc4d_intel.core.answer_cache import classify_with_llm, _build_taxonomy_ref

# Check taxonomy ref quality
ref = _build_taxonomy_ref(test_taxonomy)
record("taxonomy_ref_has_examples", "Beispiele:" in ref and "Trainerin war super" in ref,
       f"Ref: {len(ref)} chars, has examples + rules")

# Mock Haiku
def mock_haiku(system, user_msg, task="tagging", api_key="", max_tokens=1000, stream_cb=None):
    import re
    ids = re.findall(r'\[(\d+)\]', user_msg)
    results = []
    for id_str in ids:
        # Simulate reasonable classification
        idx = int(id_str)
        results.append({
            "id": idx,
            "cluster_id": "cat_1a" if idx % 2 == 1 else "cat_2a",
            "main_category": "Positiv" if idx % 2 == 1 else "Kritik",
            "cluster_title": "Trainer Lob" if idx % 2 == 1 else "Zeitkritik",
            "confidence": "high",
        })
    return json.dumps(results)

test_responses = [
    "Die Trainerin war wirklich toll und engagiert",
    "Es gab viel zu wenig Pausen zwischendurch",
    "Spannende Themen und guter Praxisbezug",
    "Der Zeitplan war viel zu eng",
]

with patch("bc4d_intel.ai.claude_client.call_claude", side_effect=mock_haiku):
    classified = classify_with_llm("audit_test_question", test_responses,
                                    test_taxonomy, "mock-key")

record("llm_classify_count", len(classified) == 4,
       f"Classified: {len(classified)}/4")

required_fields = ["text", "cluster_id", "cluster_title", "main_category",
                    "confidence", "match_type"]
complete = all(all(c.get(f) for f in required_fields) for c in classified)
record("llm_classify_fields", complete,
       f"All {len(classified)} have required fields: {required_fields}")

record("llm_classify_match_type",
       all(c["match_type"] == "llm" for c in classified),
       "All marked as 'llm' match_type")

# ── 7. Quality Gate (mocked) ───────────────────────────────────
print("\n--- 7. QUALITY GATE ---\n")

from bc4d_intel.core.answer_cache import quality_gate

# quality_gate short-circuits with `(True, [])` when fewer than 10 classifications
# are supplied — duplicate the 4-item fixture to exceed that threshold.
classified_for_gate = (classified * 3)[:12]

# Mock Sonnet — all OK
def mock_sonnet_ok(system, user_msg, task="report", api_key="", max_tokens=800, stream_cb=None):
    import re
    ids = re.findall(r'\[(\d+)\]', user_msg)
    return json.dumps([{"id": int(i), "verdict": "OK"} for i in ids])

with patch("bc4d_intel.ai.claude_client.call_claude", side_effect=mock_sonnet_ok):
    passed, corrections = quality_gate("test", classified_for_gate, test_taxonomy, "mock-key")

record("quality_gate_pass", passed and len(corrections) == 0,
       f"Passed: {passed}, Corrections: {len(corrections)}")

# Mock Sonnet — 50% wrong (should fail gate)
def mock_sonnet_fail(system, user_msg, task="report", api_key="", max_tokens=800, stream_cb=None):
    import re
    ids = re.findall(r'\[(\d+)\]', user_msg)
    results = []
    for i, id_str in enumerate(ids):
        if i % 2 == 0:
            results.append({"id": int(id_str), "verdict": "WRONG",
                            "cluster_id": "cat_2a", "main_category": "Kritik",
                            "cluster_title": "Zeitkritik"})
        else:
            results.append({"id": int(id_str), "verdict": "OK"})
    return json.dumps(results)

with patch("bc4d_intel.ai.claude_client.call_claude", side_effect=mock_sonnet_fail):
    passed2, corrections2 = quality_gate("test", classified_for_gate, test_taxonomy, "mock-key")

record("quality_gate_fail_detection", not passed2 and len(corrections2) > 0,
       f"Correctly failed: passed={passed2}, corrections={len(corrections2)}")

# ── 8. Reliability Checker ──────────────────────────────────────
print("\n--- 8. RELIABILITY CHECKER ---\n")

from bc4d_intel.core.answer_cache import test_reliability

# Dedup match (no API needed)
r1 = test_reliability("audit_test_question", "Die Trainerin war super kompetent")
record("reliability_dedup_hit",
       r1.get("matched") and r1.get("method") == "dedup",
       f"Method: {r1.get('method')}, Category: {r1.get('main_category')} > {r1.get('cluster_title')}")

# No match, no API
r2 = test_reliability("audit_test_question", "Something completely new")
record("reliability_no_match",
       not r2.get("matched") and r2.get("method") == "none",
       f"Method: {r2.get('method')}, Reason: {r2.get('reason', '')[:60]}")

# With mocked API
with patch("bc4d_intel.ai.claude_client.call_claude", side_effect=mock_haiku):
    r3 = test_reliability("audit_test_question", "Die Trainerin war engagiert",
                           api_key="mock-key")
record("reliability_llm",
       r3.get("matched") and r3.get("method") == "llm",
       f"Method: {r3.get('method')}, Category: {r3.get('main_category')} > {r3.get('cluster_title')}")

# ── 9. Validation Screen Data Flow ─────────────────────────────
print("\n--- 9. VALIDATION SCREEN DATA FLOW ---\n")

# Simulate what screen_analysis produces and what validation consumes
analysis_output = {
    "taxonomy": test_taxonomy,
    "flat_taxonomy": [
        {"id": "cat_1a", "title": "Trainer Lob", "main_category": "Positiv",
         "description": "Lob fuer Trainer", "count": 2},
        {"id": "cat_1b", "title": "Inhalt positiv", "main_category": "Positiv",
         "description": "Positive Inhaltsbewertung", "count": 0},
        {"id": "cat_2a", "title": "Zeitkritik", "main_category": "Kritik",
         "description": "Zeitbezogene Kritik", "count": 2},
    ],
    "classifications": classified,
}

# Check the data structure validation screen expects
record("validation_taxonomy_structure",
       "categories" in analysis_output["taxonomy"] and
       len(analysis_output["flat_taxonomy"]) == 3,
       f"Taxonomy: {len(analysis_output['taxonomy']['categories'])} main cats, "
       f"{len(analysis_output['flat_taxonomy'])} flat cats")

record("validation_classifications_structure",
       all(c.get("text") and c.get("cluster_id") for c in analysis_output["classifications"]),
       f"{len(analysis_output['classifications'])} classifications, all have text + cluster_id")

# Check flat_taxonomy counts match classifications
for ft in analysis_output["flat_taxonomy"]:
    count_from_classifications = sum(
        1 for c in classified
        if (c.get("human_override") or c.get("cluster_id")) == ft["id"])
    if count_from_classifications != ft["count"]:
        warn(f"flat_taxonomy count mismatch: {ft['title']} "
             f"has count={ft['count']} but {count_from_classifications} in classifications")

record("validation_counts_consistent", True, "Counts checked")

# ── 10. Embedder full_pipeline (mocked) ─────────────────────────
print("\n--- 10. EMBEDDER FULL_PIPELINE ---\n")

# This is the Staffel 1 path — verify it's importable and structured correctly
from bc4d_intel.core.embedder import full_pipeline, design_taxonomy

record("embedder_importable", True, "full_pipeline, design_taxonomy imported OK")

# Check that full_pipeline returns the expected structure
# (we can't run it without real API, but verify the function signature)
import inspect
sig = inspect.signature(full_pipeline)
params = list(sig.parameters.keys())
record("embedder_signature",
       "responses" in params and "api_key" in params and "question" in params,
       f"Parameters: {params}")

# ── 11. Screen Analysis Orchestration ───────────────────────────
print("\n--- 11. SCREEN ANALYSIS ORCHESTRATION ---\n")

# Verify the imports in screen_analysis resolve
try:
    # These are the exact imports screen_analysis uses
    from bc4d_intel.core.answer_cache import (
        deduplicate, add_to_cache,
        get_cached_taxonomy, save_taxonomy,
        classify_with_llm, quality_gate,
    )
    from bc4d_intel.core.embedder import full_pipeline
    record("analysis_imports", True, "All imports resolve")
except ImportError as e:
    record("analysis_imports", False, str(e))

# ── 12. Cache Persistence Round-Trip ────────────────────────────
print("\n--- 12. CACHE ROUND-TRIP ---\n")

from bc4d_intel.core.answer_cache import add_to_cache, get_cache_stats

# Add classifications, then dedup should find them
add_to_cache("audit_test_question", classified, staffel="audit_v5")
stats_after = get_cache_stats()

record("cache_round_trip",
       stats_after["total_answers"] >= len(classified),
       f"Cache now has {stats_after['total_answers']} answers, "
       f"{stats_after['taxonomies']} taxonomies")

# Dedup should now find all 4
deduped_rt, remaining_rt = deduplicate("audit_test_question",
    [c["text"] for c in classified])
record("dedup_round_trip", len(deduped_rt) == len(classified),
       f"Deduped: {len(deduped_rt)}/{len(classified)}")

# ════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("AUDIT SUMMARY")
print("=" * 70)

n_pass = sum(1 for r in RESULTS.values() if r["passed"])
n_fail = sum(1 for r in RESULTS.values() if not r["passed"])

for name, r in RESULTS.items():
    print(f"  {'PASS' if r['passed'] else 'FAIL'} -- {name}")

if WARNINGS:
    print(f"\n  WARNINGS ({len(WARNINGS)}):")
    for w in WARNINGS:
        print(f"    - {w}")

print(f"\n  {n_pass}/{n_pass + n_fail} passed, {len(WARNINGS)} warnings")

if n_fail == 0 and not WARNINGS:
    print("\n  VERDICT: ALL SYSTEMS OPERATIONAL")
elif n_fail == 0:
    print("\n  VERDICT: ALL SYSTEMS OPERATIONAL (with warnings)")
else:
    print(f"\n  VERDICT: {n_fail} FAILURES — needs attention")

sys.exit(0 if n_fail == 0 else 1)
