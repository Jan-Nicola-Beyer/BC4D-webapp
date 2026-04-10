"""Chart export system — multiple formats, styles, and chart types per dataset.

Exports to a folder named after the question:
  - Multiple chart types (horizontal bar, vertical bar, pie/donut, treemap)
  - Multiple libraries (matplotlib clean, matplotlib styled, plotly if available)
  - Underlying data as Excel
  - All using ISD brand colours

ISD Colour Palette:
  Primary:   #C7074D (ISD Red), #5C6771 (ISD Dark Grey)
  Secondary: #0068B2 (Blue), #E76863 (Coral), #4C4193 (Purple), #B4B2B1 (Light Grey)
"""

from __future__ import annotations
import os, re, logging
from typing import Dict, List, Tuple

log = logging.getLogger("bc4d_intel.core.chart_exporter")

# ISD Brand Colours
ISD_RED = "#C7074D"
ISD_GREY = "#5C6771"
ISD_BLUE = "#0068B2"
ISD_CORAL = "#E76863"
ISD_PURPLE = "#4C4193"
ISD_LIGHT_GREY = "#B4B2B1"

# Extended palette for charts (cycling through brand + tints)
ISD_PALETTE = [
    ISD_RED, ISD_BLUE, ISD_CORAL, ISD_PURPLE, ISD_GREY,
    "#E0335E",  # lighter red
    "#3388CC",  # lighter blue
    "#F09090",  # lighter coral
    "#7A6BBB",  # lighter purple
    "#8899A0",  # lighter grey
    "#D4A0A8",  # pink tint
    "#80B8D8",  # blue tint
]


def _clean_filename(text: str, max_len: int = 50) -> str:
    s = text.strip().split("\n")[0]
    s = re.sub(r'\([^)]*\)', '', s)
    s = s.replace('\xa0', ' ').strip()
    s = re.sub(r'[^\w\s-]', '', s)
    s = re.sub(r'\s+', '_', s).strip('_')
    return s[:max_len]


def export_chart_pack(
    question: str,
    categories: List[Tuple[str, str, int]],
    total: int,
    output_dir: str,
    progress_cb=None,
) -> str:
    """Export a full chart pack for one question.

    Creates TWO levels of charts:
      - Main categories (aggregated, clean, few bars)
      - Sub-categories (detailed, grouped by main)

    Args:
        question: the survey question label
        categories: list of (main_category, sub_category, count) tuples
        total: total number of responses
        output_dir: base directory for export

    Returns:
        path to the created folder
    """
    folder_name = _clean_filename(question)
    folder_path = os.path.join(output_dir, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    # Sub-category level (detailed)
    labels = [sub for _, sub, _ in categories]
    mains = [main for main, _, _ in categories]
    counts = [c for _, _, c in categories]
    pcts = [round(c / max(total, 1) * 100, 1) for c in counts]

    # Main category level (aggregated — clean, few bars)
    main_agg = {}
    for main, _, count in categories:
        main_agg[main] = main_agg.get(main, 0) + count
    main_labels = list(main_agg.keys())
    main_counts = list(main_agg.values())
    main_pcts = [round(c / max(total, 1) * 100, 1) for c in main_counts]
    main_colors = [ISD_PALETTE[i % len(ISD_PALETTE)] for i in range(len(main_labels))]

    # Color sub-categories by their main category
    main_color_map = {m: ISD_PALETTE[i % len(ISD_PALETTE)] for i, m in enumerate(main_labels)}
    sub_colors = [main_color_map.get(m, ISD_GREY) for m in mains]

    n_files = 0

    if progress_cb:
        progress_cb("Exporting data...")
    n_files += _export_excel(folder_path, labels, mains, counts, pcts, total)

    if progress_cb:
        progress_cb("Exporting charts...")
    n_files += _export_matplotlib_main(folder_path, main_labels, main_counts,
                                        main_pcts, main_colors, question, total)
    n_files += _export_matplotlib_sub(folder_path, labels, mains, counts, pcts,
                                       sub_colors, question, total)

    try:
        if progress_cb:
            progress_cb("Exporting interactive charts...")
        n_files += _export_plotly(folder_path, main_labels, main_counts,
                                   main_pcts, main_colors, labels, mains,
                                   counts, pcts, sub_colors, question, total)
    except Exception:
        pass

    log.info("Exported %d files to %s", n_files, folder_path)
    return folder_path


def _export_excel(folder, labels, mains, counts, pcts, total) -> int:
    import pandas as pd
    df = pd.DataFrame({
        "Hauptkategorie": mains,
        "Unterkategorie": labels,
        "Anzahl": counts,
        "Prozent": pcts,
        "Antworten gesamt": [total] * len(labels),
    })
    path = os.path.join(folder, "data.xlsx")
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Verteilung", index=False)
        ws = writer.sheets["Verteilung"]
        for col in ws.columns:
            max_len = max(len(str(cell.value or "")) for cell in col)
            ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)
    return 1


def _export_matplotlib_main(folder, labels, counts, pcts, colors,
                             question, total) -> int:
    """Clean charts with MAIN categories only (few bars, easy to read)."""
    from bc4d_intel.core.chart_builder import _ensure_mpl
    _ensure_mpl()
    import matplotlib.pyplot as plt

    n = len(labels)
    exported = 0

    # ── Horizontal bar (white, print-friendly) ──
    fig, ax = plt.subplots(figsize=(9, max(2.5, n * 0.6 + 1)))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.barh(range(n), pcts, height=0.55, color=colors, edgecolor="white")
    ax.set_yticks(range(n))
    ax.set_yticklabels(labels, fontsize=11, color="#333333")
    ax.set_xlabel("% der Antworten", fontsize=11, color="#333333")
    ax.invert_yaxis()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#CCCCCC")
    ax.spines["bottom"].set_color("#CCCCCC")
    for i, (v, p) in enumerate(zip(counts, pcts)):
        ax.text(p + 0.5, i, f"{v} ({p}%)", va="center", fontsize=10, color="#333333")
    ax.set_xlim(0, max(pcts) * 1.3 if pcts else 10)
    fig.tight_layout()
    fig.savefig(os.path.join(folder, "main_categories_bar.png"), dpi=200, bbox_inches="tight")
    fig.savefig(os.path.join(folder, "main_categories_bar.pdf"), bbox_inches="tight")
    plt.close(fig)
    exported += 2

    # ── Donut chart ──
    fig, ax = plt.subplots(figsize=(7, 5))
    fig.patch.set_facecolor("white")
    wedges, _, autotexts = ax.pie(
        counts, labels=None, autopct="%1.0f%%",
        colors=colors, startangle=90,
        pctdistance=0.75, wedgeprops=dict(width=0.4, edgecolor="white"))
    for t in autotexts:
        t.set_fontsize(10)
        t.set_color("#333333")
    ax.legend([f"{l} ({c})" for l, c in zip(labels, counts)],
              loc="center left", bbox_to_anchor=(1, 0.5), fontsize=10,
              frameon=False)
    fig.tight_layout()
    fig.savefig(os.path.join(folder, "main_categories_donut.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)
    exported += 1

    return exported


def _export_matplotlib_sub(folder, labels, mains, counts, pcts, colors,
                            question, total) -> int:
    """Detailed sub-category charts (more bars, grouped by main)."""
    from bc4d_intel.core.chart_builder import _ensure_mpl
    _ensure_mpl()
    import matplotlib.pyplot as plt

    n = len(labels)
    exported = 0

    # ── Sub-category horizontal bar (white, detailed) ──
    fig, ax = plt.subplots(figsize=(10, max(3, n * 0.45 + 1)))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.barh(range(n), pcts, height=0.55, color=colors, edgecolor="white")
    ax.set_yticks(range(n))
    ax.set_yticklabels([l[:30] for l in labels], fontsize=9, color="#333333")
    ax.set_xlabel("% der Antworten", fontsize=10, color="#333333")
    ax.invert_yaxis()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for i, (v, p) in enumerate(zip(counts, pcts)):
        ax.text(p + 0.3, i, f"{v} ({p}%)", va="center", fontsize=8, color="#333333")
    ax.set_xlim(0, max(pcts) * 1.3 if pcts else 10)
    # Add main category as color legend
    from matplotlib.patches import Patch
    unique_mains = list(dict.fromkeys(mains))
    main_color_map = {m: colors[mains.index(m)] for m in unique_mains}
    legend_items = [Patch(facecolor=main_color_map[m], label=m) for m in unique_mains]
    ax.legend(handles=legend_items, fontsize=8, loc="lower right", frameon=False)
    fig.tight_layout()
    fig.savefig(os.path.join(folder, "sub_categories_bar.png"), dpi=200, bbox_inches="tight")
    fig.savefig(os.path.join(folder, "sub_categories_bar.pdf"), bbox_inches="tight")
    plt.close(fig)
    exported += 2

    # ── Dark version for presentations ──
    fig, ax = plt.subplots(figsize=(10, max(3, n * 0.45 + 1)))
    fig.patch.set_facecolor("#1a1a2e")
    ax.set_facecolor("#1a1a2e")
    ax.barh(range(n), pcts, height=0.55, color=colors, edgecolor="#1a1a2e")
    ax.set_yticks(range(n))
    ax.set_yticklabels([l[:30] for l in labels], fontsize=9, color="#e0e0e0")
    ax.set_xlabel("% der Antworten", fontsize=10, color="#e0e0e0")
    ax.invert_yaxis()
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#444444")
    ax.spines["bottom"].set_color("#444444")
    ax.tick_params(colors="#999999")
    for i, (v, p) in enumerate(zip(counts, pcts)):
        ax.text(p + 0.3, i, f"{v} ({p}%)", va="center", fontsize=8, color="#e0e0e0")
    ax.set_xlim(0, max(pcts) * 1.3 if pcts else 10)
    fig.tight_layout()
    fig.savefig(os.path.join(folder, "sub_categories_bar_dark.png"), dpi=200, bbox_inches="tight")
    plt.close(fig)
    exported += 1

    return exported


def _export_plotly(folder, main_labels, main_counts, main_pcts, main_colors,
                    sub_labels, sub_mains, sub_counts, sub_pcts, sub_colors,
                    question, total) -> int:
    import plotly.graph_objects as go

    exported = 0

    # Interactive main category bar
    fig = go.Figure(go.Bar(
        x=main_pcts, y=main_labels, orientation="h",
        marker_color=main_colors,
        text=[f"{c} ({p}%)" for c, p in zip(main_counts, main_pcts)],
        textposition="outside",
    ))
    fig.update_layout(
        title=dict(text="Hauptkategorien", font=dict(size=14, color=ISD_RED)),
        xaxis_title="% der Antworten",
        yaxis=dict(autorange="reversed"),
        template="plotly_white",
        font=dict(family="Segoe UI", size=12),
        margin=dict(l=200, r=100, t=60, b=40),
        height=max(300, len(main_labels) * 50 + 100),
    )
    fig.write_html(os.path.join(folder, "main_categories_interactive.html"))
    exported += 1

    # Interactive sunburst (main > sub hierarchy)
    sun_labels, sun_parents, sun_values = [], [], []
    seen = set()
    for main, sub, count in zip(sub_mains, sub_labels, sub_counts):
        if main not in seen:
            sun_labels.append(main)
            sun_parents.append("")
            sun_values.append(0)
            seen.add(main)
        sun_labels.append(sub[:25])
        sun_parents.append(main)
        sun_values.append(count)

    fig2 = go.Figure(go.Sunburst(
        labels=sun_labels, parents=sun_parents, values=sun_values,
        branchvalues="total",
        marker=dict(colors=[main_colors[i % len(main_colors)]
                            for i in range(len(sun_labels))]),
    ))
    fig2.update_layout(
        title=dict(text="Kategorie-Hierarchie", font=dict(size=14, color=ISD_RED)),
        margin=dict(t=60, l=0, r=0, b=0), height=500,
    )
    fig2.write_html(os.path.join(folder, "sunburst_interactive.html"))
    exported += 1

    return exported
