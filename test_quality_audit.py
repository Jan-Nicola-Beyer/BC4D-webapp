"""Quality audit: cross-check pipeline classifications for systematic errors.

Takes classified responses from the pipeline and checks:
1. Does the assigned category make semantic sense?
2. Are there systematic misclassification patterns?
3. Are negative responses in positive categories (or vice versa)?
4. Are short/ambiguous responses handled correctly?
5. Category consistency: similar responses in same category?

Uses bi-encoder embeddings to detect within-category outliers
and cross-category confusion without any API calls.
"""

from __future__ import annotations
import os, sys, time, random
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "bc4d_intel"))
sys.path.insert(0, os.path.dirname(__file__))

import numpy as np

from bc4d_intel.core.answer_cache import (
    classify_from_cache, get_cached_answers, _sentiment,
    _get_bi_encoder, _get_cross_encoder, find_anomalies,
)

random.seed(42)


def audit_question(question: str, n_sample: int = 100):
    """Run a full quality audit on one question's classifications."""
    cached = get_cached_answers(question)
    if len(cached) < 20:
        return None

    sample = random.sample(cached, min(n_sample, len(cached)))
    responses = [s["response_text"] for s in sample]
    expected = {s["response_text"]: {
        "cluster_id": s["cluster_id"],
        "cluster_title": s["cluster_title"],
        "main_category": s["main_category"],
    } for s in sample}

    # Run through pipeline
    classified, uncertain = classify_from_cache(question, responses)

    # ── Audit 1: Category accuracy ──────────────────────────────
    correct = wrong = 0
    mismatches = []
    for c in classified:
        exp = expected.get(c["text"])
        if not exp:
            continue
        if exp["cluster_id"] == c["cluster_id"]:
            correct += 1
        else:
            wrong += 1
            mismatches.append({
                "text": c["text"][:70],
                "expected_cat": f"{exp['main_category']} > {exp['cluster_title']}",
                "got_cat": f"{c['main_category']} > {c['cluster_title']}",
                "case": c.get("match_case", "?"),
                "score": c.get("cache_score", 0),
            })

    # ── Audit 2: Sentiment vs category alignment ────────────────
    sentiment_issues = []
    for c in classified:
        sent = _sentiment(c["text"])
        cat_lower = (c.get("main_category", "") + " " +
                     c.get("cluster_title", "")).lower()

        # Negative response in positive category?
        if sent == -1 and any(w in cat_lower for w in
                              ["positiv", "lob", "staerke", "gut"]):
            sentiment_issues.append({
                "text": c["text"][:60],
                "sentiment": "NEG",
                "category": f"{c['main_category']} > {c['cluster_title']}",
                "issue": "Negative response in positive category",
            })
        # Positive response in negative category?
        if sent == 1 and any(w in cat_lower for w in
                             ["negativ", "kritik", "schlecht"]):
            sentiment_issues.append({
                "text": c["text"][:60],
                "sentiment": "POS",
                "category": f"{c['main_category']} > {c['cluster_title']}",
                "issue": "Positive response in negative category",
            })

    # ── Audit 3: Short response handling ────────────────────────
    short_classified = [c for c in classified if len(c["text"].split()) < 4]
    short_uncertain = [u for u in uncertain if len(u.split()) < 4]

    # ── Audit 4: Category distribution ──────────────────────────
    cat_dist = Counter(c.get("main_category", "?") for c in classified)
    # Flag if >80% in one category (suspicious)
    total_classified = len(classified)
    dominant = cat_dist.most_common(1)[0] if cat_dist else ("?", 0)
    dominance_pct = dominant[1] / max(total_classified, 1) * 100

    # ── Audit 5: Within-category consistency (embeddings) ───────
    bi_enc = _get_bi_encoder()
    texts = [c["text"] for c in classified]
    if texts:
        embeddings = bi_enc.encode(texts, show_progress_bar=False,
                                   normalize_embeddings=True)

        cat_groups = {}
        for i, c in enumerate(classified):
            cat_groups.setdefault(c.get("cluster_id", "?"), []).append(i)

        low_coherence_cats = []
        for cat_id, indices in cat_groups.items():
            if len(indices) < 3:
                continue
            cat_embs = embeddings[indices]
            centroid = cat_embs.mean(axis=0)
            centroid = centroid / (np.linalg.norm(centroid) + 1e-8)
            distances = 1.0 - np.dot(cat_embs, centroid)
            avg_dist = float(distances.mean())
            if avg_dist > 0.5:
                cat_name = classified[indices[0]].get("cluster_title", "?")
                low_coherence_cats.append((cat_name, avg_dist, len(indices)))

    return {
        "question": question,
        "n_sample": len(sample),
        "n_classified": len(classified),
        "n_uncertain": len(uncertain),
        "accuracy": correct / max(correct + wrong, 1) * 100,
        "correct": correct,
        "wrong": wrong,
        "mismatches": mismatches[:5],
        "sentiment_issues": sentiment_issues[:5],
        "n_sentiment_issues": len(sentiment_issues),
        "short_classified": len(short_classified),
        "short_uncertain": len(short_uncertain),
        "category_dist": dict(cat_dist.most_common(5)),
        "dominance_pct": dominance_pct,
        "dominant_cat": dominant[0],
        "low_coherence_cats": low_coherence_cats,
    }


if __name__ == "__main__":
    print("\nBC4D Intel -- Quality Audit (Systematic Error Detection)")
    print("No API calls. Cross-checking pipeline classifications.\n")

    # Load models
    print("Loading models...")
    t0 = time.perf_counter()
    _get_bi_encoder()
    _get_cross_encoder()
    print(f"Loaded in {time.perf_counter()-t0:.1f}s\n")

    # Get all questions
    from bc4d_intel.core.answer_cache import _get_conn
    conn = _get_conn()
    questions = [r[0] for r in conn.execute(
        "SELECT DISTINCT question_pattern FROM answers "
        "WHERE question_pattern NOT IN ('Test Question', 'test_safeguards')"
    ).fetchall()]
    conn.close()

    grand_correct = grand_wrong = 0
    grand_sentiment_issues = 0
    all_mismatches = []

    for q in questions:
        print(f"{'='*70}")
        print(f"Auditing: {q[:65]}")
        print(f"{'='*70}")

        t0 = time.perf_counter()
        result = audit_question(q, n_sample=80)
        elapsed = time.perf_counter() - t0

        if result is None:
            print("  SKIP: not enough data\n")
            continue

        grand_correct += result["correct"]
        grand_wrong += result["wrong"]
        grand_sentiment_issues += result["n_sentiment_issues"]
        all_mismatches.extend(result["mismatches"])

        print(f"\n  Classified: {result['n_classified']}/{result['n_sample']} "
              f"| Uncertain: {result['n_uncertain']} | Time: {elapsed:.1f}s")

        # Accuracy
        print(f"\n  ACCURACY: {result['correct']}/{result['correct']+result['wrong']} "
              f"({result['accuracy']:.0f}%)")
        if result["mismatches"]:
            print(f"  Mismatches ({result['wrong']} total):")
            for m in result["mismatches"][:3]:
                print(f"    \"{m['text']}\"")
                print(f"      Expected: {m['expected_cat']}")
                print(f"      Got:      {m['got_cat']} (case={m['case']}, score={m['score']})")

        # Sentiment alignment
        if result["n_sentiment_issues"]:
            print(f"\n  SENTIMENT ISSUES: {result['n_sentiment_issues']}")
            for s in result["sentiment_issues"][:3]:
                print(f"    [{s['sentiment']}] \"{s['text']}\"")
                print(f"      -> {s['category']} ({s['issue']})")
        else:
            print(f"\n  SENTIMENT: No issues detected")

        # Short responses
        print(f"\n  SHORT RESPONSES: {result['short_classified']} classified, "
              f"{result['short_uncertain']} sent to API")

        # Category distribution
        print(f"\n  CATEGORY DISTRIBUTION:")
        for cat, count in result["category_dist"].items():
            bar = "#" * min(count, 40)
            print(f"    {cat[:25]:25s} | {count:3d} {bar}")
        if result["dominance_pct"] > 70:
            print(f"    WARNING: '{result['dominant_cat']}' dominates "
                  f"at {result['dominance_pct']:.0f}%")

        # Coherence
        if result["low_coherence_cats"]:
            print(f"\n  LOW COHERENCE CATEGORIES (avg distance > 0.5):")
            for name, dist, n in result["low_coherence_cats"]:
                print(f"    {name[:30]:30s} | avg_dist={dist:.3f} | n={n}")
        else:
            print(f"\n  COHERENCE: All categories well-clustered")

        print()

    # ── Grand Summary ───────────────────────────────────────────
    print("=" * 70)
    print("GRAND SUMMARY")
    print("=" * 70)

    grand_total = grand_correct + grand_wrong
    grand_acc = grand_correct / max(grand_total, 1) * 100

    print(f"\n  Overall accuracy: {grand_correct}/{grand_total} ({grand_acc:.0f}%)")
    print(f"  Sentiment issues: {grand_sentiment_issues}")
    print(f"  Questions audited: {len(questions)}")

    if all_mismatches:
        # Find systematic patterns
        print(f"\n  MISMATCH PATTERNS:")
        confusion = Counter()
        for m in all_mismatches:
            confusion[f"{m['expected_cat']} -> {m['got_cat']}"] += 1
        for pattern, count in confusion.most_common(5):
            print(f"    {count}x: {pattern}")

    if grand_acc >= 95:
        print(f"\n  VERDICT: EXCELLENT ({grand_acc:.0f}% accuracy)")
    elif grand_acc >= 85:
        print(f"\n  VERDICT: GOOD ({grand_acc:.0f}% accuracy)")
    elif grand_acc >= 70:
        print(f"\n  VERDICT: ACCEPTABLE ({grand_acc:.0f}% accuracy, needs tuning)")
    else:
        print(f"\n  VERDICT: NEEDS WORK ({grand_acc:.0f}% accuracy)")

    sys.exit(0 if grand_acc >= 85 else 1)
