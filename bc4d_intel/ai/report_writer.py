"""Report section generation via Sonnet.

Generates 7 report sections based on analysis data.
Each section is generated independently and can be re-generated.
Supports streaming to UI for real-time feedback.
Cost: ~$0.15-0.40 per staffel (7 sections).
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional

from bc4d_intel.ai.claude_client import call_claude
from bc4d_intel.ai.prompts import REPORT_SYSTEM, REPORT_SECTIONS

log = logging.getLogger("bc4d_intel.ai.report")


def generate_section(
    section_name: str,
    data_context: str,
    api_key: str,
    stream_cb=None,
) -> str:
    """Generate one report section via Sonnet.

    Args:
        section_name: key from REPORT_SECTIONS
        data_context: formatted string with all relevant data/stats
        api_key: Anthropic API key
        stream_cb: optional streaming callback

    Returns: generated text (markdown)
    """
    section_prompt = REPORT_SECTIONS.get(section_name, "")
    if not section_prompt:
        return f"*Unknown section: {section_name}*"

    prompt = f"""{section_prompt}

DATA CONTEXT:
{data_context}

Write in German. Use clear headings, bullet points, and specific numbers.
Be balanced — note both strengths and areas for improvement."""

    try:
        text = call_claude(
            system=REPORT_SYSTEM,
            user_msg=prompt,
            task="report",
            api_key=api_key,
            max_tokens=2000,
            stream_cb=stream_cb,
        )
        return text
    except Exception as e:
        log.warning("Section generation failed for %s: %s", section_name, e)
        return f"*Error generating {section_name}: {e}*"


def build_data_context(app_state, match_result=None, tagged_data=None) -> str:
    """Build a data context string for the report writer.

    Summarizes all available analysis data so the LLM can write about it.
    """
    parts = []

    # Basic info
    parts.append(f"Staffel: {app_state.staffel_name or '13'}")
    parts.append(f"Pre-survey: {app_state.n_pre} respondents")
    parts.append(f"Post-survey: {app_state.n_post} respondents")
    parts.append(f"Matched pairs: {app_state.matched_pairs}")

    # Stats from matched panel
    if match_result and "matched" in match_result:
        matched_df = match_result["matched"]
        if len(matched_df) > 0:
            parts.append(f"\nMatched panel: {len(matched_df)} paired respondents")
            parts.append(f"Match rate: {app_state.matched_pairs}/{app_state.n_post} "
                         f"({round(app_state.matched_pairs / max(app_state.n_post, 1) * 100, 1)}%)")

    # Likert analysis results
    if match_result:
        from bc4d_intel.core.stats_engine import analyze_all_likert, analyze_matched_likert
        from bc4d_intel.screens.screen_import import ImportScreen

        # We can't access import_screen directly, so summarize from app_state
        parts.append("\n--- QUANTITATIVE RESULTS ---")
        parts.append(f"Pre-survey columns: {len(app_state.pre_columns)} detected")
        parts.append(f"Post-survey columns: {len(app_state.post_columns)} detected")
        parts.append(f"Likert items (pre): {sum(1 for r in app_state.pre_columns.values() if r == 'likert')}")
        parts.append(f"Likert items (post): {sum(1 for r in app_state.post_columns.values() if r == 'likert')}")
        parts.append(f"Free-text questions (post): {sum(1 for r in app_state.post_columns.values() if r == 'free_text')}")

    # Tagged responses summary
    if tagged_data:
        parts.append("\n--- QUALITATIVE FINDINGS ---")
        for question, tags in tagged_data.items():
            parts.append(f"\nQuestion: {question}")
            from collections import Counter
            tag_counts = Counter(t.get("human_override") or t["tag"] for t in tags)
            for tag, count in tag_counts.most_common():
                parts.append(f"  {tag}: {count}")
            # Include a few example responses
            for t in tags[:3]:
                parts.append(f"  Example: \"{t['text'][:100]}\" → {t.get('human_override') or t['tag']}")

    return "\n".join(parts)
