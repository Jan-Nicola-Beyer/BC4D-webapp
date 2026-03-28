"""Insights screen — qualitative analysis charts based on AI-discovered taxonomy.

Shows distribution charts, semantic maps, and cross-tabulations from
the AI Analysis results. Separate from Clusters (taxonomy) and Responses (row data).

View selector: Pre-Survey / Post-Survey / All Questions
Each question gets: distribution bar chart + semantic map + confidence breakdown.
"""

from __future__ import annotations
import customtkinter as ctk
import numpy as np
from bc4d_intel import constants as C
from bc4d_intel.ui import widgets as W

CLUSTER_COLORS = [
    "#C8175D", "#0077B6", "#059669", "#d97706", "#6366f1",
    "#ec4899", "#14b8a6", "#f59e0b", "#a855f7", "#22c55e",
]


class InsightsScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C.BG, corner_radius=0)
        self.app = app
        self._canvas_widgets = []
        self._build()

    def _build(self):
        from bc4d_intel.ui.guide import workflow_steps

        top = W.make_toolbar(self, height=100)
        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=30, pady=8)
        workflow_steps(inner, current_step=5).pack(anchor="w", pady=(0, 4))

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        W.heading(row, "Insights", size=22).pack(side="left")

        # View selector
        self._view_var = ctk.StringVar(value="All Questions")
        self._view_selector = ctk.CTkSegmentedButton(
            row, values=["Pre-Survey", "Post-Survey", "All Questions"],
            variable=self._view_var,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            height=32, corner_radius=6,
            command=self._on_view_change,
        )
        self._view_selector.pack(side="right")

        # Chart area
        self._chart_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._chart_scroll.pack(fill="both", expand=True, padx=20, pady=10)

        W.muted_label(self._chart_scroll,
            "Run AI Analysis first to see qualitative insights here.\n\n"
            "Use the selector above to filter by Pre-Survey or Post-Survey questions.",
            size=12).pack(padx=20, pady=40)

    def refresh(self):
        results = getattr(self.app, "_analysis_results", {})
        if results:
            self._render_charts()

    def _on_view_change(self, value):
        self._render_charts()

    def _render_charts(self):
        results = getattr(self.app, "_analysis_results", {})
        if not results:
            return

        for w in self._chart_scroll.winfo_children():
            w.destroy()
        self._canvas_widgets.clear()

        view = self._view_var.get()

        # Filter questions by survey type
        for label, data in results.items():
            if view == "Pre-Survey" and not label.startswith("[Pre]"):
                continue
            if view == "Post-Survey" and not label.startswith("[Post]"):
                continue

            flat_tax = data.get("flat_taxonomy", [])
            classifications = data.get("classifications", [])
            umap_coords = data.get("umap_coords")

            if not flat_tax or not classifications:
                continue

            # Question header
            ctk.CTkLabel(self._chart_scroll,
                text=label,
                font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
                text_color=C.TEXT).pack(anchor="w", padx=10, pady=(16, 4))

            n = len(classifications)
            from collections import Counter
            confs = Counter(c["confidence"] for c in classifications)
            ctk.CTkLabel(self._chart_scroll,
                text=f"{n} responses | {confs.get('high', 0)} high, "
                     f"{confs.get('medium', 0)} medium, {confs.get('low', 0)} low confidence",
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=C.MUTED).pack(anchor="w", padx=10, pady=(0, 8))

            # Two-column: distribution bar + semantic map
            chart_row = ctk.CTkFrame(self._chart_scroll, fg_color="transparent")
            chart_row.pack(fill="x", padx=5, pady=4)
            chart_row.columnconfigure(0, weight=3)
            chart_row.columnconfigure(1, weight=2)

            # Distribution bar chart
            self._embed_distribution(chart_row, flat_tax, classifications, 0)

            # Semantic map
            if umap_coords is not None:
                self._embed_umap(chart_row, data, flat_tax, 1)

        if not self._canvas_widgets:
            W.muted_label(self._chart_scroll,
                "No matching questions for this filter.",
                size=12).pack(padx=20, pady=40)

    def _embed_distribution(self, parent, flat_tax, classifications, col):
        """Embed a horizontal bar chart showing cluster distribution."""
        from bc4d_intel.core.chart_builder import _ensure_mpl, _apply_style
        _ensure_mpl()
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        counts = {}
        total = len(classifications)
        for c in classifications:
            cid = c.get("human_override") or c["cluster_id"]
            counts[cid] = counts.get(cid, 0) + 1

        n = len(flat_tax)
        fig, ax = plt.subplots(figsize=(7, max(2, n * 0.45 + 0.5)))
        _apply_style(fig, ax)

        labels = [f"{c['main_category'][:12]} > {c['title'][:20]}" for c in flat_tax]
        values = [counts.get(c["id"], 0) for c in flat_tax]
        pcts = [round(v / max(total, 1) * 100, 1) for v in values]
        colors = [CLUSTER_COLORS[i % len(CLUSTER_COLORS)] for i in range(n)]
        y = range(n)

        ax.barh(y, pcts, height=0.6, color=colors, edgecolor="#0d1117")
        ax.set_yticks(y)
        ax.set_yticklabels(labels, fontsize=9)
        ax.set_xlabel("%", fontsize=10)
        ax.set_title("Category Distribution", fontsize=12, fontweight="bold", pad=8)
        ax.invert_yaxis()

        for i, (v, p) in enumerate(zip(values, pcts)):
            ax.text(p + 0.5, i, f"{v} ({p}%)", va="center", fontsize=9, color="#e6edf3")

        fig.tight_layout()

        card = W.make_card(parent)
        card.grid(row=0, column=col, sticky="nsew", padx=3)
        canvas = FigureCanvasTkAgg(fig, master=card)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", padx=4, pady=4)
        self._canvas_widgets.append(canvas)

    def _embed_umap(self, parent, data, flat_tax, col):
        """Embed UMAP semantic scatter plot."""
        from bc4d_intel.core.chart_builder import _ensure_mpl, _apply_style
        _ensure_mpl()
        import matplotlib.pyplot as plt
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

        umap_coords = data.get("umap_coords")
        classifications = data.get("classifications", [])

        if umap_coords is None:
            return

        fig, ax = plt.subplots(figsize=(5, max(2, len(flat_tax) * 0.45 + 0.5)))
        _apply_style(fig, ax)

        cat_ids = list(set(c["cluster_id"] for c in classifications))
        for ci, cid in enumerate(cat_ids):
            mask = np.array([c["cluster_id"] == cid for c in classifications])
            if mask.any():
                color = CLUSTER_COLORS[ci % len(CLUSTER_COLORS)]
                title = next((t["title"][:15] for t in flat_tax if t["id"] == cid), cid[:15])
                ax.scatter(umap_coords[mask, 0], umap_coords[mask, 1],
                           c=color, s=15, alpha=0.7, label=title)

        ax.set_title("Semantic Map", fontsize=12, fontweight="bold", pad=8)
        ax.set_xticks([]); ax.set_yticks([])
        ax.legend(fontsize=7, loc="best", facecolor="#161b22",
                  edgecolor="#30363d", labelcolor="#9ca3af")
        fig.tight_layout()

        card = W.make_card(parent)
        card.grid(row=0, column=col, sticky="nsew", padx=3)
        canvas = FigureCanvasTkAgg(fig, master=card)
        canvas.draw()
        canvas.get_tk_widget().pack(fill="both", padx=4, pady=4)
        self._canvas_widgets.append(canvas)

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.BG)
        self._canvas_widgets.clear()
        self._build()
