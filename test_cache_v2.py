"""Quick end-to-end test of the v2 two-stage answer cache.

Tests:
  1. Question normalization
  2. Fuzzy question matching (including parenthetical DB patterns)
  3. Sentiment detection (with litotes / negated negatives)
  4. Safety guard telemetry
  5. Two-stage retrieval speed
  6. Hold-out category accuracy across all questions
  7. test_reliability function

No API calls — uses only local models + existing cache DB.
"""

import sys, os, time, random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "bc4d_intel"))
sys.path.insert(0, os.path.dirname(__file__))

from bc4d_intel.core.answer_cache import (
    _normalize_question, _fuzzy_match_question, _get_conn,
    get_cached_answers, classify_from_cache, test_reliability,
    get_cache_stats, _check_safety_guards, _sentiment,
)

random.seed(42)


def test_normalization():
    print("=" * 60)
    print("TEST 1: Question Normalization")
    print("=" * 60)
    cases = [
        ("[Pre] Was erhoffen Sie sich von diesem Kurs? (offene Frage)",
         "was erhoffen sie sich von diesem kurs?"),
        ("[Post] Bitte nennen Sie Stärken des Kurses.",
         "bitte nennen sie staerken des kurses."),
        ("Was hat Ihnen besonders gut gefallen? (Angabe erforderlich)",
         "was hat ihnen besonders gut gefallen?"),
        ("Bitte nennen Sie Verbesserungsmöglichkeiten.",
         "bitte nennen sie verbesserungsmoeglichkeiten."),
        ("Warum denken Sie so? (Wichtigkeit digitaler Zivilcourage)",
         "warum denken sie so?"),
    ]
    all_pass = True
    for raw, expected in cases:
        result = _normalize_question(raw)
        ok = result == expected
        if not ok:
            all_pass = False
        print(f"  [{'PASS' if ok else 'FAIL'}] '{raw[:55]}...' -> '{result}'")
        if not ok:
            print(f"         expected: '{expected}'")
    print()
    return all_pass


def test_fuzzy_matching():
    print("=" * 60)
    print("TEST 2: Fuzzy Question Matching")
    print("=" * 60)
    conn = _get_conn()
    rows = conn.execute("SELECT DISTINCT question_pattern FROM answers").fetchall()
    print(f"  DB has {len(rows)} distinct question patterns\n")

    test_questions = [
        # Standard cases
        ("[Pre] Was erhoffen Sie sich von diesem Kurs? (offene Frage)", True),
        ("[Post] Bitte nennen Sie Stärken des Kurses.", True),
        ("Was hat Ihnen besonders gut gefallen? (Angabe erforderlich)", True),
        ("[Pre] Haben Sie bereits eigene Erfahrungen mit Hassrede?", True),
        ("Bitte nennen Sie Verbesserungsmöglichkeiten.", True),
        # The previously failing case: parenthetical in DB pattern
        ("Warum denken Sie so?", True),
        # Should not match
        ("THIS SHOULD NOT MATCH ANYTHING AT ALL xyz123", False),
    ]

    all_pass = True
    for q, should_match in test_questions:
        match = _fuzzy_match_question(q, conn)
        ok = (match is not None) == should_match
        if not ok:
            all_pass = False
        status = "PASS" if ok else "FAIL"
        if should_match:
            print(f"  [{status}] '{q[:55]}...'")
            print(f"         -> matched: '{match}'")
        else:
            print(f"  [{status}] No match expected: '{q[:50]}'")
            if match:
                print(f"         Unexpected: '{match}'")
    conn.close()
    print()
    return all_pass


def test_sentiment():
    """Test sentiment detection including litotes (negated negatives)."""
    print("=" * 60)
    print("TEST 3: Sentiment Detection (with litotes)")
    print("=" * 60)
    cases = [
        # Basic positive/negative
        ("Die Trainerin war toll und kompetent", 1),
        ("Das war langweilig und schlecht", -1),
        ("Alles okay", 0),
        # Litotes: negated negatives → positive
        ("Die Lautstärke des Beamers war nicht störend", 0),  # "nicht" + no neg/pos words from list → neutral
        ("Kein Schönreden, keine leeren Phrasen", 0),  # negation words only → neutral
        ("nicht langweilig", 1),  # "nicht" cancels "langweilig" → pos
        ("nicht schlecht", 1),  # "nicht" cancels "schlecht" → pos
        # Negated positives → negative
        ("nicht gut", -1),
        ("nicht hilfreich", -1),
        # Mixed: positive words + negation words present
        ("gut, aber nicht perfekt", 1),  # "gut" is POS, "perfekt" not in wordlist so "nicht perfekt" is ignored → POS
        # Complex real examples
        ("Der Referent hat Fragen direkt beantwortet. Nicht rumgedruckst.", 0),
        ("Super, dass Diversität nicht nur als Buzzword behandelt wurde", 1),  # "nicht nur" is intensifier, not negation → super counts as POS
    ]

    all_pass = True
    for text, expected in cases:
        result = _sentiment(text)
        ok = result == expected
        if not ok:
            all_pass = False
        labels = {1: "POS", -1: "NEG", 0: "NEU"}
        print(f"  [{'PASS' if ok else 'FAIL'}] '{text[:55]}' -> {labels[result]}", end="")
        if not ok:
            print(f" (expected {labels[expected]})")
        else:
            print()
    print()
    return all_pass


def test_safety_telemetry():
    print("=" * 60)
    print("TEST 4: Safety Guard Telemetry")
    print("=" * 60)
    cases = [
        ("Die Trainerin war super toll", "Die Schulung war langweilig und schlecht",
         False, "sentiment_polarity"),
        ("Trainerin toll", "Material toll",
         False, "subject_mismatch"),
        ("Die Trainerin war sehr kompetent", "Die Trainerin war kompetent und freundlich",
         True, ""),
    ]
    all_pass = True
    for new, cached, exp_pass, exp_guard in cases:
        passed, guard = _check_safety_guards(new, cached)
        ok = (passed == exp_pass) and (guard == exp_guard)
        if not ok:
            all_pass = False
        print(f"  [{'PASS' if ok else 'FAIL'}] '{new}' vs '{cached}'")
        print(f"         passed={passed}, guard='{guard}'")
        if not ok:
            print(f"         expected: passed={exp_pass}, guard='{exp_guard}'")
    print()
    return all_pass


def test_cache_stats():
    print("=" * 60)
    print("TEST 5: Cache Stats")
    print("=" * 60)
    stats = get_cache_stats()
    print(f"  Total answers: {stats['total_answers']}")
    print(f"  Questions: {stats['questions']}")
    print(f"  Staffels: {stats['staffels']}")
    print()
    return stats['total_answers'] > 0


def test_two_stage_retrieval():
    print("=" * 60)
    print("TEST 6: Two-Stage Retrieval (Speed)")
    print("=" * 60)
    question = "Was hat Ihnen besonders gut gefallen?"
    cached = get_cached_answers(question)
    print(f"  {len(cached)} cached answers")
    if len(cached) < 10:
        print("  SKIP: not enough cached answers")
        return True

    test_responses = [c["response_text"] for c in cached[:20]]
    test_responses.extend(["Nonsense xyz", "Kaffee kalt", "abc 123"])

    progress = []
    t0 = time.perf_counter()
    hits, misses = classify_from_cache(question, test_responses,
                                       progress_cb=lambda m: progress.append(m))
    elapsed = time.perf_counter() - t0

    print(f"  Time: {elapsed:.2f}s | Hits: {len(hits)}/{len(test_responses)}")
    for msg in progress:
        print(f"    {msg}")
    print()
    return elapsed < 60  # generous for cold start


def test_holdout_accuracy():
    """Hold-out accuracy across all questions."""
    print("=" * 60)
    print("TEST 7: Hold-out Category Accuracy (all questions)")
    print("=" * 60)

    conn = _get_conn()
    questions = [r[0] for r in conn.execute(
        "SELECT DISTINCT question_pattern FROM answers "
        "WHERE question_pattern NOT IN ('Test Question', 'test_safeguards')"
    ).fetchall()]
    conn.close()

    total_correct = 0
    total_wrong = 0
    total_matched = 0
    total_tested = 0
    guard_blocks = {}

    for q in questions:
        cached = get_cached_answers(q)
        if len(cached) < 20:
            continue

        indices = random.sample(range(len(cached)), 20)
        holdout = [cached[i] for i in indices]
        holdout_texts = [h["response_text"] for h in holdout]

        hits, misses = classify_from_cache(q, holdout_texts)

        correct = wrong = 0
        for hit in hits:
            orig = next((h for h in holdout if h["response_text"] == hit["text"]), None)
            if orig:
                if orig["cluster_id"] == hit["cluster_id"]:
                    correct += 1
                else:
                    wrong += 1

        total_correct += correct
        total_wrong += wrong
        total_matched += len(hits)
        total_tested += 20

        # Sample guard blocks
        for miss in misses[:5]:
            r = test_reliability(q, miss)
            g = r.get("blocked_by_guard", "below_threshold")
            guard_blocks[g] = guard_blocks.get(g, 0) + 1

        acc = f"{correct}/{correct+wrong}" if (correct + wrong) > 0 else "N/A"
        print(f"  {q[:55]:55s} | {len(hits):2d}/20 matched | acc: {acc}")

    print(f"\n  TOTALS across {len(questions)} questions:")
    print(f"    Tested: {total_tested}")
    match_pct = total_matched / max(total_tested, 1) * 100
    print(f"    Matched: {total_matched} ({match_pct:.0f}%)")
    print(f"    Sent to AI: {total_tested - total_matched} ({100 - match_pct:.0f}%)")
    if total_correct + total_wrong > 0:
        acc_pct = total_correct / (total_correct + total_wrong) * 100
        print(f"    Category accuracy: {total_correct}/{total_correct + total_wrong} ({acc_pct:.0f}%)")
    print(f"\n  Guard block breakdown:")
    for g, c in sorted(guard_blocks.items(), key=lambda x: -x[1]):
        print(f"    {g}: {c}")

    all_correct = total_wrong == 0
    high_match = match_pct >= 85
    print(f"\n  Accuracy 100%: {'YES' if all_correct else 'NO'}")
    print(f"  Match rate >=85%: {'YES' if high_match else f'NO ({match_pct:.0f}%)'}")
    print()
    return all_correct


def test_reliability_function():
    print("=" * 60)
    print("TEST 8: test_reliability()")
    print("=" * 60)
    question = "Was hat Ihnen besonders gut gefallen?"
    cached = get_cached_answers(question)
    if not cached:
        print("  SKIP")
        return True

    test_text = cached[0]["response_text"]
    result = test_reliability(question, test_text)
    print(f"  Known cached: matched={result['matched']}, score={result['score']}")

    result2 = test_reliability(question, "xyz abc 123")
    print(f"  Nonsense: matched={result2['matched']}, score={result2['score']}")

    # Test the previously failing question
    result3 = test_reliability("Warum denken Sie so?", "Weil es wichtig ist")
    print(f"  Fuzzy Q match: matched={result3['matched']}, n_cached={result3.get('n_cached', 0)}")
    print()
    return result["matched"] and not result2["matched"]


if __name__ == "__main__":
    print("\nBC4D Intel — Answer Cache v2 Test Suite")
    print("No API calls. Local models only.\n")

    results = {}
    results["normalization"] = test_normalization()
    results["fuzzy_matching"] = test_fuzzy_matching()
    results["sentiment"] = test_sentiment()
    results["safety_telemetry"] = test_safety_telemetry()
    results["cache_stats"] = test_cache_stats()

    print("Loading ML models...\n")
    results["two_stage_retrieval"] = test_two_stage_retrieval()
    results["holdout_accuracy"] = test_holdout_accuracy()
    results["reliability"] = test_reliability_function()

    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results.items():
        print(f"  {'PASS' if passed else 'FAIL'} — {name}")
    n_pass = sum(results.values())
    print(f"\n  {n_pass}/{len(results)} passed")
    sys.exit(0 if n_pass == len(results) else 1)
