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


def _short_label(label: str) -> str:
    import re
    s = label.strip().split("\n")[0].split("\r")[0]
    s = re.sub(r'\s*\([^)]*\)', '', s)
    s = s.replace('\xa0', ' ').strip()
    return s[:70] + "..." if len(s) > 70 else s


class ClustersScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C.BG, corner_radius=0)
        self.app = app
        self._label_map = {}
        self._build()

    def _build(self):
        from bc4d_intel.ui.guide import workflow_steps

        top = W.make_toolbar(self, height=100)
        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=30, pady=8)
        workflow_steps(inner, current_step=3).pack(anchor="w", pady=(0, 4))

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        W.heading(row, "Categories", size=22).pack(side="left")

        # Question dropdown (full-width so long question text is visible)
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
        self._question_menu.pack(side="right", fill="x", expand=True, padx=(16, 0))

        self._question_full_lbl = ctk.CTkLabel(inner,
            text="Select a question to see how responses were grouped into categories.",
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color=C.MUTED, anchor="w", wraplength=800)
        self._question_full_lbl.pack(anchor="w")

        # Body: taxonomy list
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=10)
        card = W.make_card(body)
        card.pack(fill="both", expand=True)

        self._tax_scroll = ctk.CTkScrollableFrame(card, fg_color="transparent")
        self._tax_scroll.pack(fill="both", expand=True, padx=6, pady=6)
        W.muted_label(self._tax_scroll,
            "Select a question above to see its categories.\n\n"
            "Each category shows its definition, example responses, and count.\n"
            "For charts, go to the Insights screen.",
            size=12).pack(padx=20, pady=40)

    def refresh(self):
        results = getattr(self.app, "_analysis_results", {})
        if results:
            self._label_map = {}
            short_labels = []
            for orig in results.keys():
                short = _short_label(orig)
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
        label = self._label_map.get(short_label, short_label)
        self._question_full_lbl.configure(text=label)
        if label not in results:
            return
        data = results[label]
        self._show_taxonomy(data)

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

                # Coding rule (with magnifier for long rules)
                rule = sub.get("include_rule", "")
                if rule:
                    rule_lbl = ctk.CTkLabel(card, text=f"Include: {rule[:100]}",
                                 font=ctk.CTkFont(family="Segoe UI", size=9),
                                 text_color=C.MUTED, anchor="w", wraplength=400)
                    rule_lbl.pack(fill="x", padx=10, pady=(0, 2))
                    W.magnify(rule_lbl, text=f"Include: {rule}")

                exclude = sub.get("exclude_rule", "")
                if exclude:
                    ctk.CTkLabel(card, text=f"Exclude: {exclude[:100]}",
                                 font=ctk.CTkFont(family="Segoe UI", size=9),
                                 text_color=C.MUTED, anchor="w", wraplength=400,
                                 ).pack(fill="x", padx=10, pady=(0, 2))

                # Examples (with magnifier for truncated quotes)
                examples = sub.get("examples", [])
                if examples:
                    for ex in examples[:2]:
                        ex_lbl = ctk.CTkLabel(card, text=f'  "{ex[:80]}"',
                                     font=ctk.CTkFont(family="Segoe UI", size=9, slant="italic"),
                                     text_color=C.DIM, anchor="w")
                        ex_lbl.pack(fill="x", padx=10, pady=0)
                        if len(ex) > 60:
                            W.magnify(ex_lbl, text=f'"{ex}"')
                    ctk.CTkFrame(card, height=4, fg_color="transparent").pack()

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.BG)
        self._build()
