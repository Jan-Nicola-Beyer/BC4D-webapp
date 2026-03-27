"""Responses screen — row-level view of each response + assigned concept.

Dropdown to select question → full-screen table showing:
  - Response text (full, readable)
  - Assigned main category + sub-category
  - Confidence badge
  - Dropdown to reassign to different category
  - Filter by confidence level
"""

from __future__ import annotations
import customtkinter as ctk
from bc4d_intel import constants as C
from bc4d_intel.ui import widgets as W

CLUSTER_COLORS = [
    "#C8175D", "#0077B6", "#059669", "#d97706", "#6366f1",
    "#ec4899", "#14b8a6", "#f59e0b", "#a855f7", "#22c55e",
]


class ResponsesScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C.BG, corner_radius=0)
        self.app = app
        self._current_question = None
        self._build()

    def _build(self):
        from bc4d_intel.ui.guide import workflow_steps

        top = W.make_toolbar(self, height=100)
        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=30, pady=8)
        workflow_steps(inner, current_step=4).pack(anchor="w", pady=(0, 4))

        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        W.heading(row, "Responses", size=22).pack(side="left")

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

        # Filter bar
        filter_bar = ctk.CTkFrame(self, fg_color="transparent")
        filter_bar.pack(fill="x", padx=30, pady=(4, 0))

        ctk.CTkLabel(filter_bar, text="Filter:",
                     font=ctk.CTkFont(family="Segoe UI", size=10),
                     text_color=C.MUTED).pack(side="left", padx=(0, 6))

        self._conf_filter = ctk.StringVar(value="all")
        for label, val in [("All", "all"), ("High", "high"), ("Medium", "medium"), ("Low", "low")]:
            ctk.CTkRadioButton(
                filter_bar, text=label, variable=self._conf_filter, value=val,
                font=ctk.CTkFont(family="Segoe UI", size=10), text_color=C.MUTED, height=22,
                command=self._refresh_list,
            ).pack(side="left", padx=4)

        self._count_lbl = ctk.CTkLabel(filter_bar, text="",
            font=ctk.CTkFont(family="Consolas", size=10), text_color=C.MUTED)
        self._count_lbl.pack(side="right")

        # Response list
        self._list_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._list_scroll.pack(fill="both", expand=True, padx=20, pady=8)

        W.muted_label(self._list_scroll,
            "Select a question above to see individual responses with their assigned categories.\n"
            "Use the dropdown on each response to reassign it to a different category.",
            size=12).pack(padx=20, pady=40)

    def refresh(self):
        results = getattr(self.app, "_analysis_results", {})
        if results:
            labels = list(results.keys())
            self._question_menu.configure(values=labels)

    def _on_question_change(self, label):
        self._current_question = label
        self._refresh_list()

    def _refresh_list(self):
        if not self._current_question:
            return

        results = getattr(self.app, "_analysis_results", {})
        data = results.get(self._current_question)
        if not data:
            return

        for w in self._list_scroll.winfo_children():
            w.destroy()

        classifications = data.get("classifications", [])
        flat_tax = data.get("flat_taxonomy", [])
        cat_titles = {c["id"]: c["title"] for c in flat_tax}
        cat_mains = {c["id"]: c["main_category"] for c in flat_tax}
        dropdown_values = [f"{c['main_category']} > {c['title']}" for c in flat_tax]

        # Filter
        conf_filter = self._conf_filter.get()
        if conf_filter == "all":
            visible = list(enumerate(classifications))
        else:
            visible = [(i, c) for i, c in enumerate(classifications)
                       if c["confidence"] == conf_filter]

        self._count_lbl.configure(text=f"{len(visible)}/{len(classifications)} shown")

        # Render each response
        for idx, item in visible:
            cid = item.get("human_override") or item["cluster_id"]
            conf = item["confidence"]
            main_cat = cat_mains.get(cid, "")
            sub_cat = cat_titles.get(cid, cid)

            card = ctk.CTkFrame(self._list_scroll, fg_color=C.PANEL, corner_radius=6)
            card.pack(fill="x", padx=4, pady=3)

            # Top row: confidence + category
            top_row = ctk.CTkFrame(card, fg_color="transparent")
            top_row.pack(fill="x", padx=10, pady=(6, 2))

            # Confidence badge
            conf_color = C.SUCCESS if conf == "high" else (C.WARN if conf == "medium" else C.MUTED)
            ctk.CTkLabel(top_row, text=conf.upper()[:3], width=35,
                         font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
                         text_color=conf_color).pack(side="left", padx=(0, 6))

            # Category display
            if main_cat:
                ctk.CTkLabel(top_row, text=main_cat,
                             font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
                             text_color=C.ACCENT).pack(side="left", padx=(0, 4))
                ctk.CTkLabel(top_row, text=">",
                             font=ctk.CTkFont(size=9), text_color=C.DIM).pack(side="left", padx=2)

            # Find color for this category
            ci = next((i for i, c in enumerate(flat_tax) if c["id"] == cid), 0)
            color = CLUSTER_COLORS[ci % len(CLUSTER_COLORS)]
            W.status_badge(top_row, sub_cat[:25], color).pack(side="left")

            # Reassign dropdown (right side)
            reassign_var = ctk.StringVar(value=f"{main_cat} > {sub_cat}" if main_cat else sub_cat)
            reassign = ctk.CTkOptionMenu(
                top_row, variable=reassign_var, values=dropdown_values,
                font=ctk.CTkFont(size=9), height=22, width=200,
                fg_color=C.DIM, button_color=C.MUTED,
                command=lambda v, i=idx: self._reassign(i, v),
            )
            reassign.pack(side="right")

            if item.get("human_override"):
                ctk.CTkLabel(top_row, text="(edited)",
                             font=ctk.CTkFont(size=8), text_color=C.WARN).pack(side="right", padx=4)

            # Response text (full, readable)
            ctk.CTkLabel(card, text=item["text"],
                         font=ctk.CTkFont(family="Segoe UI", size=11),
                         text_color=C.TEXT, anchor="w", wraplength=700,
                         justify="left").pack(fill="x", padx=10, pady=(0, 6))

    def _reassign(self, idx, display_value):
        """Reassign a response to a different category."""
        results = getattr(self.app, "_analysis_results", {})
        data = results.get(self._current_question)
        if not data:
            return

        flat_tax = data.get("flat_taxonomy", [])
        # Parse "Main > Sub" format
        parts = display_value.split(" > ")
        sub_title = parts[-1] if parts else display_value

        for cat in flat_tax:
            if cat["title"] == sub_title or display_value == f"{cat['main_category']} > {cat['title']}":
                data["classifications"][idx]["human_override"] = cat["id"]
                break

        self._refresh_list()

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.BG)
        self._build()
