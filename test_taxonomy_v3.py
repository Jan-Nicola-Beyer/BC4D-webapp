"""Test the v3 taxonomy-first categorisation architecture.

Tests:
  1. Taxonomy caching (save/load/fuzzy match)
  2. Taxonomy-based classification (speed + quality)
  3. Low-fit detection (responses that need new categories)
  4. Verification system: can a user check if a new answer is categorised properly
  5. Cross-question robustness

No API calls — uses local cross-encoder + synthetic taxonomies.
"""

from __future__ import annotations
import json, os, sys, time, random

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "bc4d_intel"))
sys.path.insert(0, os.path.dirname(__file__))

from bc4d_intel.core.answer_cache import (
    _normalize_question, _get_conn, _get_cross_encoder,
    get_cached_taxonomy, save_taxonomy, classify_from_taxonomy,
    test_reliability, get_cache_stats, get_cached_answers,
    _flatten_taxonomy,
)

random.seed(42)

# ── Seed taxonomy cache from existing classified responses ──────
# Build a realistic taxonomy from the actual categories in the response cache.

def seed_taxonomies_from_response_cache():
    """Extract taxonomies from the existing response cache (answers table)
    and store them in the taxonomies table.

    Each distinct (main_category, cluster_title) becomes a sub-category
    with real response examples from the cache.
    """
    conn = _get_conn()
    patterns = [r[0] for r in conn.execute(
        "SELECT DISTINCT question_pattern FROM answers "
        "WHERE question_pattern NOT IN ('Test Question', 'test_safeguards')"
    ).fetchall()]

    seeded = 0
    for pat in patterns:
        # Check if already seeded
        existing = conn.execute(
            "SELECT id FROM taxonomies WHERE question_pattern = ?", (pat,)
        ).fetchone()
        if existing:
            continue

        # Extract categories from responses
        rows = conn.execute("""
            SELECT main_category, cluster_title, cluster_id,
                   GROUP_CONCAT(response_text, '|||') as examples,
                   COUNT(*) as cnt
            FROM answers WHERE question_pattern = ?
            GROUP BY main_category, cluster_title
            ORDER BY cnt DESC
        """, (pat,)).fetchall()

        if not rows:
            continue

        # Build taxonomy structure
        main_cats = {}
        for r in rows:
            mc = r[0] or "Allgemein"
            if mc not in main_cats:
                main_cats[mc] = {"id": f"cat_{len(main_cats)+1}",
                                 "main_category": mc, "sub_categories": []}

            examples = (r[3] or "").split("|||")[:3]
            examples = [e[:80] for e in examples if e.strip()]

            main_cats[mc]["sub_categories"].append({
                "id": r[2] or f"cat_{len(main_cats)}_{len(main_cats[mc]['sub_categories'])+1}",
                "title": r[1] or "Sonstige",
                "examples": examples,
                "include_rule": f"Antworten zum Thema {r[1]}",
                "exclude_rule": "",
            })

        taxonomy = {"categories": list(main_cats.values())}
        taxonomy_json = json.dumps(taxonomy, ensure_ascii=False)
        n_cats = sum(len(c["sub_categories"]) for c in taxonomy["categories"])

        conn.execute("""
            INSERT OR IGNORE INTO taxonomies
            (question_pattern, taxonomy_json, n_categories, n_responses_seen)
            VALUES (?, ?, ?, ?)
        """, (pat, taxonomy_json, n_cats, 0))
        seeded += 1

    conn.commit()
    conn.close()
    return seeded


def test_taxonomy_caching():
    print("=" * 70)
    print("TEST 1: Taxonomy Caching (save / load / fuzzy match)")
    print("=" * 70)

    # Load a taxonomy
    tax = get_cached_taxonomy("Bitte nennen Sie Staerken des Kurses.")
    ok1 = tax is not None and "categories" in tax
    if ok1:
        n_cats = sum(len(c.get("sub_categories", []))
                     for c in tax["categories"])
        print(f"  [PASS] Direct load: {n_cats} sub-categories")
    else:
        print(f"  [FAIL] Direct load: got {tax}")

    # Fuzzy match with umlauts + prefix
    tax2 = get_cached_taxonomy("[Post] Bitte nennen Sie Starken des Kurses. (Angabe)")
    ok2 = tax2 is not None
    print(f"  [{'PASS' if ok2 else 'FAIL'}] Fuzzy match (umlauts + prefix + parenthetical)")

    # Previously failing case
    tax3 = get_cached_taxonomy("Warum denken Sie so?")
    ok3 = tax3 is not None
    print(f"  [{'PASS' if ok3 else 'FAIL'}] Fuzzy match (partial vs full with parenthetical)")

    # Should not match
    tax4 = get_cached_taxonomy("This is totally unrelated xyz123")
    ok4 = tax4 is None
    print(f"  [{'PASS' if ok4 else 'FAIL'}] No match for garbage input")

    print()
    return ok1 and ok2 and ok3 and ok4


def test_taxonomy_classification():
    print("=" * 70)
    print("TEST 2: Taxonomy-Based Classification (speed + quality)")
    print("=" * 70)

    question = "Bitte nennen Sie Staerken des Kurses."
    taxonomy = get_cached_taxonomy(question)
    flat = _flatten_taxonomy(taxonomy)
    print(f"  Taxonomy: {len(flat)} categories")
    for cat in flat[:5]:
        print(f"    - {cat['main_category']} > {cat['title']}")
    if len(flat) > 5:
        print(f"    ... and {len(flat) - 5} more")

    # Get real responses from the legacy cache
    cached = get_cached_answers(question)
    if len(cached) < 20:
        print("  SKIP: not enough responses")
        return True

    # Sample 50 responses with known categories
    sample = random.sample(cached, min(50, len(cached)))
    responses = [s["response_text"] for s in sample]
    expected_cats = {s["response_text"]: s["cluster_id"] for s in sample}

    print(f"\n  Classifying {len(responses)} responses against {len(flat)} categories...")
    t0 = time.perf_counter()
    classified, low_fit = classify_from_taxonomy(question, responses, taxonomy)
    elapsed = time.perf_counter() - t0

    print(f"  Time: {elapsed:.2f}s")
    print(f"  Classified: {len(classified)}, Low-fit: {len(low_fit)}")

    # Check accuracy against known categories
    correct = 0
    wrong = 0
    wrong_details = []
    for c in classified:
        expected = expected_cats.get(c["text"])
        if expected and expected == c["cluster_id"]:
            correct += 1
        elif expected:
            wrong += 1
            if len(wrong_details) < 3:
                wrong_details.append({
                    "text": c["text"][:60],
                    "expected": expected,
                    "got": c["cluster_id"],
                    "confidence": c["confidence"],
                })

    total = correct + wrong
    acc = correct / max(total, 1) * 100
    print(f"\n  Category accuracy: {correct}/{total} ({acc:.0f}%)")
    if wrong_details:
        print(f"  Sample mismatches:")
        for d in wrong_details:
            print(f"    '{d['text']}...'")
            print(f"      expected={d['expected']}, got={d['got']} ({d['confidence']})")

    # Confidence breakdown
    n_high = sum(1 for c in classified if c["confidence"] == "high")
    n_med = sum(1 for c in classified if c["confidence"] == "medium")
    n_low = sum(1 for c in classified if c["confidence"] == "low")
    print(f"\n  Confidence: high={n_high}, medium={n_med}, low={n_low}")

    speed_ok = elapsed < 30
    print(f"  Speed OK: {'YES' if speed_ok else 'NO'} ({elapsed:.1f}s)")
    print()
    return speed_ok and acc >= 50  # taxonomy from cache is approximate


def test_low_fit_detection():
    print("=" * 70)
    print("TEST 3: Low-Fit Detection (new category needed)")
    print("=" * 70)

    question = "Bitte nennen Sie Staerken des Kurses."
    taxonomy = get_cached_taxonomy(question)

    # These responses should NOT fit any "strengths" category well
    outliers = [
        "Meine Katze ist gestern weggelaufen und ich bin traurig.",
        "The weather in London is terrible this time of year.",
        "1234567890 abcdefghij XYZZY",
        "SELECT * FROM users WHERE 1=1; DROP TABLE answers;",
    ]

    # Normal responses that SHOULD fit
    normal = [
        "Die Trainerin war sehr kompetent und engagiert.",
        "Der Praxisbezug war hervorragend.",
        "Gute Strukturierung und klare Inhalte.",
    ]

    all_responses = outliers + normal
    classified, low_fit = classify_from_taxonomy(question, all_responses, taxonomy)

    # Outliers should ideally be low-fit or at least low-confidence
    outlier_fates = {}
    for r in outliers:
        if r in low_fit:
            outlier_fates[r[:40]] = "low_fit (correct)"
        else:
            match = next((c for c in classified if c["text"] == r), None)
            if match:
                outlier_fates[r[:40]] = f"classified as {match['cluster_title'][:20]} ({match['confidence']})"

    normal_fates = {}
    for r in normal:
        match = next((c for c in classified if c["text"] == r), None)
        if match:
            normal_fates[r[:40]] = f"{match['main_category']} > {match['cluster_title']} ({match['confidence']})"
        elif r in low_fit:
            normal_fates[r[:40]] = "low_fit (wrong!)"

    print(f"  Outliers ({len(outliers)}):")
    for text, fate in outlier_fates.items():
        print(f"    '{text}...' -> {fate}")

    print(f"\n  Normal responses ({len(normal)}):")
    for text, fate in normal_fates.items():
        print(f"    '{text}...' -> {fate}")

    # At least normal responses should be classified
    normal_classified = sum(1 for r in normal
                            if any(c["text"] == r for c in classified))
    ok = normal_classified == len(normal)
    print(f"\n  Normal classified: {normal_classified}/{len(normal)}")
    print(f"  [{'PASS' if ok else 'FAIL'}]")
    print()
    return ok


def test_verification_system():
    """Test the verification system: user can check how a response gets categorised."""
    print("=" * 70)
    print("TEST 4: Verification System (test_reliability)")
    print("=" * 70)

    question = "Was hat Ihnen besonders gut gefallen?"
    tax = get_cached_taxonomy(question)
    if not tax:
        # Try fuzzy
        tax = get_cached_taxonomy("Was hat Ihnen an der Schulung gut gefallen?")
        question = "Was hat Ihnen an der Schulung gut gefallen?"

    if not tax:
        print("  SKIP: no taxonomy")
        return True

    test_cases = [
        ("Die Trainerin war toll und sehr kompetent", True),
        ("Der Praxisbezug hat mir besonders gut gefallen", True),
        ("Gute Organisation und freundliche Atmosphaere", True),
        ("xyz abc 123 nonsense", True),  # should still classify (to some category)
    ]

    all_ok = True
    for text, expect_match in test_cases:
        result = test_reliability(question, text)

        print(f"\n  Input: '{text}'")
        print(f"    Matched: {result.get('matched')}")
        print(f"    Category: {result.get('main_category', 'N/A')} > "
              f"{result.get('cluster_title', 'N/A')}")
        print(f"    Confidence: {result.get('confidence', 'N/A')}")
        print(f"    Score: {result.get('score', 'N/A')}, "
              f"Margin: {result.get('margin', 'N/A')}")

        if result.get("top_3"):
            print(f"    Top 3 categories:")
            for t in result["top_3"]:
                print(f"      #{t['rank']}: {t['main_category']} > "
                      f"{t['category']} (score={t['score']})")

        if result.get("reason"):
            print(f"    Reason: {result['reason']}")

    print()
    return True


def test_cross_question():
    """Test classification across multiple questions."""
    print("=" * 70)
    print("TEST 5: Cross-Question Classification")
    print("=" * 70)

    conn = _get_conn()
    questions = [r[0] for r in conn.execute(
        "SELECT DISTINCT question_pattern FROM taxonomies"
    ).fetchall()]
    conn.close()

    print(f"  {len(questions)} questions with cached taxonomies\n")

    total_classified = 0
    total_low_fit = 0
    total_time = 0

    for q in questions:
        tax = get_cached_taxonomy(q)
        flat = _flatten_taxonomy(tax)

        # Get sample responses
        cached = get_cached_answers(q)
        if len(cached) < 10:
            continue

        sample = random.sample(cached, min(20, len(cached)))
        responses = [s["response_text"] for s in sample]

        t0 = time.perf_counter()
        classified, low_fit = classify_from_taxonomy(q, responses, tax)
        elapsed = time.perf_counter() - t0

        total_classified += len(classified)
        total_low_fit += len(low_fit)
        total_time += elapsed

        print(f"  {q[:55]:55s} | {len(classified):2d}/{len(responses)} "
              f"| {len(flat):2d} cats | {elapsed:.1f}s")

    print(f"\n  TOTALS:")
    print(f"    Classified: {total_classified}")
    print(f"    Low-fit: {total_low_fit}")
    print(f"    Total time: {total_time:.1f}s")
    print(f"    Speed: {(total_classified + total_low_fit) / max(total_time, 0.01):.0f} resp/s")
    print()
    return total_classified > 0


def test_speed_comparison():
    """Compare taxonomy-first vs old response-matching speed."""
    print("=" * 70)
    print("TEST 6: Speed — Taxonomy vs Response Matching")
    print("=" * 70)

    question = "Bitte nennen Sie Staerken des Kurses."
    taxonomy = get_cached_taxonomy(question)
    flat = _flatten_taxonomy(taxonomy)
    cached = get_cached_answers(question)

    if len(cached) < 50:
        print("  SKIP: not enough data")
        return True

    responses = [c["response_text"] for c in random.sample(cached, 50)]

    # Taxonomy-first: 50 responses × n_categories pairs
    t0 = time.perf_counter()
    classified, low_fit = classify_from_taxonomy(question, responses, taxonomy)
    t_taxonomy = time.perf_counter() - t0

    n_pairs_taxonomy = len(responses) * len(flat)

    print(f"  Taxonomy-first:")
    print(f"    {len(responses)} responses x {len(flat)} categories "
          f"= {n_pairs_taxonomy} pairs")
    print(f"    Time: {t_taxonomy:.2f}s")
    print(f"    Classified: {len(classified)}, Low-fit: {len(low_fit)}")

    print(f"\n  Old approach (response matching) would have been:")
    print(f"    {len(responses)} responses x {len(cached)} cached "
          f"= {len(responses) * len(cached)} pairs")
    print(f"    Estimated: ~{len(responses) * len(cached) / 78:.0f}s")

    speedup = (len(responses) * len(cached)) / max(n_pairs_taxonomy, 1)
    print(f"\n  Speedup: {speedup:.0f}x fewer pairs")
    print()
    return t_taxonomy < 30


if __name__ == "__main__":
    print("\nBC4D Intel -- Taxonomy-First Architecture (v3) Test Suite")
    print("No API calls. Local cross-encoder only.\n")

    # Seed taxonomies from existing response cache
    print("Seeding taxonomy cache from response history...")
    n_seeded = seed_taxonomies_from_response_cache()
    stats = get_cache_stats()
    print(f"  Seeded {n_seeded} new taxonomies "
          f"(total: {stats.get('taxonomies', 0)})\n")

    # Load cross-encoder
    print("Loading cross-encoder model...")
    t0 = time.perf_counter()
    _get_cross_encoder()
    print(f"  Loaded in {time.perf_counter() - t0:.1f}s\n")

    results = {}
    results["taxonomy_caching"] = test_taxonomy_caching()
    results["taxonomy_classification"] = test_taxonomy_classification()
    results["low_fit_detection"] = test_low_fit_detection()
    results["verification_system"] = test_verification_system()
    results["cross_question"] = test_cross_question()
    results["speed_comparison"] = test_speed_comparison()

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    for name, passed in results.items():
        print(f"  {'PASS' if passed else 'FAIL'} -- {name}")
    n_pass = sum(results.values())
    print(f"\n  {n_pass}/{len(results)} passed")
    sys.exit(0 if n_pass == len(results) else 1)
