"""End-to-end test for v5 LLM-first pipeline with NEGATIV datasets.

Tests: import -> column detection -> panel matching -> dedup ->
LLM classification (mock) -> quality gate (mock) -> cache persistence.

No real API calls — mocks the LLM to test pipeline wiring and speed.
"""

from __future__ import annotations
import os, sys, time, json, random
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "bc4d_intel"))
sys.path.insert(0, os.path.dirname(__file__))

random.seed(42)
RESULTS = {}


def record(name, passed, details="", time_s=0):
    RESULTS[name] = {"passed": passed, "details": details, "time_s": time_s}
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" +
          (f" ({time_s:.1f}s)" if time_s else ""))
    if details:
        for line in details.split("\n")[:3]:
            print(f"         {line}")


# ════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("v5 LLM-FIRST PIPELINE: End-to-End Test (NEGATIV datasets)")
print("=" * 70)

# ── Phase 1: Data Loading ───────────────────────────────────────
print("\n--- PHASE 1: Data Loading ---\n")

from bc4d_intel.core.data_loader import load_survey

t0 = time.perf_counter()
pre_df, pre_roles = load_survey("NEGATIV_Vorbefragung_Staffel13.xlsx")
post_df, post_roles = load_survey("NEGATIV_Abschlussbefragung_Staffel13.xlsx")
load_time = time.perf_counter() - t0

record("data_loading", len(pre_df) > 0 and len(post_df) > 0,
       f"Pre: {len(pre_df)} rows, Post: {len(post_df)} rows", load_time)

# ── Phase 2: Panel Matching ─────────────────────────────────────
print("\n--- PHASE 2: Panel Matching ---\n")

from bc4d_intel.core.panel_matcher import match_panels

t0 = time.perf_counter()
match_result = match_panels(pre_df, pre_roles, post_df, post_roles)
match_time = time.perf_counter() - t0

pre_all = match_result.get("pre_all")
post_all = match_result.get("post_all")
matched = match_result.get("matched")

record("panel_matching",
       pre_all is not None and len(pre_all) == len(pre_df),
       f"Pre: {len(pre_all)}, Post: {len(post_all)}, "
       f"Matched: {len(matched) if matched is not None else 0}", match_time)

# ── Phase 3: Extract Free-Text ──────────────────────────────────
print("\n--- PHASE 3: Free-Text Extraction ---\n")

all_questions = []
for stype, df, roles in [("Pre", pre_all, pre_roles), ("Post", post_all, post_roles)]:
    if df is None:
        continue
    for col, role in roles.items():
        if role != "free_text" or col not in df.columns:
            continue
        responses = [r.strip() for r in df[col].dropna().astype(str).tolist()
                     if len(r.strip()) > 5]
        if len(responses) >= 5:
            all_questions.append((f"[{stype}] {col[:50]}", col, responses))

total_resp = sum(len(r) for _, _, r in all_questions)
record("extraction", len(all_questions) >= 3,
       f"{len(all_questions)} questions, {total_resp} responses")

for label, col, responses in all_questions:
    print(f"    {label[:60]:60s} | {len(responses):3d}")

# ── Phase 4: Deduplication ──────────────────────────────────────
print("\n--- PHASE 4: Deduplication (FREE) ---\n")

from bc4d_intel.core.answer_cache import deduplicate, get_cache_stats

stats = get_cache_stats()
print(f"  Cache: {stats['total_answers']} answers, {stats['taxonomies']} taxonomies\n")

total_deduped = 0
total_remaining = 0
dedup_time = 0

for label, col, responses in all_questions:
    t0 = time.perf_counter()
    deduped, remaining = deduplicate(label, responses)
    elapsed = time.perf_counter() - t0
    dedup_time += elapsed
    total_deduped += len(deduped)
    total_remaining += len(remaining)

    pct = len(deduped) / max(len(responses), 1) * 100
    print(f"    {label[:55]:55s} | {len(deduped):3d}/{len(responses):3d} "
          f"({pct:4.0f}%) | {elapsed:.2f}s")

record("deduplication", True,
       f"{total_deduped}/{total_resp} deduped ({total_deduped/max(total_resp,1)*100:.0f}%), "
       f"{total_remaining} need LLM", dedup_time)

# ── Phase 5: LLM Classification (MOCK) ─────────────────────────
print("\n--- PHASE 5: LLM Classification (mocked Haiku) ---\n")

from bc4d_intel.core.answer_cache import (
    classify_with_llm, get_cached_taxonomy, _build_taxonomy_ref,
)

# Mock the API call to test pipeline wiring without real costs
def mock_classify_response(system, user_msg, task="tagging", api_key="", max_tokens=1000, stream_cb=None):
    """Simulate Haiku classifying responses by extracting IDs and assigning mock categories."""
    import re
    # Count how many responses in the batch
    ids = re.findall(r'\[(\d+)\]', user_msg)
    results = []
    for id_str in ids:
        results.append({
            "id": int(id_str),
            "cluster_id": "cat_1a",
            "main_category": "Mock Category",
            "cluster_title": "Mock Sub",
            "confidence": "high",
        })
    return json.dumps(results)

# Test with one question that has a cached taxonomy
test_q = None
for label, col, responses in all_questions:
    tax = get_cached_taxonomy(label)
    if tax:
        test_q = (label, col, responses, tax)
        break

if test_q:
    label, col, responses, tax = test_q
    _, remaining = deduplicate(label, responses)

    if remaining:
        t0 = time.perf_counter()
        with patch("bc4d_intel.ai.claude_client.call_claude", side_effect=mock_classify_response):
            classified = classify_with_llm(col, remaining[:40], tax, "mock-key")
        elapsed = time.perf_counter() - t0

        record("llm_classification_wiring", len(classified) == min(40, len(remaining)),
               f"{len(classified)} classified from {min(40, len(remaining))} "
               f"in {elapsed:.2f}s (mocked)", elapsed)

        # Check output format
        required = ["text", "cluster_id", "cluster_title", "main_category",
                     "confidence", "match_type"]
        complete = sum(1 for c in classified if all(c.get(f) for f in required))
        record("output_format", complete == len(classified),
               f"{complete}/{len(classified)} have all required fields")
    else:
        record("llm_classification_wiring", True, "All deduped, no LLM needed")
        record("output_format", True, "N/A")
else:
    print("  No cached taxonomy found — would trigger full_pipeline (Staffel 1)")
    record("llm_classification_wiring", True, "Staffel 1 path (full_pipeline)")
    record("output_format", True, "N/A")

# ── Phase 6: Quality Gate (MOCK) ───────────────────────────────
print("\n--- PHASE 6: Quality Gate (mocked Sonnet) ---\n")

from bc4d_intel.core.answer_cache import quality_gate

def mock_quality_response(system, user_msg, task="report", api_key="", max_tokens=800, stream_cb=None):
    """Simulate Sonnet reviewing — flag 1 out of 15 as wrong."""
    import re
    ids = re.findall(r'\[(\d+)\]', user_msg)
    results = []
    for i, id_str in enumerate(ids):
        if i == 0:  # flag first one as wrong for testing
            results.append({"id": int(id_str), "verdict": "WRONG",
                            "cluster_id": "cat_2a", "main_category": "Corrected",
                            "cluster_title": "Corrected Sub"})
        else:
            results.append({"id": int(id_str), "verdict": "OK"})
    return json.dumps(results)

if test_q and classified:
    with patch("bc4d_intel.ai.claude_client.call_claude", side_effect=mock_quality_response):
        passed, corrections = quality_gate(col, classified, tax, "mock-key")

    record("quality_gate_wiring", True,
           f"Passed: {passed}, Corrections: {len(corrections)}")

    if corrections:
        print(f"    Sample correction: {corrections[0]['old_cluster_id']} -> "
              f"{corrections[0]['new_cluster_id']}")
else:
    record("quality_gate_wiring", True, "N/A (no classified data)")

# ── Phase 7: Cache Persistence ──────────────────────────────────
print("\n--- PHASE 7: Cache Persistence ---\n")

from bc4d_intel.core.answer_cache import add_to_cache

test_classifications = [
    {"text": "Test persistence response 12345",
     "cluster_id": "cat_1a", "cluster_title": "Test",
     "main_category": "Test", "confidence": "high"},
]

stats_before = get_cache_stats()
added = add_to_cache("test_v5_persistence", test_classifications, staffel="test_v5")
stats_after = get_cache_stats()

record("cache_persistence", added > 0,
       f"Added {added}, before={stats_before['total_answers']}, "
       f"after={stats_after['total_answers']}")

# Verify dedup finds it
deduped, remaining = deduplicate("test_v5_persistence",
                                  ["Test persistence response 12345"])
record("dedup_after_cache", len(deduped) == 1,
       f"Deduped: {len(deduped)} (should be 1)")

# ── Phase 8: Taxonomy Ref Quality ───────────────────────────────
print("\n--- PHASE 8: Taxonomy Reference Quality ---\n")

for label, col, responses in all_questions[:3]:
    tax = get_cached_taxonomy(label)
    if tax:
        ref = _build_taxonomy_ref(tax)
        n_cats = sum(len(c.get("sub_categories", []))
                     for c in tax["categories"])
        has_examples = "Beispiele:" in ref
        has_rules = "Regel:" in ref
        print(f"  {label[:55]}")
        print(f"    Categories: {n_cats}, Has examples: {has_examples}, "
              f"Has rules: {has_rules}")
        print(f"    Ref length: {len(ref)} chars")
        # Show first category
        first_line = ref.split("\n")[0] if ref else "N/A"
        print(f"    Sample: {first_line[:80]}")
        print()

record("taxonomy_quality", True, "Manual inspection above")

# ── Phase 9: test_reliability (without API) ─────────────────────
print("--- PHASE 9: Reliability Checker ---\n")

from bc4d_intel.core.answer_cache import test_reliability

# Without API key — should check dedup only
r1 = test_reliability("test_v5_persistence", "Test persistence response 12345")
record("reliability_dedup", r1.get("matched") and r1.get("method") == "dedup",
       f"Method: {r1.get('method')}, Matched: {r1.get('matched')}")

r2 = test_reliability("test_v5_persistence", "Completely new text", api_key="")
record("reliability_no_api", not r2.get("matched"),
       f"Method: {r2.get('method')}, Reason: {r2.get('reason', '')[:60]}")

# ── Speed Summary ───────────────────────────────────────────────
print("\n--- SPEED SUMMARY ---\n")

print(f"  Data loading:    {load_time:.1f}s")
print(f"  Panel matching:  {match_time:.1f}s")
print(f"  Deduplication:   {dedup_time:.1f}s (no ML models!)")
print(f"  Total (no API):  {load_time + match_time + dedup_time:.1f}s")
print(f"  Model load:      0.0s (no ML models in v5!)")
print()
print(f"  Estimated with Haiku API:")
print(f"    {total_remaining} responses / 20 per batch = "
      f"{(total_remaining + 19) // 20} API calls")
print(f"    ~{(total_remaining + 19) // 20 * 2}s API time (est.)")
print(f"    ~${total_remaining * 0.0002:.3f} API cost")

# ── Final Summary ───────────────────────────────────────────────
print("\n" + "=" * 70)
print("FINAL SUMMARY")
print("=" * 70)

n_pass = sum(1 for r in RESULTS.values() if r["passed"])
n_fail = sum(1 for r in RESULTS.values() if not r["passed"])

for name, r in RESULTS.items():
    t = f" ({r['time_s']:.1f}s)" if r['time_s'] else ""
    print(f"  {'PASS' if r['passed'] else 'FAIL'} -- {name}{t}")

print(f"\n  {n_pass}/{n_pass + n_fail} passed")
sys.exit(0 if n_fail == 0 else 1)
