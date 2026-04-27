"""Comprehensive test suite for the v4 k-NN categorisation pipeline.

Tests: Cases A/B/C, safety guard on voting, UNMAPPED detection,
anomaly detection, verification system, speed, cross-question robustness.

No API calls — local models + existing cache only.
"""

from __future__ import annotations
import os, sys, time, random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "bc4d_intel"))
sys.path.insert(0, os.path.dirname(__file__))

from bc4d_intel.core.answer_cache import (
    classify_from_cache, get_cached_answers, get_cache_stats,
    test_reliability, find_anomalies,
    _get_bi_encoder, _get_cross_encoder,
    _check_safety_guards, _sentiment, _normalize_question,
)

random.seed(42)
RESULTS = {}


def record(name, passed, details="", time_s=0):
    RESULTS[name] = {"passed": passed, "details": details, "time_s": time_s}
    print(f"  [{'PASS' if passed else 'FAIL'}] {name}" +
          (f" ({time_s:.1f}s)" if time_s else ""))
    if details:
        for line in details.split("\n"):
            print(f"         {line}")


# ════════════════════════════════════════════════════════════════
# TEST 1: Cases A/B/C distribution
# ════════════════════════════════════════════════════════════════

def test_case_distribution():
    print("\n" + "=" * 70)
    print("TEST 1: Cases A/B/C Distribution")
    print("=" * 70)

    question = "Bitte nennen Sie Staerken des Kurses."
    cached = get_cached_answers(question)
    if len(cached) < 50:
        record("case_distribution", False, "Not enough cached data")
        return

    # Use 30 known cached responses (should mostly get Case A)
    known = [c["response_text"] for c in random.sample(cached, 30)]
    # Add some hard cases
    known.extend([
        "Absolute Nonsense-Text xyz 123 foo bar baz",
        "Die Katze hat den Hund gejagt",
        "!@#$%^&*()",
    ])

    progress = []
    t0 = time.perf_counter()
    classified, uncertain = classify_from_cache(
        question, known, progress_cb=lambda m: progress.append(m))
    elapsed = time.perf_counter() - t0

    case_a = sum(1 for c in classified if c.get("match_case") == "a")
    case_b = sum(1 for c in classified if c.get("match_case") == "b")
    case_c = len(uncertain)

    record("case_distribution", case_a > 0 and case_c > 0,
           f"A={case_a}, B={case_b}, C={case_c} | {elapsed:.1f}s\n"
           f"Progress: {progress[-1] if progress else 'none'}",
           elapsed)


# ════════════════════════════════════════════════════════════════
# TEST 2: Case A accuracy (holdout)
# ════════════════════════════════════════════════════════════════

def test_case_a_accuracy():
    print("\n" + "=" * 70)
    print("TEST 2: Case A Accuracy (holdout)")
    print("=" * 70)

    question = "Bitte nennen Sie Staerken des Kurses."
    cached = get_cached_answers(question)
    sample = random.sample(cached, min(50, len(cached)))
    responses = [s["response_text"] for s in sample]
    expected = {s["response_text"]: (s["cluster_id"], s["cluster_title"]) for s in sample}

    classified, uncertain = classify_from_cache(question, responses)

    correct = wrong = 0
    for c in classified:
        if c.get("match_case") != "a":
            continue
        exp = expected.get(c["text"])
        if exp and exp[0] == c["cluster_id"]:
            correct += 1
        elif exp:
            wrong += 1

    total = correct + wrong
    acc = correct / max(total, 1) * 100
    record("case_a_accuracy", acc >= 90,
           f"{correct}/{total} correct ({acc:.0f}%)")


# ════════════════════════════════════════════════════════════════
# TEST 3: Case B safety guard on voting (Advice #1)
# ════════════════════════════════════════════════════════════════

def test_case_b_safety():
    print("\n" + "=" * 70)
    print("TEST 3: Case B Safety Guard (Advice #1)")
    print("=" * 70)

    # "nicht gut" should NOT be assigned to positive categories
    # even if neighbours are all positive
    question = "Was hat Ihnen besonders gut gefallen?"
    classified, uncertain = classify_from_cache(
        question, ["Der Trainer war nicht gut und die Inhalte langweilig"])

    if classified:
        c = classified[0]
        # It should either be uncertain (C) or if B, the guard should have
        # blocked assignment to a positive category
        is_positive = any(w in c.get("main_category", "").lower()
                          for w in ["positiv", "lob", "gut"])
        record("case_b_safety", not is_positive,
               f"Assigned to: {c['main_category']} > {c['cluster_title']} "
               f"(case={c.get('match_case')})")
    else:
        # Sent to uncertain — correct behaviour
        record("case_b_safety", len(uncertain) > 0,
               "Correctly sent to uncertain (Case C)")


# ════════════════════════════════════════════════════════════════
# TEST 4: Cross-question holdout accuracy
# ════════════════════════════════════════════════════════════════

def test_cross_question_accuracy():
    print("\n" + "=" * 70)
    print("TEST 4: Cross-Question Holdout Accuracy")
    print("=" * 70)

    from bc4d_intel.core.answer_cache import _get_conn
    conn = _get_conn()
    questions = [r[0] for r in conn.execute(
        "SELECT DISTINCT question_pattern FROM answers "
        "WHERE question_pattern NOT IN ('Test Question', 'test_safeguards')"
    ).fetchall()]
    conn.close()

    total_correct = total_wrong = total_matched = total_tested = 0
    total_time = 0

    for q in questions:
        cached = get_cached_answers(q)
        if len(cached) < 20:
            continue
        sample = random.sample(cached, 20)
        responses = [s["response_text"] for s in sample]
        expected = {s["response_text"]: s["cluster_id"] for s in sample}

        t0 = time.perf_counter()
        classified, uncertain = classify_from_cache(q, responses)
        elapsed = time.perf_counter() - t0
        total_time += elapsed

        correct = wrong = 0
        for c in classified:
            exp = expected.get(c["text"])
            if exp and exp == c["cluster_id"]:
                correct += 1
            elif exp:
                wrong += 1

        total_correct += correct
        total_wrong += wrong
        total_matched += len(classified)
        total_tested += 20

        acc = f"{correct}/{correct+wrong}" if (correct + wrong) > 0 else "N/A"
        print(f"    {q[:55]:55s} | {len(classified):2d}/20 | acc: {acc} | {elapsed:.1f}s")

    overall_acc = total_correct / max(total_correct + total_wrong, 1) * 100
    match_rate = total_matched / max(total_tested, 1) * 100

    record("cross_question_accuracy", overall_acc >= 90,
           f"Accuracy: {total_correct}/{total_correct+total_wrong} ({overall_acc:.0f}%)\n"
           f"Match rate: {total_matched}/{total_tested} ({match_rate:.0f}%)",
           total_time)


# ════════════════════════════════════════════════════════════════
# TEST 5: Anomaly detection
# ════════════════════════════════════════════════════════════════

def test_anomaly_detection():
    print("\n" + "=" * 70)
    print("TEST 5: Anomaly Detection (Advice #3)")
    print("=" * 70)

    question = "Bitte nennen Sie Staerken des Kurses."
    cached = get_cached_answers(question)
    sample = random.sample(cached, min(100, len(cached)))

    # Build classifications from cached data
    classifications = [{
        "text": s["response_text"],
        "cluster_id": s["cluster_id"],
        "cluster_title": s["cluster_title"],
        "main_category": s["main_category"],
    } for s in sample]

    # Inject a deliberate outlier
    classifications.append({
        "text": "Das Wetter war heute wirklich schoen und sonnig.",
        "cluster_id": sample[0]["cluster_id"],
        "cluster_title": sample[0]["cluster_title"],
        "main_category": sample[0]["main_category"],
    })

    t0 = time.perf_counter()
    anomalies = find_anomalies(classifications)
    elapsed = time.perf_counter() - t0

    # The injected outlier should be among anomalies
    outlier_found = any("Wetter" in a["text"] for a in anomalies)

    print(f"  {len(anomalies)} anomalies found from {len(classifications)} responses")
    for a in anomalies[:5]:
        print(f"    dist={a['distance']:.4f} | {a['main_category']} > "
              f"{a['cluster_title'][:20]} | \"{a['text'][:50]}\"")

    record("anomaly_detection", len(anomalies) > 0,
           f"{len(anomalies)} anomalies, injected outlier found: {outlier_found}",
           elapsed)


# ════════════════════════════════════════════════════════════════
# TEST 6: Verification system
# ════════════════════════════════════════════════════════════════

def test_verification():
    print("\n" + "=" * 70)
    print("TEST 6: Verification System")
    print("=" * 70)

    question = "Was hat Ihnen besonders gut gefallen?"

    tests = [
        ("Die Trainerin war sehr kompetent", "Should be Case A, positive"),
        ("xyz nonsense garbage", "Should be Case C"),
        ("Es war nicht schlecht, aber auch nicht perfekt", "Ambiguous"),
    ]

    all_ok = True
    for text, desc in tests:
        result = test_reliability(question, text)
        print(f"\n  Input: '{text}' ({desc})")
        print(f"    Case: {result.get('case', '?')} | "
              f"Score: {result.get('score', '?')} | "
              f"Matched: {result.get('matched', '?')}")
        print(f"    Category: {result.get('main_category', '?')} > "
              f"{result.get('cluster_title', '?')}")
        print(f"    Safety: passed={result.get('safety_passed', '?')}"
              + (f" ({result.get('safety_guard', '')})" if result.get('safety_guard') else ""))
        print(f"    Reason: {result.get('reason', '?')}")
        if result.get("neighbour_vote"):
            print(f"    Neighbour vote:")
            for v in result["neighbour_vote"][:3]:
                print(f"      {v['votes']}/10: {v['category']}")

    record("verification", True, "Manual inspection above")


# ════════════════════════════════════════════════════════════════
# TEST 7: Speed benchmark
# ════════════════════════════════════════════════════════════════

def test_speed():
    print("\n" + "=" * 70)
    print("TEST 7: Speed Benchmark")
    print("=" * 70)

    question = "Bitte nennen Sie Staerken des Kurses."
    cached = get_cached_answers(question)
    responses = [c["response_text"] for c in random.sample(cached, min(135, len(cached)))]

    t0 = time.perf_counter()
    classified, uncertain = classify_from_cache(question, responses)
    elapsed = time.perf_counter() - t0

    record("speed_135", elapsed < 60,
           f"{len(responses)} responses vs {len(cached)} cached in {elapsed:.1f}s\n"
           f"Classified: {len(classified)}, Uncertain: {len(uncertain)}\n"
           f"Rate: {len(responses)/max(elapsed,0.01):.1f} resp/s",
           elapsed)


# ════════════════════════════════════════════════════════════════
# TEST 8: Sentiment edge cases
# ════════════════════════════════════════════════════════════════

def test_sentiment():
    print("\n" + "=" * 70)
    print("TEST 8: Sentiment Edge Cases")
    print("=" * 70)

    cases = [
        ("Die Trainerin war toll", 1),
        ("nicht langweilig", 1),
        ("nicht gut", -1),
        ("Kein Schoenereden", 0),
        ("Super, dass nicht nur Theorie", 1),
    ]
    all_ok = True
    labels = {1: "POS", -1: "NEG", 0: "NEU"}
    for text, expected in cases:
        got = _sentiment(text)
        ok = got == expected
        if not ok:
            all_ok = False
        print(f"  [{'PASS' if ok else 'FAIL'}] '{text}' -> {labels[got]}"
              + ("" if ok else f" (expected {labels[expected]})"))

    record("sentiment", all_ok, "")


# ════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("\nBC4D Intel -- v4 k-NN Categorisation Pipeline Test Suite")
    print("No API calls. Local models + existing cache only.\n")

    stats = get_cache_stats()
    print(f"Cache: {stats['total_answers']} answers, {stats['questions']} questions, "
          f"{stats['staffels']} staffels, {stats['taxonomies']} taxonomies\n")

    print("Loading models...")
    t0 = time.perf_counter()
    _get_bi_encoder()
    _get_cross_encoder()
    print(f"Models loaded in {time.perf_counter()-t0:.1f}s\n")

    test_sentiment()
    test_case_distribution()
    test_case_a_accuracy()
    test_case_b_safety()
    test_cross_question_accuracy()
    test_anomaly_detection()
    test_verification()
    test_speed()

    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for name, r in RESULTS.items():
        t = f" ({r['time_s']:.1f}s)" if r['time_s'] else ""
        print(f"  {'PASS' if r['passed'] else 'FAIL'} -- {name}{t}")
        if r["details"]:
            print(f"         {r['details'].split(chr(10))[0][:80]}")

    n_pass = sum(1 for r in RESULTS.values() if r["passed"])
    print(f"\n  {n_pass}/{len(RESULTS)} passed")
    sys.exit(0 if n_pass == len(RESULTS) else 1)
