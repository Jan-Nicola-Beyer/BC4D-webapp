"""Dashboard screen — quantitative analysis with charts.

Three analysis views (tabs):
  1. Pre-Survey: baseline attitudes for ALL pre-respondents
  2. Post-Survey: outcomes for ALL post-respondents
  3. Matched Panel: individual-level change for paired respondents
"""

from __future__ import annotations
import threading, tkinter as tk
import customtkinter as ctk
from bc4d_intel import constants as C
from bc4d_intel.ui import widgets as W


class DashboardScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C.BG, corner_radius=0)
        self.app = app
        self._current_tab = "pre"
        self._canvas_widgets = []  # track embedded charts for cleanup
        self._build()

    def _build(self):
        # ── Top bar ──
        top = W.make_toolbar(self, height=80)
        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=30, pady=12)
        W.heading(inner, "Dashboard", size=22).pack(side="left")

        # Tab selector
        self._tab_var = ctk.StringVar(value="pre")
        self._tab_selector = ctk.CTkSegmentedButton(
            inner, values=["Pre-Survey", "Post-Survey", "Matched Panel"],
            variable=self._tab_var,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            height=32, corner_radius=6,
            command=self._on_tab_change,
        )
        self._tab_selector.pack(side="right")

        # ── Chart area (scrollable) ──
        self._chart_frame = ctk.CTkScrollableFrame(self, fg_color=C.BG)
        self._chart_frame.pack(fill="both", expand=True, padx=20, pady=10)

        self._show_placeholder()

    def _show_placeholder(self):
        for w in self._chart_frame.winfo_children():
            w.destroy()
        W.muted_label(self._chart_frame,
            "Load both survey files from the Import screen to see charts.\n\n"
            "Use the tabs above to switch between:\n"
            "  - Pre-Survey: baseline data (all respondents)\n"
            "  - Post-Survey: outcome data (all respondents)\n"
            "  - Matched Panel: individual change (paired respondents only)",
            size=12).pack(padx=20, pady=40)

    def _on_tab_change(self, value):
        tab_map = {"Pre-Survey": "pre", "Post-Survey": "post", "Matched Panel": "matched"}
        self._current_tab = tab_map.get(value, "pre")
        self._render_charts()

    def refresh(self):
        """Called when screen becomes visible."""
        if hasattr(self.app, "_match_result") and self.app._match_result:
            self._render_charts()

    def _render_charts(self):
        """Render charts for the current tab."""
        if not hasattr(self.app, "_match_result") or not self.app._match_result:
            self._show_placeholder()
            return

        # Clear previous charts
        for w in self._chart_frame.winfo_children():
            w.destroy()
        self._canvas_widgets.clear()

        result = self.app._match_result
        tab = self._current_tab

        if tab == "pre":
            self._render_pre_charts(result)
        elif tab == "post":
            self._render_post_charts(result)
        elif tab == "matched":
            self._render_matched_charts(result)

    def _render_pre_charts(self, result):
        """Charts for pre-survey (all respondents)."""
        from bc4d_intel.core.stats_engine import analyze_all_likert
        from bc4d_intel.core.data_loader import normalize_likert_column

        pre_df = result["pre_all"]
        # Get roles from the import screen
        import_screen = self.app._frames.get("import")
        if not import_screen or not import_screen._pre_roles:
            W.muted_label(self._chart_frame, "Pre-survey roles not detected.").pack(pady=20)
            return

        roles = import_screen._pre_roles

        # Header
        ctk.CTkLabel(self._chart_frame,
            text=f"Pre-Survey Analysis — {len(pre_df)} respondents (baseline)",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=C.TEXT).pack(anchor="w", padx=10, pady=(10, 5))

        # Likert analysis
        items = analyze_all_likert(pre_df, roles)
        if items:
            self._embed_chart("likert_pre", items, "Pre-Survey: Attitude & Knowledge Scales")

        # Demographics
        demo_cols = [c for c, r in roles.items() if r == "demographic"]
        for col in demo_cols[:2]:
            self._embed_demographic(pre_df[col], col[:40])

    def _render_post_charts(self, result):
        """Charts for post-survey (all respondents)."""
        from bc4d_intel.core.stats_engine import analyze_all_likert

        post_df = result["post_all"]
        import_screen = self.app._frames.get("import")
        if not import_screen or not import_screen._post_roles:
            W.muted_label(self._chart_frame, "Post-survey roles not detected.").pack(pady=20)
            return

        roles = import_screen._post_roles

        ctk.CTkLabel(self._chart_frame,
            text=f"Post-Survey Analysis — {len(post_df)} respondents (outcomes)",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=C.TEXT).pack(anchor="w", padx=10, pady=(10, 5))

        items = analyze_all_likert(post_df, roles)
        if items:
            self._embed_chart("likert_post", items, "Post-Survey: Competence & Confidence Scales")

    def _render_matched_charts(self, result):
        """Charts for matched panel (paired respondents)."""
        from bc4d_intel.core.stats_engine import analyze_matched_likert

        matched_df = result["matched"]
        if len(matched_df) == 0:
            W.muted_label(self._chart_frame,
                "No matched pairs found. Panel matching requires valid pseudokeys in both surveys.",
                size=12).pack(pady=40)
            return

        import_screen = self.app._frames.get("import")
        if not import_screen:
            return

        ctk.CTkLabel(self._chart_frame,
            text=f"Matched Panel Analysis — {len(matched_df)} paired respondents",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=C.TEXT).pack(anchor="w", padx=10, pady=(10, 5))

        ctk.CTkLabel(self._chart_frame,
            text="Only respondents who completed BOTH surveys. Enables individual-level change analysis.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=C.MUTED).pack(anchor="w", padx=10, pady=(0, 10))

        comparisons = analyze_matched_likert(matched_df, import_screen._pre_roles, import_screen._post_roles)

        if comparisons:
            # Pre/post grouped bar
            self._embed_comparison_chart(comparisons, "Pre vs Post Mean Scores")
            # Change distribution
            self._embed_change_chart(comparisons, "Direction of Individual Change")
            # Stats table
            self._embed_stats_table(comparisons)

    def _embed_chart(self, chart_id, items, title):
        """Embed a Likert stacked bar chart."""
        from bc4d_intel.core.chart_builder import likert_stacked_bar
        fig = likert_stacked_bar(items, title)
        self._embed_figure(fig)

    def _embed_comparison_chart(self, comparisons, title):
        from bc4d_intel.core.chart_builder import pre_post_grouped_bar
        fig = pre_post_grouped_bar(comparisons, title)
        self._embed_figure(fig)

    def _embed_change_chart(self, comparisons, title):
        from bc4d_intel.core.chart_builder import change_histogram
        fig = change_histogram(comparisons, title)
        self._embed_figure(fig)

    def _embed_demographic(self, series, title):
        from bc4d_intel.core.chart_builder import demographic_pie
        fig = demographic_pie(series, title)
        self._embed_figure(fig)

    def _embed_figure(self, fig):
        """Embed a matplotlib figure in the scrollable frame."""
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        card = W.make_card(self._chart_frame)
        card.pack(fill="x", padx=5, pady=8)

        canvas = FigureCanvasTkAgg(fig, master=card)
        canvas.draw()
        widget = canvas.get_tk_widget()
        widget.pack(fill="x", padx=8, pady=8)
        self._canvas_widgets.append(canvas)

    def _embed_stats_table(self, comparisons):
        """Show a summary stats table for matched comparisons."""
        card = W.make_card(self._chart_frame)
        card.pack(fill="x", padx=5, pady=8)

        ctk.CTkLabel(card, text="Statistical Summary (Matched Panel)",
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                     text_color=C.TEXT).pack(anchor="w", padx=12, pady=(10, 4))

        # Header row
        header = ctk.CTkFrame(card, fg_color=C.PANEL, corner_radius=4)
        header.pack(fill="x", padx=8, pady=2)
        for text, width in [("Item", 250), ("Pre", 50), ("Post", 50),
                            ("Change", 60), ("d", 50), ("Effect", 70), ("p", 60)]:
            ctk.CTkLabel(header, text=text, width=width,
                         font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
                         text_color=C.MUTED).pack(side="left", padx=4, pady=4)

        for c in comparisons:
            comp = c.get("comparison", {})
            if "error" in comp:
                continue

            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=1)

            # Color based on direction
            change = comp.get("mean_change", 0)
            change_color = C.SUCCESS if change > 0.1 else (C.DANGER if change < -0.1 else C.MUTED)

            label = c["label"][:35]
            p_val = comp.get("p_value")
            p_text = f"{p_val:.3f}" if p_val is not None else "N/A"
            sig = "*" if comp.get("significant") else ""

            for text, width, color in [
                (label, 250, C.TEXT),
                (str(comp.get("pre_mean", "")), 50, C.MUTED),
                (str(comp.get("post_mean", "")), 50, C.MUTED),
                (f"{'+' if change > 0 else ''}{change}", 60, change_color),
                (str(comp.get("cohens_d", "")), 50, C.MUTED),
                (comp.get("effect_label", ""), 70, change_color),
                (f"{p_text}{sig}", 60, C.MUTED),
            ]:
                ctk.CTkLabel(row, text=str(text), width=width,
                             font=ctk.CTkFont(family="Consolas", size=9),
                             text_color=color).pack(side="left", padx=4, pady=2)

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.BG)
        self._canvas_widgets.clear()
        self._build()
