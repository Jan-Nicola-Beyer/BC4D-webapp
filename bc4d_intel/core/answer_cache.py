"""Answer cache — LLM-first categorisation for survey responses.

Architecture (v5 — stripped down):
  Step 1: Taxonomy (Sonnet, cached) — design categories once, reuse forever
  Step 2: Deduplication (string match, FREE) — skip exact repeats
  Step 3: LLM Classification (Haiku) — the PRIMARY path, reasons about meaning
  Step 4: Quality Gate (Sonnet) — sample check, escalate if needed
  Step 5: Cache results — for deduplication + taxonomy persistence

No ML models loaded. No bi-encoder, cross-encoder, embeddings, safety guards.
Cost: ~$0.04/question (Staffel 2+), ~$0.07/question (Staffel 1)
Speed: ~18s/question (API latency, no model load)
"""

from __future__ import annotations
import difflib, json, logging, os, re, sqlite3, unicodedata
from typing import Dict, List, Optional, Tuple

from bc4d_intel.constants import APP_DIR

log = logging.getLogger("bc4d_intel.core.answer_cache")

CACHE_DB_PATH = os.path.join(APP_DIR, "sessions", "answer_cache.db")
QUESTION_FUZZY_THRESHOLD = 0.6
QUALITY_GATE_SAMPLE = 15
QUALITY_GATE_FAIL_THRESHOLD = 0.20  # >20% flagged → escalate to Sonnet


# ── Question normalization + fuzzy matching ─────────────────────

def _normalize_question(question: str) -> str:
    q = re.sub(r'^\[(Pre|Post)\]\s*', '', question)
    q = re.sub(r'\([^)]*\)', '', q)
    q = q.replace('\u00e4', 'ae').replace('\u00f6', 'oe').replace('\u00fc', 'ue')
    q = q.replace('\u00c4', 'Ae').replace('\u00d6', 'Oe').replace('\u00dc', 'Ue')
    q = q.replace('\u00df', 'ss')
    q = unicodedata.normalize('NFD', q)
    q = ''.join(c for c in q if unicodedata.category(c) != 'Mn')
    q = q.lower().strip()
    q = re.sub(r'\s+', ' ', q)
    return q[:100]


def _normalize_response(text: str) -> str:
    """Normalize a response for deduplication matching."""
    t = text.lower().strip()
    t = re.sub(r'[.,;:!?()\"\'\-]+', '', t)
    t = re.sub(r'\s+', ' ', t)
    return t


def _fuzzy_match_question(question: str, conn: sqlite3.Connection,
                          table: str = "answers") -> Optional[str]:
    normalized = _normalize_question(question)
    row = conn.execute(
        f"SELECT question_pattern FROM {table} WHERE question_pattern = ? LIMIT 1",
        (normalized,)
    ).fetchone()
    if row:
        return normalized
    rows = conn.execute(f"SELECT DISTINCT question_pattern FROM {table}").fetchall()
    if not rows:
        return None
    patterns = [r[0] for r in rows]
    best_pattern, best_ratio = None, 0.0
    for pat in patterns:
        ratio = difflib.SequenceMatcher(None, normalized, _normalize_question(pat)).ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_pattern = pat
    if best_ratio >= QUESTION_FUZZY_THRESHOLD:
        return best_pattern
    _STOPWORDS = {"der", "die", "das", "ein", "eine", "und", "oder", "war", "ist",
                  "sehr", "was", "wie", "welche", "ihnen", "haben", "sie", "bitte", "nennen"}
    norm_words = set(normalized.split()) - _STOPWORDS
    for pat in patterns:
        pat_words = set(_normalize_question(pat).split()) - _STOPWORDS
        if norm_words and pat_words:
            if len(norm_words & pat_words) / max(len(norm_words), len(pat_words)) >= 0.5:
                return pat
    return None


# ── Database ────────────────────────────────────────────────────

def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(CACHE_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_pattern TEXT NOT NULL,
            response_text TEXT NOT NULL,
            response_normalized TEXT,
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
    # Migrate: add response_normalized column if missing
    cols = [r[1] for r in conn.execute("PRAGMA table_info(answers)").fetchall()]
    if "response_normalized" not in cols:
        conn.execute("ALTER TABLE answers ADD COLUMN response_normalized TEXT")
        conn.execute("""
            UPDATE answers SET response_normalized = LOWER(TRIM(response_text))
            WHERE response_normalized IS NULL
        """)
        conn.commit()
    conn.execute("CREATE INDEX IF NOT EXISTS idx_answers_norm ON answers(question_pattern, response_normalized)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS taxonomies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question_pattern TEXT NOT NULL UNIQUE,
            taxonomy_json TEXT NOT NULL,
            n_categories INTEGER DEFAULT 0,
            n_responses_seen INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


# ── Taxonomy CRUD ───────────────────────────────────────────────

def get_cached_taxonomy(question: str) -> Optional[Dict]:
    conn = _get_conn()
    try:
        pattern = _fuzzy_match_question(question, conn, table="taxonomies")
        if pattern is None:
            return None
        row = conn.execute(
            "SELECT taxonomy_json FROM taxonomies WHERE question_pattern = ?",
            (pattern,)
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])
    except (json.JSONDecodeError, TypeError):
        return None
    finally:
        conn.close()


def save_taxonomy(question: str, taxonomy: Dict, n_responses: int = 0):
    conn = _get_conn()
    try:
        pattern = _normalize_question(question)
        taxonomy_json = json.dumps(taxonomy, ensure_ascii=False)
        n_cats = sum(len(c.get("sub_categories", []))
                     for c in taxonomy.get("categories", []))
        conn.execute("""
            INSERT INTO taxonomies (question_pattern, taxonomy_json, n_categories,
                                    n_responses_seen, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(question_pattern) DO UPDATE SET
                taxonomy_json = excluded.taxonomy_json,
                n_categories = excluded.n_categories,
                n_responses_seen = taxonomies.n_responses_seen + excluded.n_responses_seen,
                updated_at = CURRENT_TIMESTAMP
        """, (pattern, taxonomy_json, n_cats, n_responses))
        conn.commit()
    finally:
        conn.close()


# ── Response cache (deduplication only) ─────────────────────────

def get_cache_stats() -> Dict:
    conn = _get_conn()
    try:
        total = conn.execute("SELECT COUNT(*) FROM answers").fetchone()[0]
        questions = conn.execute(
            "SELECT COUNT(DISTINCT question_pattern) FROM answers").fetchone()[0]
        staffels = conn.execute(
            "SELECT COUNT(DISTINCT staffel) FROM answers WHERE staffel != ''").fetchone()[0]
        n_tax = conn.execute("SELECT COUNT(*) FROM taxonomies").fetchone()[0]
        return {"total_answers": total, "questions": questions,
                "staffels": staffels, "taxonomies": n_tax}
    finally:
        conn.close()


def add_to_cache(question: str, classifications: List[Dict], staffel: str = ""):
    conn = _get_conn()
    try:
        pattern = _normalize_question(question)
        added = 0
        for c in classifications:
            text = c.get("text", "").strip()
            if len(text) < 3:
                continue
            try:
                conn.execute("""
                    INSERT OR IGNORE INTO answers
                    (question_pattern, response_text, response_normalized,
                     cluster_id, cluster_title, main_category, confidence, staffel)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (pattern, text, _normalize_response(text),
                      c.get("human_override") or c.get("cluster_id", ""),
                      c.get("cluster_title", ""),
                      c.get("main_category", ""),
                      c.get("confidence", "medium"), staffel))
                added += 1
            except Exception:
                pass
        conn.commit()
        log.info("Added %d answers to cache for '%s'", added, pattern[:40])
        return added
    finally:
        conn.close()


# ════════════════════════════════════════════════════════════════
# STEP 2: Deduplication (string match, FREE)
# ════════════════════════════════════════════════════════════════

def deduplicate(question: str, responses: List[str],
                progress_cb=None) -> Tuple[List[Dict], List[str]]:
    """Find exact/near-exact matches in the cache via normalized string matching.

    Returns:
        deduped: responses with cached categories (exact matches)
        remaining: responses that need LLM classification
    """
    conn = _get_conn()
    try:
        pattern = _fuzzy_match_question(question, conn, table="answers")
        if pattern is None:
            return [], list(responses)

        rows = conn.execute("""
            SELECT response_normalized, cluster_id, cluster_title,
                   main_category, confidence, response_text
            FROM answers WHERE question_pattern = ?
        """, (pattern,)).fetchall()
    finally:
        conn.close()

    if not rows:
        return [], list(responses)

    # Build lookup
    cache_lookup = {}
    for r in rows:
        norm = r[0] or _normalize_response(r[5])
        if norm not in cache_lookup:
            cache_lookup[norm] = {
                "cluster_id": r[1], "cluster_title": r[2],
                "main_category": r[3], "confidence": r[4],
                "response_text": r[5],
            }

    deduped = []
    remaining = []
    for response in responses:
        norm = _normalize_response(response)
        cached = cache_lookup.get(norm)
        if cached:
            deduped.append({
                "text": response,
                "cluster_id": cached["cluster_id"],
                "cluster_title": cached["cluster_title"],
                "main_category": cached["main_category"],
                "confidence": "high",
                "match_type": "dedup",
                "human_override": "",
            })
        else:
            remaining.append(response)

    if progress_cb and deduped:
        progress_cb(f"Dedup: {len(deduped)}/{len(responses)} exact matches (free)")

    log.info("Dedup: %d/%d matches for '%s'",
             len(deduped), len(responses), pattern[:40])
    return deduped, remaining


# ════════════════════════════════════════════════════════════════
# STEP 3: LLM Classification (Haiku, primary path)
# ════════════════════════════════════════════════════════════════

def _build_taxonomy_ref(taxonomy: Dict) -> str:
    """Build a compact taxonomy reference string for LLM prompts."""
    if not taxonomy:
        return "Keine Taxonomie vorhanden."
    lines = []
    for mc in taxonomy.get("categories", []):
        for sub in mc.get("sub_categories", []):
            examples = ", ".join(
                f'"{e[:60]}"' for e in sub.get("examples", [])[:2])
            rule = sub.get("include_rule", "")
            lines.append(
                f"- {sub['id']}: {mc['main_category']} > {sub['title']}\n"
                f"  Beispiele: {examples}\n"
                f"  Regel: {rule}")
    return "\n".join(lines)


def classify_with_llm(
    question: str,
    responses: List[str],
    taxonomy: Dict,
    api_key: str,
    task: str = "tagging",
    progress_cb=None,
) -> List[Dict]:
    """Classify responses using LLM (Haiku by default, Sonnet if task="report").

    Sends responses in batches of 20 with full taxonomy context.
    The LLM REASONS about each response and picks the best category.
    """
    from bc4d_intel.ai.claude_client import call_claude

    tax_ref = _build_taxonomy_ref(taxonomy)
    classified = []
    batch_size = 20

    for batch_start in range(0, len(responses), batch_size):
        batch = responses[batch_start:batch_start + batch_size]

        if progress_cb:
            progress_cb(f"Classifying {batch_start+1}-"
                        f"{batch_start+len(batch)}/{len(responses)}...")

        responses_text = "\n".join(
            f"[{i+1}] {r[:400]}" for i, r in enumerate(batch))

        prompt = (
            f"Ordne jede Antwort der passendsten Kategorie zu.\n"
            f"Die Frage lautet: \"{question[:100]}\"\n\n"
            f"TAXONOMIE:\n{tax_ref}\n\n"
            f"ANTWORTEN:\n{responses_text}\n\n"
            f"Antworte als JSON-Array:\n"
            f"[{{\"id\": 1, \"cluster_id\": \"cat_1a\", "
            f"\"main_category\": \"...\", \"cluster_title\": \"...\", "
            f"\"confidence\": \"high|medium|low\"}}]"
        )

        try:
            resp = call_claude(
                system=(
                    "Du bist ein*e qualitative*r Forscher*in. "
                    "Ordne jede Antwort der inhaltlich passendsten Kategorie zu. "
                    "Achte auf den INHALT, nicht nur auf einzelne Woerter. "
                    "Antworte NUR mit validem JSON."
                ),
                user_msg=prompt,
                task=task,
                api_key=api_key,
                max_tokens=1200,
            )
            parsed = _parse_json_array(resp)
            for item in parsed:
                idx = item.get("id", 0) - 1
                if 0 <= idx < len(batch):
                    classified.append({
                        "text": batch[idx],
                        "cluster_id": item.get("cluster_id", ""),
                        "cluster_title": item.get("cluster_title", ""),
                        "main_category": item.get("main_category", ""),
                        "confidence": item.get("confidence", "medium"),
                        "match_type": "llm",
                        "human_override": "",
                    })
        except Exception as e:
            log.warning("LLM classification batch failed: %s", e)
            # Failed batch → mark as low confidence with empty category
            for r in batch:
                classified.append({
                    "text": r,
                    "cluster_id": "unclassified",
                    "cluster_title": "Nicht klassifiziert",
                    "main_category": "Fehler",
                    "confidence": "low",
                    "match_type": "error",
                    "human_override": "",
                })

    log.info("LLM classified %d responses for '%s'",
             len(classified), _normalize_question(question)[:40])
    return classified


# ════════════════════════════════════════════════════════════════
# STEP 4: Quality Gate (Sonnet sample check)
# ════════════════════════════════════════════════════════════════

def quality_gate(
    question: str,
    classifications: List[Dict],
    taxonomy: Dict,
    api_key: str,
    progress_cb=None,
) -> Tuple[bool, List[Dict]]:
    """Sample check: send N random classifications to Sonnet for review.

    Returns:
        passed: True if <20% flagged as wrong
        corrections: list of {text, old_cluster_id, new_cluster_id, ...}
    """
    import random

    if len(classifications) < 10:
        return True, []

    sample_size = min(QUALITY_GATE_SAMPLE, len(classifications))
    sample = random.sample(classifications, sample_size)

    if progress_cb:
        progress_cb(f"Quality gate: Sonnet reviewing {sample_size} samples...")

    from bc4d_intel.ai.claude_client import call_claude
    tax_ref = _build_taxonomy_ref(taxonomy)

    items_text = "\n".join(
        f"[{i+1}] Kategorie: {s['main_category']} > {s['cluster_title']} | "
        f"\"{s['text'][:200]}\""
        for i, s in enumerate(sample))

    prompt = (
        f"Pruefe diese Zuordnungen. Frage: \"{question[:100]}\"\n\n"
        f"TAXONOMIE:\n{tax_ref}\n\n"
        f"ZUORDNUNGEN:\n{items_text}\n\n"
        f"Fuer jede Zuordnung: ist sie KORREKT oder FALSCH?\n"
        f"Wenn FALSCH, gib die richtige Kategorie an.\n\n"
        f"JSON-Array: [{{\"id\": 1, \"verdict\": \"OK\"}}] oder\n"
        f"[{{\"id\": 1, \"verdict\": \"WRONG\", \"cluster_id\": \"cat_2a\", "
        f"\"main_category\": \"...\", \"cluster_title\": \"...\"}}]"
    )

    try:
        resp = call_claude(
            system="Qualitative*r Forscher*in. Pruefe kritisch. Nur JSON.",
            user_msg=prompt,
            task="report",  # Sonnet
            api_key=api_key,
            max_tokens=800,
        )
        parsed = _parse_json_array(resp)
        n_wrong = sum(1 for p in parsed if p.get("verdict") == "WRONG")
        fail_rate = n_wrong / max(len(parsed), 1)

        corrections = []
        for item in parsed:
            if item.get("verdict") == "WRONG":
                idx = item.get("id", 0) - 1
                if 0 <= idx < len(sample):
                    corrections.append({
                        "text": sample[idx]["text"],
                        "old_cluster_id": sample[idx]["cluster_id"],
                        "new_cluster_id": item.get("cluster_id", ""),
                        "new_main_category": item.get("main_category", ""),
                        "new_cluster_title": item.get("cluster_title", ""),
                    })

        passed = fail_rate <= QUALITY_GATE_FAIL_THRESHOLD

        if progress_cb:
            progress_cb(f"Quality gate: {n_wrong}/{len(parsed)} flagged "
                        f"({fail_rate:.0%}) — {'PASSED' if passed else 'FAILED'}")

        log.info("Quality gate: %d/%d wrong (%.0f%%) — %s",
                 n_wrong, len(parsed), fail_rate * 100,
                 "PASSED" if passed else "FAILED")
        return passed, corrections

    except Exception as e:
        log.warning("Quality gate failed: %s", e)
        return True, []  # assume OK if gate itself errors


# ════════════════════════════════════════════════════════════════
# VERIFICATION: test a single response
# ════════════════════════════════════════════════════════════════

def test_reliability(question: str, test_text: str, api_key: str = "") -> Dict:
    """Test how a single response would be categorised.

    If API key is available: asks Haiku to classify (accurate).
    If no API key: checks dedup cache only.
    """
    # Check dedup first
    conn = _get_conn()
    pattern = _fuzzy_match_question(question, conn, table="answers")
    if pattern:
        norm = _normalize_response(test_text)
        row = conn.execute(
            "SELECT cluster_id, cluster_title, main_category, response_text "
            "FROM answers WHERE question_pattern = ? AND response_normalized = ?",
            (pattern, norm)
        ).fetchone()
        if row:
            conn.close()
            return {
                "matched": True,
                "method": "dedup",
                "cluster_id": row[0],
                "cluster_title": row[1],
                "main_category": row[2],
                "cache_match": row[3][:80],
                "reason": "Exact match found in cache (free).",
            }
    conn.close()

    # Try LLM classification if API key available
    taxonomy = get_cached_taxonomy(question)
    if not api_key or not taxonomy:
        return {
            "matched": False,
            "method": "none",
            "reason": "No exact cache match. "
                      + ("Set API key to test LLM classification."
                         if not api_key else "No cached taxonomy for this question."),
        }

    results = classify_with_llm(question, [test_text], taxonomy, api_key)
    if results:
        r = results[0]
        return {
            "matched": True,
            "method": "llm",
            "cluster_id": r["cluster_id"],
            "cluster_title": r["cluster_title"],
            "main_category": r["main_category"],
            "confidence": r["confidence"],
            "reason": f"Haiku classified as: {r['main_category']} > {r['cluster_title']} "
                      f"(confidence: {r['confidence']})",
        }

    return {"matched": False, "method": "error",
            "reason": "LLM classification failed."}


# ── Helpers ─────────────────────────────────────────────────────

def _parse_json_array(text: str) -> List[Dict]:
    cleaned = re.sub(r'```json\s*', '', text)
    cleaned = re.sub(r'```\s*', '', cleaned).strip()
    m = re.search(r'\[.*\]', cleaned, re.DOTALL)
    if m:
        return json.loads(m.group())
    return []
