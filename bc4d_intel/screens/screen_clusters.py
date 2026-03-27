"""Clusters screen — full-screen taxonomy view per question.

Dropdown to select question → shows:
  - Hierarchical taxonomy (main categories → sub-categories)
  - Editable cluster titles
  - Coding rules per category
  - Semantic map (UMAP scatter plot)
  - Distribution bar chart
"""

from __future__ import annotations
import customtkinter as ctk
from bc4d_intel import constants as C
from bc4d_intel.ui import widgets as W

CLUSTER_COLORS = [
    "#C8175D", "#0077B6", "#059669", "#d97706", "#6366f1",
    "#ec4899", "#14b8a6", "#f59e0b", "#a855f7", "#22c55e",
]


class ClustersScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C.BG, corner_radius=0)
        self.app = app
        self._build()

    def _build(self):
        from bc4d_intel.ui.guide import workflow_steps

        top = W.make_toolbar(self, height=100)
        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=30, pady=8)
        workflow_steps(inner, current_step=3).pack(anchor="w", pady=(0, 4))

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        W.heading(row, "Clusters", size=22).pack(side="left")

        # Question dropdown
        self._question_var = ctk.StringVar(value="Select a question...")
        self._question_menu = ctk.CTkOptionMenu(
            row, variable=self._question_var,
            values=["Run AI Analysis first"],
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=C.BTN, button_color=C.DIM,
            height=32, width=400, corner_radius=6,
            command=self._on_question_change,
        )
        self._question_menu.pack(side="right")

        # Body: taxonomy (left) + map (right)
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=10)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        # Left: Taxonomy
        left = W.make_card(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        self._tax_scroll = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self._tax_scroll.pack(fill="both", expand=True, padx=6, pady=6)
        W.muted_label(self._tax_scroll,
            "Select a question above to see its taxonomy.",
            size=12).pack(padx=20, pady=40)

        # Right: Map + distribution
        right = W.make_card(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        self._chart_frame = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self._chart_frame.pack(fill="both", expand=True, padx=6, pady=6)

    def refresh(self):
        results = getattr(self.app, "_analysis_results", {})
        if results:
            labels = list(results.keys())
            self._question_menu.configure(values=labels)
            if labels and self._question_var.get() == "Select a question...":
                self._question_var.set(labels[0])
                self._on_question_change(labels[0])

    def _on_question_change(self, label):
        results = getattr(self.app, "_analysis_results", {})
        if label not in results:
            return
        data = results[label]
        self._show_taxonomy(data)
        self._show_map(data, label)

    def _show_taxonomy(self, data):
        for w in self._tax_scroll.winfo_children():
            w.destroy()

        taxonomy = data.get("taxonomy", {})
        classifications = data.get("classifications", [])

        for main_cat in taxonomy.get("categories", []):
            # Main category header
            header = ctk.CTkFrame(self._tax_scroll, fg_color=C.ACCENT, corner_radius=6)
            header.pack(fill="x", padx=4, pady=(10, 2))
            ctk.CTkLabel(header, text=main_cat["main_category"],
                         font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                         text_color="#ffffff").pack(padx=12, pady=6)

            for si, sub in enumerate(main_cat.get("sub_categories", [])):
                color = CLUSTER_COLORS[si % len(CLUSTER_COLORS)]
                count = sum(1 for c in classifications
                            if (c.get("human_override") or c["cluster_id"]) == sub["id"])

                card = ctk.CTkFrame(self._tax_scroll, fg_color=C.PANEL, corner_radius=6)
                card.pack(fill="x", padx=12, pady=2)

                # Header row: badge + title
                card_header = ctk.CTkFrame(card, fg_color="transparent")
                card_header.pack(fill="x", padx=10, pady=(6, 2))

                W.status_badge(card_header, f"{count}", color).pack(side="left", padx=(0, 8))

                # Editable title
                title_entry = ctk.CTkEntry(
                    card_header, height=26,
                    font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                    fg_color=C.ENTRY_BG, border_color=C.ENTRY_BORDER,
                )
                title_entry.insert(0, sub["title"])
                title_entry.pack(side="left", fill="x", expand=True)

                # Coding rule
                rule = sub.get("include_rule", "")
                if rule:
                    ctk.CTkLabel(card, text=f"Include: {rule[:100]}",
                                 font=ctk.CTkFont(family="Segoe UI", size=9),
                                 text_color=C.MUTED, anchor="w", wraplength=400,
                                 ).pack(fill="x", padx=10, pady=(0, 2))

                exclude = sub.get("exclude_rule", "")
                if exclude:
                    ctk.CTkLabel(card, text=f"Exclude: {exclude[:100]}",
                                 font=ctk.CTkFont(family="Segoe UI", size=9),
                                 text_color=C.MUTED, anchor="w", wraplength=400,
                                 ).pack(fill="x", padx=10, pady=(0, 2))

                # Examples
                examples = sub.get("examples", [])
                if examples:
                    for ex in examples[:2]:
                        ctk.CTkLabel(card, text=f'  "{ex[:80]}"',
                                     font=ctk.CTkFont(family="Segoe UI", size=9, slant="italic"),
                                     text_color=C.DIM, anchor="w",
                                     ).pack(fill="x", padx=10, pady=0)
                    ctk.CTkFrame(card, height=4, fg_color="transparent").pack()

    def _show_map(self, data, label):
        for w in self._chart_frame.winfo_children():
            w.destroy()

        flat_tax = data.get("flat_taxonomy", [])
        classifications = data.get("classifications", [])
        umap_coords = data.get("umap_coords")
        labels = data.get("labels")

        # UMAP scatter plot
        if umap_coords is not None and labels is not None:
            try:
                from bc4d_intel.core.chart_builder import _ensure_mpl, _apply_style
                _ensure_mpl()
                import matplotlib.pyplot as plt
                from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
                import numpy as np

                fig, ax = plt.subplots(figsize=(5, 4.5))
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
                ax.legend(fontsize=7, loc="upper right", facecolor="#161b22",
                          edgecolor="#30363d", labelcolor="#9ca3af")
                fig.tight_layout()

                canvas = FigureCanvasTkAgg(fig, master=self._chart_frame)
                canvas.draw()
                canvas.get_tk_widget().pack(fill="x", padx=4, pady=4)
            except Exception:
                pass

        # Distribution bars
        ctk.CTkLabel(self._chart_frame, text="Distribution",
                     font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                     text_color=C.TEXT).pack(anchor="w", padx=8, pady=(10, 4))

        total = len(classifications)
        counts = {}
        for c in classifications:
            cid = c.get("human_override") or c["cluster_id"]
            counts[cid] = counts.get(cid, 0) + 1

        for ci, cat in enumerate(flat_tax):
            color = CLUSTER_COLORS[ci % len(CLUSTER_COLORS)]
            count = counts.get(cat["id"], 0)
            pct = round(count / max(total, 1) * 100, 1)

            row = ctk.CTkFrame(self._chart_frame, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=2)

            ctk.CTkLabel(row, text=cat["title"][:20],
                         font=ctk.CTkFont(family="Segoe UI", size=10),
                         text_color=C.TEXT, width=120, anchor="w").pack(side="left")

            bar_bg = ctk.CTkFrame(row, fg_color=C.ENTRY_BG, height=16, corner_radius=3)
            bar_bg.pack(side="left", fill="x", expand=True, padx=4)
            bar_bg.pack_propagate(False)
            if pct > 0:
                ctk.CTkFrame(bar_bg, fg_color=color, corner_radius=3).place(
                    relwidth=pct / 100, relheight=1.0)

            ctk.CTkLabel(row, text=f"{count} ({pct}%)", width=70,
                         font=ctk.CTkFont(family="Consolas", size=10),
                         text_color=C.MUTED).pack(side="right")

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.BG)
        self._build()
