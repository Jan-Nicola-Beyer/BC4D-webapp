"""Import screen — streamlined file loading with advanced settings.

Happy path: load two files → green checkmarks → summary → Continue
Problem path: warning shown → user opens Advanced Settings to fix
"""

from __future__ import annotations
import threading
import customtkinter as ctk
from collections import Counter
from bc4d_intel import constants as C
from bc4d_intel.ui import widgets as W


ROLE_COLORS = {
    "likert": C.BC4D_BLUE, "frequency": C.BC4D_BLUE, "relevance": C.BC4D_BLUE,
    "free_text": C.BC4D_TEAL, "demographic": C.BC4D_AMBER,
    "categorical": C.BC4D_AMBER,
    "pseudokey_street": C.BC4D_PINK, "pseudokey_birthday": C.BC4D_PINK,
    "metadata": "#6b7280", "ignore": "#374151", "other": "#6b7280",
}

ROLE_OPTIONS = ["likert", "frequency", "relevance", "free_text",
                "demographic", "categorical", "pseudokey_street",
                "pseudokey_birthday", "metadata", "ignore"]


class ImportScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C.BG, corner_radius=0)
        self.app = app
        self._pre_df = None
        self._post_df = None
        self._pre_roles = {}
        self._post_roles = {}
        self._advanced_visible = False
        self._build()

    def _build(self):
        from bc4d_intel.ui.guide import workflow_steps

        top = W.make_toolbar(self, height=90)
        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=30, pady=8)

        workflow_steps(inner, current_step=0).pack(anchor="w", pady=(0, 4))
        W.heading(inner, "Import Data", size=22).pack(anchor="w")
        W.muted_label(inner, "Load your pre- and post-training survey files.").pack(anchor="w")

        # ── Main content ──
        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=10)

        # ── File cards (side by side) ──
        file_row = ctk.CTkFrame(body, fg_color="transparent")
        file_row.pack(fill="x", pady=(0, 8))
        file_row.columnconfigure(0, weight=1)
        file_row.columnconfigure(1, weight=1)

        for col_idx, (label, survey_type, icon) in enumerate([
            ("Pre-Survey", "pre", "\U0001F4C4"),
            ("Post-Survey", "post", "\U0001F4CB"),
        ]):
            card = W.make_card(file_row)
            card.grid(row=0, column=col_idx, sticky="ew", padx=4, pady=4)

            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=14, pady=10)

            # Status icon (updates to checkmark on load)
            status_lbl = ctk.CTkLabel(row, text="\u25CB",
                                       font=ctk.CTkFont(size=18),
                                       text_color=C.MUTED, width=30)
            status_lbl.pack(side="left", padx=(0, 6))
            setattr(self, f"_{survey_type}_status", status_lbl)

            ctk.CTkLabel(row, text=f"{icon} {label}",
                         font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                         text_color=C.TEXT).pack(side="left")

            W.accent_button(row, text="Choose File", width=110,
                           command=lambda t=survey_type: self._choose_file(t)
                           ).pack(side="right")

            # File info line
            info_lbl = W.muted_label(card, "No file loaded", size=10)
            info_lbl.pack(fill="x", padx=14, pady=(0, 10))
            setattr(self, f"_{survey_type}_info", info_lbl)

        # ── Summary card (hidden until both loaded) ──
        self._summary_card = ctk.CTkFrame(body, fg_color=C.SUCCESS, corner_radius=8)
        # Not packed yet — shown after both files load

        # ── Warning card (hidden unless issues found) ──
        self._warning_card = ctk.CTkFrame(body, fg_color=C.WARN, corner_radius=8)
        # Not packed yet

        # ── Advanced Settings (collapsed by default) ──
        self._advanced_toggle = ctk.CTkButton(
            body, text="Advanced Settings  \u25BC", height=30,
            fg_color="transparent", hover_color=C.DIM,
            text_color=C.MUTED,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            anchor="w", command=self._toggle_advanced,
        )
        self._advanced_toggle.pack(fill="x", padx=4, pady=(8, 0))

        self._advanced_frame = ctk.CTkFrame(body, fg_color="transparent")
        # Not packed yet — shown on toggle

        # ── Getting started hint (shown when no files loaded) ──
        from bc4d_intel.ui.guide import info_banner
        self._hint = info_banner(body,
            "Getting Started",
            "1. Click 'Choose File' to load the Pre-Survey "
            "(questionnaire filled out BEFORE the training)\n"
            "2. Click 'Choose File' to load the Post-Survey "
            "(questionnaire filled out AFTER the training)\n"
            "3. The system automatically detects column types and "
            "links respondents across both surveys\n\n"
            "You need two Excel files (.xlsx) from the same training cohort.",
            icon="\U0001F4C2",
        )
        self._hint.pack(fill="x", padx=4, pady=12)

    # ── File loading ────────────────────────────────────────────

    def _choose_file(self, survey_type):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title=f"Select {survey_type}-survey Excel file",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")],
        )
        if not path:
            return

        info = getattr(self, f"_{survey_type}_info")
        status = getattr(self, f"_{survey_type}_status")
        info.configure(text=f"Loading...", text_color=C.ACCENT)
        status.configure(text="\u25CB", text_color=C.ACCENT)

        def work():
            from bc4d_intel.core.data_loader import load_survey
            try:
                df, roles = load_survey(path)
                self.after(0, lambda: self._on_loaded(survey_type, path, df, roles))
            except Exception as e:
                self.after(0, lambda: info.configure(
                    text=f"Error: {e}", text_color=C.DANGER))
                self.after(0, lambda: status.configure(
                    text="\u2717", text_color=C.DANGER))

        threading.Thread(target=work, daemon=True).start()

    def _on_loaded(self, survey_type, path, df, roles):
        filename = path.split("/")[-1].split("\\")[-1]
        info = getattr(self, f"_{survey_type}_info")
        status = getattr(self, f"_{survey_type}_status")

        # Count detected types
        counts = Counter(roles.values())
        n_likert = counts.get("likert", 0) + counts.get("frequency", 0) + counts.get("relevance", 0)
        n_ft = counts.get("free_text", 0)
        n_pseudo = counts.get("pseudokey_street", 0) + counts.get("pseudokey_birthday", 0)

        info.configure(
            text=f"{filename}  |  {len(df)} rows  |  "
                 f"{n_likert} scales, {n_ft} open text, {n_pseudo} matching keys",
            text_color=C.SUCCESS)
        status.configure(text="\u2714", text_color=C.SUCCESS)

        # Store
        if survey_type == "pre":
            self._pre_df = df
            self._pre_roles = roles
            self.app.app_state.pre_survey_path = path
            self.app.app_state.n_pre = len(df)
        else:
            self._post_df = df
            self._post_roles = roles
            self.app.app_state.post_survey_path = path
            self.app.app_state.n_post = len(df)

        self.app.app_state.pre_columns = self._pre_roles
        self.app.app_state.post_columns = self._post_roles
        self.app.app_state.save()

        # Hide hint once any file loaded
        self._hint.pack_forget()

        # Check if both loaded
        if self._pre_df is not None and self._post_df is not None:
            self._run_matching()

    def _run_matching(self):
        from bc4d_intel.core.panel_matcher import match_panels
        result = match_panels(self._pre_df, self._pre_roles,
                              self._post_df, self._post_roles)
        stats = result["stats"]

        self.app.app_state.matched_pairs = stats["n_matched"]
        self.app.app_state.unmatched_pre = stats["n_pre_only"]
        self.app.app_state.unmatched_post = stats["n_post_only"]
        self.app.app_state.save()
        self.app._match_result = result

        # Check for issues
        warnings = []
        pre_pseudo = sum(1 for r in self._pre_roles.values() if "pseudokey" in r)
        post_pseudo = sum(1 for r in self._post_roles.values() if "pseudokey" in r)
        if pre_pseudo < 2:
            warnings.append("Pre-survey: matching keys not detected. Check Advanced Settings.")
        if post_pseudo < 2:
            warnings.append("Post-survey: matching keys not detected. Check Advanced Settings.")
        if stats["match_rate_post"] < 30:
            warnings.append(f"Low match rate ({stats['match_rate_post']}%). "
                          f"Check if both surveys are from the same cohort.")

        self._show_summary(stats, warnings)

    def _show_summary(self, stats, warnings):
        # Clear old
        self._summary_card.pack_forget()
        self._warning_card.pack_forget()
        for w in self._summary_card.winfo_children():
            w.destroy()
        for w in self._warning_card.winfo_children():
            w.destroy()

        # Counts
        pre_likert = sum(1 for r in self._pre_roles.values() if r in ("likert", "frequency", "relevance"))
        post_likert = sum(1 for r in self._post_roles.values() if r in ("likert", "frequency", "relevance"))
        pre_ft = sum(1 for r in self._pre_roles.values() if r == "free_text")
        post_ft = sum(1 for r in self._post_roles.values() if r == "free_text")

        # ── Warning card (if issues) ──
        if warnings:
            self._warning_card.pack(fill="x", padx=4, pady=(0, 6))
            warn_inner = ctk.CTkFrame(self._warning_card, fg_color="transparent")
            warn_inner.pack(fill="x", padx=14, pady=10)
            ctk.CTkLabel(warn_inner, text="Potential issues detected",
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color="#ffffff").pack(anchor="w")
            for w in warnings:
                ctk.CTkLabel(warn_inner, text=f"  - {w}",
                             font=ctk.CTkFont(size=10),
                             text_color="#fff3cd").pack(anchor="w")

        # ── Success card ──
        self._summary_card.pack(fill="x", padx=4, pady=(0, 6))
        inner = ctk.CTkFrame(self._summary_card, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(inner, text="Data loaded successfully",
                     font=ctk.CTkFont(size=15, weight="bold"),
                     text_color="#ffffff").pack(anchor="w")

        grid = ctk.CTkFrame(inner, fg_color="transparent")
        grid.pack(fill="x", pady=(6, 2))

        for i, (label, value) in enumerate([
            ("Pre-survey respondents", str(stats["n_pre_total"])),
            ("Post-survey respondents", str(stats["n_post_total"])),
            ("Matched pairs", f"{stats['n_matched']} ({stats['match_rate_post']}%)"),
            ("Scale items (pre/post)", f"{pre_likert} / {post_likert}"),
            ("Open-ended questions (pre/post)", f"{pre_ft} / {post_ft}"),
        ]):
            row = ctk.CTkFrame(grid, fg_color="transparent")
            row.pack(fill="x")
            ctk.CTkLabel(row, text=label,
                         font=ctk.CTkFont(size=11),
                         text_color="#d0f0d0", width=220, anchor="w"
                         ).pack(side="left")
            ctk.CTkLabel(row, text=value,
                         font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
                         text_color="#ffffff"
                         ).pack(side="left")

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(fill="x", pady=(10, 0))

        ctk.CTkButton(
            btn_row, text="Continue to Dashboard  \u2192", width=220, height=38,
            fg_color="#ffffff", text_color=C.SUCCESS, hover_color="#f0f0f0",
            font=ctk.CTkFont(size=13, weight="bold"),
            corner_radius=6,
            command=lambda: self.app.show_frame("dashboard"),
        ).pack(side="left", padx=(0, 12))

        ctk.CTkButton(
            btn_row, text="Go to AI Analysis  \u2192", width=180, height=38,
            fg_color="#ffffff", text_color=C.SUCCESS, hover_color="#f0f0f0",
            font=ctk.CTkFont(size=12),
            corner_radius=6,
            command=lambda: self.app.show_frame("analysis"),
        ).pack(side="left")

    # ── Advanced Settings ───────────────────────────────────────

    def _toggle_advanced(self):
        if self._advanced_visible:
            self._advanced_frame.pack_forget()
            self._advanced_toggle.configure(text="Advanced Settings  \u25BC")
            self._advanced_visible = False
        else:
            self._build_advanced()
            self._advanced_frame.pack(fill="x", padx=4, pady=(4, 8))
            self._advanced_toggle.configure(text="Advanced Settings  \u25B2")
            self._advanced_visible = True

    def _build_advanced(self):
        for w in self._advanced_frame.winfo_children():
            w.destroy()

        # ── Tab: Pre / Post ──
        tab_var = ctk.StringVar(value="pre")
        tab_frame = ctk.CTkFrame(self._advanced_frame, fg_color="transparent")
        tab_frame.pack(fill="x", pady=(4, 8))

        ctk.CTkSegmentedButton(
            tab_frame,
            values=["Pre-Survey Columns", "Post-Survey Columns", "Column Matching"],
            variable=tab_var,
            font=ctk.CTkFont(size=11), height=30, corner_radius=6,
            command=lambda v: self._show_advanced_tab(v, content_frame),
        ).pack(side="left")

        content_frame = ctk.CTkFrame(self._advanced_frame, fg_color="transparent")
        content_frame.pack(fill="x")

        self._show_advanced_tab("Pre-Survey Columns", content_frame)

    def _show_advanced_tab(self, tab, parent):
        for w in parent.winfo_children():
            w.destroy()

        if tab == "Pre-Survey Columns":
            self._build_column_editor(parent, "pre", self._pre_df, self._pre_roles)
        elif tab == "Post-Survey Columns":
            self._build_column_editor(parent, "post", self._post_df, self._post_roles)
        elif tab == "Column Matching":
            self._build_column_matcher(parent)

    def _build_column_editor(self, parent, survey_type, df, roles):
        """Full column role editor with editable dropdowns."""
        if df is None:
            W.muted_label(parent, f"Load the {survey_type}-survey first.", size=11
                          ).pack(padx=12, pady=20)
            return

        # Legend
        legend = ctk.CTkFrame(parent, fg_color="transparent")
        legend.pack(fill="x", padx=8, pady=(4, 6))
        for role, color in [("likert", C.BC4D_BLUE), ("free_text", C.BC4D_TEAL),
                            ("demographic", C.BC4D_AMBER), ("pseudokey", C.BC4D_PINK),
                            ("metadata", "#6b7280")]:
            W.status_badge(legend, role.replace("_", " "), color).pack(side="left", padx=2)

        # Column list
        for col, role in roles.items():
            row = ctk.CTkFrame(parent, fg_color=C.PANEL, corner_radius=4)
            row.pack(fill="x", padx=8, pady=1)

            role_var = ctk.StringVar(value=role)
            dropdown = ctk.CTkOptionMenu(
                row, variable=role_var, values=ROLE_OPTIONS,
                font=ctk.CTkFont(family="Consolas", size=8),
                fg_color=ROLE_COLORS.get(role, C.DIM),
                button_color=C.MUTED,
                width=110, height=22,
                command=lambda v, c=col, st=survey_type: self._change_role(st, c, v),
            )
            dropdown.pack(side="left", padx=(6, 8), pady=3)

            col_display = col[:50] + "..." if len(col) > 50 else col
            col_lbl = ctk.CTkLabel(row, text=col_display,
                         font=ctk.CTkFont(size=10),
                         text_color=C.TEXT, anchor="w")
            col_lbl.pack(side="left", fill="x", expand=True)
            if len(col) > 50:
                W.magnify(col_lbl, text=col)

            # Sample value
            sample = df[col].dropna().head(1)
            if len(sample) > 0:
                ctk.CTkLabel(row, text=str(sample.iloc[0])[:25],
                             font=ctk.CTkFont(family="Consolas", size=9),
                             text_color=C.MUTED).pack(side="right", padx=6)

    def _build_column_matcher(self, parent):
        """Show exactly which pre columns are compared to which post columns.

        Uses the same matching logic as stats_engine.analyze_matched_likert()
        so the user sees what the system will actually compare.
        """
        if self._pre_df is None or self._post_df is None:
            W.muted_label(parent, "Load both files first.", size=11
                          ).pack(padx=12, pady=20)
            return

        from difflib import SequenceMatcher

        ctk.CTkLabel(parent, text="Pre/Post Column Pairing",
                     font=ctk.CTkFont(size=12, weight="bold"),
                     text_color=C.TEXT).pack(anchor="w", padx=12, pady=(8, 2))

        W.muted_label(parent,
            "This shows which pre-survey column is compared to which post-survey column "
            "for the statistical analysis (means, effect sizes, p-values). "
            "Columns are paired by name similarity. "
            "Verify that each pair actually asks the same question.",
            size=9).pack(anchor="w", padx=12, pady=(0, 10))

        # ── Likert/scale pairings (the critical ones) ──
        pre_likert = [(c, r) for c, r in self._pre_roles.items()
                      if r in ("likert", "frequency", "relevance")]
        post_likert = [(c, r) for c, r in self._post_roles.items()
                       if r in ("likert", "frequency", "relevance")]

        # Run the same matching logic as stats_engine
        matches = []
        used_post = set()
        unmatched_pre = []
        for pre_col, pre_role in pre_likert:
            best_match, best_ratio = None, 0
            for post_col, _ in post_likert:
                if post_col in used_post:
                    continue
                pre_norm = " ".join(pre_col.lower().split())
                post_norm = " ".join(post_col.lower().split())
                ratio = SequenceMatcher(None, pre_norm, post_norm).ratio()
                if ratio > best_ratio:
                    best_ratio = ratio
                    best_match = post_col
            if best_match and best_ratio > 0.6:
                used_post.add(best_match)
                matches.append((pre_col, best_match, best_ratio))
            else:
                unmatched_pre.append(pre_col)

        unmatched_post = [c for c, _ in post_likert if c not in used_post]

        # ── Matched pairs (green) ──
        if matches:
            header = ctk.CTkFrame(parent, fg_color=C.SUCCESS, corner_radius=4)
            header.pack(fill="x", padx=8, pady=(4, 2))
            ctk.CTkLabel(header,
                         text=f"Matched Scale Items ({len(matches)} pairs used for pre/post comparison)",
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#ffffff").pack(padx=8, pady=3)

            for pre_col, post_col, ratio in matches:
                row = ctk.CTkFrame(parent, fg_color=C.PANEL, corner_radius=3)
                row.pack(fill="x", padx=12, pady=1)

                # Match quality indicator
                quality_color = C.SUCCESS if ratio > 0.85 else C.WARN
                ctk.CTkLabel(row, text=f"{ratio:.0%}",
                             font=ctk.CTkFont(family="Consolas", size=8, weight="bold"),
                             text_color=quality_color, width=35
                             ).pack(side="left", padx=(6, 4), pady=2)

                ctk.CTkLabel(row, text=pre_col[:40],
                             font=ctk.CTkFont(size=9), text_color=C.TEXT,
                             anchor="w", width=280).pack(side="left", padx=2)
                ctk.CTkLabel(row, text="\u2192",
                             font=ctk.CTkFont(size=9),
                             text_color=C.MUTED).pack(side="left", padx=4)
                ctk.CTkLabel(row, text=post_col[:40],
                             font=ctk.CTkFont(size=9), text_color=C.TEXT,
                             anchor="w").pack(side="left", padx=2)

        # ── Unmatched pre columns (amber) ──
        if unmatched_pre:
            header = ctk.CTkFrame(parent, fg_color=C.WARN, corner_radius=4)
            header.pack(fill="x", padx=8, pady=(8, 2))
            ctk.CTkLabel(header,
                         text=f"Pre-only ({len(unmatched_pre)} items — no matching post column found)",
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#ffffff").pack(padx=8, pady=3)

            for col in unmatched_pre:
                row = ctk.CTkFrame(parent, fg_color=C.PANEL, corner_radius=3)
                row.pack(fill="x", padx=12, pady=1)
                ctk.CTkLabel(row, text="Pre",
                             font=ctk.CTkFont(family="Consolas", size=8),
                             text_color=C.WARN, width=35).pack(side="left", padx=6, pady=2)
                ctk.CTkLabel(row, text=col[:60],
                             font=ctk.CTkFont(size=9), text_color=C.MUTED,
                             anchor="w").pack(side="left", padx=2)

        # ── Unmatched post columns (amber) ──
        if unmatched_post:
            header = ctk.CTkFrame(parent, fg_color=C.WARN, corner_radius=4)
            header.pack(fill="x", padx=8, pady=(8, 2))
            ctk.CTkLabel(header,
                         text=f"Post-only ({len(unmatched_post)} items — no matching pre column found)",
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#ffffff").pack(padx=8, pady=3)

            for col in unmatched_post:
                row = ctk.CTkFrame(parent, fg_color=C.PANEL, corner_radius=3)
                row.pack(fill="x", padx=12, pady=1)
                ctk.CTkLabel(row, text="Post",
                             font=ctk.CTkFont(family="Consolas", size=8),
                             text_color=C.WARN, width=35).pack(side="left", padx=6, pady=2)
                ctk.CTkLabel(row, text=col[:60],
                             font=ctk.CTkFont(size=9), text_color=C.MUTED,
                             anchor="w").pack(side="left", padx=2)

        # ── Pseudokey matching ──
        pre_pseudo = [(c, r) for c, r in self._pre_roles.items() if "pseudokey" in r]
        post_pseudo = [(c, r) for c, r in self._post_roles.items() if "pseudokey" in r]

        if pre_pseudo or post_pseudo:
            header = ctk.CTkFrame(parent, fg_color=C.BC4D_PINK, corner_radius=4)
            header.pack(fill="x", padx=8, pady=(10, 2))
            ctk.CTkLabel(header,
                         text=f"Respondent Matching Keys (used to link pre and post surveys)",
                         font=ctk.CTkFont(size=10, weight="bold"),
                         text_color="#ffffff").pack(padx=8, pady=3)

            for label, cols in [("Pre", pre_pseudo), ("Post", post_pseudo)]:
                for col, role in cols:
                    row = ctk.CTkFrame(parent, fg_color=C.PANEL, corner_radius=3)
                    row.pack(fill="x", padx=12, pady=1)
                    role_short = "Street" if "street" in role else "Birthday"
                    ctk.CTkLabel(row, text=f"{label}:{role_short}",
                                 font=ctk.CTkFont(family="Consolas", size=8),
                                 text_color=C.BC4D_PINK, width=80
                                 ).pack(side="left", padx=6, pady=2)
                    ctk.CTkLabel(row, text=col[:55],
                                 font=ctk.CTkFont(size=9), text_color=C.TEXT,
                                 anchor="w").pack(side="left", padx=2)

        if not matches and not unmatched_pre and not unmatched_post:
            W.muted_label(parent, "No scale items found in either survey.", size=10
                          ).pack(padx=12, pady=10)

    def _change_role(self, survey_type, col, new_role):
        if survey_type == "pre":
            self._pre_roles[col] = new_role
        else:
            self._post_roles[col] = new_role
        # Re-run matching if both loaded
        if self._pre_df is not None and self._post_df is not None:
            self._run_matching()

    def refresh(self):
        pass

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.BG)
        self._build()
