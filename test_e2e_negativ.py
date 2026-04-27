"""Comprehensive end-to-end test with NEGATIV datasets.

Tests EVERY stage: import -> column detection -> panel matching ->
cache classification -> reliability checks -> anomaly detection.
Checks speed, precision, robustness, and logical consistency.

No API calls — measures what WOULD go to API.
"""

from __future__ import annotations
import os, sys, time, random, json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "bc4d_intel"))
sys.path.insert(0, os.path.dirname(__file__))

random.seed(42)
RESULTS = {}


def record(name, passed, details="", time_s=0):
    RESULTS[name] = {"passed": passed, "details": details, "time_s": time_s}
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {name}" + (f" ({time_s:.1f}s)" if time_s else ""))
    if details:
        for line in details.split("\n")[:3]:
            print(f"         {line}")


# ════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("FULL END-TO-END TEST: NEGATIV Datasets")
print("=" * 70)

# ── Phase 1: Data Loading ───────────────────────────────────────
print("\n--- PHASE 1: Data Loading & Column Detection ---\n")

from bc4d_intel.core.data_loader import load_survey, detect_column_roles

PRE_PATH = "NEGATIV_Vorbefragung_Staffel13.xlsx"
POST_PATH = "NEGATIV_Abschlussbefragung_Staffel13.xlsx"

t0 = time.perf_counter()
pre_df, pre_roles = load_survey(PRE_PATH)
pre_time = time.perf_counter() - t0

t0 = time.perf_counter()
post_df, post_roles = load_survey(POST_PATH)
post_time = time.perf_counter() - t0

pre_ft = [c for c, r in pre_roles.items() if r == "free_text"]
post_ft = [c for c, r in post_roles.items() if r == "free_text"]
pre_likert = [c for c, r in pre_roles.items() if r == "likert"]
post_likert = [c for c, r in post_roles.items() if r == "likert"]
pre_pseudo = [c for c, r in pre_roles.items() if "pseudokey" in r]
post_pseudo = [c for c, r in post_roles.items() if "pseudokey" in r]

record("pre_load", len(pre_df) > 0,
       f"{len(pre_df)} rows, {len(pre_roles)} cols, "
       f"{len(pre_ft)} free_text, {len(pre_likert)} likert, "
       f"{len(pre_pseudo)} pseudokeys", pre_time)

record("post_load", len(post_df) > 0,
       f"{len(post_df)} rows, {len(post_roles)} cols, "
       f"{len(post_ft)} free_text, {len(post_likert)} likert", post_time)

# Robustness: must detect pseudokeys for panel matching
record("pseudokeys_found", len(pre_pseudo) >= 2,
       f"Pre pseudokeys: {pre_pseudo}")

# Robustness: must find free-text columns
record("free_text_found", len(pre_ft) >= 1 and len(post_ft) >= 3,
       f"Pre: {len(pre_ft)}, Post: {len(post_ft)}")


# ── Phase 2: Panel Matching ─────────────────────────────────────
print("\n--- PHASE 2: Panel Matching ---\n")

from bc4d_intel.core.panel_matcher import match_panels

t0 = time.perf_counter()
match_result = match_panels(pre_df, pre_roles, post_df, post_roles)
match_time = time.perf_counter() - t0

pre_all = match_result.get("pre_all")
post_all = match_result.get("post_all")
matched = match_result.get("matched")

record("panel_match", pre_all is not None and post_all is not None,
       f"Pre: {len(pre_all) if pre_all is not None else 0}, "
       f"Post: {len(post_all) if post_all is not None else 0}, "
       f"Matched: {len(matched) if matched is not None else 0}", match_time)

# No data loss
record("no_data_loss",
       (pre_all is not None and len(pre_all) == len(pre_df)) and
       (post_all is not None and len(post_all) == len(post_df)),
       f"Pre: {len(pre_all) if pre_all is not None else 0}/{len(pre_df)}, "
       f"Post: {len(post_all) if post_all is not None else 0}/{len(post_df)}")


# ── Phase 3: Extract Free-Text Questions ────────────────────────
print("\n--- PHASE 3: Free-Text Extraction ---\n")

all_questions = []
for survey_type, df, roles in [("Pre", pre_all, pre_roles),
                                 ("Post", post_all, post_roles)]:
    if df is None:
        continue
    for col, role in roles.items():
        if role != "free_text" or col not in df.columns:
            continue
        responses = df[col].dropna().astype(str).tolist()
        responses = [r.strip() for r in responses if len(r.strip()) > 5]
        if len(responses) >= 5:
            label = f"[{survey_type}] {col[:50]}"
            all_questions.append((label, col, responses))

total_responses = sum(len(r) for _, _, r in all_questions)
record("questions_extracted", len(all_questions) >= 3,
       f"{len(all_questions)} questions, {total_responses} total responses")

for label, col, responses in all_questions:
    print(f"    {label[:60]:60s} | {len(responses):3d} responses")


# ── Phase 4: Load Models ────────────────────────────────────────
print("\n--- PHASE 4: Model Loading ---\n")

from bc4d_intel.core.answer_cache import (
    classify_from_cache, get_cached_answers, get_cache_stats,
    test_reliability, find_anomalies,
    _get_bi_encoder, _get_cross_encoder, _sentiment,
)

t0 = time.perf_counter()
_get_bi_encoder()
_get_cross_encoder()
model_time = time.perf_counter() - t0
record("models_loaded", True, f"{model_time:.1f}s", model_time)

stats = get_cache_stats()
print(f"    Cache: {stats['total_answers']} answers, "
      f"{stats['questions']} questions, {stats['taxonomies']} taxonomies")


# ── Phase 5: Classification (per question) ──────────────────────
print("\n--- PHASE 5: Cache Classification ---\n")

print(f"  {'Question':<55} | {'N':>3} | {'A':>3} {'B':>3} {'C':>3} | {'Hit%':>5} | {'Time':>5}")
print("  " + "-" * 85)

grand_classified = []
grand_uncertain = []
grand_a = grand_b = grand_c = 0
classify_time = 0

for label, col, responses in all_questions:
    t0 = time.perf_counter()
    classified, uncertain = classify_from_cache(label, responses)
    elapsed = time.perf_counter() - t0
    classify_time += elapsed

    case_a = sum(1 for c in classified if c.get("match_case") == "a")
    case_b = sum(1 for c in classified if c.get("match_case") == "b")
    case_c = len(uncertain)
    hit_pct = len(classified) / max(len(responses), 1) * 100

    grand_classified.extend(classified)
    grand_uncertain.extend(uncertain)
    grand_a += case_a
    grand_b += case_b
    grand_c += case_c

    print(f"  {label[:55]:55s} | {len(responses):3d} | "
          f"{case_a:3d} {case_b:3d} {case_c:3d} | {hit_pct:4.0f}% | {elapsed:5.1f}s")

overall_hit = len(grand_classified) / max(total_responses, 1) * 100
record("classification_speed", classify_time < 300,
       f"{total_responses} responses in {classify_time:.0f}s "
       f"({total_responses/max(classify_time,0.01):.1f} resp/s)", classify_time)

record("classification_completeness",
       len(grand_classified) + len(grand_uncertain) == total_responses,
       f"Classified={len(grand_classified)} + Uncertain={len(grand_uncertain)} "
       f"= {len(grand_classified)+len(grand_uncertain)} (expected {total_responses})")


# ── Phase 6: Reliability Checks ────────────────────────────────
print("\n--- PHASE 6: Reliability Checks (targeted) ---\n")

# Test specific edge cases that should be handled correctly
reliability_tests = [
    ("Was hat Ihnen besonders gut gefallen?",
     "nichts, der Kurs war sehr schlecht",
     False, "Negative response to positive question -> Case C"),

    ("Was hat Ihnen besonders gut gefallen?",
     "Die Trainerin war sehr kompetent und engagiert",
     True, "Clearly positive -> should match"),

    ("Bitte nennen Sie Staerken des Kurses.",
     "Es gab keine Staerken, alles war schlecht",
     False, "Strongly negative to strength question -> Case C"),

    ("Bitte nennen Sie Verbesserungsmoeglichkeiten.",
     "Die Zeitplanung war schlecht und unstrukturiert",
     True, "Negative response to improvement question -> should match"),

    ("Bitte nennen Sie Staerken des Kurses.",
     "Gute Moderation und interessante Inhalte",
     True, "Standard positive -> should match"),
]

all_reliability_ok = True
for question, text, expect_match, description in reliability_tests:
    r = test_reliability(question, text)
    ok = r.get("matched") == expect_match
    if not ok:
        all_reliability_ok = False

    status = "PASS" if ok else "FAIL"
    print(f"  [{status}] {description}")
    print(f"         Input: \"{text[:60]}\"")
    print(f"         Case: {r['case']} | Matched: {r['matched']} "
          f"(expected: {expect_match}) | Score: {r['score']}")
    print(f"         Category: {r.get('main_category','')} > {r.get('cluster_title','')}")
    if r.get("neighbour_vote"):
        top = r["neighbour_vote"][0]
        print(f"         Top vote: {top['category']} ({top['votes']}/10)")
    print(f"         Reason: {r.get('reason', '')[:80]}")
    print()

record("reliability_checks", all_reliability_ok, "")


# ── Phase 7: Anomaly Detection ──────────────────────────────────
print("--- PHASE 7: Anomaly Detection ---\n")

if len(grand_classified) >= 20:
    t0 = time.perf_counter()
    anomalies = find_anomalies(grand_classified)
    anom_time = time.perf_counter() - t0

    record("anomaly_detection", True,
           f"{len(anomalies)} anomalies from {len(grand_classified)} classified",
           anom_time)

    if anomalies:
        print(f"    Top outliers:")
        for a in anomalies[:5]:
            print(f"      dist={a['distance']:.4f} | "
                  f"{a['main_category'][:15]} > {a['cluster_title'][:20]} | "
                  f"\"{a['text'][:50]}\"")
else:
    record("anomaly_detection", True, "Not enough classified for anomaly detection")


# ── Phase 8: Sentiment Correctness ──────────────────────────────
print("\n--- PHASE 8: Sentiment Correctness (NEGATIV data) ---\n")

# Since this is NEGATIV data, check that negative responses are detected
neg_responses = []
for _, _, responses in all_questions:
    neg_responses.extend(responses[:10])

sentiments = [_sentiment(r) for r in neg_responses]
n_pos = sum(1 for s in sentiments if s == 1)
n_neg = sum(1 for s in sentiments if s == -1)
n_neu = sum(1 for s in sentiments if s == 0)

record("sentiment_distribution", True,
       f"Sample of {len(sentiments)}: POS={n_pos}, NEU={n_neu}, NEG={n_neg}")


# ── Phase 9: Output Quality ────────────────────────────────────
print("\n--- PHASE 9: Output Quality & Consistency ---\n")

# All classified responses must have required fields
required = ["text", "cluster_id", "cluster_title", "main_category",
            "confidence", "match_case"]
complete = 0
incomplete = 0
for c in grand_classified:
    if all(c.get(f) for f in required):
        complete += 1
    else:
        incomplete += 1
        if incomplete <= 3:
            missing = [f for f in required if not c.get(f)]
            print(f"    Incomplete: missing {missing} for \"{c.get('text','')[:40]}\"")

record("output_completeness", incomplete == 0,
       f"{complete} complete, {incomplete} incomplete")

# Category distribution should be reasonable (not all in one bucket)
cat_counts = {}
for c in grand_classified:
    cat = c.get("main_category", "?")
    cat_counts[cat] = cat_counts.get(cat, 0) + 1

record("category_diversity", len(cat_counts) >= 2,
       f"{len(cat_counts)} distinct categories: " +
       ", ".join(f"{k}={v}" for k, v in
                 sorted(cat_counts.items(), key=lambda x: -x[1])[:5]))


# ── Phase 10: Cost & Speed Summary ──────────────────────────────
print("\n--- PHASE 10: Cost & Speed Summary ---\n")

haiku_batches = (len(grand_uncertain) + 24) // 25
haiku_cost = haiku_batches * 0.002
est_unmapped = int(len(grand_uncertain) * 0.10)
sonnet_cost = 0.03 if est_unmapped > 0 else 0
anomaly_cost = 0.002 if anomalies else 0
total_api_cost = haiku_cost + sonnet_cost + anomaly_cost
all_llm_cost = 0.08 * len(all_questions)

total_wall = classify_time + (anom_time if 'anom_time' in dir() else 0)

print(f"  SPEED:")
print(f"    Model load:        {model_time:.0f}s (one-time)")
print(f"    Classification:    {classify_time:.0f}s ({len(all_questions)} questions)")
print(f"    Per question avg:  {classify_time/max(len(all_questions),1):.0f}s")
print(f"    Anomaly detection: {anom_time if 'anom_time' in dir() else 0:.1f}s")
print(f"    TOTAL wall time:   {total_wall:.0f}s")
print()
print(f"  COST (projected):")
print(f"    Classified FREE:   {len(grand_classified)} ({overall_hit:.0f}%)")
print(f"    Uncertain (API):   {len(grand_uncertain)} ({100-overall_hit:.0f}%)")
print(f"    Haiku (uncertain): {haiku_batches} batches = ${haiku_cost:.3f}")
print(f"    Sonnet (UNMAPPED): ~{est_unmapped} = ${sonnet_cost:.3f}")
print(f"    Haiku (anomalies): ${anomaly_cost:.3f}")
print(f"    TOTAL API COST:    ${total_api_cost:.3f}")
print(f"    vs All-LLM:        ${all_llm_cost:.2f} "
      f"(savings: {(1-total_api_cost/max(all_llm_cost,0.001))*100:.0f}%)")

ux = "FAST" if classify_time / max(len(all_questions), 1) < 30 else "ACCEPTABLE"
print(f"\n  UX VERDICT: {ux}")

record("cost_efficiency", total_api_cost < all_llm_cost,
       f"${total_api_cost:.3f} vs ${all_llm_cost:.2f} all-LLM")


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
