"""Validation screen — AI-discovered taxonomy + human validation.

Three-panel layout:
  LEFT:   Taxonomy editor (cluster titles, descriptions, counts)
  CENTER: Responses grouped by cluster (accept, reassign)
  RIGHT:  Live distribution chart

Two-pass workflow:
  1. AI discovers thematic clusters from ALL responses
  2. AI classifies each response into a cluster
  3. User validates taxonomy (rename, merge clusters)
  4. User validates individual assignments (accept, reassign)
"""

from __future__ import annotations
import threading
import customtkinter as ctk
from bc4d_intel import constants as C
from bc4d_intel.ui import widgets as W

# Cluster colors (cycle for arbitrary number of clusters)
CLUSTER_COLORS = [
    "#C8175D", "#0077B6", "#059669", "#d97706", "#6366f1",
    "#ec4899", "#14b8a6", "#f59e0b", "#a855f7", "#22c55e",
]


class ValidationScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C.BG, corner_radius=0)
        self.app = app
        self._questions = {}       # {label: [response_texts]}
        self._taxonomies = {}      # {label: [{id, title, description}]}
        self._classifications = {} # {label: [{text, cluster_id, confidence, human_override}]}
        self._current_question = None
        self._build()

    def _build(self):
        from bc4d_intel.ui.guide import workflow_steps, info_banner

        # ── Top bar ──
        top = W.make_toolbar(self, height=100)
        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=30, pady=8)

        workflow_steps(inner, current_step=2).pack(anchor="w", pady=(0, 4))
        row = ctk.CTkFrame(inner, fg_color="transparent")
        row.pack(fill="x")
        W.heading(row, "Validation", size=22).pack(side="left")

        btn_row = ctk.CTkFrame(row, fg_color="transparent")
        btn_row.pack(side="right")

        self._analyze_btn = W.accent_button(btn_row, text="Analyze Free Text",
                                             command=self._run_analysis, width=160)
        self._analyze_btn.pack(side="left", padx=(0, 8))

        self._status_lbl = ctk.CTkLabel(btn_row, text="",
                                         font=ctk.CTkFont(family="Segoe UI", size=11),
                                         text_color=C.MUTED)
        self._status_lbl.pack(side="left")

        # ── Body: three columns ──
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=10, pady=5)
        body.columnconfigure(0, weight=1)   # questions + taxonomy
        body.columnconfigure(1, weight=2)   # responses
        body.columnconfigure(2, weight=1)   # chart
        body.rowconfigure(0, weight=1)

        # LEFT: Questions + Taxonomy
        left = W.make_card(body)
        left.grid(row=0, column=0, sticky="nsew", padx=3)

        ctk.CTkLabel(left, text="Questions & Clusters",
                     font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                     text_color=C.TEXT).pack(anchor="w", padx=10, pady=(8, 4))

        self._left_scroll = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self._left_scroll.pack(fill="both", expand=True, padx=4, pady=4)

        info_banner(self._left_scroll,
            "How it works",
            "1. Click 'Analyze Free Text' — AI discovers themes in your responses\n"
            "2. Review the clusters — rename titles, merge similar ones\n"
            "3. Check individual responses — reassign if AI got it wrong\n"
            "4. Distribution charts update live as you validate\n\n"
            "Cost: ~$0.50 | Time: 2-5 minutes",
            icon="\U0001F50D",
        ).pack(fill="x", padx=4, pady=4)

        # CENTER: Responses
        center = W.make_card(body)
        center.grid(row=0, column=1, sticky="nsew", padx=3)

        center_header = ctk.CTkFrame(center, fg_color="transparent")
        center_header.pack(fill="x", padx=10, pady=(8, 2))

        self._response_title = ctk.CTkLabel(center_header, text="Responses",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=C.TEXT)
        self._response_title.pack(side="left")

        self._progress_lbl = ctk.CTkLabel(center_header, text="",
            font=ctk.CTkFont(family="Consolas", size=9), text_color=C.MUTED)
        self._progress_lbl.pack(side="right")

        # Filter bar
        filter_bar = ctk.CTkFrame(center, fg_color="transparent")
        filter_bar.pack(fill="x", padx=10, pady=(0, 4))

        self._conf_filter = ctk.StringVar(value="All")
        for label in ["All", "Low confidence", "Medium", "Reassigned"]:
            val = label.split()[0].lower() if label != "All" else "All"
            ctk.CTkRadioButton(
                filter_bar, text=label, variable=self._conf_filter, value=val,
                font=ctk.CTkFont(family="Segoe UI", size=9),
                text_color=C.MUTED, height=20,
                command=self._refresh_responses,
            ).pack(side="left", padx=3)

        ctk.CTkButton(filter_bar, text="Accept All High", width=120, height=22,
                       fg_color=C.SUCCESS, hover_color="#047857",
                       font=ctk.CTkFont(size=9), corner_radius=3,
                       command=self._batch_accept_high).pack(side="right")

        self._response_scroll = ctk.CTkScrollableFrame(center, fg_color="transparent")
        self._response_scroll.pack(fill="both", expand=True, padx=4, pady=4)

        W.muted_label(self._response_scroll,
            "Select a question on the left to see responses.",
            size=11).pack(padx=10, pady=30)

        # RIGHT: Distribution chart
        right = W.make_card(body)
        right.grid(row=0, column=2, sticky="nsew", padx=3)

        ctk.CTkLabel(right, text="Distribution",
                     font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                     text_color=C.TEXT).pack(anchor="w", padx=10, pady=(8, 4))

        self._chart_frame = ctk.CTkFrame(right, fg_color="transparent")
        self._chart_frame.pack(fill="both", expand=True, padx=4, pady=4)

    # ── Analysis flow ────────────────────────────────────────────

    def _run_analysis(self):
        """Two-pass analysis: induce taxonomy, then classify."""
        if not hasattr(self.app, "_match_result") or not self.app._match_result:
            self._status_lbl.configure(text="Load data first.", text_color=C.DANGER)
            return

        api_key = self.app.app_state.api_key
        if not api_key:
            self._status_lbl.configure(text="Set API key in Settings.", text_color=C.DANGER)
            return

        self._analyze_btn.configure(state="disabled", text="Analyzing...")

        # Show progress in response area
        for w in self._response_scroll.winfo_children():
            w.destroy()
        from bc4d_intel.ui.guide import progress_panel
        self._progress = progress_panel(self._response_scroll)
        self._progress["frame"].pack(fill="x", padx=8, pady=20)

        import time
        self._analysis_start = time.time()

        def work():
            from bc4d_intel.ai.tagger import induce_taxonomy, classify_responses
            import_screen = self.app._frames.get("import")
            if not import_screen:
                return

            result = self.app._match_result
            questions = {}
            taxonomies = {}
            classifications = {}

            # Collect free-text questions
            all_ft = []
            for survey_type, df_key, roles in [
                ("Pre", "pre_all", import_screen._pre_roles),
                ("Post", "post_all", import_screen._post_roles),
            ]:
                df = result[df_key]
                ft_cols = [c for c, r in roles.items() if r == "free_text"]
                for col in ft_cols:
                    responses = [r for r in df[col].dropna().astype(str).tolist()
                                 if len(r.strip()) > 5]
                    if responses:
                        label = f"[{survey_type}] {col[:45]}"
                        all_ft.append((label, col, responses))

            total_q = len(all_ft)
            total_r = sum(len(r) for _, _, r in all_ft)

            for qi, (label, col_name, responses) in enumerate(all_ft):
                # Pass 1: Induce taxonomy
                pct = qi / max(total_q, 1)
                self.after(0, lambda p=pct, l=label: self._update_progress(
                    p, int(p * 100), f"Pass 1: Discovering themes for '{l[:30]}...'"))

                taxonomy = induce_taxonomy(col_name, responses, api_key)
                taxonomies[label] = taxonomy
                questions[label] = responses

                # Pass 2: Classify
                pct2 = (qi + 0.5) / max(total_q, 1)
                self.after(0, lambda p=pct2, l=label, n=len(responses):
                    self._update_progress(p, int(p * 100),
                        f"Pass 2: Classifying {n} responses for '{l[:30]}...'"))

                def on_classify_progress(msg):
                    self.after(0, lambda m=msg: self._progress["detail_label"].configure(text=m))

                classified = classify_responses(responses, taxonomy, api_key,
                                                progress_cb=on_classify_progress)
                classifications[label] = classified

            self._questions = questions
            self._taxonomies = taxonomies
            self._classifications = classifications

            # Save to app state
            self.app.app_state.tagged_responses = {
                k: v for k, v in classifications.items()
            }
            self.app.app_state.save()

            self.after(0, lambda: self._on_analysis_complete(total_r))

        threading.Thread(target=work, daemon=True).start()

    def _update_progress(self, pct_float, pct_int, detail):
        if hasattr(self, "_progress") and self._progress:
            self._progress["bar"].set(min(pct_float, 0.99))
            self._progress["pct_label"].configure(text=f"{min(pct_int, 99)}%")
            self._progress["detail_label"].configure(text=detail)
            import time
            elapsed = int(time.time() - self._analysis_start)
            if pct_float > 0.05:
                eta = int(elapsed / pct_float * (1 - pct_float))
                self._progress["eta_label"].configure(text=f"~{eta//60}m{eta%60:02d}s left")

    def _on_analysis_complete(self, total_responses):
        self._analyze_btn.configure(state="normal", text="Analyze Free Text")
        n_q = len(self._taxonomies)
        n_clusters = sum(len(t) for t in self._taxonomies.values())
        self._status_lbl.configure(
            text=f"Done: {n_q} questions, {n_clusters} clusters, {total_responses} responses.",
            text_color=C.SUCCESS)
        self._populate_question_list()

    # ── Left panel: questions + taxonomy ─────────────────────────

    def _populate_question_list(self):
        for w in self._left_scroll.winfo_children():
            w.destroy()

        for label in self._taxonomies:
            taxonomy = self._taxonomies[label]
            classified = self._classifications.get(label, [])
            n = len(classified)

            # Question header
            q_btn = ctk.CTkButton(
                self._left_scroll,
                text=f"{label[:35]}\n{n} responses, {len(taxonomy)} clusters",
                anchor="w", height=45,
                fg_color=C.PANEL, hover_color=C.SELECT,
                text_color=C.TEXT,
                font=ctk.CTkFont(family="Segoe UI", size=10),
                corner_radius=6,
                command=lambda l=label: self._select_question(l),
            )
            q_btn.pack(fill="x", padx=4, pady=2)

            # Cluster list under this question
            for ci, cluster in enumerate(taxonomy):
                color = CLUSTER_COLORS[ci % len(CLUSTER_COLORS)]
                count = sum(1 for c in classified
                            if (c.get("human_override") or c["cluster_id"]) == cluster["id"])

                cluster_row = ctk.CTkFrame(self._left_scroll, fg_color="transparent")
                cluster_row.pack(fill="x", padx=12, pady=1)

                W.status_badge(cluster_row, f"{count}", color).pack(side="left", padx=(0, 4))

                # Editable cluster title
                title_entry = ctk.CTkEntry(
                    cluster_row, height=22, width=160,
                    font=ctk.CTkFont(family="Segoe UI", size=9),
                    fg_color=C.ENTRY_BG, border_color=C.ENTRY_BORDER,
                )
                title_entry.insert(0, cluster["title"])
                title_entry.pack(side="left", fill="x", expand=True)
                title_entry.bind("<Return>",
                    lambda e, l=label, cid=cluster["id"], entry=title_entry:
                        self._rename_cluster(l, cid, entry.get()))

    def _rename_cluster(self, question_label, cluster_id, new_title):
        """Rename a cluster title."""
        if question_label in self._taxonomies:
            for cluster in self._taxonomies[question_label]:
                if cluster["id"] == cluster_id:
                    cluster["title"] = new_title.strip()
                    break
            self._update_chart()

    def _select_question(self, label):
        """Show responses for a question, grouped by cluster."""
        self._current_question = label
        self._refresh_responses()
        self._update_chart()

    # ── Center panel: responses ──────────────────────────────────

    def _refresh_responses(self):
        if not self._current_question:
            return

        label = self._current_question
        classified = self._classifications.get(label, [])
        taxonomy = self._taxonomies.get(label, [])

        for w in self._response_scroll.winfo_children():
            w.destroy()

        # Apply filter
        conf_filter = self._conf_filter.get()
        if conf_filter == "low":
            visible = [(i, c) for i, c in enumerate(classified) if c["confidence"] == "low"]
        elif conf_filter == "medium":
            visible = [(i, c) for i, c in enumerate(classified) if c["confidence"] in ("low", "medium")]
        elif conf_filter == "reassigned":
            visible = [(i, c) for i, c in enumerate(classified) if c.get("human_override")]
        else:
            visible = list(enumerate(classified))

        n_total = len(classified)
        n_reviewed = sum(1 for c in classified if c["confidence"] == "high" or c.get("human_override"))
        self._response_title.configure(text=f"{label[:40]} ({len(visible)}/{n_total})")
        self._progress_lbl.configure(text=f"{n_reviewed}/{n_total} reviewed")

        # Group by cluster
        cluster_map = {c["id"]: c for c in taxonomy}
        by_cluster = {}
        for idx, item in visible:
            cid = item.get("human_override") or item["cluster_id"]
            by_cluster.setdefault(cid, []).append((idx, item))

        for ci, (cid, items) in enumerate(by_cluster.items()):
            cluster = cluster_map.get(cid, {"title": cid, "id": cid})
            color = CLUSTER_COLORS[ci % len(CLUSTER_COLORS)]

            # Cluster header
            header = ctk.CTkFrame(self._response_scroll, fg_color=color, corner_radius=6)
            header.pack(fill="x", padx=4, pady=(8, 2))
            ctk.CTkLabel(header,
                text=f"{cluster['title']} ({len(items)})",
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color="#ffffff").pack(padx=10, pady=4)

            # Response cards
            for idx, item in items:
                card = ctk.CTkFrame(self._response_scroll, fg_color=C.PANEL, corner_radius=4)
                card.pack(fill="x", padx=8, pady=1)

                card_inner = ctk.CTkFrame(card, fg_color="transparent")
                card_inner.pack(fill="x", padx=8, pady=4)

                # Confidence badge
                conf = item["confidence"]
                conf_color = C.SUCCESS if conf == "high" else (C.WARN if conf == "medium" else C.MUTED)
                ctk.CTkLabel(card_inner, text=conf[:3].upper(), width=30,
                             font=ctk.CTkFont(family="Consolas", size=8, weight="bold"),
                             text_color=conf_color).pack(side="left", padx=(0, 4))

                # Response text
                ctk.CTkLabel(card_inner, text=item["text"][:150],
                             font=ctk.CTkFont(family="Segoe UI", size=9),
                             text_color=C.TEXT, anchor="w", wraplength=350,
                             justify="left").pack(side="left", fill="x", expand=True)

                # Reassign dropdown
                cluster_titles = [c["title"][:20] for c in taxonomy]
                reassign = ctk.CTkOptionMenu(
                    card_inner, values=cluster_titles,
                    font=ctk.CTkFont(size=8), height=20, width=110,
                    fg_color=C.DIM, button_color=C.MUTED,
                    command=lambda v, i=idx, tax=taxonomy: self._reassign(i, v, tax),
                )
                reassign.pack(side="right", padx=2)

    def _reassign(self, idx, new_title, taxonomy):
        """Reassign a response to a different cluster."""
        if not self._current_question:
            return
        classified = self._classifications.get(self._current_question, [])
        if idx < len(classified):
            # Find cluster_id by title
            for c in taxonomy:
                if c["title"][:20] == new_title:
                    classified[idx]["human_override"] = c["id"]
                    break
            self._refresh_responses()
            self._update_chart()

    def _batch_accept_high(self):
        """Accept all high-confidence classifications."""
        if not self._current_question:
            return
        classified = self._classifications.get(self._current_question, [])
        accepted = sum(1 for c in classified if c["confidence"] == "high")
        self._progress_lbl.configure(text=f"Accepted {accepted} high-confidence")
        self._refresh_responses()

    # ── Right panel: distribution chart ──────────────────────────

    def _update_chart(self):
        """Update the distribution chart for the current question."""
        for w in self._chart_frame.winfo_children():
            w.destroy()

        if not self._current_question:
            return

        taxonomy = self._taxonomies.get(self._current_question, [])
        classified = self._classifications.get(self._current_question, [])

        if not taxonomy or not classified:
            return

        # Count per cluster
        counts = {}
        for item in classified:
            cid = item.get("human_override") or item["cluster_id"]
            counts[cid] = counts.get(cid, 0) + 1

        total = len(classified)

        # Build bar chart data
        for ci, cluster in enumerate(taxonomy):
            color = CLUSTER_COLORS[ci % len(CLUSTER_COLORS)]
            count = counts.get(cluster["id"], 0)
            pct = round(count / max(total, 1) * 100, 1)

            row = ctk.CTkFrame(self._chart_frame, fg_color="transparent")
            row.pack(fill="x", padx=4, pady=2)

            # Label
            ctk.CTkLabel(row, text=cluster["title"][:18],
                         font=ctk.CTkFont(family="Segoe UI", size=9),
                         text_color=C.TEXT, width=110, anchor="w").pack(side="left")

            # Bar
            bar_frame = ctk.CTkFrame(row, fg_color=C.ENTRY_BG, height=16, corner_radius=3)
            bar_frame.pack(side="left", fill="x", expand=True, padx=4)
            bar_frame.pack_propagate(False)

            if pct > 0:
                fill = ctk.CTkFrame(bar_frame, fg_color=color, corner_radius=3)
                fill.place(relwidth=pct / 100, relheight=1.0)

            # Count label
            ctk.CTkLabel(row, text=f"{count} ({pct}%)", width=70,
                         font=ctk.CTkFont(family="Consolas", size=9),
                         text_color=C.MUTED).pack(side="right")

    # ── Lifecycle ────────────────────────────────────────────────

    def refresh(self):
        if self.app.app_state.tagged_responses and not self._classifications:
            self._classifications = dict(self.app.app_state.tagged_responses)

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.BG)
        self._build()
