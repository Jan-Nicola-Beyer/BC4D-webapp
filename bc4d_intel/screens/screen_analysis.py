"""AI Analysis screen — explains the process, triggers analysis, shows progress.

This is where the user starts the free-text analysis pipeline.
Shows a clear explanation of what happens, cost estimate, and progress.
After completion, directs user to Clusters and Responses screens.
"""

from __future__ import annotations
import os, threading, time
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
            "The system reads all open-ended survey responses and groups them "
            "into meaningful thematic categories. This helps you quickly understand "
            "what participants said, without reading every response individually.\n\n"
            "What happens when you click 'Start':\n\n"
            "1. Category Design — The AI reads every response for each question "
            "and creates a set of thematic categories (e.g. 'Praise for Trainer', "
            "'Time Management Criticism', 'Content Suggestions'). Each category "
            "gets a clear definition and example responses. This only happens the "
            "first time — categories are saved and reused for future staffels.\n\n"
            "2. Classification — The AI assigns each response to the most fitting "
            "category based on its actual content and meaning. Responses that were "
            "already seen in a previous staffel are recognised automatically (free).\n\n"
            "After analysis, you can review the results:\n"
            "  Clusters — see all categories per question with counts\n"
            "  Responses — see each response with its category (editable)",
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
        self._run_btn.pack(side="left", padx=(0, 8))

        ctk.CTkButton(
            btn_row, text="Import Results", width=130, height=44,
            fg_color=C.BTN, hover_color=C.SELECT,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            corner_radius=8, command=self._import_results,
        ).pack(side="left", padx=(0, 16))

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
                result = self.app._match_result
                n_questions = 0
                total_responses = 0
                for survey_type, df_key, roles in [
                    ("Pre", "pre_all", import_screen._pre_roles),
                    ("Post", "post_all", import_screen._post_roles),
                ]:
                    df = result.get(df_key)
                    if df is None:
                        continue
                    for col, role in roles.items():
                        if role == "free_text" and col in df.columns:
                            n_resp = len([r for r in df[col].dropna().astype(str).tolist()
                                          if len(r.strip()) > 5])
                            if n_resp >= 5:
                                n_questions += 1
                                total_responses += n_resp

                # Check which questions already have cached taxonomies
                from bc4d_intel.core.answer_cache import get_cached_taxonomy
                n_new = 0  # questions needing taxonomy design
                for survey_type, df_key, roles in [
                    ("Pre", "pre_all", import_screen._pre_roles),
                    ("Post", "post_all", import_screen._post_roles),
                ]:
                    for col, role in roles.items():
                        if role == "free_text":
                            label = f"[{survey_type}] {col[:45]}"
                            if not get_cached_taxonomy(label):
                                n_new += 1

                # Cost: taxonomy design ~$0.03 (Sonnet, new questions only)
                #        + classification ~$0.028/question (Haiku, all)
                taxonomy_cost = n_new * 0.03
                classify_batches = (total_responses + 19) // 20
                classify_cost = classify_batches * 0.002
                total_cost = taxonomy_cost + classify_cost
                est_time = n_questions * 2 + classify_batches * 2  # ~2s per batch

                lines = [
                    f"Found: {n_questions} open-ended questions, "
                    f"{total_responses} responses total",
                    "",
                ]
                if n_new > 0:
                    lines.append(f"Category design (first time): "
                                 f"{n_new} questions x ~$0.03 = ~${taxonomy_cost:.2f}")
                else:
                    lines.append("Category design: $0.00 (reusing saved categories)")
                lines.extend([
                    f"Classification: {total_responses} responses in "
                    f"{classify_batches} batches x ~$0.002 = ~${classify_cost:.3f}",
                    "",
                    f"Estimated total cost: ~${total_cost:.2f}",
                    f"Estimated time: ~{max(est_time, 10)}s",
                ])

                self._estimate_lbl.configure(
                    text="\n".join(lines),
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
                self.after(0, lambda: self._status_lbl.configure(
                    text="Load survey files first (Import screen).", text_color=C.DANGER))
                self.after(0, lambda: self._run_btn.configure(state="normal", text="Start Free-Text Analysis"))
                return

            result = getattr(self.app, "_match_result", None)
            if not result:
                self.after(0, lambda: self._status_lbl.configure(
                    text="Load both survey files first (Import screen).", text_color=C.DANGER))
                self.after(0, lambda: self._run_btn.configure(state="normal", text="Start Free-Text Analysis"))
                return

            all_results = {}
            failed = []

            all_ft = []
            for survey_type, df_key, roles in [
                ("Pre", "pre_all", import_screen._pre_roles),
                ("Post", "post_all", import_screen._post_roles),
            ]:
                df = result.get(df_key)
                if df is None:
                    continue
                for col, role in roles.items():
                    if role == "free_text":
                        responses = [r for r in df[col].dropna().astype(str).tolist()
                                     if len(r.strip()) > 5]
                        if len(responses) >= 5:
                            label = f"[{survey_type}] {col[:45]}"
                            all_ft.append((label, col, responses))

            total_q = len(all_ft)
            if total_q == 0:
                # Debug: log what roles were found
                import logging
                log = logging.getLogger("bc4d_intel")
                pre_r = import_screen._pre_roles if import_screen else {}
                post_r = import_screen._post_roles if import_screen else {}
                n_pre_ft = sum(1 for r in pre_r.values() if r == "free_text")
                n_post_ft = sum(1 for r in post_r.values() if r == "free_text")
                from collections import Counter
                pre_counts = dict(Counter(pre_r.values()))
                post_counts = dict(Counter(post_r.values()))
                debug_msg = (f"No open-ended questions found. "
                             f"Pre: {pre_counts}, Post: {post_counts}")
                log.warning(debug_msg)
                self.after(0, lambda m=debug_msg: self._status_lbl.configure(
                    text=m, text_color=C.DANGER))
                self.after(0, lambda: self._run_btn.configure(state="normal", text="Start Free-Text Analysis"))
                return
            n_errors = 0

            for qi, (label, col_name, responses) in enumerate(all_ft):
                # Check if user cancelled (closed app or clicked stop)
                if self.app._analysis_cancel:
                    break

                pct = (qi + 0.5) / max(total_q, 1)
                self.after(0, lambda p=pct, l=label, n=len(responses):
                    self._update_progress(p, f"Analyzing: {l[:35]}... ({n} responses)"))

                def on_progress(msg):
                    self.after(0, lambda m=msg: self._progress["detail_label"].configure(text=m))

                try:
                    from bc4d_intel.core.answer_cache import (
                        deduplicate, add_to_cache,
                        get_cached_taxonomy, save_taxonomy,
                        classify_with_llm,
                    )

                    # ── Step 1: Taxonomy ────────────────────────────
                    taxonomy = get_cached_taxonomy(label)

                    if not taxonomy:
                        # Staffel 1: Sonnet designs taxonomy + classifies
                        on_progress(f"First time: AI building taxonomy for "
                                    f"{len(responses)} responses...")
                        res = full_pipeline(responses, api_key,
                                            question=col_name,
                                            progress_cb=on_progress)
                        if res.get("taxonomy"):
                            save_taxonomy(label, res["taxonomy"],
                                          n_responses=len(responses))
                            taxonomy = res["taxonomy"]
                        classified = res.get("classifications", [])

                    else:
                        # ── Step 2: Deduplication (FREE) ────────────
                        deduped, remaining = deduplicate(
                            label, responses, progress_cb=on_progress)

                        # ── Step 3: LLM Classification (Haiku) ─────
                        if remaining:
                            on_progress(f"Haiku classifying {len(remaining)} "
                                        f"responses ({len(deduped)} deduped)...")
                            llm_classified = classify_with_llm(
                                col_name, remaining, taxonomy, api_key,
                                progress_cb=on_progress)
                        else:
                            llm_classified = []

                        classified = deduped + llm_classified

                    # Build flat_taxonomy for UI
                    flat_taxonomy = []
                    if taxonomy:
                        for mc in taxonomy.get("categories", []):
                            for sub in mc.get("sub_categories", []):
                                count = sum(1 for c in classified
                                            if (c.get("human_override") or
                                                c.get("cluster_id", "")) == sub["id"])
                                flat_taxonomy.append({
                                    "id": sub["id"],
                                    "title": sub["title"],
                                    "main_category": mc["main_category"],
                                    "description": sub.get("include_rule", ""),
                                    "count": count,
                                })

                    res = {
                        "taxonomy": taxonomy or {},
                        "flat_taxonomy": flat_taxonomy,
                        "classifications": classified,
                    }

                    # ── Step 5: Cache results ──────────────────────
                    add_to_cache(label, classified,
                                 staffel=self.app.app_state.staffel_name)

                    all_results[label] = res

                    # CHECKPOINT: save after each question
                    self.app.app_state.tagged_responses[label] = res["classifications"]
                    self.app.app_state.taxonomies[label] = res.get("taxonomy", {})
                    self.app.app_state.flat_taxonomies[label] = res.get("flat_taxonomy", [])
                    self.app.app_state.save()

                    # Count classification errors in this question
                    error_count = sum(1 for c in res.get("classifications", [])
                                      if c.get("match_type") == "error")
                    if error_count > 0:
                        n_errors += error_count
                        on_progress(f"Warning: {error_count} responses could not "
                                    f"be classified (API issue)")

                except Exception as e:
                    failed.append(label)
                    self.after(0, lambda err=str(e), l=label: self._status_lbl.configure(
                        text=f"Error on {l[:20]}: {err}", text_color=C.DANGER))

            # Final progress update
            self.after(0, lambda: self._update_progress(1.0, "Complete!"))

            # Store globally
            self.app._analysis_results = all_results
            self.app._analysis_cancel = False

            # Clear old report sections — data has changed, report must be regenerated
            self.app.app_state.report_sections = {}
            report_screen = self.app._frames.get("report")
            if report_screen:
                report_screen._sections = {}

            # Unlock sidebar
            if all_results:
                self.after(0, lambda: self.app._sidebar.unlock_analysis_screens())

            # Show warning if there were errors
            if n_errors > 0 or failed:
                self.after(0, lambda ne=n_errors, nf=len(failed):
                    self._status_lbl.configure(
                        text=f"Done with issues: {ne} classification errors, "
                             f"{nf} failed questions. Review in Responses screen.",
                        text_color=C.WARN))

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
                       ).pack(side="left", padx=(0, 8))

        ctk.CTkButton(btn_row, text="Export Results", width=130, height=36,
                       fg_color="#ffffff", text_color=C.SUCCESS, hover_color="#f0f0f0",
                       font=ctk.CTkFont(family="Segoe UI", size=12),
                       corner_radius=6,
                       command=self._export_results,
                       ).pack(side="left")

    def _export_results(self):
        """Export analysis results (taxonomies + classifications) to a JSON file."""
        import json
        from tkinter import filedialog

        results = getattr(self.app, "_analysis_results", {})
        if not results:
            return

        path = filedialog.asksaveasfilename(
            title="Export Analysis Results",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=f"bc4d_analysis_{self.app.app_state.staffel_name or 'export'}.json",
        )
        if not path:
            return

        export_data = {
            "version": "v5",
            "staffel": self.app.app_state.staffel_name,
            "questions": {},
        }
        for label, res in results.items():
            export_data["questions"][label] = {
                "taxonomy": res.get("taxonomy", {}),
                "flat_taxonomy": res.get("flat_taxonomy", []),
                "classifications": res.get("classifications", []),
            }

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)
            self._status_lbl.configure(
                text=f"Exported to {os.path.basename(path)}",
                text_color=C.SUCCESS)
        except Exception as e:
            self._status_lbl.configure(text=f"Export failed: {e}", text_color=C.DANGER)

    def _import_results(self):
        """Import analysis results from a JSON file exported by another user."""
        import json
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title="Import Analysis Results",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not path:
            return

        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if "questions" not in data:
                self._status_lbl.configure(
                    text="Invalid file: no 'questions' key found.", text_color=C.DANGER)
                return

            # Restore into app state
            all_results = {}
            for label, qdata in data["questions"].items():
                all_results[label] = {
                    "taxonomy": qdata.get("taxonomy", {}),
                    "flat_taxonomy": qdata.get("flat_taxonomy", []),
                    "classifications": qdata.get("classifications", []),
                }
                self.app.app_state.tagged_responses[label] = qdata.get("classifications", [])
                self.app.app_state.taxonomies[label] = qdata.get("taxonomy", {})
                self.app.app_state.flat_taxonomies[label] = qdata.get("flat_taxonomy", [])

                # Also save taxonomies to cache DB for future dedup
                from bc4d_intel.core.answer_cache import save_taxonomy, add_to_cache
                if qdata.get("taxonomy"):
                    save_taxonomy(label, qdata["taxonomy"])
                if qdata.get("classifications"):
                    add_to_cache(label, qdata["classifications"],
                                 staffel=data.get("staffel", "imported"))

            self.app._analysis_results = all_results
            self.app.app_state.save()

            # Unlock sidebar
            self.app._sidebar.unlock_analysis_screens()

            n_q = len(all_results)
            n_r = sum(len(r.get("classifications", [])) for r in all_results.values())

            # Check if Excel data is loaded for dashboard
            has_excel = hasattr(self.app, "_match_result") and self.app._match_result
            extra_msg = ""
            if not has_excel:
                extra_msg = ("\nFor Dashboard charts, also load the Excel files "
                             "via the Import screen.")

            self._status_lbl.configure(
                text=f"Imported {n_q} questions, {n_r} classifications from "
                     f"{os.path.basename(path)}{extra_msg}",
                text_color=C.SUCCESS)

            self._show_completion()

        except Exception as e:
            self._status_lbl.configure(text=f"Import failed: {e}", text_color=C.DANGER)

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.BG)
        self._build()
