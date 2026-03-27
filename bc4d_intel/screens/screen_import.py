"""Import screen — load pre/post Excel files, detect columns, preview data."""

from __future__ import annotations
import threading, tkinter as tk
import customtkinter as ctk
from bc4d_intel import constants as C
from bc4d_intel.ui import widgets as W


# Role → display color mapping
ROLE_COLORS = {
    "likert": C.BC4D_BLUE,
    "frequency": C.BC4D_BLUE,
    "relevance": C.BC4D_BLUE,
    "free_text": C.BC4D_TEAL,
    "demographic": C.BC4D_AMBER,
    "categorical": C.BC4D_AMBER,
    "pseudokey_street": C.BC4D_PINK,
    "pseudokey_birthday": C.BC4D_PINK,
    "metadata": "#6b7280",
    "ignore": "#374151",
    "other": "#6b7280",
}


class ImportScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C.BG, corner_radius=0)
        self.app = app
        self._pre_df = None
        self._post_df = None
        self._pre_roles = {}
        self._post_roles = {}
        self._build()

    def _build(self):
        # ── Top bar ──
        top = W.make_toolbar(self, height=80)
        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=30, pady=12)
        W.heading(inner, "Import Data", size=22).pack(anchor="w")
        W.muted_label(inner, "Load pre-survey and post-survey Excel files").pack(anchor="w")

        # ── Body: two-column layout ──
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=10)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(1, weight=1)

        # File selection row
        for col_idx, (label, survey_type, icon) in enumerate([
            ("Pre-Survey (Vorabfragebogen)", "pre", "\U0001F4C4"),
            ("Post-Survey (Abschlussbefragung)", "post", "\U0001F4CB"),
        ]):
            card = W.make_card(body)
            card.grid(row=0, column=col_idx, sticky="ew", padx=5, pady=5)

            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=10)

            ctk.CTkLabel(row, text=f"{icon} {label}",
                         font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                         text_color=C.TEXT).pack(side="left")

            W.accent_button(row, text="Choose File", width=110,
                           command=lambda t=survey_type: self._choose_file(t)
                           ).pack(side="right")

            # File path label
            path_lbl = W.muted_label(card, "No file loaded", size=10)
            path_lbl.pack(fill="x", padx=12, pady=(0, 8))
            setattr(self, f"_{survey_type}_path_lbl", path_lbl)

        # Status bar
        status_card = W.make_card(body)
        status_card.grid(row=0, column=0, columnspan=2, sticky="ew", padx=5, pady=(60, 5))
        # Reposition file cards
        for i, child in enumerate(body.winfo_children()):
            if i < 2:
                child.grid(row=0, column=i, sticky="ew", padx=5, pady=5)

        self._status_lbl = ctk.CTkLabel(
            status_card, text="Load both survey files to begin analysis.",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=C.MUTED, anchor="w")
        self._status_lbl.pack(fill="x", padx=12, pady=8)

        # Column role preview (scrollable, below file cards)
        preview_frame = ctk.CTkFrame(body, fg_color="transparent")
        preview_frame.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)

        self._preview_scroll = ctk.CTkScrollableFrame(preview_frame, fg_color=C.CARD,
                                                       corner_radius=10)
        self._preview_scroll.pack(fill="both", expand=True)

        W.muted_label(self._preview_scroll,
                       "Column roles will appear here after loading files.",
                       size=11).pack(padx=20, pady=30)

    def _choose_file(self, survey_type):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title=f"Select {survey_type}-survey Excel file",
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")],
        )
        if not path:
            return

        # Show loading
        lbl = getattr(self, f"_{survey_type}_path_lbl")
        lbl.configure(text=f"Loading: {path.split('/')[-1]}...", text_color=C.ACCENT)

        def work():
            from bc4d_intel.core.data_loader import load_survey
            try:
                df, roles = load_survey(path)
                self.after(0, lambda: self._on_loaded(survey_type, path, df, roles))
            except Exception as e:
                self.after(0, lambda: lbl.configure(
                    text=f"Error: {e}", text_color=C.DANGER))

        threading.Thread(target=work, daemon=True).start()

    def _on_loaded(self, survey_type, path, df, roles):
        """Handle successful file load."""
        filename = path.split("/")[-1].split("\\")[-1]
        lbl = getattr(self, f"_{survey_type}_path_lbl")
        lbl.configure(text=f"{filename} ({len(df)} rows, {len(df.columns)} cols)",
                       text_color=C.SUCCESS)

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

        # Update status + show next step
        pre_ok = self._pre_df is not None
        post_ok = self._post_df is not None
        if pre_ok and post_ok:
            self._status_lbl.configure(
                text=f"Both files loaded. Pre: {len(self._pre_df)} rows, "
                     f"Post: {len(self._post_df)} rows.",
                text_color=C.SUCCESS)
            self._show_next_step()
        elif pre_ok:
            self._status_lbl.configure(
                text="Pre-survey loaded. Now load the post-survey.",
                text_color=C.ACCENT)
        else:
            self._status_lbl.configure(
                text="Post-survey loaded. Now load the pre-survey.",
                text_color=C.ACCENT)

        # Show column role preview
        self._show_column_preview(survey_type, df, roles)

        # Save state
        self.app.app_state.pre_columns = self._pre_roles
        self.app.app_state.post_columns = self._post_roles
        self.app.app_state.save()

    def _show_next_step(self):
        """Run panel matching and show a prominent results + next-step panel."""
        # Remove any previous next-step panel
        if hasattr(self, "_next_step_frame") and self._next_step_frame:
            self._next_step_frame.destroy()

        # Run panel matching
        from bc4d_intel.core.panel_matcher import match_panels
        match_result = match_panels(self._pre_df, self._pre_roles,
                                     self._post_df, self._post_roles)
        stats = match_result["stats"]

        # Store in app state
        self.app.app_state.matched_pairs = stats["n_matched"]
        self.app.app_state.unmatched_pre = stats["n_pre_only"]
        self.app.app_state.unmatched_post = stats["n_post_only"]
        self.app.app_state.save()

        # Store match result for other screens to access
        self.app._match_result = match_result

        self._next_step_frame = ctk.CTkFrame(
            self._preview_scroll, fg_color=C.ACCENT, corner_radius=8)
        children = self._preview_scroll.winfo_children()
        if children:
            self._next_step_frame.pack(fill="x", padx=8, pady=(8, 4), before=children[0])
        else:
            self._next_step_frame.pack(fill="x", padx=8, pady=(8, 4))

        inner = ctk.CTkFrame(self._next_step_frame, fg_color="transparent")
        inner.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(
            inner, text="Data loaded & panel matching complete",
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color="#ffffff",
        ).pack(anchor="w")

        # Three-dataset summary
        pre_likert = sum(1 for r in self._pre_roles.values() if r in ("likert", "frequency", "relevance"))
        post_likert = sum(1 for r in self._post_roles.values() if r in ("likert", "frequency", "relevance"))
        pre_ft = sum(1 for r in self._pre_roles.values() if r == "free_text")
        post_ft = sum(1 for r in self._post_roles.values() if r == "free_text")

        summary = (
            f"Three analysis datasets ready:\n\n"
            f"  1. Pre-survey (all):  {stats['n_pre_total']} respondents, "
            f"{pre_likert} scale items, {pre_ft} open questions\n"
            f"  2. Post-survey (all): {stats['n_post_total']} respondents, "
            f"{post_likert} scale items, {post_ft} open questions\n"
            f"  3. Matched panel:     {stats['n_matched']} paired respondents "
            f"({stats['match_rate_post']}% of post matched)"
        )

        ctk.CTkLabel(
            inner, text=summary,
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color="#f0f0f0", justify="left",
        ).pack(anchor="w", pady=(4, 4))

        # Dropout note
        if stats["n_pre_only"] > 0 or stats["n_post_only"] > 0:
            note = (
                f"\n{stats['n_pre_only']} pre-only respondents included in baseline analysis.\n"
                f"{stats['n_post_only']} post-only respondents included in outcome analysis.\n"
                f"No data is lost from dropouts."
            )
            ctk.CTkLabel(
                inner, text=note,
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color="#d0d0d0", justify="left",
            ).pack(anchor="w", pady=(0, 8))

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(fill="x")

        ctk.CTkButton(
            btn_row, text="Continue to Dashboard  \u2192", width=200, height=38,
            fg_color="#ffffff", text_color=C.ACCENT, hover_color="#f0f0f0",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            corner_radius=6,
            command=lambda: self.app.show_frame("dashboard"),
        ).pack(side="left", padx=(0, 10))

        ctk.CTkLabel(
            btn_row, text="or go to Settings to configure your API key for AI features",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color="#d0d0d0",
        ).pack(side="left")

    def _show_column_preview(self, survey_type, df, roles):
        """Show detected column roles with color badges."""
        # Clear previous preview for this survey
        for w in self._preview_scroll.winfo_children():
            w.destroy()

        label = "Pre-Survey" if survey_type == "pre" else "Post-Survey"
        ctk.CTkLabel(
            self._preview_scroll, text=f"{label} — Column Roles Detected",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=C.TEXT,
        ).pack(anchor="w", padx=12, pady=(10, 4))

        # Role legend
        legend = ctk.CTkFrame(self._preview_scroll, fg_color="transparent")
        legend.pack(fill="x", padx=12, pady=(0, 8))
        for role, color in [("likert", C.BC4D_BLUE), ("free_text", C.BC4D_TEAL),
                            ("demographic", C.BC4D_AMBER), ("pseudokey", C.BC4D_PINK),
                            ("metadata", "#6b7280")]:
            W.status_badge(legend, role.replace("_", " ").title(), color).pack(side="left", padx=2)

        # Column list
        from collections import Counter
        role_counts = Counter(roles.values())

        role_options = ["likert", "frequency", "relevance", "free_text",
                       "demographic", "categorical", "pseudokey_street",
                       "pseudokey_birthday", "metadata", "ignore"]

        for col, role in roles.items():
            if role == "ignore":
                continue

            row = ctk.CTkFrame(self._preview_scroll, fg_color=C.PANEL, corner_radius=4)
            row.pack(fill="x", padx=8, pady=1)

            # Editable role dropdown (Improvement #3)
            role_var = ctk.StringVar(value=role)
            dropdown = ctk.CTkOptionMenu(
                row, variable=role_var, values=role_options,
                font=ctk.CTkFont(family="Consolas", size=8),
                fg_color=ROLE_COLORS.get(role, C.DIM),
                button_color=C.MUTED,
                width=100, height=22,
                command=lambda v, c=col, st=survey_type, rv=role_var: self._change_role(st, c, v),
            )
            dropdown.pack(side="left", padx=(6, 8), pady=4)

            col_display = col[:55] if len(col) <= 55 else col[:52] + "..."
            ctk.CTkLabel(row, text=col_display,
                         font=ctk.CTkFont(family="Segoe UI", size=10),
                         text_color=C.TEXT, anchor="w").pack(side="left", fill="x", expand=True)

            # Sample value
            sample = df[col].dropna().head(1)
            if len(sample) > 0:
                val = str(sample.iloc[0])[:25]
                ctk.CTkLabel(row, text=val,
                             font=ctk.CTkFont(family="Consolas", size=9),
                             text_color=C.MUTED).pack(side="right", padx=6)

        # Summary
        summary = f"\nDetected: {role_counts.get('likert', 0)} Likert, " \
                  f"{role_counts.get('frequency', 0)} frequency, " \
                  f"{role_counts.get('free_text', 0)} free-text, " \
                  f"{role_counts.get('demographic', 0)} demographic"
        W.muted_label(self._preview_scroll, summary, size=10).pack(
            anchor="w", padx=12, pady=(8, 12))

    def _change_role(self, survey_type, col, new_role):
        """Handle manual column role override."""
        if survey_type == "pre":
            self._pre_roles[col] = new_role
        else:
            self._post_roles[col] = new_role
        # Re-run matching if both loaded
        if self._pre_df is not None and self._post_df is not None:
            self._show_next_step()

    def refresh(self):
        pass

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.BG)
        self._build()
