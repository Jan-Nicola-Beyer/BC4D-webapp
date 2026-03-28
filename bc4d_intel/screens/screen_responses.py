"""Responses screen — row-level view with editable category assignments.

Two-level dropdown: Main Category → Sub-Category
Add new categories on the fly.
All changes saved immediately and propagated to other screens.
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

        # Filter + action bar
        action_bar = ctk.CTkFrame(self, fg_color="transparent")
        action_bar.pack(fill="x", padx=30, pady=(4, 0))

        ctk.CTkLabel(action_bar, text="Filter:",
                     font=ctk.CTkFont(family="Segoe UI", size=10),
                     text_color=C.MUTED).pack(side="left", padx=(0, 6))

        self._conf_filter = ctk.StringVar(value="all")
        for label, val in [("All", "all"), ("High", "high"), ("Medium", "medium"), ("Low", "low")]:
            ctk.CTkRadioButton(
                action_bar, text=label, variable=self._conf_filter, value=val,
                font=ctk.CTkFont(family="Segoe UI", size=10), text_color=C.MUTED, height=22,
                command=self._refresh_list,
            ).pack(side="left", padx=4)

        # Add new category button
        ctk.CTkButton(action_bar, text="+ Add Category", width=120, height=26,
                       fg_color=C.BC4D_TEAL, hover_color="#047857",
                       font=ctk.CTkFont(size=10, weight="bold"), corner_radius=4,
                       command=self._add_category).pack(side="right", padx=(8, 0))

        self._count_lbl = ctk.CTkLabel(action_bar, text="",
            font=ctk.CTkFont(family="Consolas", size=10), text_color=C.MUTED)
        self._count_lbl.pack(side="right")

        # Response list
        self._list_scroll = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self._list_scroll.pack(fill="both", expand=True, padx=20, pady=8)

        W.muted_label(self._list_scroll,
            "Select a question above to see individual responses.\n"
            "Each response shows its assigned Main Category > Sub-Category.\n"
            "Use the dropdowns to reassign. Changes are saved immediately.",
            size=12).pack(padx=20, pady=40)

    def refresh(self):
        results = getattr(self.app, "_analysis_results", {})
        if not results:
            # Try to reconstruct from app_state
            if self.app.app_state.tagged_responses and self.app.app_state.taxonomies:
                results = {}
                for label in self.app.app_state.tagged_responses:
                    results[label] = {
                        "taxonomy": self.app.app_state.taxonomies.get(label, {}),
                        "flat_taxonomy": self.app.app_state.flat_taxonomies.get(label, []),
                        "classifications": self.app.app_state.tagged_responses[label],
                    }
                self.app._analysis_results = results

        if results:
            labels = list(results.keys())
            self._question_menu.configure(values=labels)
            if labels and self._question_var.get() in ("Select a question...", "Run AI Analysis first"):
                self._question_var.set(labels[0])
                self._on_question_change(labels[0])

    def _on_question_change(self, label):
        self._current_question = label
        self._refresh_list()

    def _get_data(self):
        """Get current question's data from analysis results."""
        results = getattr(self.app, "_analysis_results", {})
        return results.get(self._current_question) if self._current_question else None

    def _refresh_list(self):
        data = self._get_data()
        if not data:
            return

        for w in self._list_scroll.winfo_children():
            w.destroy()

        classifications = data.get("classifications", [])
        flat_tax = data.get("flat_taxonomy", [])

        # Build lookup tables
        cat_titles = {c["id"]: c["title"] for c in flat_tax}
        cat_mains = {c["id"]: c["main_category"] for c in flat_tax}

        # Build two-level dropdown values
        main_cats = list(dict.fromkeys(c["main_category"] for c in flat_tax))
        sub_by_main = {}
        for c in flat_tax:
            sub_by_main.setdefault(c["main_category"], []).append(c)

        # Filter
        conf_filter = self._conf_filter.get()
        if conf_filter == "all":
            visible = list(enumerate(classifications))
        else:
            visible = [(i, c) for i, c in enumerate(classifications) if c["confidence"] == conf_filter]

        self._count_lbl.configure(text=f"{len(visible)}/{len(classifications)} shown")

        for idx, item in visible:
            cid = item.get("human_override") or item["cluster_id"]
            conf = item["confidence"]
            main_cat = cat_mains.get(cid, "Unknown")
            sub_cat = cat_titles.get(cid, cid)

            card = ctk.CTkFrame(self._list_scroll, fg_color=C.PANEL, corner_radius=6)
            card.pack(fill="x", padx=4, pady=3)

            # Row 1: Confidence + category display + dropdowns
            top_row = ctk.CTkFrame(card, fg_color="transparent")
            top_row.pack(fill="x", padx=10, pady=(6, 2))

            conf_color = C.SUCCESS if conf == "high" else (C.WARN if conf == "medium" else C.MUTED)
            ctk.CTkLabel(top_row, text=conf.upper()[:3], width=35,
                         font=ctk.CTkFont(family="Consolas", size=9, weight="bold"),
                         text_color=conf_color).pack(side="left", padx=(0, 6))

            if item.get("human_override"):
                ctk.CTkLabel(top_row, text="(edited)",
                             font=ctk.CTkFont(size=8), text_color=C.WARN).pack(side="left", padx=(0, 4))

            # Two-level dropdowns (right side)
            dd_frame = ctk.CTkFrame(top_row, fg_color="transparent")
            dd_frame.pack(side="right")

            # Sub-category dropdown
            sub_values = [s["title"] for s in sub_by_main.get(main_cat, flat_tax)]
            sub_var = ctk.StringVar(value=sub_cat)
            sub_dd = ctk.CTkOptionMenu(
                dd_frame, variable=sub_var, values=sub_values,
                font=ctk.CTkFont(size=9), height=22, width=180,
                fg_color=C.DIM, button_color=C.MUTED,
                command=lambda v, i=idx, mc=main_cat: self._reassign_sub(i, mc, v),
            )
            sub_dd.pack(side="right", padx=2)

            ctk.CTkLabel(dd_frame, text=">",
                         font=ctk.CTkFont(size=9), text_color=C.DIM).pack(side="right", padx=2)

            # Main category dropdown
            main_var = ctk.StringVar(value=main_cat)
            main_dd = ctk.CTkOptionMenu(
                dd_frame, variable=main_var, values=main_cats,
                font=ctk.CTkFont(size=9, weight="bold"), height=22, width=160,
                fg_color=C.ACCENT, button_color=C.ACCENT,
                command=lambda v, i=idx, sd=sub_dd, sv=sub_var: self._on_main_change(i, v, sd, sv),
            )
            main_dd.pack(side="right", padx=2)

            # Row 2: Full response text
            ctk.CTkLabel(card, text=item["text"],
                         font=ctk.CTkFont(family="Segoe UI", size=11),
                         text_color=C.TEXT, anchor="w", wraplength=700,
                         justify="left").pack(fill="x", padx=10, pady=(0, 6))

    def _on_main_change(self, idx, new_main, sub_dropdown, sub_var):
        """When main category changes, update sub-category dropdown options."""
        data = self._get_data()
        if not data:
            return
        flat_tax = data.get("flat_taxonomy", [])
        subs = [c for c in flat_tax if c["main_category"] == new_main]
        sub_titles = [s["title"] for s in subs]
        sub_dropdown.configure(values=sub_titles)
        if sub_titles:
            sub_var.set(sub_titles[0])
            self._reassign_sub(idx, new_main, sub_titles[0])

    def _reassign_sub(self, idx, main_cat, sub_title):
        """Reassign a response to a specific sub-category. Saves immediately."""
        data = self._get_data()
        if not data:
            return

        flat_tax = data.get("flat_taxonomy", [])
        for cat in flat_tax:
            if cat["title"] == sub_title and cat["main_category"] == main_cat:
                data["classifications"][idx]["human_override"] = cat["id"]
                data["classifications"][idx]["main_category"] = main_cat
                data["classifications"][idx]["cluster_title"] = sub_title
                break

        # SAVE IMMEDIATELY — never lose edits
        self._save_and_propagate()

    def _add_category(self):
        """Add a new category via popup dialog."""
        if not self._current_question:
            return

        popup = ctk.CTkToplevel(self)
        popup.title("Add New Category")
        popup.geometry("400x250")
        popup.attributes("-topmost", True)

        ctk.CTkLabel(popup, text="Add New Category",
                     font=ctk.CTkFont(size=14, weight="bold"),
                     text_color=C.TEXT).pack(padx=20, pady=(16, 8))

        ctk.CTkLabel(popup, text="Main Category:",
                     font=ctk.CTkFont(size=11), text_color=C.MUTED).pack(padx=20, anchor="w")
        main_entry = ctk.CTkEntry(popup, height=30, placeholder_text="e.g., Verbesserungsvorschläge")
        main_entry.pack(fill="x", padx=20, pady=(0, 8))

        ctk.CTkLabel(popup, text="Sub-Category:",
                     font=ctk.CTkFont(size=11), text_color=C.MUTED).pack(padx=20, anchor="w")
        sub_entry = ctk.CTkEntry(popup, height=30, placeholder_text="e.g., Zeitliche Flexibilität")
        sub_entry.pack(fill="x", padx=20, pady=(0, 12))

        def _create():
            main = main_entry.get().strip()
            sub = sub_entry.get().strip()
            if not main or not sub:
                return

            data = self._get_data()
            if not data:
                popup.destroy()
                return

            # Generate new ID
            existing_ids = {c["id"] for c in data.get("flat_taxonomy", [])}
            new_id = f"cat_custom_{len(existing_ids) + 1}"

            # Add to flat taxonomy
            data["flat_taxonomy"].append({
                "id": new_id,
                "title": sub,
                "main_category": main,
                "description": "Manuell hinzugefügt",
                "count": 0,
            })

            # Add to hierarchical taxonomy
            taxonomy = data.get("taxonomy", {"categories": []})
            found_main = False
            for mc in taxonomy.get("categories", []):
                if mc["main_category"] == main:
                    mc["sub_categories"].append({
                        "id": new_id, "title": sub, "examples": [],
                        "include_rule": "Manuell hinzugefügt", "exclude_rule": "",
                    })
                    found_main = True
                    break
            if not found_main:
                taxonomy.setdefault("categories", []).append({
                    "id": f"main_{new_id}",
                    "main_category": main,
                    "sub_categories": [{
                        "id": new_id, "title": sub, "examples": [],
                        "include_rule": "Manuell hinzugefügt", "exclude_rule": "",
                    }]
                })

            self._save_and_propagate()
            self._refresh_list()
            popup.destroy()

        ctk.CTkButton(popup, text="Create Category", fg_color=C.ACCENT,
                       command=_create).pack(pady=8)

    def _save_and_propagate(self):
        """Save current state and update all dependent screens."""
        if not self._current_question:
            return

        data = self._get_data()
        if not data:
            return

        # Update flat_taxonomy counts
        counts = {}
        for c in data.get("classifications", []):
            cid = c.get("human_override") or c["cluster_id"]
            counts[cid] = counts.get(cid, 0) + 1
        for cat in data.get("flat_taxonomy", []):
            cat["count"] = counts.get(cat["id"], 0)

        # Persist to app_state
        self.app.app_state.tagged_responses[self._current_question] = data["classifications"]
        self.app.app_state.taxonomies[self._current_question] = data.get("taxonomy", {})
        self.app.app_state.flat_taxonomies[self._current_question] = data.get("flat_taxonomy", [])
        self.app.app_state.save()

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.BG)
        self._build()
