"""Batch free-text tagging via Haiku.

Processes free-text survey responses in batches of 20.
Returns [{text, tag, confidence, rationale}, ...] for each response.
Cost: ~$0.05-0.15 per staffel (~700 responses).
"""

from __future__ import annotations
import json, logging, re
from typing import Dict, List

from bc4d_intel.ai.claude_client import call_claude
from bc4d_intel.ai.prompts import TAGGING_SYSTEM, FREE_TEXT_TAGS

log = logging.getLogger("bc4d_intel.ai.tagger")

BATCH_SIZE = 20

TAG_PROMPT = """Tag each response below with exactly ONE tag from this list:
{tags}

For each response, return a JSON array with objects:
[{{"id": 1, "tag": "positive_feedback", "confidence": "high", "rationale": "..."}}]

RESPONSES:
{responses}

Return ONLY the JSON array."""


def tag_responses(
    responses: List[str],
    api_key: str,
    progress_cb=None,
) -> List[Dict]:
    """Tag a list of free-text responses via Haiku in batches.

    Args:
        responses: list of text strings to tag
        api_key: Anthropic API key
        progress_cb: optional callback(message) for progress

    Returns list of {text, tag, confidence, rationale, human_override} dicts
    """
    results = []
    total = len(responses)
    n_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(n_batches):
        start = batch_idx * BATCH_SIZE
        end = min(start + BATCH_SIZE, total)
        batch = responses[start:end]

        if progress_cb:
            progress_cb(f"Tagging batch {batch_idx + 1}/{n_batches} "
                        f"({start + 1}-{end} of {total})")

        # Format responses for the prompt
        formatted = "\n".join(f"[{i + 1}] {text[:300]}" for i, text in enumerate(batch))

        prompt = TAG_PROMPT.format(
            tags=", ".join(FREE_TEXT_TAGS),
            responses=formatted,
        )

        try:
            response = call_claude(
                system=TAGGING_SYSTEM,
                user_msg=prompt,
                task="tagging",
                api_key=api_key,
                max_tokens=500,
            )

            # Parse JSON array from response
            parsed = _parse_tags(response, batch)

            for i, text in enumerate(batch):
                tag_info = parsed.get(i + 1, {})
                results.append({
                    "text": text,
                    "tag": tag_info.get("tag", "other"),
                    "confidence": tag_info.get("confidence", "low"),
                    "rationale": tag_info.get("rationale", ""),
                    "human_override": "",  # empty until human reviews
                })

        except Exception as e:
            log.warning("Tagging batch %d failed: %s", batch_idx, e)
            # Fall back to "other" for failed batch
            for text in batch:
                results.append({
                    "text": text,
                    "tag": "other",
                    "confidence": "low",
                    "rationale": f"Tagging failed: {e}",
                    "human_override": "",
                })

    log.info("Tagged %d responses in %d batches", total, n_batches)
    return results


def _parse_tags(response: str, batch: List[str]) -> Dict[int, Dict]:
    """Parse JSON array from LLM response into {id: {tag, confidence, rationale}}."""
    m = re.search(r'\[.*\]', response, re.DOTALL)
    if not m:
        return {}
    try:
        parsed = json.loads(m.group())
        result = {}
        for item in parsed:
            if isinstance(item, dict):
                idx = item.get("id", 0)
                tag = item.get("tag", "other")
                if tag not in FREE_TEXT_TAGS:
                    tag = "other"
                result[idx] = {
                    "tag": tag,
                    "confidence": item.get("confidence", "low"),
                    "rationale": item.get("rationale", ""),
                }
        return result
    except json.JSONDecodeError:
        return {}
