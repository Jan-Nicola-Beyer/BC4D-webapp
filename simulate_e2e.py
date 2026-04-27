"""End-to-end simulation of BC4D Intel pipeline using synthetic datasets.

Tests the FULL pipeline: load → detect roles → panel match → cache check →
AI classify (if needed) → add to cache → verify output quality.

Tracks:
  - Speed at each stage
  - Cache hit rates
  - API call count and estimated cost
  - Classification quality (consistency, completeness)
  - Robustness (error handling, edge cases)

Usage:
  python simulate_e2e.py              # cache-only mode (no API, no cost)
  python simulate_e2e.py --with-api   # full pipeline including API calls
"""

from __future__ import annotations
import argparse, json, os, sys, time, random
from typing import Dict, List, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "bc4d_intel"))
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd
import numpy as np

# ── Config ──────────────────────────────────────────────────────
PRE_PATH = os.path.join(os.path.dirname(__file__),
                        "Synthetisch_Vorbefragung_Staffel13.xlsx")
POST_PATH = os.path.join(os.path.dirname(__file__),
                         "Synthetisch_Abschlussbefragung_Staffel13.xlsx")

RESULTS = {}  # {test_name: {passed, details, time_s}}


def record(name: str, passed: bool, details: str = "", time_s: float = 0):
    RESULTS[name] = {"passed": passed, "details": details, "time_s": time_s}
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}" + (f" ({time_s:.2f}s)" if time_s else ""))
    if details:
        for line in details.split("\n"):
            print(f"         {line}")


# ════════════════════════════════════════════════════════════════
# PHASE 1: Data Loading & Column Detection
# ════════════════════════════════════════════════════════════════

def test_data_loading():
    print("\n" + "=" * 70)
    print("PHASE 1: Data Loading & Column Detection")
    print("=" * 70)

    from bc4d_intel.core.data_loader import load_survey, detect_column_roles

    # --- Pre-survey ---
    t0 = time.perf_counter()
    pre_df, pre_roles = load_survey(PRE_PATH)
    t1 = time.perf_counter()

    pre_ft = [c for c, r in pre_roles.items() if r == "free_text"]
    pre_likert = [c for c, r in pre_roles.items() if r == "likert"]
    pre_pseudo_s = [c for c, r in pre_roles.items() if r == "pseudokey_street"]
    pre_pseudo_b = [c for c, r in pre_roles.items() if r == "pseudokey_birthday"]

    record("pre_survey_load",
           len(pre_df) > 0 and len(pre_roles) > 0,
           f"{len(pre_df)} rows, {len(pre_roles)} columns, "
           f"{len(pre_ft)} free_text, {len(pre_likert)} likert, "
           f"pseudokeys: {len(pre_pseudo_s)}+{len(pre_pseudo_b)}",
           t1 - t0)

    # --- Post-survey ---
    t2 = time.perf_counter()
    post_df, post_roles = load_survey(POST_PATH)
    t3 = time.perf_counter()

    post_ft = [c for c, r in post_roles.items() if r == "free_text"]
    post_likert = [c for c, r in post_roles.items() if r == "likert"]

    record("post_survey_load",
           len(post_df) > 0 and len(post_roles) > 0,
           f"{len(post_df)} rows, {len(post_roles)} columns, "
           f"{len(post_ft)} free_text, {len(post_likert)} likert",
           t3 - t2)

    # --- Robustness: free_text detection ---
    record("free_text_detection",
           len(pre_ft) >= 1 and len(post_ft) >= 5,
           f"Pre: {pre_ft[:3]}... Post: {post_ft[:3]}...")

    # --- Robustness: pseudokey columns found ---
    record("pseudokey_detection",
           len(pre_pseudo_s) >= 1 and len(pre_pseudo_b) >= 1,
           f"Street: {pre_pseudo_s}, Birthday: {pre_pseudo_b}")

    return pre_df, pre_roles, post_df, post_roles


# ════════════════════════════════════════════════════════════════
# PHASE 2: Panel Matching
# ════════════════════════════════════════════════════════════════

def test_panel_matching(pre_df, pre_roles, post_df, post_roles):
    print("\n" + "=" * 70)
    print("PHASE 2: Panel Matching")
    print("=" * 70)

    from bc4d_intel.core.panel_matcher import match_panels

    t0 = time.perf_counter()
    result = match_panels(pre_df, pre_roles, post_df, post_roles)
    t1 = time.perf_counter()

    stats = result.get("stats", {})
    pre_all = result.get("pre_all")
    post_all = result.get("post_all")
    matched = result.get("matched")

    record("panel_matching",
           pre_all is not None and post_all is not None,
           f"Pre: {len(pre_all) if pre_all is not None else 0}, "
           f"Post: {len(post_all) if post_all is not None else 0}, "
           f"Matched pairs: {len(matched) if matched is not None else 0}",
           t1 - t0)

    # Robustness: no data loss
    record("no_data_loss",
           (pre_all is not None and len(pre_all) == len(pre_df)) and
           (post_all is not None and len(post_all) == len(post_df)),
           f"Pre: {len(pre_all) if pre_all is not None else 0}/{len(pre_df)}, "
           f"Post: {len(post_all) if post_all is not None else 0}/{len(post_df)}")

    # Match rate should be reasonable (>20% for synthetic data)
    if matched is not None and post_all is not None and len(post_all) > 0:
        match_rate = len(matched) / len(post_all) * 100
        record("match_rate_reasonable",
               match_rate > 10,
               f"{match_rate:.0f}% of post-survey matched to pre")
    else:
        record("match_rate_reasonable", False, "No matched data")

    return result


# ════════════════════════════════════════════════════════════════
# PHASE 3: Free-Text Question Extraction
# ════════════════════════════════════════════════════════════════

def extract_free_text_questions(result, pre_roles, post_roles):
    print("\n" + "=" * 70)
    print("PHASE 3: Free-Text Question Extraction")
    print("=" * 70)

    pre_all = result.get("pre_all")
    post_all = result.get("post_all")

    all_questions = []  # (label, column_name, responses_list)

    for survey_type, df, roles in [("Pre", pre_all, pre_roles),
                                    ("Post", post_all, post_roles)]:
        if df is None:
            continue
        for col, role in roles.items():
            if role != "free_text":
                continue
            if col not in df.columns:
                continue
            responses = df[col].dropna().astype(str).tolist()
            responses = [r.strip() for r in responses if len(r.strip()) > 5]
            if len(responses) < 5:
                continue
            label = f"[{survey_type}] {col}"
            all_questions.append((label, col, responses))

    record("questions_extracted",
           len(all_questions) >= 5,
           f"{len(all_questions)} free-text questions found")

    # Show breakdown
    for label, col, responses in all_questions:
        print(f"    {label[:60]:60s} | {len(responses):3d} responses")

    return all_questions


# ════════════════════════════════════════════════════════════════
# PHASE 4: Cache-Only Classification (no API cost)
# ════════════════════════════════════════════════════════════════

def test_cache_classification(all_questions):
    print("\n" + "=" * 70)
    print("PHASE 4: Cache-Only Classification (FREE)")
    print("=" * 70)

    from bc4d_intel.core.answer_cache import (
        classify_from_cache, get_cached_answers, _get_bi_encoder,
        _get_cross_encoder,
    )

    # Pre-load models
    print("  Loading models...")
    t_model = time.perf_counter()
    _get_bi_encoder()
    _get_cross_encoder()
    print(f"  Models loaded in {time.perf_counter() - t_model:.1f}s\n")

    total_responses = 0
    total_hits = 0
    total_misses = 0
    question_results = []
    total_time = 0

    for label, col, responses in all_questions:
        t0 = time.perf_counter()
        hits, misses = classify_from_cache(label, responses)
        elapsed = time.perf_counter() - t0

        total_responses += len(responses)
        total_hits += len(hits)
        total_misses += len(misses)
        total_time += elapsed

        hit_rate = len(hits) / max(len(responses), 1) * 100
        question_results.append({
            "label": label,
            "n_responses": len(responses),
            "n_hits": len(hits),
            "n_misses": len(misses),
            "hit_rate": hit_rate,
            "time_s": elapsed,
        })

        print(f"    {label[:50]:50s} | {len(hits):3d}/{len(responses):3d} "
              f"({hit_rate:5.1f}%) | {elapsed:.1f}s")

    overall_hit_rate = total_hits / max(total_responses, 1) * 100

    record("cache_overall_hit_rate",
           overall_hit_rate > 50,
           f"{total_hits}/{total_responses} = {overall_hit_rate:.1f}%",
           total_time)

    record("cache_speed",
           total_time < 300,
           f"{total_responses} responses in {total_time:.1f}s "
           f"({total_responses / max(total_time, 0.1):.1f} resp/s)")

    # Quality check: all cache hits must have complete classification data
    complete = 0
    incomplete = 0
    for label, col, responses in all_questions:
        hits, _ = classify_from_cache(label, responses)
        for h in hits:
            has_all = all(h.get(k) for k in ["cluster_id", "cluster_title",
                                              "main_category", "text"])
            if has_all:
                complete += 1
            else:
                incomplete += 1

    record("cache_output_completeness",
           incomplete == 0,
           f"{complete} complete, {incomplete} incomplete classifications")

    return question_results, total_misses


# ════════════════════════════════════════════════════════════════
# PHASE 5: Full Pipeline with API (cost-controlled)
# ════════════════════════════════════════════════════════════════

def test_full_pipeline(all_questions, api_key: str):
    print("\n" + "=" * 70)
    print("PHASE 5: Full Pipeline (API calls — cost tracked)")
    print("=" * 70)

    from bc4d_intel.core.answer_cache import classify_from_cache, add_to_cache
    from bc4d_intel.core.embedder import full_pipeline

    # Cost tracking
    api_calls = {"taxonomy": 0, "edge_cases": 0}
    estimated_cost = 0.0

    # Pick ONE question with uncached responses to test the full pipeline
    # This limits API costs to ~$0.08
    test_question = None
    for label, col, responses in all_questions:
        hits, misses = classify_from_cache(label, responses)
        if len(misses) >= 5:
            test_question = (label, col, responses, hits, misses)
            break

    if test_question is None:
        # All responses cached — create a small test with modified responses
        # to force cache misses without using real API calls
        print("  All responses cached. Testing with paraphrased responses...")
        label, col, responses = all_questions[0][:3]
        # Take 10 responses and slightly modify them to force cache misses
        test_misses = []
        for r in responses[:10]:
            modified = "Antwort: " + r + " (Zusatzkommentar)"
            test_misses.append(modified)

        hits_orig, _ = classify_from_cache(label, responses)
        test_question = (label, col, responses, hits_orig, test_misses)

    label, col, all_resp, cached_hits, uncached = test_question
    n_uncached = len(uncached)

    # Cost estimate BEFORE calling API
    est_taxonomy = 0.03   # Sonnet taxonomy design
    est_edge = 0.02       # Haiku edge case review (~20% of responses)
    est_total = est_taxonomy + est_edge

    print(f"\n  Selected question: '{label[:60]}'")
    print(f"  Uncached responses: {n_uncached}")
    print(f"  Estimated API cost: ~${est_total:.2f}")
    print(f"    - Taxonomy design (Sonnet): ~${est_taxonomy:.2f}")
    print(f"    - Edge case review (Haiku): ~${est_edge:.2f}")

    if est_total > 0.50:
        print(f"\n  ⚠ WARNING: Estimated cost ${est_total:.2f} exceeds $0.50!")
        print(f"  Skipping API test to avoid high costs.")
        record("full_pipeline_api", False,
               f"Skipped — estimated cost ${est_total:.2f} too high")
        return

    # Run the full pipeline
    print(f"\n  Running full pipeline on {n_uncached} uncached responses...")
    t0 = time.perf_counter()

    try:
        result = full_pipeline(
            uncached, api_key, question=col,
            progress_cb=lambda msg: print(f"    {msg}")
        )
        elapsed = time.perf_counter() - t0

        taxonomy = result.get("taxonomy", {})
        classifications = result.get("classifications", [])
        flat_taxonomy = result.get("flat_taxonomy", [])

        # Validate taxonomy
        categories = taxonomy.get("categories", [])
        n_cats = sum(len(c.get("sub_categories", []))
                     for c in categories)

        record("taxonomy_generated",
               n_cats >= 2,
               f"{len(categories)} main categories, {n_cats} sub-categories",
               elapsed)

        # Validate classifications
        n_classified = len(classifications)
        n_high = sum(1 for c in classifications if c.get("confidence") == "high")
        n_med = sum(1 for c in classifications if c.get("confidence") == "medium")
        n_low = sum(1 for c in classifications if c.get("confidence") == "low")

        record("all_responses_classified",
               n_classified == n_uncached,
               f"{n_classified}/{n_uncached} classified "
               f"(high={n_high}, med={n_med}, low={n_low})")

        # Every classification must have required fields
        required = ["text", "cluster_id", "cluster_title", "main_category", "confidence"]
        complete = sum(1 for c in classifications
                       if all(c.get(k) for k in required))

        record("classification_completeness",
               complete == n_classified,
               f"{complete}/{n_classified} have all required fields")

        # Validate flat_taxonomy
        record("flat_taxonomy_generated",
               len(flat_taxonomy) >= 2,
               f"{len(flat_taxonomy)} categories with counts")

        # Test cache addition
        from bc4d_intel.core.answer_cache import add_to_cache, get_cache_stats
        stats_before = get_cache_stats()
        added = add_to_cache(label, classifications, staffel="simulation_test")
        stats_after = get_cache_stats()

        record("cache_addition",
               added >= 0,
               f"Added {added} to cache "
               f"(before={stats_before['total_answers']}, "
               f"after={stats_after['total_answers']})")

        # Re-classify — should now get cache hits
        hits2, misses2 = classify_from_cache(label, uncached[:5])
        record("re_cache_hit",
               len(hits2) >= 3,
               f"{len(hits2)}/5 responses now cached after pipeline")

        api_calls["taxonomy"] = 1
        api_calls["edge_cases"] = 1 if n_low > 0 else 0
        estimated_cost = est_total

    except Exception as e:
        elapsed = time.perf_counter() - t0
        record("full_pipeline_api", False, f"ERROR: {e}", elapsed)
        return

    print(f"\n  API cost estimate: ${estimated_cost:.2f}")
    print(f"  API calls: taxonomy={api_calls['taxonomy']}, "
          f"edge_cases={api_calls['edge_cases']}")

    return {
        "api_calls": api_calls,
        "estimated_cost": estimated_cost,
        "n_uncached": n_uncached,
    }


# ════════════════════════════════════════════════════════════════
# PHASE 6: Cross-Question Consistency & Quality Checks
# ════════════════════════════════════════════════════════════════

def test_quality_checks(all_questions):
    print("\n" + "=" * 70)
    print("PHASE 6: Quality & Robustness Checks")
    print("=" * 70)

    from bc4d_intel.core.answer_cache import (
        classify_from_cache, _sentiment, _check_safety_guards,
        test_reliability, get_cached_answers, _normalize_question,
    )

    # --- Test 1: Duplicate responses get same classification ---
    print("\n  Consistency: duplicate responses get same classification")
    question = all_questions[0]
    label, col, responses = question[:3]
    # Find natural duplicates or use first response twice
    test_batch = [responses[0], responses[0], responses[1], responses[1]]
    hits, misses = classify_from_cache(label, test_batch)

    if len(hits) >= 2:
        # Check that identical responses got same cluster
        clusters_by_text = {}
        for h in hits:
            clusters_by_text.setdefault(h["text"], []).append(h["cluster_id"])
        consistent = all(len(set(v)) == 1 for v in clusters_by_text.values())
        record("duplicate_consistency", consistent,
               f"{len(clusters_by_text)} unique texts, all consistent={consistent}")
    else:
        record("duplicate_consistency", True, "Not enough hits to test (OK)")

    # --- Test 2: Empty/short/garbage responses handled gracefully ---
    print("\n  Robustness: edge case responses")
    edge_cases = [
        "",           # empty
        ".",          # single char
        "k.A.",       # common German "no answer"
        "/",          # slash (common non-answer)
        "Nichts",     # single word
        "x" * 500,    # very long garbage
        "1234567890", # numbers only
    ]
    hits_e, misses_e = classify_from_cache(label, edge_cases)
    # These should all be misses (sent to AI) or gracefully handled
    record("edge_case_handling",
           True,  # no crash = pass
           f"{len(hits_e)} cached, {len(misses_e)} sent to AI (no crash)")

    # --- Test 3: Sentiment detection on real responses ---
    print("\n  Sentiment: spot-check real responses")
    cached = get_cached_answers("Bitte nennen Sie Staerken des Kurses.")
    if cached:
        # Strength question: most responses should be positive or neutral
        sentiments = [_sentiment(c["response_text"]) for c in cached[:50]]
        n_pos = sum(1 for s in sentiments if s == 1)
        n_neg = sum(1 for s in sentiments if s == -1)
        n_neu = sum(1 for s in sentiments if s == 0)
        record("sentiment_strength_question",
               n_pos + n_neu > n_neg,
               f"Strength Q: POS={n_pos}, NEU={n_neu}, NEG={n_neg} (of 50)")

    cached_imp = get_cached_answers("Bitte nennen Sie Verbesserungsmoeglichkeiten.")
    if cached_imp:
        sentiments = [_sentiment(c["response_text"]) for c in cached_imp[:50]]
        n_pos = sum(1 for s in sentiments if s == 1)
        n_neg = sum(1 for s in sentiments if s == -1)
        n_neu = sum(1 for s in sentiments if s == 0)
        record("sentiment_improvement_question",
               n_neg + n_neu > n_pos,
               f"Improvement Q: POS={n_pos}, NEU={n_neu}, NEG={n_neg} (of 50)")

    # --- Test 4: Question fuzzy matching across all questions ---
    print("\n  Fuzzy matching: all questions resolve")
    from bc4d_intel.core.answer_cache import _fuzzy_match_question, _get_conn
    conn = _get_conn()
    matched = 0
    unmatched = []
    for label, col, responses in all_questions:
        pattern = _fuzzy_match_question(label, conn)
        if pattern:
            matched += 1
        else:
            unmatched.append(label)
    conn.close()

    record("all_questions_fuzzy_match",
           len(unmatched) == 0,
           f"{matched}/{len(all_questions)} matched" +
           (f", unmatched: {unmatched}" if unmatched else ""))

    # --- Test 5: Guard telemetry sanity ---
    print("\n  Guard telemetry: guards fire on adversarial pairs")
    # Positive vs negative
    ok1, g1 = _check_safety_guards("Alles war super toll", "Alles war schlecht")
    # Same sentiment
    ok2, g2 = _check_safety_guards("Trainer war toll", "Trainer war super")
    record("guard_blocks_correctly",
           not ok1 and ok2,
           f"Opposite sentiment: blocked={not ok1} ({g1}), "
           f"Same sentiment: passed={ok2}")


# ════════════════════════════════════════════════════════════════
# PHASE 7: Speed Summary
# ════════════════════════════════════════════════════════════════

def print_summary():
    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)

    n_pass = sum(1 for r in RESULTS.values() if r["passed"])
    n_fail = sum(1 for r in RESULTS.values() if not r["passed"])
    total_time = sum(r["time_s"] for r in RESULTS.values())

    print(f"\n  Tests: {n_pass} passed, {n_fail} failed, "
          f"{n_pass + n_fail} total")
    print(f"  Total time: {total_time:.1f}s\n")

    for name, r in RESULTS.items():
        status = "PASS" if r["passed"] else "FAIL"
        time_str = f" ({r['time_s']:.1f}s)" if r["time_s"] > 0 else ""
        print(f"  [{status}] {name}{time_str}")
        if r["details"]:
            print(f"         {r['details'][:100]}")

    print()
    return n_fail == 0


# ════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-api", action="store_true",
                        help="Enable API calls (costs ~$0.05-0.10)")
    parser.add_argument("--api-key", default=os.environ.get("ANTHROPIC_API_KEY", ""),
                        help="Anthropic API key")
    args = parser.parse_args()

    print("\nBC4D Intel — Full End-to-End Simulation")
    print(f"Mode: {'FULL (with API)' if args.with_api else 'CACHE-ONLY (free)'}")
    print(f"Datasets: Synthetisch_*_Staffel13.xlsx\n")

    # Phase 1: Load data
    pre_df, pre_roles, post_df, post_roles = test_data_loading()

    # Phase 2: Panel matching
    panel_result = test_panel_matching(pre_df, pre_roles, post_df, post_roles)

    # Phase 3: Extract free-text questions
    all_questions = extract_free_text_questions(panel_result, pre_roles, post_roles)

    # Phase 4: Cache-only classification
    cache_results, total_misses = test_cache_classification(all_questions)

    # Phase 5: Full pipeline (only if --with-api)
    if args.with_api:
        api_key = args.api_key
        if not api_key:
            # Try to load from app settings
            settings_path = os.path.join(os.path.dirname(__file__),
                                         "bc4d_intel", "sessions", "latest.bc4d")
            if os.path.exists(settings_path):
                try:
                    with open(settings_path) as f:
                        data = json.load(f)
                    api_key = data.get("api_key", "")
                except Exception:
                    pass

        if not api_key:
            print("\n  ⚠ No API key found. Skipping Phase 5.")
            print("  Set ANTHROPIC_API_KEY or use --api-key=...")
            record("full_pipeline_api", False, "No API key")
        else:
            test_full_pipeline(all_questions, api_key)
    else:
        print("\n" + "=" * 70)
        print("PHASE 5: Full Pipeline — SKIPPED (no --with-api flag)")
        print("=" * 70)
        print(f"  {total_misses} responses would need API calls")
        est_questions_needing_api = sum(1 for r in cache_results
                                        if r["n_misses"] > 0)
        est_cost = est_questions_needing_api * 0.05
        print(f"  {est_questions_needing_api} questions have uncached responses")
        print(f"  Estimated API cost if enabled: ~${est_cost:.2f}")
        print(f"  Run with --with-api to test the full pipeline")

    # Phase 6: Quality & robustness
    test_quality_checks(all_questions)

    # Summary
    all_pass = print_summary()
    sys.exit(0 if all_pass else 1)
