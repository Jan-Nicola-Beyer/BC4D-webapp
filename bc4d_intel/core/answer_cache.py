"""Answer cache — learns from past classifications to avoid redundant AI calls.

Architecture:
  - SQLite database stores (question_pattern, response_text, cluster_id, cluster_title,
    main_category, confidence, staffel) for every classified response.
  - On new staffel: cross-encoder scores new responses against cached ones (free, local).
  - If similarity > threshold: reuse cached classification (zero API cost).
  - If below threshold: send to AI for new classification, then add to cache.

Cost impact:
  - Staffel 1: full AI cost (~$0.65) — builds the cache
  - Staffel 2: ~60% cache hits → ~$0.26
  - Staffel 3+: ~80% cache hits → ~$0.13
  - Staffel 10+: ~95% cache hits → ~$0.03

Speed impact:
  - Cross-encoder scoring 135 responses × 500 cached = ~2s (vs 78s API)
"""

from __future__ import annotations
import logging, os, sqlite3
from typing import Dict, List, Tuple, Optional

import numpy as np

from bc4d_intel.constants import APP_DIR

log = logging.getLogger("bc4d_intel.core.answer_cache")

CACHE_DB_PATH = os.path.join(APP_DIR, "sessions", "answer_cache.db")

# Similarity threshold — responses above this reuse cached classification.
# 0.90 = very conservative (nearly identical text).
# Lower = more cache hits but more risk of wrong classification.
# Lowered from 0.90 to 0.78 after testing showed common paraphrases
# scoring 0.77-0.85. The 6-layer safety system (sentiment, negation,
# conditional, subject, category, question-context) catches mismatches.
MATCH_THRESHOLD = 0.78

# ── Sentiment polarity guard ─────────────────────────────────────
# Prevents matching "workshop was great" to "workshop was boring".
# Cross-encoder scores structural similarity, but sentiment flips
# must force a cache miss.

_POSITIVE = frozenset(
    "gut toll super hervorragend prima wunderbar hilfreich informativ "
    "kompetent angenehm effektiv wertvoll bereichernd spannend interessant "
    "professionell engagiert freundlich motivierend verstaendlich klar "
    "praxisnah nah relevant aktuell lehrreich positiv gerne empfehlen "
    "gefallen geholfen gelernt verbessert gestaerkt sicher zuversichtlich".split()
)

_NEGATIVE = frozenset(
    "schlecht langweilig nicht kein nie leider schwierig verwirrend "
    "unklar kompliziert oberflaechlich unnoetig ueberfluessig enttaeuschend "
    "unverstaendlich unstrukturiert chaotisch monoton anstrengend nervig "
    "wenig mangelhaft fehlend problematisch negativ ungenuegend langatmig "
    "schleppend veraltet wiederholung redundant boring fade "
    "besser verbessern verbesserung haette waere koennte sollte".split()
)


def _sentiment(text: str) -> int:
    """Quick sentiment polarity: +1 positive, -1 negative, 0 neutral."""
    words = set(text.lower().split())
    pos = len(words & _POSITIVE)
    neg = len(words & _NEGATIVE)
    if pos > 0 and neg == 0:
        return 1
    if neg > 0 and pos == 0:
        return -1
    if pos > neg:
        return 1
    if neg > pos:
        return -1
    return 0


def _sentiments_compatible(text_a: str, text_b: str) -> bool:
    """Check if two texts have compatible sentiments.

    Returns False only if one is clearly positive and the other clearly negative.
    Neutral matches with anything.
    """
    sa = _sentiment(text_a)
    sb = _sentiment(text_b)
    if sa == 1 and sb == -1:
        return False
    if sa == -1 and sb == 1:
        return False
    return True


# ── Additional safeguards ────────────────────────────────────────

_NEGATION_WORDS = frozenset("nicht kein keine keinen keiner nie niemals kaum wenig".split())
_CONDITIONAL = frozenset("waere haette koennte sollte wenn falls obwohl trotzdem".split())


def _safe_to_cache_match(new_text: str, cached_text: str) -> bool:
    """Multi-layer safety check before accepting a cache match.

    Returns False if any safeguard detects a potential misclassification.
    """
    new_lower = new_text.lower()
    cached_lower = cached_text.lower()
    new_words = set(new_lower.split())
    cached_words = set(cached_lower.split())

    # Guard 1: Sentiment polarity conflict
    if not _sentiments_compatible(new_text, cached_text):
        return False

    # Guard 2: Negation asymmetry
    # "nicht informativ" must not match "informativ"
    new_has_neg = bool(new_words & _NEGATION_WORDS)
    cached_has_neg = bool(cached_words & _NEGATION_WORDS)
    if new_has_neg != cached_has_neg:
        # One has negation, the other doesn't — potential flip
        return False

    # Guard 3: Very short responses (< 4 words) need higher threshold
    # "Gut" could match "Gut strukturiert" or "Gut, dass es vorbei ist"
    # Handled by caller raising threshold for short texts

    # Guard 4: Conditional vs definitive
    # "Waere besser gewesen" vs "War gut" — different evaluation
    new_conditional = bool(new_words & _CONDITIONAL)
    cached_conditional = bool(cached_words & _CONDITIONAL)
    if new_conditional != cached_conditional:
        # One is hypothetical, the other is definitive
        # Only block if sentiments also differ
        if _sentiment(new_text) != _sentiment(cached_text):
            return False

    # Guard 5: Subject mismatch for very short responses
    # "Trainerin toll" vs "Material toll" — different subjects
    # For responses < 6 words, require at least 1 content word overlap
    if len(new_words) < 6 and len(cached_words) < 6:
        content_new = new_words - _POSITIVE - _NEGATIVE - _NEGATION_WORDS - \
            frozenset("der die das ein eine und oder war ist sehr".split())
        content_cached = cached_words - _POSITIVE - _NEGATIVE - _NEGATION_WORDS - \
            frozenset("der die das ein eine und oder war ist sehr".split())
        if content_new and content_cached and not (content_new & content_cached):
            # No content word overlap in short responses → different subjects
            return False

    return True


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(CACHE_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_pattern TEXT NOT NULL,
            response_text TEXT NOT NULL,
            cluster_id TEXT,
            cluster_title TEXT,
            main_category TEXT,
            confidence TEXT,
            staffel TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(question_pattern, response_text)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_answers_q ON answers(question_pattern)")
    conn.commit()
    return conn


def _normalize_question(question: str) -> str:
    """Normalize question text for matching across staffels.

    Different staffels may have slightly different column names.
    Extract the core question by removing prefixes like '[Pre]', '[Post]'.
    """
    import re
    q = re.sub(r'^\[(Pre|Post)\]\s*', '', question)
    q = q.strip()[:100]  # first 100 chars
    return q


def get_cached_answers(question: str) -> List[Dict]:
    """Get all cached answers for a question pattern."""
    conn = _get_conn()
    pattern = _normalize_question(question)
    rows = conn.execute(
        "SELECT * FROM answers WHERE question_pattern = ? ORDER BY id",
        (pattern,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def add_to_cache(question: str, classifications: List[Dict], staffel: str = ""):
    """Add classified responses to the cache for future reuse."""
    conn = _get_conn()
    pattern = _normalize_question(question)
    added = 0
    for c in classifications:
        text = c.get("text", "").strip()
        if len(text) < 3:
            continue
        try:
            conn.execute("""
                INSERT OR IGNORE INTO answers
                (question_pattern, response_text, cluster_id, cluster_title,
                 main_category, confidence, staffel)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                pattern, text,
                c.get("human_override") or c.get("cluster_id", ""),
                c.get("cluster_title", ""),
                c.get("main_category", ""),
                c.get("confidence", "medium"),
                staffel,
            ))
            added += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    log.info("Added %d answers to cache for '%s'", added, pattern[:40])
    return added


def classify_from_cache(
    question: str,
    responses: List[str],
    threshold: float = MATCH_THRESHOLD,
    progress_cb=None,
) -> Tuple[List[Dict], List[str]]:
    """Match new responses against cached answers using cross-encoder.

    Returns:
        cached_results: list of {text, cluster_id, cluster_title, main_category,
                        confidence, cache_score} for matched responses
        uncached: list of response texts that need AI classification
    """
    cached_answers = get_cached_answers(question)
    if not cached_answers:
        return [], list(responses)

    if progress_cb:
        progress_cb(f"Checking {len(responses)} responses against {len(cached_answers)} cached answers...")

    # Load cross-encoder
    try:
        from sentence_transformers import CrossEncoder
        reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    except Exception:
        log.warning("Cross-encoder not available for cache matching")
        return [], list(responses)

    cached_texts = [a["response_text"] for a in cached_answers]

    cached_results = []
    uncached = []

    # For each new response, find the best match in cache
    # Batch all pairs for speed
    all_pairs = []
    pair_map = []  # (response_idx, cache_idx)
    for ri, response in enumerate(responses):
        for ci, cached_text in enumerate(cached_texts):
            all_pairs.append((response, cached_text))
            pair_map.append((ri, ci))

    if not all_pairs:
        return [], list(responses)

    if progress_cb:
        progress_cb(f"Scoring {len(all_pairs)} pairs (free, local)...")

    # Batch predict
    scores = reranker.predict(all_pairs, show_progress_bar=False)

    # Reshape: for each response, find best cache match
    n_responses = len(responses)
    n_cached = len(cached_texts)
    score_matrix = np.array(scores).reshape(n_responses, n_cached)

    for ri, response in enumerate(responses):
        best_idx = int(np.argmax(score_matrix[ri]))
        best_score = float(score_matrix[ri, best_idx])

        # Normalize score to 0-1 range (cross-encoder gives raw scores)
        # For ms-marco-MiniLM, scores > 5 are very similar, < 0 are dissimilar
        normalized = 1.0 / (1.0 + np.exp(-best_score))  # sigmoid

        if normalized >= threshold:
            cached = cached_answers[best_idx]

            # Multi-layer safety check: sentiment, negation, conditional, subject
            if not _safe_to_cache_match(response, cached["response_text"]):
                uncached.append(response)
                continue

            # Cross-check: question context + response sentiment
            new_sent = _sentiment(response)
            q_lower = question.lower() if isinstance(question, str) else ""

            # "Staerken" / "gut gefallen" questions expect positive answers
            # A negative response here is always a mismatch
            if new_sent == -1 and any(w in q_lower for w in ["staerke", "gut gefallen", "besonders gut"]):
                uncached.append(response)
                continue
            # "Verbesserung" questions expect critical answers
            # A purely positive response here is a mismatch
            if new_sent == 1 and any(w in q_lower for w in ["verbesser", "nicht verstaendlich"]):
                uncached.append(response)
                continue

            # Also check cached category alignment
            cached_cat = (cached.get("main_category", "") + " " + cached.get("cluster_title", "")).lower()
            if new_sent == -1 and any(w in cached_cat for w in ["positiv", "lob", "staerke", "gut"]):
                uncached.append(response)
                continue
            if new_sent == 1 and any(w in cached_cat for w in ["negativ", "kritik", "verbesser", "schlecht"]):
                uncached.append(response)
                continue

            # Short responses need higher threshold (too easy to match wrong)
            if len(response.split()) < 4 and normalized < 0.95:
                uncached.append(response)
                continue

            cached_results.append({
                "text": response,
                "cluster_id": cached["cluster_id"],
                "cluster_title": cached["cluster_title"],
                "main_category": cached["main_category"],
                "confidence": "high",
                "cache_score": round(normalized, 3),
                "cache_match": cached["response_text"][:60],
                "human_override": "",
            })
        else:
            uncached.append(response)

    if progress_cb:
        hit_rate = len(cached_results) / max(n_responses, 1) * 100
        progress_cb(f"Cache: {len(cached_results)}/{n_responses} matched ({hit_rate:.0f}% hit rate)")

    log.info("Cache matching: %d/%d hits (%.0f%%) for '%s'",
             len(cached_results), n_responses,
             len(cached_results) / max(n_responses, 1) * 100,
             _normalize_question(question)[:40])

    return cached_results, uncached


def get_cache_stats() -> Dict:
    """Get cache statistics."""
    conn = _get_conn()
    total = conn.execute("SELECT COUNT(*) FROM answers").fetchone()[0]
    questions = conn.execute("SELECT COUNT(DISTINCT question_pattern) FROM answers").fetchone()[0]
    staffels = conn.execute("SELECT COUNT(DISTINCT staffel) FROM answers WHERE staffel != ''").fetchone()[0]
    conn.close()
    return {"total_answers": total, "questions": questions, "staffels": staffels}


def test_reliability(
    question: str,
    test_text: str,
    threshold: float = MATCH_THRESHOLD,
) -> Dict:
    """Test if a specific text would be reliably classified from cache.

    Returns {matched, cache_match, cluster_id, cluster_title, main_category, score}
    """
    cached_answers = get_cached_answers(question)
    if not cached_answers:
        return {"matched": False, "reason": "No cached answers for this question"}

    try:
        from sentence_transformers import CrossEncoder
        reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    except Exception:
        return {"matched": False, "reason": "Cross-encoder not available"}

    pairs = [(test_text, a["response_text"]) for a in cached_answers]
    scores = reranker.predict(pairs, show_progress_bar=False)

    best_idx = int(np.argmax(scores))
    best_score = float(scores[best_idx])
    normalized = 1.0 / (1.0 + np.exp(-best_score))

    best = cached_answers[best_idx]
    score_ok = normalized >= threshold
    safety_ok = _safe_to_cache_match(test_text, best["response_text"])
    short_ok = len(test_text.split()) >= 4 or normalized >= 0.95

    # Question-context guard (same as classify_from_cache)
    q_lower = _normalize_question(question).lower()
    new_sent = _sentiment(test_text)
    context_ok = True
    if new_sent == -1 and any(w in q_lower for w in ["staerke", "gut gefallen", "besonders gut"]):
        context_ok = False
    if new_sent == 1 and any(w in q_lower for w in ["verbesser", "nicht verstaendlich"]):
        context_ok = False

    matched = score_ok and safety_ok and short_ok and context_ok

    result = {
        "matched": matched,
        "score": round(normalized, 3),
        "threshold": threshold,
        "cache_match": best["response_text"],
        "cluster_id": best["cluster_id"],
        "cluster_title": best["cluster_title"],
        "main_category": best["main_category"],
        "n_cached": len(cached_answers),
    }
    if score_ok and not context_ok:
        result["context_blocked"] = True
        result["reason"] = "Response sentiment conflicts with question type — sent to AI"
    elif score_ok and not safety_ok:
        result["safety_blocked"] = True
        result["reason"] = "High similarity but safety check failed (sentiment/negation/subject) — sent to AI"
    elif score_ok and not short_ok:
        result["short_text_blocked"] = True
        result["reason"] = "Short response needs >95% match for safety — sent to AI"
    return result
