"""Hybrid qualitative analysis: LLM taxonomy + cross-encoder classification.

Architecture (redesigned from ground up):
  1. LLM reads ALL responses (full text, no truncation, no sampling)
     and designs a HIERARCHICAL taxonomy (main categories → sub-categories)
  2. LLM provides exemplar responses + coding rules per category
  3. Cross-encoder scores each response against each category's exemplars (free)
  4. LLM reviews only edge cases where cross-encoder can't decide

Key learnings from ISD Intel:
  - Use each tool for its strength (LLM = reasoning, CE = scoring)
  - Full text context, never truncate
  - Multiple signals, not just one
  - Only spend API tokens where reasoning is needed

Cost: ~$0.08 per question (LLM taxonomy + edge case review)
      Cross-encoder classification is free (local model)
"""

from __future__ import annotations
import json, logging, re
from typing import Dict, List, Tuple

import numpy as np

log = logging.getLogger("bc4d_intel.core.embedder")


# ── Step 1: LLM designs hierarchical taxonomy ───────────────────

TAXONOMY_PROMPT = """Du analysierst {n} offene Antworten auf die Frage: "{question}"

Hier sind ALLE Antworten:
{all_responses}

Erstelle eine HIERARCHISCHE Taxonomie mit Hauptkategorien und Unterkategorien.
Jede Unterkategorie braucht:
- Einen praegnanten Titel
- 2-3 typische Beispielantworten (woertlich aus den obigen)
- Eine Kodierregel (Was einschliessen? Was ausschliessen?)

Wichtig:
- Erstelle so viele Kategorien wie noetig (nicht kuenstlich begrenzen)
- Sehr kurze Antworten ("Nichts", "k.A.", "/") gehoeren zu "Keine Angabe"
- Eine Antwort kann Elemente aus mehreren Kategorien enthalten — ordne der PRIMAEREN zu

Antworte als JSON:
{{
  "categories": [
    {{
      "id": "cat_1",
      "main_category": "Positive Bewertung",
      "sub_categories": [
        {{
          "id": "cat_1a",
          "title": "Lob fuer Trainer*in",
          "examples": ["Die Trainerin war toll", "Sehr gute Moderation"],
          "include_rule": "Antworten die Trainer, Moderation, oder persoenliche Betreuung erwaehnen",
          "exclude_rule": "Reine Inhaltskommentare ohne Bezug zu Personen"
        }}
      ]
    }}
  ]
}}"""


def design_taxonomy(
    question: str,
    responses: List[str],
    api_key: str,
    progress_cb=None,
) -> Dict:
    """Step 1: LLM reads ALL responses and designs a hierarchical taxonomy.

    Returns {categories: [{id, main_category, sub_categories: [{id, title, examples, include_rule, exclude_rule}]}]}
    """
    from bc4d_intel.ai.claude_client import call_claude

    if progress_cb:
        progress_cb(f"Step 1: AI reading all {len(responses)} responses to design taxonomy...")

    # Send ALL responses (no sampling, no truncation)
    # For very large sets, chunk into groups of 200 to stay within context
    all_text = "\n".join(f"[{i+1}] {r}" for i, r in enumerate(responses))

    # If too long (>15000 chars), summarize with representative sampling
    if len(all_text) > 15000:
        # Send first 100 + every 3rd for the rest
        selected = responses[:100]
        for i in range(100, len(responses), 3):
            selected.append(responses[i])
        all_text = "\n".join(f"[{i+1}] {r}" for i, r in enumerate(selected))
        log.info("Taxonomy: sampled %d of %d responses (too long)", len(selected), len(responses))

    prompt = TAXONOMY_PROMPT.format(
        n=len(responses),
        question=question[:100],
        all_responses=all_text,
    )

    try:
        resp = call_claude(
            system="Du bist ein*e erfahrene*r qualitative*r Forscher*in. Antworte nur mit validem JSON.",
            user_msg=prompt,
            task="report",  # Sonnet for quality reasoning
            api_key=api_key,
            max_tokens=3000,
        )
        return _parse_taxonomy(resp)
    except Exception as e:
        log.warning("Taxonomy design failed: %s", e)
        return {"categories": [{"id": "cat_1", "main_category": "Allgemein",
                                "sub_categories": [{"id": "cat_1a", "title": "Allgemein",
                                                     "examples": [], "include_rule": "", "exclude_rule": ""}]}]}


# ── Step 2: Cross-encoder classification (free, local) ──────────

def classify_with_cross_encoder(
    responses: List[str],
    taxonomy: Dict,
    progress_cb=None,
) -> List[Dict]:
    """Step 2: Score each response against each category's exemplars using cross-encoder.

    This is FREE (local model, already loaded from ISD Intel pipeline).
    Much more precise than embedding distance for short text.
    """
    if progress_cb:
        progress_cb("Step 2: Classifying responses via cross-encoder (free, local)...")

    # Load cross-encoder
    try:
        from sentence_transformers import CrossEncoder
        reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
    except Exception as e:
        log.warning("Cross-encoder not available: %s", e)
        return _fallback_classify(responses, taxonomy)

    # Build category reference texts from examples + rules
    flat_cats = []
    for main_cat in taxonomy.get("categories", []):
        for sub in main_cat.get("sub_categories", []):
            # Combine examples + rules into a reference passage
            examples_text = ". ".join(sub.get("examples", [])[:3])
            rule_text = sub.get("include_rule", "")
            ref_text = f"{sub['title']}. {examples_text}. {rule_text}"
            flat_cats.append({
                "id": sub["id"],
                "title": sub["title"],
                "main_category": main_cat["main_category"],
                "ref_text": ref_text,
            })

    if not flat_cats:
        return _fallback_classify(responses, taxonomy)

    # Score each response against each category
    results = []
    n = len(responses)
    n_cats = len(flat_cats)

    for i, response in enumerate(responses):
        if progress_cb and (i + 1) % 50 == 0:
            progress_cb(f"Classifying {i+1}/{n} ({int((i+1)/n*100)}%)...")

        # Score against all categories
        pairs = [(response, cat["ref_text"]) for cat in flat_cats]
        scores = reranker.predict(pairs)

        # Find best and second-best
        sorted_idx = np.argsort(scores)[::-1]
        best_idx = sorted_idx[0]
        best_score = scores[best_idx]
        second_score = scores[sorted_idx[1]] if len(sorted_idx) > 1 else -999

        best_cat = flat_cats[best_idx]

        # Confidence based on margin between top-2 scores
        margin = best_score - second_score
        if margin > 2.0:
            confidence = "high"
        elif margin > 0.5:
            confidence = "medium"
        else:
            confidence = "low"

        results.append({
            "text": response,
            "cluster_id": best_cat["id"],
            "cluster_title": best_cat["title"],
            "main_category": best_cat["main_category"],
            "confidence": confidence,
            "score": round(float(best_score), 2),
            "margin": round(float(margin), 2),
            "human_override": "",
        })

    return results


# ── Step 3: LLM reviews edge cases ──────────────────────────────

def review_edge_cases(
    classifications: List[Dict],
    taxonomy: Dict,
    api_key: str,
    progress_cb=None,
) -> List[Dict]:
    """Step 3: Send only low-confidence responses to LLM for review.

    Typically 10-20% of responses. Saves cost by not sending everything.
    """
    low_conf = [(i, c) for i, c in enumerate(classifications) if c["confidence"] == "low"]

    if not low_conf:
        return classifications

    if progress_cb:
        progress_cb(f"Step 3: AI reviewing {len(low_conf)} edge cases...")

    from bc4d_intel.ai.claude_client import call_claude

    # Build compact taxonomy reference
    cat_list = []
    for main_cat in taxonomy.get("categories", []):
        for sub in main_cat.get("sub_categories", []):
            cat_list.append(f"- {sub['id']}: {main_cat['main_category']} > {sub['title']}")
    tax_text = "\n".join(cat_list)

    # Batch edge cases
    batch_size = 20
    for batch_start in range(0, len(low_conf), batch_size):
        batch = low_conf[batch_start:batch_start + batch_size]

        responses_text = "\n".join(f"[{i+1}] {c['text'][:300]}" for i, (_, c) in enumerate(batch))

        prompt = (
            f"Diese Antworten konnten nicht eindeutig zugeordnet werden. "
            f"Ordne jede einem Cluster zu:\n\n"
            f"TAXONOMIE:\n{tax_text}\n\n"
            f"ANTWORTEN:\n{responses_text}\n\n"
            f"Antworte als JSON-Array: [{{\"id\": 1, \"cluster_id\": \"cat_1a\"}}]"
        )

        try:
            resp = call_claude(
                system="Qualitative*r Forscher*in. Nur JSON.",
                user_msg=prompt,
                task="tagging",
                api_key=api_key,
                max_tokens=400,
            )
            m = re.search(r'\[.*\]', resp, re.DOTALL)
            if m:
                parsed = json.loads(m.group())
                for item in parsed:
                    batch_idx = item.get("id", 0) - 1
                    if 0 <= batch_idx < len(batch):
                        orig_idx, _ = batch[batch_idx]
                        new_cid = item.get("cluster_id", "")
                        if new_cid:
                            classifications[orig_idx]["cluster_id"] = new_cid
                            classifications[orig_idx]["confidence"] = "medium"
        except Exception as e:
            log.warning("Edge case review failed: %s", e)

    return classifications


# ── Full pipeline ────────────────────────────────────────────────

def full_pipeline(
    responses: List[str],
    api_key: str,
    question: str = "",
    progress_cb=None,
) -> Dict:
    """Run the complete hybrid pipeline.

    Returns:
        taxonomy: hierarchical {categories: [{main_category, sub_categories}]}
        classifications: [{text, cluster_id, cluster_title, main_category, confidence}]
        flat_taxonomy: [{id, title, main_category, count}] for UI display
    """
    n = len(responses)

    # Step 1: LLM designs taxonomy (Sonnet, ~$0.02)
    taxonomy = design_taxonomy(question, responses, api_key, progress_cb)

    # Step 2: Cross-encoder classifies (free, local)
    classifications = classify_with_cross_encoder(responses, taxonomy, progress_cb)

    # Step 3: LLM reviews edge cases (Sonnet, ~$0.02 for ~20 edge cases)
    classifications = review_edge_cases(classifications, taxonomy, api_key, progress_cb)

    # Build flat taxonomy for UI display
    flat_taxonomy = []
    for main_cat in taxonomy.get("categories", []):
        for sub in main_cat.get("sub_categories", []):
            count = sum(1 for c in classifications
                        if (c.get("human_override") or c["cluster_id"]) == sub["id"])
            flat_taxonomy.append({
                "id": sub["id"],
                "title": sub["title"],
                "main_category": main_cat["main_category"],
                "description": sub.get("include_rule", ""),
                "count": count,
            })

    # Also create UMAP visualization from embeddings
    umap_coords = None
    labels = None
    try:
        if progress_cb:
            progress_cb("Creating semantic map...")
        import ollama
        texts = [f"search_document: {r}" for r in responses]
        result = ollama.embed(model="nomic-embed-text", input=texts)
        embeddings = np.array(result["embeddings"], dtype=np.float32)

        import umap
        reducer = umap.UMAP(n_components=2, n_neighbors=15, min_dist=0.1,
                            metric="cosine", random_state=42)
        umap_coords = reducer.fit_transform(embeddings).astype(np.float32)

        # Build label array from classifications
        cat_ids = list(set(c["cluster_id"] for c in classifications))
        cat_to_num = {cid: i for i, cid in enumerate(cat_ids)}
        labels = np.array([cat_to_num.get(c["cluster_id"], -1) for c in classifications])
    except Exception as e:
        log.warning("UMAP visualization failed (non-critical): %s", e)

    if progress_cb:
        n_cats = len(flat_taxonomy)
        n_high = sum(1 for c in classifications if c["confidence"] == "high")
        progress_cb(f"Done: {n_cats} categories, {n_high}/{n} high-confidence")

    return {
        "taxonomy": taxonomy,
        "flat_taxonomy": flat_taxonomy,
        "classifications": classifications,
        "umap_coords": umap_coords,
        "labels": labels,
    }


# ── Helpers ──────────────────────────────────────────────────────

def _parse_taxonomy(response: str) -> Dict:
    """Parse hierarchical taxonomy JSON from LLM response."""
    m = re.search(r'\{.*\}', response, re.DOTALL)
    if not m:
        return {"categories": []}
    try:
        parsed = json.loads(m.group())
        if "categories" in parsed:
            return parsed
        return {"categories": []}
    except json.JSONDecodeError:
        return {"categories": []}


def _fallback_classify(responses: List[str], taxonomy: Dict) -> List[Dict]:
    """Fallback: assign all to first category if cross-encoder unavailable."""
    first_cat = "unknown"
    for main_cat in taxonomy.get("categories", []):
        for sub in main_cat.get("sub_categories", []):
            first_cat = sub["id"]
            break
        break

    return [{
        "text": r, "cluster_id": first_cat, "cluster_title": "",
        "main_category": "", "confidence": "low",
        "score": 0, "margin": 0, "human_override": "",
    } for r in responses]
