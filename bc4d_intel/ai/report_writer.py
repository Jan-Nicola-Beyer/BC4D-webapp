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


# Which data context sections each report section needs.
# This avoids sending 6,000+ tokens when 1,000 would suffice.
_SECTION_DATA_NEEDS = {
    "executive_summary": ["STAFFEL", "QUANTITATIVE", "PRE/POST", "QUALITATIVE"],
    "method_sample":     ["STAFFEL"],
    "quantitative_results": ["QUANTITATIVE"],
    "qualitative_findings": ["QUALITATIVE"],
    "pre_post_comparison": ["PRE/POST"],
    "recommendations": ["QUANTITATIVE", "PRE/POST", "QUALITATIVE"],
    "appendix": ["QUANTITATIVE", "PRE/POST"],
}


def _filter_context(data_context: str, section_name: str) -> str:
    """Extract only the data sections relevant to this report section.

    Reduces token usage by ~60% per call (e.g. qualitative_findings
    doesn't need quantitative stats).
    """
    needs = _SECTION_DATA_NEEDS.get(section_name)
    if not needs:
        return data_context

    blocks = data_context.split("===")
    filtered = []
    for i in range(0, len(blocks) - 1, 2):
        header = blocks[i + 1].strip().split("\n")[0] if i + 1 < len(blocks) else ""
        content = blocks[i + 2] if i + 2 < len(blocks) else ""
        if any(need in header for need in needs):
            filtered.append(f"=== {header} ==={content}")

    # Always include staffel info (tiny, always useful)
    if "STAFFEL" not in needs:
        for i in range(0, len(blocks) - 1, 2):
            header = blocks[i + 1].strip().split("\n")[0] if i + 1 < len(blocks) else ""
            if "STAFFEL" in header:
                content = blocks[i + 2] if i + 2 < len(blocks) else ""
                filtered.insert(0, f"=== {header} ==={content}")
                break

    return "\n".join(filtered) if filtered else data_context


def generate_section(
    section_name: str,
    data_context: str,
    api_key: str,
    stream_cb=None,
    previous_sections: Optional[Dict[str, str]] = None,
) -> str:
    """Generate one report section via Sonnet.

    Each section gets only the data it needs (filtered context)
    and a brief summary of previously generated sections for coherence.
    """
    section_prompt = REPORT_SECTIONS.get(section_name, "")
    if not section_prompt:
        return f"*Unbekannter Abschnitt: {section_name}*"

    # Filter context to only relevant data
    focused_context = _filter_context(data_context, section_name)

    # Add brief summary of previous sections for coherence
    prev_summary = ""
    if previous_sections:
        summaries = []
        for name, text in previous_sections.items():
            # Take first 200 chars of each previous section
            first_lines = text.strip()[:200]
            summaries.append(f"[{name}]: {first_lines}...")
        prev_summary = (
            "\n\nBEREITS GESCHRIEBENE ABSCHNITTE (Zusammenfassung):\n"
            + "\n".join(summaries)
            + "\n\nVermeide Wiederholungen. Baue auf den vorherigen Abschnitten auf."
        )

    prompt = f"""{section_prompt}

DATENKONTEXT:
{focused_context}
{prev_summary}

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

            # Category distribution
            for tag, count in tag_counts.most_common():
                pct = round(count / total * 100, 1)
                parts.append(f"  Kategorie: {tag}: {count} Nennungen ({pct}%)")

            # Representative quotes per top category (2 per category, top 5 categories)
            tags_by_cat = {}
            for t in tags:
                cat = t.get("human_override") or t.get("tag", "?")
                tags_by_cat.setdefault(cat, []).append(t.get("text", ""))

            parts.append("  Beispielzitate:")
            for cat, _ in tag_counts.most_common(5):
                examples = tags_by_cat.get(cat, [])[:2]
                for ex in examples:
                    parts.append(f"    [{cat}]: \"{ex[:150]}\"")

    return "\n".join(parts)
