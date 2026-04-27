"""
BC4D Intel -- Pipeline Simulation (all 5 phases)
Sampled version: 20 responses per column for speed.
Includes performance profiling + real-world speed predictions.

Run: cd "C:/Users/beyer/Claude/V2/BC4D Intel" && python simulate.py
"""
import pandas as pd
import sys, time, json, os, sqlite3, random, io
from collections import defaultdict

sys.path.insert(0, ".")

SAMPLE_SIZE = 20  # responses per column (enough for stats)

# -- Column-to-cache mapping --------------------------------------------------
COL_MAP = {
    "warum denken sie so": "Warum denken Sie so? (Wichtigkeit digitaler Zivilcourage)",
    "was hat ihnen an der schulung gut gefallen": "Was hat Ihnen an der Schulung gut gefallen?",
    "besonders gut gefallen": "Was hat Ihnen besonders gut gefallen?",
    "materialien aus dem loginbereich": "Welche Materialien haben Sie genutzt?",
    "staerken des kurses": "Bitte nennen Sie Staerken des Kurses.",
    "staerke": "Bitte nennen Sie Staerken des Kurses.",
    "verbesserungsmoeglichkeiten": "Bitte nennen Sie Verbesserungsmoeglichkeiten.",
    "kenntnisse oder kompetenzen haben sie angewendet": "Welche Kenntnisse oder Kompetenzen haben Sie angewendet?",
    "inhalte oder tools haben sie weitergegeben": "Welche Inhalte oder Tools haben Sie weitergegeben?",
    "nicht verstaendlich": "Wann war es nicht verstaendlich?",
    "erfahrungen mit hassrede": "Haben Sie bereits eigene Erfahrungen mit Hassrede?",
    "erhoffen sie sich von diesem kurs": "Was erhoffen Sie sich von diesem Kurs?",
}


def find_cache_pattern(col_name):
    col_lower = col_name.lower()
    for key, pattern in COL_MAP.items():
        if key in col_lower:
            return pattern
    return None


def get_free_text_responses(fname):
    from bc4d_intel.core.data_loader import load_survey
    df, roles = load_survey(fname)
    ft_cols = [c for c, r in roles.items() if r == "free_text"]
    result = {}
    for col in ft_cols:
        responses = df[col].dropna().astype(str).tolist()
        responses = [r for r in responses if len(r.strip()) > 3]
        if len(responses) >= 5:
            result[col] = responses
    return result


def sample_responses(responses, n=SAMPLE_SIZE):
    """Sample n responses, return (sample, full_count)."""
    if len(responses) <= n:
        return responses, len(responses)
    return random.sample(responses, n), len(responses)


# ==============================================================================
# PHASE 1: Cache Hit Rate Test (sampled, with performance profiling)
# ==============================================================================
def phase1():
    from bc4d_intel.core.answer_cache import classify_from_cache, get_cached_answers

    files = {
        "POSITIVE": "POSITIV_Abschlussbefragung_Staffel13.xlsx",
        "NEGATIVE": "NEGATIV_Abschlussbefragung_Staffel13.xlsx",
        "MIXED":    "Synthetisch_Abschlussbefragung_Staffel13.xlsx",
    }

    all_results = {}
    perf_data = []  # (n_responses, n_cache_entries, n_pairs, elapsed_sec)

    for label, fname in files.items():
        print("\n" + "=" * 60)
        print("  PHASE 1 -- %s dataset" % label)
        print("=" * 60)

        ft_data = get_free_text_responses(fname)
        total_cached = 0
        total_uncached = 0

        for col, all_responses in ft_data.items():
            cache_pattern = find_cache_pattern(col)
            short_col = col[:55].strip()

            if not cache_pattern:
                print("  %s -> SKIP (no pattern)" % short_col)
                continue

            cached_answers = get_cached_answers(cache_pattern)
            if not cached_answers:
                print("  %s -> SKIP (0 cache entries)" % short_col)
                continue

            responses, full_count = sample_responses(all_responses)
            n_cache = len(cached_answers)
            n_pairs = len(responses) * n_cache

            t0 = time.time()
            cached, uncached = classify_from_cache(cache_pattern, responses)
            elapsed = time.time() - t0

            perf_data.append((len(responses), n_cache, n_pairs, elapsed))

            n_cached = len(cached)
            n_total = n_cached + len(uncached)
            hit_rate = n_cached / n_total * 100 if n_total else 0

            total_cached += n_cached
            total_uncached += len(uncached)

            print("  %s" % short_col)
            print("    cache: %s (%d entries)" % (cache_pattern[:40], n_cache))
            print("    sample %d/%d -> %.1f%% hits (%d/%d) [%.1fs, %d pairs]" % (
                len(responses), full_count, hit_rate, n_cached, n_total, elapsed, n_pairs))

            if cached:
                m = cached[0]
                print('      e.g. HIT: "%s" -> "%s" (%.2f)' % (
                    m.get("text", "")[:40], m.get("cache_match", "")[:40], m.get("cache_score", 0)))
            if uncached:
                print('      e.g. MISS: "%s"' % uncached[0][:55])

        total = total_cached + total_uncached
        overall = total_cached / total * 100 if total else 0
        print("\n  OVERALL: %.1f%% cache hits (%d/%d)" % (overall, total_cached, total))
        all_results[label] = {"overall": overall, "cached": total_cached, "total": total}

    # -- Summary --
    print("\n" + "=" * 60)
    print("  PHASE 1 SUMMARY")
    print("=" * 60)
    for label, r in all_results.items():
        target = {"POSITIVE": ">70%", "NEGATIVE": "<30%", "MIXED": "50-60%"}[label]
        if label == "POSITIVE":
            status = "PASS" if r["overall"] > 70 else ("WARN" if r["overall"] > 50 else "FAIL")
        elif label == "NEGATIVE":
            status = "PASS" if r["overall"] < 30 else ("WARN" if r["overall"] < 50 else "FAIL")
        else:
            status = "PASS" if 30 <= r["overall"] <= 70 else "WARN"
        print("  %-10s: %5.1f%% hits (%d/%d) [target %s] %s" % (
            label, r["overall"], r["cached"], r["total"], target, status))

    # -- Performance profiling --
    print("\n" + "=" * 60)
    print("  PERFORMANCE PROFILE (cross-encoder)")
    print("=" * 60)
    if perf_data:
        total_pairs = sum(p[2] for p in perf_data)
        total_time = sum(p[3] for p in perf_data)
        pairs_per_sec = total_pairs / total_time if total_time else 0

        print("  Measured: %d total pairs in %.1fs = %.0f pairs/sec" % (
            total_pairs, total_time, pairs_per_sec))

        # Predict real-world full-run times
        # Real staffel: ~6 free-text cols, ~140 responses each, ~600 avg cache entries
        real_cols = 6
        real_responses = 140
        real_cache = 600
        real_pairs = real_cols * real_responses * real_cache
        real_time = real_pairs / pairs_per_sec if pairs_per_sec else 999

        print("\n  --- Real-World Predictions ---")
        print("  Typical staffel: %d cols x %d responses x %d cache = %d pairs" % (
            real_cols, real_responses, real_cache, real_pairs))
        print("  Predicted cache-check time: %.0fs (%.1f min)" % (real_time, real_time / 60))

        if real_time > 300:
            print("  !! WARNING: Cache check alone takes >5 min")
            print("     This is TOO SLOW for a GUI app.")
            print("     ROOT CAUSE: O(responses x cache_entries) pair explosion")
            print("     The cross-encoder scores ALL pairs in one batch,")
            print("     but batch size grows quadratically.")
            print("")
            print("  --- Recommended Fixes (pick one) ---")
            print("  1. PRE-FILTER with TF-IDF: reduce candidates to top-50")
            print("     per response before cross-encoder (10x speedup)")
            print("  2. EMBEDDING INDEX: precompute cache embeddings,")
            print("     use cosine similarity for top-k, then cross-encoder")
            print("     on top-k only (20-50x speedup)")
            print("  3. BATCH CHUNKING: split into chunks of 5k pairs,")
            print("     early-stop if high-confidence match found (2-5x)")
            print("  4. LIMIT CACHE CANDIDATES per question to ~200 most")
            print("     diverse (trim duplicates/near-duplicates)")
        elif real_time > 60:
            print("  ! CAUTION: Cache check takes >1 min per staffel")
            print("    Acceptable with progress bar, but could be faster")
        else:
            print("  OK: Cache check under 1 min -- acceptable for GUI")

        # Per-column breakdown
        print("\n  Per-column timing:")
        for resp, cache, pairs, t in perf_data:
            print("    %3d resp x %3d cache = %6d pairs -> %5.1fs (%.0f p/s)" % (
                resp, cache, pairs, t, pairs / t if t else 0))

    return all_results, perf_data


# ==============================================================================
# PHASE 2: Safety Guard Audit
# ==============================================================================
def phase2():
    from bc4d_intel.core.answer_cache import _safe_to_cache_match, _sentiment, test_reliability

    print("\n" + "=" * 60)
    print("  PHASE 2 -- Safety Guard Audit")
    print("=" * 60)

    # (new_text, cached_text, should_block, reason)
    safety_tests = [
        ("Der Kurs war ausgezeichnet", "Der Kurs war schlecht", True,
         "Sentiment flip: positive vs negative"),
        ("Sehr langweilig und unnoetig", "Sehr spannend und hilfreich", True,
         "Sentiment flip: negative vs positive"),
        ("Gute Inhalte", "Gute Inhalte und Methoden", False,
         "Same sentiment should match"),

        ("Nicht informativ", "Informativ", True, "Negation asymmetry"),
        ("Nicht hilfreich", "Sehr hilfreich", True, "Negation asymmetry"),
        ("Nicht schlecht, eigentlich gut", "Nicht schlecht", False, "Both have negation"),
        ("Kein Verbesserungsvorschlag", "Kein Verbesserungsbedarf", False, "Both have negation"),

        ("Haette besser sein koennen", "War gut", True,
         "Conditional vs definitive (diff sentiment)"),
        ("Waere noch besser mit mehr Praxis", "Gut mit Praxisbezug", True,
         "Conditional vs definitive"),

        ("Trainerin toll", "Material toll", True, "Subject mismatch (short)"),
        ("Tempo gut", "Inhalt gut", True, "Subject mismatch (short)"),
        ("Praxis gut", "Praxis super", False, "Same subject (short)"),

        ("Die Trainerin war sehr kompetent und freundlich",
         "Kompetente und sympathische Trainerin", False, "Paraphrase should pass"),
        ("Mehr praktische Uebungen waeren gut",
         "Mehr Praxisuebungen waeren wuenschenswert", False, "Similar suggestions"),
    ]

    passed = 0
    failed = 0

    for new_text, cached_text, should_block, reason in safety_tests:
        is_safe = _safe_to_cache_match(new_text, cached_text)
        blocked = not is_safe
        correct = (blocked == should_block)
        passed += correct
        failed += (not correct)

        print("\n  [%s] %s" % ("PASS" if correct else "FAIL", reason))
        print("    new:    \"%s\"" % new_text[:60])
        print("    cached: \"%s\"" % cached_text[:60])
        print("    blocked=%s (expected=%s)" % (blocked, should_block))

    # Question-context safety
    print("\n  --- Question-Context Safety Tests ---")
    qcontext_tests = [
        ("Bitte nennen Sie Staerken des Kurses.",
         "Der Kurs war schrecklich und langweilig", True,
         "Negative on strengths question"),
        ("Bitte nennen Sie Staerken des Kurses.",
         "Sehr gute Inhalte und tolle Trainerin", False,
         "Positive on strengths question"),
        ("Bitte nennen Sie Verbesserungsmoeglichkeiten.",
         "Alles war perfekt und toll", True,
         "Positive on improvements question"),
        ("Bitte nennen Sie Verbesserungsmoeglichkeiten.",
         "Mehr Praxisbezug waere besser", False,
         "Suggestion on improvements question"),
    ]

    for question, response, should_block, reason in qcontext_tests:
        result = test_reliability(question, response)
        blocked = not result.get("would_cache", False)
        correct = (blocked == should_block)
        passed += correct
        failed += (not correct)

        print("\n  [%s] %s" % ("PASS" if correct else "FAIL", reason))
        print("    q: \"%s\"" % question[:50])
        print("    r: \"%s\"" % response[:55])
        print("    blocked=%s (expected=%s), score=%.3f" % (
            blocked, should_block, result.get("score", 0)))

    total = passed + failed
    pct = passed / total * 100 if total else 0
    print("\n" + "=" * 60)
    print("  PHASE 2 SUMMARY: %d/%d passed (%.0f%%)" % (passed, total, pct))
    print("  Target: >90%%   %s" % ("PASS" if pct > 90 else "FAIL"))
    print("=" * 60)

    return {"passed": passed, "failed": failed, "total": total}


# ==============================================================================
# PHASE 3: Full Pipeline Run (mixed dataset, sampled, costs ~$0.05-0.15)
# ==============================================================================
def phase3(api_key):
    from bc4d_intel.core.answer_cache import classify_from_cache, add_to_cache
    from bc4d_intel.core.embedder import full_pipeline

    print("\n" + "=" * 60)
    print("  PHASE 3 -- Full Pipeline Run (Synthetisch, sampled)")
    print("=" * 60)

    fname = "Synthetisch_Abschlussbefragung_Staffel13.xlsx"
    ft_data = get_free_text_responses(fname)

    all_results = {}
    total_cost = 0.0
    timings = {}

    for col, all_responses in ft_data.items():
        cache_pattern = find_cache_pattern(col)
        short_col = col[:55].strip()

        if not cache_pattern:
            print("\n  %s -- SKIP (no pattern)" % short_col)
            continue

        responses, full_count = sample_responses(all_responses)
        print("\n  --- %s (sample %d/%d) ---" % (short_col, len(responses), full_count))

        # Step 1: Cache
        t0 = time.time()
        cached, uncached = classify_from_cache(cache_pattern, responses)
        t_cache = time.time() - t0

        n_total = len(cached) + len(uncached)
        hit_rate = len(cached) / n_total * 100 if n_total else 0
        print("  Cache: %d/%d hits (%.0f%%) [%.1fs]" % (len(cached), n_total, hit_rate, t_cache))

        t_ai = 0
        if uncached:
            print("  AI pipeline on %d uncached..." % len(uncached))
            t0 = time.time()

            def progress(msg):
                print("    > %s" % msg)

            res = full_pipeline(uncached, api_key, question=cache_pattern, progress_cb=progress)
            t_ai = time.time() - t0
            print("  AI pipeline: %.1fs" % t_ai)

            all_classifications = cached + res["classifications"]
            taxonomy = res["taxonomy"]
            flat_taxonomy = res["flat_taxonomy"]

            est = 0.04
            total_cost += est

            # DO NOT add synthetic test results to cache (per simulation rules)
            # add_to_cache(cache_pattern, res["classifications"], staffel="synthetic_test")
        else:
            all_classifications = cached
            taxonomy = {}
            flat_taxonomy = []
            print("  100%% cache hit!")

        timings[short_col] = {"cache": t_cache, "ai": t_ai, "total": t_cache + t_ai}

        all_results[col] = {
            "classifications": all_classifications,
            "taxonomy": taxonomy,
            "flat_taxonomy": flat_taxonomy,
            "n_cached": len(cached),
            "n_uncached": len(uncached),
        }

        # Distribution
        cats = defaultdict(int)
        for c in all_classifications:
            cats[c.get("main_category", "Unknown")] += 1
        print("  Categories: %s" % ", ".join(
            "%s(%d)" % (k[:20], v) for k, v in sorted(cats.items(), key=lambda x: -x[1])[:4]))

    print("\n" + "=" * 60)
    print("  PHASE 3 SUMMARY")
    print("=" * 60)
    print("  Questions processed: %d" % len(all_results))
    print("  Estimated cost: ~$%.2f" % total_cost)
    print("  Timings:")
    for col, t in timings.items():
        print("    %s: cache=%.1fs  ai=%.1fs  total=%.1fs" % (col[:40], t["cache"], t["ai"], t["total"]))

    return all_results


# ==============================================================================
# PHASE 4: Classification Quality Audit
# ==============================================================================
def phase4(phase3_results):
    print("\n" + "=" * 60)
    print("  PHASE 4 -- Classification Quality Audit")
    print("=" * 60)

    total_classified = 0
    total_confident = 0
    total_from_cache = 0
    category_counts = defaultdict(int)
    low_conf = []
    cache_scores = []

    for col, data in phase3_results.items():
        short_col = col[:55].strip()
        cls = data["classifications"]
        n = len(cls)
        total_classified += n

        n_cache = sum(1 for c in cls if c.get("cache_score"))
        total_from_cache += n_cache

        n_high = sum(1 for c in cls if c.get("confidence") == "high")
        total_confident += n_high

        print("\n  %s: %d total | %d cached | %d high-conf" % (short_col, n, n_cache, n_high))

        cats = defaultdict(int)
        for c in cls:
            mc = c.get("main_category", "Unknown")
            cats[mc] += 1
            category_counts[mc] += 1

        for cat, cnt in sorted(cats.items(), key=lambda x: -x[1])[:3]:
            print("    %3d (%.0f%%) %s" % (cnt, cnt / n * 100, cat[:40]))

        for c in cls:
            if c.get("cache_score"):
                cache_scores.append(c["cache_score"])
            if c.get("confidence") != "high" and not c.get("cache_score"):
                low_conf.append(c)

    print("\n" + "=" * 60)
    print("  PHASE 4 SUMMARY")
    print("=" * 60)
    if total_classified:
        print("  Total: %d | Cached: %d (%.0f%%) | High-conf: %d (%.0f%%)" % (
            total_classified, total_from_cache,
            total_from_cache / total_classified * 100,
            total_confident, total_confident / total_classified * 100))
    print("  Low-confidence: %d" % len(low_conf))
    if cache_scores:
        print("  Cache scores: avg=%.3f min=%.3f max=%.3f" % (
            sum(cache_scores) / len(cache_scores), min(cache_scores), max(cache_scores)))
    print("  Unique categories: %d" % len(category_counts))

    quality = total_confident / total_classified * 100 if total_classified else 0
    print("  Quality: %.0f%% high-confidence [target >85%%] %s" % (
        quality, "PASS" if quality > 85 else ("WARN" if quality > 70 else "FAIL")))

    return {
        "total": total_classified, "cached": total_from_cache,
        "confident": total_confident, "low_confidence": len(low_conf),
        "categories": len(category_counts),
    }


# ==============================================================================
# PHASE 5: Architecture Decisions + Speed Predictions
# ==============================================================================
def phase5(p1_results, p1_perf, p2_results, p4_results):
    print("\n" + "=" * 60)
    print("  PHASE 5 -- Architecture Decisions")
    print("=" * 60)

    findings = []

    # 1. Question pattern matching
    print("\n  FINDING 1: Question Pattern Matching is BRITTLE")
    print("  " + "-" * 50)
    print("  Cache uses EXACT match on normalized patterns.")
    print("  Excel column names != cached patterns.")
    print("  Without manual mapping, 0%% cache hits.")
    print("  FIX: fuzzy matching (difflib ratio > 0.6) or keyword extraction.")
    print("  SEVERITY: CRITICAL")
    findings.append("CRITICAL: Add fuzzy question pattern matching")

    # 2. Speed / scalability
    print("\n  FINDING 2: Cross-Encoder Speed is a BOTTLENECK")
    print("  " + "-" * 50)
    if p1_perf:
        total_pairs = sum(p[2] for p in p1_perf)
        total_time = sum(p[3] for p in p1_perf)
        pps = total_pairs / total_time if total_time else 1

        # Real-world prediction
        # 6 post-survey FT cols, ~140 responses, ~600 cache entries avg
        real_pairs = 6 * 140 * 600
        real_sec = real_pairs / pps
        print("  Measured throughput: %.0f pairs/sec" % pps)
        print("  Real staffel (6 cols x 140 resp x 600 cache): %d pairs" % real_pairs)
        print("  Predicted wall time: %.0fs (%.1f min)" % (real_sec, real_sec / 60))

        if real_sec > 300:
            severity = "CRITICAL"
            print("  VERDICT: TOO SLOW (>5 min). Users will think app is frozen.")
        elif real_sec > 120:
            severity = "HIGH"
            print("  VERDICT: SLOW (>2 min). Needs progress bar + optimization.")
        elif real_sec > 60:
            severity = "MEDIUM"
            print("  VERDICT: ACCEPTABLE with progress bar.")
        else:
            severity = "LOW"
            print("  VERDICT: Fast enough.")

        print("  FIX OPTIONS:")
        print("    a) Pre-filter with TF-IDF cosine to top-50 candidates (~10x faster)")
        print("    b) Precompute cache embeddings, FAISS index for top-k (~20x faster)")
        print("    c) Cap cache at 200 diverse entries per question (~3x faster)")
        print("    d) Use sentence-transformers bi-encoder for first pass (~5x faster)")
        findings.append("%s: Cross-encoder cache check ~%.0fs per staffel" % (severity, real_sec))
    else:
        findings.append("No perf data collected")

    # 3. Cache hit rates
    print("\n  FINDING 3: Cache Hit Rate Analysis")
    print("  " + "-" * 50)
    if p1_results:
        for label, r in p1_results.items():
            target = {"POSITIVE": ">70%", "NEGATIVE": "<30%", "MIXED": "50-60%"}[label]
            print("  %-10s: %.1f%% (target %s)" % (label, r["overall"], target))

    # 4. Safety layers
    print("\n  FINDING 4: Safety Layer Effectiveness")
    print("  " + "-" * 50)
    if p2_results:
        pct = p2_results["passed"] / p2_results["total"] * 100 if p2_results["total"] else 0
        print("  Safety tests: %d/%d passed (%.0f%%)" % (
            p2_results["passed"], p2_results["total"], pct))
        findings.append("Safety guards: %.0f%% accuracy" % pct)

    # 5. Cache size
    print("\n  FINDING 5: Cache Size")
    print("  " + "-" * 50)
    from bc4d_intel.core.answer_cache import get_cache_stats
    stats = get_cache_stats()
    print("  %d entries, %d questions, %d staffels" % (
        stats["total_answers"], stats["questions"], stats["staffels"]))
    findings.append("Cache: %d entries, %d questions" % (stats["total_answers"], stats["questions"]))

    # 6. Overall pipeline time prediction
    print("\n  FINDING 6: End-to-End Pipeline Time Prediction")
    print("  " + "-" * 50)
    if p1_perf:
        total_pairs = sum(p[2] for p in p1_perf)
        total_time = sum(p[3] for p in p1_perf)
        pps = total_pairs / total_time if total_time else 1
        cache_sec = 6 * 140 * 600 / pps

        # AI pipeline: ~15s per question for taxonomy + classification + edge cases
        # Assume 40% cache miss -> 3-4 questions need AI
        ai_sec = 4 * 15  # 60s
        total_pred = cache_sec + ai_sec

        print("  Cache check:  ~%.0fs" % cache_sec)
        print("  AI pipeline:  ~%.0fs (assuming 40%% cache miss)" % ai_sec)
        print("  TOTAL:        ~%.0fs (%.1f min)" % (total_pred, total_pred / 60))
        print("")
        if total_pred > 600:
            print("  !! APP IS UNUSABLE at this speed (>10 min)")
            print("  !! Must fix cross-encoder bottleneck BEFORE shipping")
        elif total_pred > 180:
            print("  ! Marginal -- needs progress bar + speed optimization")
        else:
            print("  OK -- acceptable with progress indicators")
        findings.append("Predicted e2e time: ~%.0fs (%.1f min)" % (total_pred, total_pred / 60))

    print("\n" + "=" * 60)
    print("  ALL FINDINGS")
    print("=" * 60)
    for i, f in enumerate(findings, 1):
        print("  %d. %s" % (i, f))

    return findings


# ==============================================================================
# MAIN
# ==============================================================================
if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8",
                                  errors="replace", line_buffering=True)

    print("=" * 60)
    print("  BC4D Intel -- Pipeline Simulation (sampled, N=%d)" % SAMPLE_SIZE)
    print("=" * 60)

    random.seed(42)  # reproducible samples

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        try:
            from bc4d_intel.app_state import AppState
            state = AppState.load()
            api_key = state.api_key
        except Exception:
            pass

    # Phase 1 (free)
    print("\n" + "#" * 60)
    print("  PHASE 1: Cache Hit Rate Test (sampled)")
    print("#" * 60)
    p1_results, p1_perf = phase1()

    # Phase 2 (free, instant)
    print("\n" + "#" * 60)
    print("  PHASE 2: Safety Guard Audit")
    print("#" * 60)
    p2_results = phase2()

    # Phase 3 (costs money, sampled)
    p3_results = None
    if api_key:
        print("\n" + "#" * 60)
        print("  PHASE 3: Full Pipeline Run (sampled)")
        print("#" * 60)
        p3_results = phase3(api_key)
    else:
        print("\n  PHASE 3 SKIPPED -- no API key")
        print("  Set ANTHROPIC_API_KEY or save in app settings")

    # Phase 4
    p4_results = None
    if p3_results:
        print("\n" + "#" * 60)
        print("  PHASE 4: Classification Quality Audit")
        print("#" * 60)
        p4_results = phase4(p3_results)

    # Phase 5
    print("\n" + "#" * 60)
    print("  PHASE 5: Architecture Decisions + Speed Predictions")
    print("#" * 60)
    p5_findings = phase5(p1_results, p1_perf, p2_results, p4_results)

    print("\n" + "=" * 60)
    print("  SIMULATION COMPLETE")
    print("=" * 60)
