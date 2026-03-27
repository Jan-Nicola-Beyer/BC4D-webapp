"""Two-pass qualitative analysis: taxonomy induction + classification.

Pass 1 — INDUCE: AI reads all responses, discovers emergent thematic clusters.
Pass 2 — CLASSIFY: AI assigns each response to a cluster.

The user validates both:
  - The taxonomy itself (rename, merge, split, add clusters)
  - Individual cluster assignments (accept, reassign)
"""

from __future__ import annotations
import json, logging, re
from typing import Dict, List

from bc4d_intel.ai.claude_client import call_claude

log = logging.getLogger("bc4d_intel.ai.tagger")

# ── Pass 1: Taxonomy induction ───────────────────────────────────

INDUCE_SYSTEM = """Du bist ein*e qualitative*r Forschungsassistent*in fuer das BC4D-Programm.

Du analysierst offene Antworten aus Evaluierungsbefragungen und entwickelst eine
datengestuetzte Taxonomie (Cluster-System) fuer die thematische Gruppierung."""

INDUCE_PROMPT = """Lies alle folgenden Antworten auf die Frage: "{question}"

Entwickle 4-8 thematische Cluster, die die Antworten sinnvoll gruppieren.
Jeder Cluster soll:
- Einen praegnanten deutschen Titel haben (3-6 Woerter)
- Eine kurze Beschreibung (1 Satz)
- Mindestens 3 Antworten abdecken

Orientiere dich an den tatsaechlichen Inhalten, nicht an vordefinierten Kategorien.

ANTWORTEN:
{responses}

Antworte mit einem JSON-Array:
[
  {{"id": "cluster_1", "title": "Praxisnahe Inhalte", "description": "Teilnehmende schaetzten den Praxisbezug der Schulung."}},
  {{"id": "cluster_2", "title": "Zeitmangel und Terminprobleme", "description": "Schwierigkeiten bei der zeitlichen Einbindung in den Arbeitsalltag."}}
]

NUR das JSON-Array zurueckgeben."""

# ── Pass 2: Classification ───────────────────────────────────────

CLASSIFY_SYSTEM = """Du bist ein*e qualitative*r Forschungsassistent*in. Du ordnest Antworten
einer vorgegebenen Taxonomie zu. Jede Antwort gehoert zu genau EINEM Cluster."""

CLASSIFY_PROMPT = """Ordne jede Antwort einem der folgenden Cluster zu:

TAXONOMIE:
{taxonomy}

ANTWORTEN:
{responses}

Antworte mit einem JSON-Array:
[{{"response_id": 1, "cluster_id": "cluster_1", "confidence": "high"}}]

Konfidenz:
- high: Antwort passt eindeutig zu einem Cluster
- medium: Antwort koennte zu 2 Clustern passen
- low: Antwort ist mehrdeutig oder passt schlecht

NUR das JSON-Array zurueckgeben."""

BATCH_SIZE = 25


def induce_taxonomy(
    question: str,
    responses: List[str],
    api_key: str,
    progress_cb=None,
) -> List[Dict]:
    """Pass 1: Read all responses and discover emergent thematic clusters.

    Returns list of {id, title, description} cluster dicts.
    """
    if progress_cb:
        progress_cb("Reading all responses to discover themes...")

    # Send a representative sample (max 80 responses for context window)
    sample = responses[:80] if len(responses) > 80 else responses
    formatted = "\n".join(f"- {r[:200]}" for r in sample)

    prompt = INDUCE_PROMPT.format(
        question=question[:100],
        responses=formatted,
    )

    try:
        response = call_claude(
            system=INDUCE_SYSTEM,
            user_msg=prompt,
            task="report",  # Sonnet for quality reasoning
            api_key=api_key,
            max_tokens=1500,
        )
        return _parse_taxonomy(response)
    except Exception as e:
        log.warning("Taxonomy induction failed: %s", e)
        return [{"id": "cluster_1", "title": "Allgemein", "description": f"Fehler: {e}"}]


def classify_responses(
    responses: List[str],
    taxonomy: List[Dict],
    api_key: str,
    progress_cb=None,
) -> List[Dict]:
    """Pass 2: Assign each response to a cluster from the taxonomy.

    Returns list of {text, cluster_id, confidence} dicts.
    """
    # Format taxonomy for prompt
    tax_text = "\n".join(
        f"- {c['id']}: {c['title']} — {c.get('description', '')}"
        for c in taxonomy
    )

    results = []
    total = len(responses)
    n_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(n_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, total)
        batch = responses[start:end]

        if progress_cb:
            pct = int((batch_idx + 1) / n_batches * 100)
            progress_cb(f"Classifying batch {batch_idx + 1}/{n_batches} ({pct}%)")

        formatted = "\n".join(f"[{i + 1}] {r[:250]}" for i, r in enumerate(batch))
        prompt = CLASSIFY_PROMPT.format(
            taxonomy=tax_text,
            responses=formatted,
        )

        try:
            response = call_claude(
                system=CLASSIFY_SYSTEM,
                user_msg=prompt,
                task="tagging",  # Can use cheaper model for classification
                api_key=api_key,
                max_tokens=600,
            )
            parsed = _parse_classifications(response, batch)

            for i, text in enumerate(batch):
                info = parsed.get(i + 1, {})
                results.append({
                    "text": text,
                    "cluster_id": info.get("cluster_id", taxonomy[0]["id"] if taxonomy else "unknown"),
                    "confidence": info.get("confidence", "low"),
                    "human_override": "",
                })

        except Exception as e:
            log.warning("Classification batch %d failed: %s", batch_idx, e)
            for text in batch:
                results.append({
                    "text": text,
                    "cluster_id": "unclassified",
                    "confidence": "low",
                    "human_override": "",
                })

    return results


def _parse_taxonomy(response: str) -> List[Dict]:
    """Parse taxonomy JSON from LLM response."""
    m = re.search(r'\[.*\]', response, re.DOTALL)
    if not m:
        return []
    try:
        parsed = json.loads(m.group())
        result = []
        for item in parsed:
            if isinstance(item, dict) and item.get("title"):
                result.append({
                    "id": item.get("id", f"cluster_{len(result) + 1}"),
                    "title": item.get("title", ""),
                    "description": item.get("description", ""),
                })
        return result
    except json.JSONDecodeError:
        return []


def _parse_classifications(response: str, batch: List[str]) -> Dict[int, Dict]:
    """Parse classification JSON into {response_id: {cluster_id, confidence}}."""
    m = re.search(r'\[.*\]', response, re.DOTALL)
    if not m:
        return {}
    try:
        parsed = json.loads(m.group())
        result = {}
        for item in parsed:
            if isinstance(item, dict):
                result[item.get("response_id", 0)] = {
                    "cluster_id": item.get("cluster_id", ""),
                    "confidence": item.get("confidence", "low"),
                }
        return result
    except json.JSONDecodeError:
        return {}
