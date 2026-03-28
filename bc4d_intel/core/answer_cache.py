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
MATCH_THRESHOLD = 0.90


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
            cached_results.append({
                "text": response,
                "cluster_id": cached["cluster_id"],
                "cluster_title": cached["cluster_title"],
                "main_category": cached["main_category"],
                "confidence": "high",  # cache match = high confidence
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
    return {
        "matched": normalized >= threshold,
        "score": round(normalized, 3),
        "threshold": threshold,
        "cache_match": best["response_text"],
        "cluster_id": best["cluster_id"],
        "cluster_title": best["cluster_title"],
        "main_category": best["main_category"],
        "n_cached": len(cached_answers),
    }
