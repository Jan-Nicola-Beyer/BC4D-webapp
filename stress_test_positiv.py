"""Stress test: POSITIV datasets through the v4 pipeline.

Measures speed, cache hit rates, and how much would go to API.
NO actual API calls — just local classification + cost projection.
"""

import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "bc4d_intel"))
sys.path.insert(0, os.path.dirname(__file__))

import pandas as pd

from bc4d_intel.core.answer_cache import (
    classify_from_cache, get_cached_answers, get_cache_stats,
    find_anomalies, _get_bi_encoder, _get_cross_encoder,
)

PRE_PATH = "POSITIV_Vorbefragung_Staffel13.xlsx"
POST_PATH = "POSITIV_Abschlussbefragung_Staffel13.xlsx"

# ── Load data ───────────────────────────────────────────────────
print("=" * 70)
print("STRESS TEST: POSITIV Datasets (987 responses, 8 questions)")
print("=" * 70)

pre_df = pd.read_excel(PRE_PATH)
post_df = pd.read_excel(POST_PATH)

# Find free-text columns
def find_free_text(df):
    ft = []
    for col in df.columns:
        if df[col].dtype == object:
            valid = df[col].dropna().astype(str)
            valid = valid[valid.str.len() > 5]
            if len(valid) >= 5 and valid.str.len().mean() > 30 and valid.nunique() > 10:
                responses = valid.tolist()
                ft.append((col, responses))
    return ft

pre_ft = find_free_text(pre_df)
post_ft = find_free_text(post_df)

all_questions = []
for col, responses in pre_ft:
    all_questions.append((f"[Pre] {col[:50]}", col, responses))
for col, responses in post_ft:
    all_questions.append((f"[Post] {col[:50]}", col, responses))

total_responses = sum(len(r) for _, _, r in all_questions)
print(f"\n  {len(all_questions)} questions, {total_responses} total responses")

# ── Load models ─────────────────────────────────────────────────
print("\n  Loading models...")
t_load = time.perf_counter()
_get_bi_encoder()
_get_cross_encoder()
model_time = time.perf_counter() - t_load
print(f"  Models loaded in {model_time:.1f}s\n")

# ── Cache stats ─────────────────────────────────────────────────
stats = get_cache_stats()
print(f"  Cache: {stats['total_answers']} answers, {stats['questions']} questions")

# ── Classify each question ──────────────────────────────────────
print("\n" + "-" * 70)
print(f"  {'Question':<55} | {'N':>3} | {'A':>3} {'B':>3} {'C':>3} | {'Hit%':>5} | {'Time':>5}")
print("-" * 70)

grand_classified = []
grand_uncertain = []
grand_a = grand_b = grand_c = 0
total_time = 0
question_details = []

for label, col, responses in all_questions:
    progress_msgs = []

    t0 = time.perf_counter()
    classified, uncertain = classify_from_cache(
        label, responses,
        progress_cb=lambda m: progress_msgs.append(m))
    elapsed = time.perf_counter() - t0
    total_time += elapsed

    case_a = sum(1 for c in classified if c.get("match_case") == "a")
    case_b = sum(1 for c in classified if c.get("match_case") == "b")
    case_c = len(uncertain)
    hit_pct = len(classified) / max(len(responses), 1) * 100

    grand_classified.extend(classified)
    grand_uncertain.extend(uncertain)
    grand_a += case_a
    grand_b += case_b
    grand_c += case_c

    short_label = label[:55]
    print(f"  {short_label:<55} | {len(responses):3d} | "
          f"{case_a:3d} {case_b:3d} {case_c:3d} | {hit_pct:4.0f}% | {elapsed:5.1f}s")

    # Show guard blocks if any
    last_msg = progress_msgs[-1] if progress_msgs else ""
    if "Guards:" in last_msg:
        guards_part = last_msg.split("Guards:")[1].strip()
        print(f"  {'':55}   guards: {guards_part}")

    question_details.append({
        "label": label, "n": len(responses),
        "a": case_a, "b": case_b, "c": case_c,
        "hit_pct": hit_pct, "time": elapsed,
    })

# ── Anomaly detection ───────────────────────────────────────────
print("\n" + "-" * 70)
print("  Anomaly detection...")
t_anom = time.perf_counter()
anomalies = find_anomalies(grand_classified)
anom_time = time.perf_counter() - t_anom
print(f"  {len(anomalies)} anomalies from {len(grand_classified)} classified ({anom_time:.1f}s)")
if anomalies:
    print(f"  Top 5 outliers:")
    for a in anomalies[:5]:
        print(f"    dist={a['distance']:.4f} | {a['main_category'][:15]} > "
              f"{a['cluster_title'][:20]} | \"{a['text'][:50]}\"")

# ── Summary ─────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("RESULTS SUMMARY")
print("=" * 70)

pct_classified = len(grand_classified) / max(total_responses, 1) * 100
pct_uncertain = len(grand_uncertain) / max(total_responses, 1) * 100

print(f"""
  Total responses:    {total_responses}
  Classified (FREE):  {len(grand_classified)} ({pct_classified:.0f}%)
    Case A (direct):  {grand_a}
    Case B (vote):    {grand_b}
  Uncertain (API):    {len(grand_uncertain)} ({pct_uncertain:.0f}%)
    Case C (no match):{grand_c}

  Classification time: {total_time:.1f}s (+ {model_time:.1f}s model load)
  Anomaly detection:   {anom_time:.1f}s
  TOTAL wall time:     {total_time + anom_time:.1f}s (excl. model load)

  Speed: {total_responses / max(total_time, 0.01):.1f} responses/sec
  Per question avg: {total_time / max(len(all_questions), 1):.1f}s
""")

# ── Cost projection ─────────────────────────────────────────────
print("=" * 70)
print("COST PROJECTION (if API were enabled)")
print("=" * 70)

n_uncertain = len(grand_uncertain)
n_questions_with_uncertain = sum(1 for d in question_details if d["c"] > 0)

# Step 3b: Haiku for uncertain (~$0.0003 per 1K input tokens)
# Average uncertain response: ~100 chars = ~30 tokens
# Batch of 25 responses + taxonomy context: ~2000 tokens input, ~500 output
haiku_batches = (n_uncertain + 24) // 25
haiku_cost = haiku_batches * 0.002  # ~$0.002 per batch

# Step 3b+: Sonnet for UNMAPPED (estimate 10% of uncertain are truly unmapped)
est_unmapped = int(n_uncertain * 0.10)
sonnet_cost = 0.03 if est_unmapped > 0 else 0  # one Sonnet call for taxonomy update

# Step 4: Anomaly review (Haiku, one batch)
anomaly_cost = 0.002 if anomalies else 0

total_api_cost = haiku_cost + sonnet_cost + anomaly_cost

print(f"""
  Uncertain responses needing API: {n_uncertain}
  Questions with uncertain:        {n_questions_with_uncertain}/{len(all_questions)}

  Step 3b (Haiku - uncertain):     {haiku_batches} batches x ~$0.002 = ${haiku_cost:.3f}
  Step 3b+ (Sonnet - UNMAPPED):    ~{est_unmapped} responses = ${sonnet_cost:.3f}
  Step 4 (Haiku - anomalies):      {len(anomalies)} anomalies = ${anomaly_cost:.3f}

  TOTAL ESTIMATED API COST:        ${total_api_cost:.3f}
  (Local classification was FREE)

  Comparison:
    All-LLM approach:  ~$0.08 x {len(all_questions)} questions = ${0.08 * len(all_questions):.2f}
    This pipeline:     ${total_api_cost:.3f} ({total_api_cost / max(0.08 * len(all_questions), 0.001) * 100:.0f}% of all-LLM)
""")

# ── Would user be annoyed? ──────────────────────────────────────
print("=" * 70)
print("USER EXPERIENCE")
print("=" * 70)

per_q = total_time / max(len(all_questions), 1)
total_with_api_est = total_time + n_uncertain * 0.5  # ~0.5s per API response

print(f"""
  Classification only:   {total_time:.0f}s ({per_q:.0f}s per question)
  With API calls (est.): {total_with_api_est:.0f}s
  With model load:       {total_time + model_time:.0f}s (first run only)

  Verdict: {'FAST - good UX' if per_q < 30 else 'SLOW - needs optimization' if per_q < 60 else 'TOO SLOW'}
  (Model load is one-time; subsequent questions use warm cache)
""")
