"""Insights screen — visual charts for AI Analysis results, one question at a time.

Select a question from the dropdown to see:
  - Horizontal bar chart showing category distribution
  - Response count and confidence breakdown
"""

from __future__ import annotations
import os
import customtkinter as ctk
from bc4d_intel import constants as C
from bc4d_intel.ui import widgets as W

CLUSTER_COLORS = [
    "#C8175D", "#0077B6", "#059669", "#d97706", "#6366f1",
    "#ec4899", "#14b8a6", "#f59e0b", "#a855f7", "#22c55e",
]


def _short_label(label: str) -> str:
    """Create a short display label from a long question column name.

    '[Post] Was hat Ihnen an der Schulung gut gefallen?\\n(Mehrfach...'
    -> '[Post] Was hat Ihnen an der Schulung gut gefallen?'
    """
    import re
    s = label.strip()
    # Remove newlines and everything after
    s = s.split("\n")[0].split("\r")[0]
    # Remove parenthetical suffixes like (Angabe erforderlich)
    s = re.sub(r'\s*\([^)]*\)', '', s)
    # Remove non-breaking spaces
    s = s.replace('\xa0', ' ').strip()
    # Cap at 70 chars
    if len(s) > 70:
        s = s[:67] + "..."
    return s


class InsightsScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C.BG, corner_radius=0)
        self.app = app
        self._canvas_widgets = []
        self._label_map = {}  # short_label -> original_label
        self._build()

    def _build(self):
        from bc4d_intel.ui.guide import workflow_steps

        top = W.make_toolbar(self, height=100)
        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=30, pady=8)
        workflow_steps(inner, current_step=4).pack(anchor="w", pady=(0, 4))

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        W.heading(row, "Insights", size=22).pack(side="left")

        # Question dropdown
        self._question_var = ctk.StringVar(value="Select a question...")
        self._question_menu = ctk.CTkComboBox(
            row, variable=self._question_var,
            values=["Run AI Analysis first"],
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=C.ENTRY_BG, border_color=C.ENTRY_BORDER,
            button_color=C.DIM, dropdown_font=ctk.CTkFont(size=11),
            height=32, corner_radius=6, state="readonly",
            command=self._on_question_change,
        )
        self._question_menu.pack(side="left", fill="x", expand=True, padx=(16, 8))

        ctk.CTkButton(
            row, text="Export Chart Pack", width=140, height=32,
            fg_color=C.BTN, hover_color=C.SELECT,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=6, command=self._export_chart_pack,
        ).pack(side="right", padx=(0, 8))

        ctk.CTkButton(
            row, text="Export Data", width=100, height=32,
            fg_color=C.BTN, hover_color=C.SELECT,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            corner_radius=6, command=self._export_chart_data,
        ).pack(side="right")

        self._question_full_lbl = ctk.CTkLabel(inner,
            text="Select a question to see how responses are distributed across categories.",
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color=C.MUTED, anchor="w", wraplength=800)
        self._question_full_lbl.pack(anchor="w")

        # Chart area
        self._chart_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._chart_scroll.pack(fill="both", expand=True, padx=20, pady=10)

        W.muted_label(self._chart_scroll,
            "Select a question above to see the distribution chart.\n\n"
            "Charts show how many responses fall into each category,\n"
            "helping you quickly identify the main themes.",
            size=12).pack(padx=20, pady=40)

    def refresh(self):
        results = getattr(self.app, "_analysis_results", {})
        if results:
            # Build short label -> original label mapping
            self._label_map = {}
            short_labels = []
            for orig in results.keys():
                short = _short_label(orig)
                # Handle duplicates by appending index
                if short in self._label_map:
                    short = short + " (2)"
                self._label_map[short] = orig
                short_labels.append(short)

            self._question_menu.configure(values=short_labels)
            if short_labels and self._question_var.get() == "Select a question...":
                self._question_var.set(short_labels[0])
                self._on_question_change(short_labels[0])

    def _on_question_change(self, short_label):
        results = getattr(self.app, "_analysis_results", {})
        orig = self._label_map.get(short_label, short_label)
        if orig not in results:
            return
        # Show full question text below dropdown
        self._question_full_lbl.configure(text=orig)
        data = results[orig]
        self._render_chart(orig, data)

    def _render_chart(self, label, data):
        # Close matplotlib figures to prevent memory leak
        import matplotlib.pyplot as plt
        for c in self._canvas_widgets:
            try:
                plt.close(c.figure)
                c.get_tk_widget().destroy()
            except Exception:
                pass
        self._canvas_widgets.clear()
        for w in self._chart_scroll.winfo_children():
            w.destroy()

        classifications = data.get("classifications", [])
        if not classifications:
            W.muted_label(self._chart_scroll,
                "No classifications for this question yet.",
                size=12).pack(padx=20, pady=40)
            return

        total = len(classifications)
        from collections import Counter
        confs = Counter(c.get("confidence", "?") for c in classifications)

        # Summary
        ctk.CTkLabel(self._chart_scroll,
            text=f"{total} responses classified",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=C.TEXT).pack(anchor="w", padx=10, pady=(10, 2))

        ctk.CTkLabel(self._chart_scroll,
            text=f"Confidence: {confs.get('high', 0)} high, "
                 f"{confs.get('medium', 0)} medium, {confs.get('low', 0)} low",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=C.MUTED).pack(anchor="w", padx=10, pady=(0, 12))

        # Count per category, grouped by main category
        cat_data = {}
        for c in classifications:
            main = c.get("main_category", "Other")
            sub = c.get("cluster_title", "Unknown")
            key = (main, sub)
            cat_data[key] = cat_data.get(key, 0) + 1

        # Sort: group by main category, then by count within each group
        by_main = {}
        for (main, sub), count in cat_data.items():
            by_main.setdefault(main, []).append(((main, sub), count))
        # Sort main categories by total count, sub-categories by count within
        main_totals = {m: sum(c for _, c in subs) for m, subs in by_main.items()}
        sorted_cats = []
        for main in sorted(main_totals, key=main_totals.get, reverse=True):
            for item in sorted(by_main[main], key=lambda x: -x[1]):
                sorted_cats.append(item)

        # Try matplotlib chart first, fall back to native bars
        chart_drawn = False
        try:
            chart_drawn = self._draw_matplotlib_chart(sorted_cats, total)
        except Exception as e:
            import logging
            logging.getLogger("bc4d_intel").warning("Chart rendering failed: %s", e)

        if not chart_drawn:
            self._draw_native_bars(sorted_cats, total)

    def _draw_matplotlib_chart(self, sorted_cats, total) -> bool:
        """Draw a horizontal bar chart grouped by main category."""
        from bc4d_intel.core.chart_builder import _ensure_mpl, _apply_style
        _ensure_mpl()
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        n = len(sorted_cats)
        if n == 0:
            return False

        # Short labels: sub-category only (main category shown as group separator)
        labels = [sub[:30] for (main, sub), _ in sorted_cats]
        values = [count for _, count in sorted_cats]
        pcts = [round(v / max(total, 1) * 100, 1) for v in values]

        # Color by main category (same main = same color)
        main_cats = list(dict.fromkeys(m for (m, _), _ in sorted_cats))
        main_color_map = {m: CLUSTER_COLORS[i % len(CLUSTER_COLORS)]
                          for i, m in enumerate(main_cats)}
        colors = [main_color_map[main] for (main, _), _ in sorted_cats]

        fig, ax = plt.subplots(figsize=(9, max(3, n * 0.45 + 1.5)))
        _apply_style(fig, ax)

        y = range(n)
        from bc4d_intel.core.chart_builder import _chart_colors
        cc = _chart_colors()

        bars = ax.barh(y, pcts, height=0.6, color=colors, edgecolor=cc["edge"])
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=10)
        ax.set_xlabel("% der Antworten", fontsize=11)
        ax.invert_yaxis()

        max_pct = max(pcts) if pcts else 10
        for i, (v, p) in enumerate(zip(values, pcts)):
            ax.text(p + max_pct * 0.02, i, f"{v} ({p}%)", va="center",
                    fontsize=10, color=cc["text"], fontweight="bold")

        from matplotlib.patches import Patch
        legend_items = [Patch(facecolor=main_color_map[m], label=m)
                        for m in main_cats]
        ax.legend(handles=legend_items, loc="lower right", fontsize=9,
                  facecolor=cc["legend_bg"], edgecolor=cc["legend_border"],
                  labelcolor=cc["legend_text"])

        ax.set_xlim(0, max_pct * 1.25)

        fig.tight_layout()

        card = W.make_card(self._chart_scroll)
        card.pack(fill="x", padx=5, pady=4)
        canvas = FigureCanvasTkAgg(fig, master=card)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="x", padx=4, pady=4)
        self._canvas_widgets.append(canvas)
        return True

    def _draw_native_bars(self, sorted_cats, total):
        """Fallback: draw bars with native customtkinter frames."""
        ctk.CTkLabel(self._chart_scroll, text="Category Distribution",
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                     text_color=C.TEXT).pack(anchor="w", padx=8, pady=(6, 8))

        current_main = None
        ci = 0
        for (main_cat, sub_title), count in sorted_cats:
            pct = count / max(total, 1) * 100

            if main_cat != current_main:
                current_main = main_cat
                ctk.CTkLabel(self._chart_scroll, text=main_cat,
                             font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                             text_color=C.ACCENT).pack(anchor="w", padx=8, pady=(10, 2))

            color = CLUSTER_COLORS[ci % len(CLUSTER_COLORS)]
            ci += 1

            row = ctk.CTkFrame(self._chart_scroll, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=2)

            ctk.CTkLabel(row, text=sub_title[:25],
                         font=ctk.CTkFont(family="Segoe UI", size=10),
                         text_color=C.TEXT, width=150, anchor="w").pack(side="left")

            bar_bg = ctk.CTkFrame(row, fg_color=C.ENTRY_BG, height=18, corner_radius=3)
            bar_bg.pack(side="left", fill="x", expand=True, padx=4)
            bar_bg.pack_propagate(False)
            if pct > 0:
                ctk.CTkFrame(bar_bg, fg_color=color, corner_radius=3).place(
                    relwidth=min(pct / 100, 1.0), relheight=1.0)

            ctk.CTkLabel(row, text=f"{count} ({pct:.0f}%)", width=80,
                         font=ctk.CTkFont(family="Consolas", size=10),
                         text_color=C.MUTED).pack(side="right")

    def _export_chart_data(self):
        """Export chart data for the selected question as formatted Excel.

        Two sheets: Distribution (summary for graphic designer) +
        All Responses (individual responses with categories).
        """
        import re
        from tkinter import filedialog
        import pandas as pd

        results = getattr(self.app, "_analysis_results", {})
        short = self._question_var.get()
        orig = self._label_map.get(short, short)
        if orig not in results:
            return

        data = results[orig]
        classifications = data.get("classifications", [])
        if not classifications:
            return

        # Build summary table
        from collections import Counter
        total = len(classifications)
        cat_counts = Counter()
        for c in classifications:
            cat_counts[(c.get("main_category", ""), c.get("cluster_title", ""))] += 1

        summary_rows = []
        for (main, sub), count in cat_counts.most_common():
            summary_rows.append({
                "Hauptkategorie": main,
                "Unterkategorie": sub,
                "Anzahl": count,
                "Prozent": round(count / total * 100, 1),
            })

        # Build responses table
        resp_rows = [{"Antwort": c.get("text", ""),
                      "Hauptkategorie": c.get("main_category", ""),
                      "Unterkategorie": c.get("cluster_title", ""),
                      "Konfidenz": c.get("confidence", "")}
                     for c in classifications]

        clean_name = re.sub(r'[^\w\s-]', '', _short_label(orig))[:40].strip()
        path = filedialog.asksaveasfilename(
            title="Export Chart Data",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx")],
            initialfile=f"chart_data_{clean_name}.xlsx",
        )
        if not path:
            return

        try:
            summary_df = pd.DataFrame(summary_rows)
            resp_df = pd.DataFrame(resp_rows)

            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                summary_df.to_excel(writer, sheet_name="Verteilung", index=False)
                resp_df.to_excel(writer, sheet_name="Alle Antworten", index=False)
                for sn in writer.sheets:
                    ws = writer.sheets[sn]
                    for col in ws.columns:
                        max_len = max(len(str(cell.value or "")) for cell in col)
                        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 60)

            self._question_full_lbl.configure(
                text=f"Exported to {path.split('/')[-1].split(chr(92))[-1]}")
        except Exception as e:
            self._question_full_lbl.configure(text=f"Export failed: {e}")

    def _export_chart_pack(self):
        """Export full chart pack: multiple chart types + styles + data."""
        from tkinter import filedialog
        from collections import Counter

        results = getattr(self.app, "_analysis_results", {})
        short = self._question_var.get()
        orig = self._label_map.get(short, short)
        if orig not in results:
            return

        data = results[orig]
        classifications = data.get("classifications", [])
        if not classifications:
            return

        output_dir = filedialog.askdirectory(title="Select folder for chart export")
        if not output_dir:
            return

        total = len(classifications)
        cat_counts = Counter()
        for c in classifications:
            cat_counts[(c.get("main_category", ""), c.get("cluster_title", ""))] += 1

        categories = [(main, sub, count) for (main, sub), count
                      in cat_counts.most_common()]

        try:
            from bc4d_intel.core.chart_exporter import export_chart_pack
            folder = export_chart_pack(
                orig, categories, total, output_dir,
                progress_cb=lambda m: self._question_full_lbl.configure(text=m))

            n_files = len([f for f in os.listdir(folder)])
            self._question_full_lbl.configure(
                text=f"Exported {n_files} files to {os.path.basename(folder)}/")
        except Exception as e:
            self._question_full_lbl.configure(text=f"Export failed: {e}")

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.BG)
        self._canvas_widgets.clear()
        self._build()
