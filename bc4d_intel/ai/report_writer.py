"""Report section generation via Sonnet.

Improvement #1: build_data_context now includes full statistical results
(means, SDs, CIs, p-values, effect sizes) so Sonnet can write data-rich sections.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Optional
from collections import Counter

from bc4d_intel.ai.claude_client import call_claude
from bc4d_intel.ai.prompts import REPORT_SYSTEM, REPORT_SECTIONS

log = logging.getLogger("bc4d_intel.ai.report")


def generate_section(
    section_name: str,
    data_context: str,
    api_key: str,
    stream_cb=None,
) -> str:
    """Generate one report section via Sonnet."""
    section_prompt = REPORT_SECTIONS.get(section_name, "")
    if not section_prompt:
        return f"*Unbekannter Abschnitt: {section_name}*"

    prompt = f"""{section_prompt}

DATENKONTEXT:
{data_context}

Schreibe auf Deutsch. Verwende klare Ueberschriften und konkrete Zahlen."""

    try:
        text = call_claude(
            system=REPORT_SYSTEM,
            user_msg=prompt,
            task="report",
            api_key=api_key,
            max_tokens=2500,
            stream_cb=stream_cb,
        )
        return text
    except Exception as e:
        log.warning("Section generation failed for %s: %s", section_name, e)
        return f"*Fehler bei {section_name}: {e}*"


def build_data_context(app_state, match_result=None, tagged_data=None,
                       pre_roles=None, post_roles=None,
                       pre_df=None, post_df=None) -> str:
    """Build a comprehensive data context for the report writer.

    Includes actual statistics (means, CIs, effect sizes, p-values)
    so Sonnet can write data-rich sections.
    """
    parts = []

    # ── Basic info ──
    parts.append("=== STAFFEL-INFORMATIONEN ===")
    parts.append(f"Staffel: {app_state.staffel_name or '13'}")
    parts.append(f"Vorabfragebogen (Pre): {app_state.n_pre} Befragte")
    parts.append(f"Nachbefragung (Post): {app_state.n_post} Befragte")
    parts.append(f"Gematchte Paare: {app_state.matched_pairs}")
    if app_state.n_post > 0:
        match_rate = round(app_state.matched_pairs / app_state.n_post * 100, 1)
        parts.append(f"Match-Rate: {match_rate}% der Post-Befragten")
    parts.append(f"Nur Pre (Dropout): {app_state.unmatched_pre}")
    parts.append(f"Nur Post (ohne Pre): {app_state.unmatched_post}")

    # ── Quantitative results ──
    if pre_df is not None and pre_roles:
        from bc4d_intel.core.stats_engine import analyze_all_likert, cronbachs_alpha

        parts.append("\n=== QUANTITATIVE ERGEBNISSE: VORABFRAGEBOGEN ===")
        pre_items = analyze_all_likert(pre_df, pre_roles)
        likert_cols = [item["column"] for item in pre_items if item["role"] == "likert"]
        alpha = cronbachs_alpha(pre_df, likert_cols)
        if alpha:
            parts.append(f"Cronbachs Alpha (Likert-Skala): {alpha}")

        for item in pre_items:
            s = item["stats"]
            if s["mean"] is not None:
                parts.append(
                    f"\nItem: {item['label']}"
                    f"\n  M={s['mean']}, SD={s['sd']}, n={s['n']}"
                    f"\n  95%-KI: [{s['ci_lower']}, {s['ci_upper']}]"
                    f"\n  Zustimmung (4-5): {s['pct_agree']}%, Ablehnung (1-2): {s['pct_disagree']}%"
                )

    if post_df is not None and post_roles:
        from bc4d_intel.core.stats_engine import analyze_all_likert, practical_transfer_stats

        parts.append("\n=== QUANTITATIVE ERGEBNISSE: NACHBEFRAGUNG ===")
        post_items = analyze_all_likert(post_df, post_roles)
        for item in post_items:
            s = item["stats"]
            if s["mean"] is not None:
                parts.append(
                    f"\nItem: {item['label']}"
                    f"\n  M={s['mean']}, SD={s['sd']}, n={s['n']}"
                    f"\n  Zustimmung (4-5): {s['pct_agree']}%"
                )

        # Practical transfer
        transfer = practical_transfer_stats(post_df, post_roles)
        if transfer:
            parts.append("\n--- Praktischer Transfer ---")
            for t in transfer:
                parts.append(f"  {t['label']}: {t['pct_applied']}% angewendet (M={t['mean']})")

    # ── Matched panel comparison ──
    if match_result and len(match_result.get("matched", [])) > 0 and pre_roles and post_roles:
        from bc4d_intel.core.stats_engine import analyze_matched_likert

        parts.append("\n=== PRE/POST-VERGLEICH (GEMATCHTES PANEL) ===")
        comparisons = analyze_matched_likert(
            match_result["matched"], pre_roles, post_roles)

        for c in comparisons:
            comp = c.get("comparison", {})
            if "error" in comp:
                continue
            sig = "***" if comp.get("significant") else "n.s."
            parts.append(
                f"\nItem: {c['label']}"
                f"\n  Pre: M={comp['pre_mean']}, Post: M={comp['post_mean']}"
                f"\n  Differenz: {'+' if comp['mean_change'] > 0 else ''}{comp['mean_change']}"
                f" [{comp['ci_lower']}, {comp['ci_upper']}]"
                f"\n  Cohen's d = {comp['cohens_d']} ({comp['effect_label']}), "
                f"p = {comp.get('p_corrected', 'N/A')} {sig}"
                f"\n  Verbessert: {comp['improved_pct']}%, Verschlechtert: {comp['declined_pct']}%"
            )

    # ── Qualitative findings ──
    if tagged_data:
        parts.append("\n=== QUALITATIVE ERGEBNISSE ===")
        for question, tags in tagged_data.items():
            parts.append(f"\nFrage: {question}")
            tag_counts = Counter(t.get("human_override") or t["tag"] for t in tags)
            total = len(tags)
            parts.append(f"  Antworten gesamt: {total}")
            for tag, count in tag_counts.most_common():
                pct = round(count / total * 100, 1)
                parts.append(f"  {tag}: {count} ({pct}%)")
            # Top 5 representative quotes
            for t in tags[:5]:
                final_tag = t.get("human_override") or t["tag"]
                parts.append(f"  Zitat ({final_tag}): \"{t['text'][:120]}\"")

    return "\n".join(parts)
