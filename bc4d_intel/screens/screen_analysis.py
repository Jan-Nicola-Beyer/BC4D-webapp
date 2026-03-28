"""AI Analysis screen — explains the process, triggers analysis, shows progress.

This is where the user starts the free-text analysis pipeline.
Shows a clear explanation of what happens, cost estimate, and progress.
After completion, directs user to Clusters and Responses screens.
"""

from __future__ import annotations
import threading, time
import customtkinter as ctk
from bc4d_intel import constants as C
from bc4d_intel.ui import widgets as W


class AnalysisScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C.BG, corner_radius=0)
        self.app = app
        self._build()

    def _build(self):
        from bc4d_intel.ui.guide import workflow_steps, info_banner, progress_panel

        top = W.make_toolbar(self, height=100)
        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=30, pady=8)
        workflow_steps(inner, current_step=2).pack(anchor="w", pady=(0, 4))
        W.heading(inner, "AI Analysis", size=22).pack(anchor="w")

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=30, pady=10)

        # ── Explanation ──
        info_banner(body,
            "How Free-Text Analysis Works",
            "The system analyzes all open-ended survey responses in three steps:\n\n"
            "Step 1 — Taxonomy Design (Sonnet AI)\n"
            "AI reads ALL responses for each question (full text, no sampling) and "
            "designs a hierarchical taxonomy with main categories and sub-categories. "
            "Each category gets exemplar responses and coding rules.\n\n"
            "Step 2 — Classification (Cross-Encoder, free)\n"
            "A local AI model scores each response against every category. "
            "Responses are assigned to the best-matching category. "
            "Confidence is based on the mathematical margin between top categories.\n\n"
            "Step 3 — Edge Case Review (Sonnet AI)\n"
            "Only ambiguous responses (typically 10-20%) are sent back to the AI "
            "for a second opinion. This keeps costs low while ensuring quality.\n\n"
            "After analysis, review results in:\n"
            "  Clusters — see the taxonomy per question, with a semantic map\n"
            "  Responses — see each response and its assigned category, editable",
            icon="\U0001F916",
        ).pack(fill="x", pady=(0, 12))

        # ── Cost & time estimate ──
        est_card = W.make_card(body)
        est_card.pack(fill="x", pady=8)
        est_inner = ctk.CTkFrame(est_card, fg_color="transparent")
        est_inner.pack(fill="x", padx=16, pady=12)

        self._estimate_lbl = ctk.CTkLabel(est_inner,
            text="Load survey data first to see cost and time estimates.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=C.MUTED, justify="left")
        self._estimate_lbl.pack(anchor="w")

        # ── Action button ──
        btn_row = ctk.CTkFrame(body, fg_color="transparent")
        btn_row.pack(fill="x", pady=12)

        self._run_btn = ctk.CTkButton(
            btn_row, text="Start Free-Text Analysis", width=250, height=44,
            fg_color=C.ACCENT, hover_color=C.SELECT,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            corner_radius=8, command=self._run_analysis,
        )
        self._run_btn.pack(side="left", padx=(0, 16))

        self._status_lbl = ctk.CTkLabel(btn_row, text="",
            font=ctk.CTkFont(family="Segoe UI", size=11), text_color=C.MUTED)
        self._status_lbl.pack(side="left")

        # ── Progress area ──
        self._progress_area = ctk.CTkFrame(body, fg_color="transparent")
        self._progress_area.pack(fill="x", pady=8)

        # ── Results summary (shown after completion) ──
        self._results_area = ctk.CTkFrame(body, fg_color="transparent")
        self._results_area.pack(fill="x", pady=8)

    def refresh(self):
        """Update estimates when screen becomes visible."""
        if hasattr(self.app, "_match_result") and self.app._match_result:
            import_screen = self.app._frames.get("import")
            if import_screen:
                total = 0
                n_questions = 0
                for roles in [import_screen._pre_roles, import_screen._post_roles]:
                    for c, r in roles.items():
                        if r == "free_text":
                            n_questions += 1
                            total += 100  # rough estimate
                n_batches = (total + 24) // 25
                cost = n_questions * 0.03 + n_batches * 0.005 + n_questions * 0.01
                est_time = n_questions * 10 + n_batches * 4

                self._estimate_lbl.configure(
                    text=f"Estimated: {n_questions} questions, ~{total} responses\n"
                         f"Cost: ~${cost:.2f} (taxonomy + edge cases)\n"
                         f"Time: ~{est_time // 60}m {est_time % 60}s\n"
                         f"Cross-encoder classification is free (local model)",
                    text_color=C.TEXT)

        # Show completion if analysis already done
        if hasattr(self.app, "_analysis_results") and self.app._analysis_results:
            self._show_completion()

    def _run_analysis(self):
        """Run the full pipeline on all free-text questions."""
        if not hasattr(self.app, "_match_result") or not self.app._match_result:
            self._status_lbl.configure(text="Load data first (Import screen).", text_color=C.DANGER)
            return
        api_key = self.app.app_state.api_key
        if not api_key:
            self._status_lbl.configure(text="Set API key in Settings.", text_color=C.DANGER)
            return

        self._run_btn.configure(state="disabled", text="Analyzing...")

        # Show progress
        for w in self._progress_area.winfo_children():
            w.destroy()
        from bc4d_intel.ui.guide import progress_panel
        self._progress = progress_panel(self._progress_area)
        self._progress["frame"].pack(fill="x")
        self._start_time = time.time()

        def work():
            from bc4d_intel.core.embedder import full_pipeline
            import_screen = self.app._frames.get("import")
            if not import_screen:
                return

            result = self.app._match_result
            all_results = {}
            failed = []

            all_ft = []
            for survey_type, df_key, roles in [
                ("Pre", "pre_all", import_screen._pre_roles),
                ("Post", "post_all", import_screen._post_roles),
            ]:
                df = result[df_key]
                for col, role in roles.items():
                    if role == "free_text":
                        responses = [r for r in df[col].dropna().astype(str).tolist()
                                     if len(r.strip()) > 5]
                        if len(responses) >= 5:
                            label = f"[{survey_type}] {col[:45]}"
                            all_ft.append((label, col, responses))

            total_q = len(all_ft)
            for qi, (label, col_name, responses) in enumerate(all_ft):
                pct = (qi + 0.5) / max(total_q, 1)  # mid-question progress
                self.after(0, lambda p=pct, l=label, n=len(responses):
                    self._update_progress(p, f"Analyzing: {l[:35]}... ({n} responses)"))

                def on_progress(msg):
                    self.after(0, lambda m=msg: self._progress["detail_label"].configure(text=m))

                try:
                    # CACHE-FIRST: check if responses already classified
                    from bc4d_intel.core.answer_cache import classify_from_cache, add_to_cache
                    cached, uncached = classify_from_cache(
                        label, responses, progress_cb=on_progress)

                    if uncached:
                        # AI only for uncached responses
                        on_progress(f"AI classifying {len(uncached)} new responses "
                                    f"({len(cached)} from cache)...")
                        res = full_pipeline(uncached, api_key, question=col_name,
                                            progress_cb=on_progress)
                        # Merge cached + AI results
                        res["classifications"] = cached + res["classifications"]
                        # Add new AI results to cache for future use
                        add_to_cache(label, res["classifications"],
                                     staffel=self.app.app_state.staffel_name)
                    else:
                        # 100% cache hit — no AI needed!
                        on_progress(f"100% cache hit! All {len(cached)} from cache (free)")
                        res = {
                            "taxonomy": self.app.app_state.taxonomies.get(label, {}),
                            "flat_taxonomy": self.app.app_state.flat_taxonomies.get(label, []),
                            "classifications": cached,
                        }

                    all_results[label] = res

                    # CHECKPOINT: save after each question
                    self.app.app_state.tagged_responses[label] = res["classifications"]
                    self.app.app_state.taxonomies[label] = res.get("taxonomy", {})
                    self.app.app_state.flat_taxonomies[label] = res.get("flat_taxonomy", [])
                    self.app.app_state.save()

                except Exception as e:
                    failed.append(label)
                    self.after(0, lambda err=str(e), l=label: self._status_lbl.configure(
                        text=f"Error on {l[:20]}: {err}", text_color=C.DANGER))

            # Final progress update
            self.after(0, lambda: self._update_progress(1.0, "Complete!"))

            # Store globally (includes all successful results)
            self.app._analysis_results = all_results

            self.after(0, self._show_completion)

        threading.Thread(target=work, daemon=True).start()

    def _update_progress(self, pct, detail):
        if hasattr(self, "_progress"):
            self._progress["bar"].set(min(pct, 0.99))
            self._progress["pct_label"].configure(text=f"{int(pct * 100)}%")
            self._progress["detail_label"].configure(text=detail)
            elapsed = int(time.time() - self._start_time)
            if pct > 0.05:
                eta = int(elapsed / pct * (1 - pct))
                self._progress["eta_label"].configure(text=f"~{eta // 60}m{eta % 60:02d}s left")

    def _show_completion(self):
        self._run_btn.configure(state="normal", text="Re-run Analysis")
        results = getattr(self.app, "_analysis_results", {})

        for w in self._results_area.winfo_children():
            w.destroy()

        # Summary card
        card = ctk.CTkFrame(self._results_area, fg_color=C.SUCCESS, corner_radius=8)
        card.pack(fill="x", pady=8)
        card_inner = ctk.CTkFrame(card, fg_color="transparent")
        card_inner.pack(fill="x", padx=16, pady=12)

        total_cats = sum(len(r.get("flat_taxonomy", [])) for r in results.values())
        total_resp = sum(len(r.get("classifications", [])) for r in results.values())
        total_high = sum(1 for r in results.values()
                         for c in r.get("classifications", []) if c["confidence"] == "high")

        ctk.CTkLabel(card_inner, text="Analysis Complete",
                     font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
                     text_color="#ffffff").pack(anchor="w")
        ctk.CTkLabel(card_inner,
            text=f"{len(results)} questions analyzed\n"
                 f"{total_cats} categories discovered\n"
                 f"{total_resp} responses classified\n"
                 f"{total_high} high-confidence ({int(total_high / max(total_resp, 1) * 100)}%)",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#e0e0e0", justify="left").pack(anchor="w", pady=(4, 8))

        btn_row = ctk.CTkFrame(card_inner, fg_color="transparent")
        btn_row.pack(fill="x")

        ctk.CTkButton(btn_row, text="View Clusters  \u2192", width=150, height=36,
                       fg_color="#ffffff", text_color=C.SUCCESS, hover_color="#f0f0f0",
                       font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                       corner_radius=6,
                       command=lambda: self.app.show_frame("clusters"),
                       ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(btn_row, text="View Responses  \u2192", width=150, height=36,
                       fg_color="#ffffff", text_color=C.SUCCESS, hover_color="#f0f0f0",
                       font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                       corner_radius=6,
                       command=lambda: self.app.show_frame("responses"),
                       ).pack(side="left")

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.BG)
        self._build()
