"""Validation screen — AI tagging of free text + human override.

Shows each free-text response with its AI-assigned tag.
Three-level override: accept, change tag, flag for review.
"""

from __future__ import annotations
import threading
import customtkinter as ctk
from bc4d_intel import constants as C
from bc4d_intel.ui import widgets as W

TAG_COLORS = {
    "positive_feedback": "#22c55e",
    "negative_feedback": "#dc2626",
    "content_suggestion": "#0077B6",
    "methodology_feedback": "#6366f1",
    "trainer_feedback": "#ec4899",
    "personal_reflection": "#14b8a6",
    "knowledge_gain": "#84cc16",
    "behavior_change_intent": "#f59e0b",
    "organizational_context": "#a855f7",
    "other": "#6b7280",
}


class ValidationScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C.BG, corner_radius=0)
        self.app = app
        self._tagged_data = {}  # {question_col: [tagged_responses]}
        self._current_question = None
        self._build()

    def _build(self):
        # ── Top bar ──
        top = W.make_toolbar(self, height=80)
        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=30, pady=12)

        W.heading(inner, "Validation", size=22).pack(side="left")

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(side="right")

        self._tag_btn = W.accent_button(btn_row, text="Run AI Tagging",
                                         command=self._run_tagging, width=150)
        self._tag_btn.pack(side="left", padx=(0, 8))

        self._status_lbl = ctk.CTkLabel(btn_row, text="",
                                         font=ctk.CTkFont(family="Segoe UI", size=11),
                                         text_color=C.MUTED)
        self._status_lbl.pack(side="left")

        # ── Body: question selector (left) + responses (right) ──
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=10)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(0, weight=1)

        # Left: question list
        left = W.make_card(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        ctk.CTkLabel(left, text="Free-Text Questions",
                     font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                     text_color=C.TEXT).pack(anchor="w", padx=12, pady=(10, 4))

        self._question_frame = ctk.CTkScrollableFrame(left, fg_color="transparent")
        self._question_frame.pack(fill="both", expand=True, padx=6, pady=6)

        W.muted_label(self._question_frame,
            "Load data and run AI Tagging\nto see free-text questions here.",
            size=11).pack(padx=10, pady=20)

        # Right: response cards
        right = W.make_card(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        self._response_header = ctk.CTkLabel(right, text="Responses",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=C.TEXT)
        self._response_header.pack(anchor="w", padx=12, pady=(10, 4))

        self._response_frame = ctk.CTkScrollableFrame(right, fg_color="transparent")
        self._response_frame.pack(fill="both", expand=True, padx=6, pady=6)

        W.muted_label(self._response_frame,
            "Select a question on the left to review responses.",
            size=11).pack(padx=10, pady=20)

    def _run_tagging(self):
        """Run AI tagging on all free-text columns."""
        if not hasattr(self.app, "_match_result") or not self.app._match_result:
            self._status_lbl.configure(text="Load data first.", text_color=C.DANGER)
            return

        api_key = self.app.app_state.api_key
        if not api_key:
            self._status_lbl.configure(text="Set API key in Settings first.", text_color=C.DANGER)
            return

        self._tag_btn.configure(state="disabled", text="Tagging...")
        self._status_lbl.configure(text="Starting AI tagging...", text_color=C.ACCENT)

        def work():
            from bc4d_intel.ai.tagger import tag_responses
            import_screen = self.app._frames.get("import")
            if not import_screen:
                return

            # Collect all free-text columns from both surveys
            result = self.app._match_result
            tagged = {}

            for survey_type, df_key, roles in [
                ("Pre", "pre_all", import_screen._pre_roles),
                ("Post", "post_all", import_screen._post_roles),
            ]:
                df = result[df_key]
                ft_cols = [c for c, r in roles.items() if r == "free_text"]

                for col in ft_cols:
                    responses = df[col].dropna().astype(str).tolist()
                    responses = [r for r in responses if len(r.strip()) > 5]
                    if not responses:
                        continue

                    label = f"[{survey_type}] {col[:50]}"

                    def on_progress(msg, lbl=label):
                        self.after(0, lambda m=msg: self._status_lbl.configure(
                            text=m, text_color=C.ACCENT))

                    try:
                        tags = tag_responses(responses, api_key, progress_cb=on_progress)
                        tagged[label] = tags
                    except Exception as e:
                        self.after(0, lambda err=str(e): self._status_lbl.configure(
                            text=f"Error: {err}", text_color=C.DANGER))

            self._tagged_data = tagged
            self.app.app_state.tagged_responses = {
                k: v for k, v in tagged.items()
            }
            self.app.app_state.save()

            self.after(0, self._on_tagging_complete)

        threading.Thread(target=work, daemon=True).start()

    def _on_tagging_complete(self):
        self._tag_btn.configure(state="normal", text="Run AI Tagging")
        total = sum(len(v) for v in self._tagged_data.values())
        self._status_lbl.configure(
            text=f"Tagged {total} responses across {len(self._tagged_data)} questions.",
            text_color=C.SUCCESS)
        self._populate_question_list()

    def _populate_question_list(self):
        """Show list of free-text questions in the left panel."""
        for w in self._question_frame.winfo_children():
            w.destroy()

        for label, tags in self._tagged_data.items():
            n = len(tags)
            n_high = sum(1 for t in tags if t["confidence"] == "high")

            btn = ctk.CTkButton(
                self._question_frame,
                text=f"{label[:40]}\n{n} responses, {n_high} high-confidence",
                anchor="w", height=50,
                fg_color=C.PANEL, hover_color=C.SELECT,
                text_color=C.TEXT,
                font=ctk.CTkFont(family="Segoe UI", size=10),
                corner_radius=6,
                command=lambda l=label: self._show_responses(l),
            )
            btn.pack(fill="x", padx=4, pady=2)

    def _show_responses(self, question_label):
        """Show tagged responses for a specific question."""
        self._current_question = question_label
        tags = self._tagged_data.get(question_label, [])

        for w in self._response_frame.winfo_children():
            w.destroy()

        self._response_header.configure(text=f"{question_label[:55]} ({len(tags)} responses)")

        for i, item in enumerate(tags):
            card = ctk.CTkFrame(self._response_frame, fg_color=C.PANEL, corner_radius=6)
            card.pack(fill="x", padx=4, pady=3)

            # Header: tag badge + confidence
            header = ctk.CTkFrame(card, fg_color="transparent")
            header.pack(fill="x", padx=8, pady=(6, 2))

            tag = item.get("human_override") or item["tag"]
            tag_color = TAG_COLORS.get(tag, C.MUTED)
            W.status_badge(header, tag.replace("_", " ").title(), tag_color).pack(side="left", padx=(0, 6))

            conf = item["confidence"]
            conf_color = C.SUCCESS if conf == "high" else (C.WARN if conf == "medium" else C.MUTED)
            ctk.CTkLabel(header, text=conf,
                         font=ctk.CTkFont(family="Consolas", size=9),
                         text_color=conf_color).pack(side="left")

            if item.get("human_override"):
                ctk.CTkLabel(header, text="(overridden)",
                             font=ctk.CTkFont(family="Segoe UI", size=8),
                             text_color=C.WARN).pack(side="left", padx=4)

            # Response text
            ctk.CTkLabel(card, text=item["text"][:200],
                         font=ctk.CTkFont(family="Segoe UI", size=10),
                         text_color=C.TEXT, anchor="w", wraplength=450,
                         justify="left").pack(fill="x", padx=10, pady=(0, 2))

            # Rationale
            if item.get("rationale"):
                ctk.CTkLabel(card, text=f"AI: {item['rationale'][:100]}",
                             font=ctk.CTkFont(family="Segoe UI", size=9),
                             text_color=C.MUTED, anchor="w").pack(fill="x", padx=10, pady=(0, 2))

            # Override buttons
            btn_row = ctk.CTkFrame(card, fg_color="transparent")
            btn_row.pack(fill="x", padx=8, pady=(0, 6))

            ctk.CTkButton(btn_row, text="Accept", width=60, height=22,
                          fg_color=C.SUCCESS, hover_color="#047857",
                          font=ctk.CTkFont(size=9), corner_radius=3,
                          command=lambda idx=i: self._accept_tag(idx),
                          ).pack(side="left", padx=(0, 3))

            # Tag override dropdown
            override_var = ctk.StringVar(value="Change tag...")
            from bc4d_intel.ai.prompts import FREE_TEXT_TAGS
            tag_menu = ctk.CTkOptionMenu(
                btn_row, variable=override_var,
                values=[t.replace("_", " ").title() for t in FREE_TEXT_TAGS],
                font=ctk.CTkFont(size=9), height=22, width=130,
                fg_color=C.DIM, button_color=C.MUTED,
                command=lambda v, idx=i: self._override_tag(idx, v),
            )
            tag_menu.pack(side="left", padx=(0, 3))

            ctk.CTkButton(btn_row, text="Flag", width=50, height=22,
                          fg_color=C.WARN, hover_color="#b45309",
                          font=ctk.CTkFont(size=9), corner_radius=3,
                          command=lambda idx=i: self._flag_tag(idx),
                          ).pack(side="left")

    def _accept_tag(self, idx):
        """Accept AI tag as correct."""
        if self._current_question and self._current_question in self._tagged_data:
            self._tagged_data[self._current_question][idx]["human_override"] = ""
            self._show_responses(self._current_question)

    def _override_tag(self, idx, new_tag_display):
        """Override AI tag with human selection."""
        new_tag = new_tag_display.lower().replace(" ", "_")
        if self._current_question and self._current_question in self._tagged_data:
            self._tagged_data[self._current_question][idx]["human_override"] = new_tag
            self._show_responses(self._current_question)

    def _flag_tag(self, idx):
        """Flag response for further review."""
        if self._current_question and self._current_question in self._tagged_data:
            self._tagged_data[self._current_question][idx]["human_override"] = "flagged"
            self._show_responses(self._current_question)

    def refresh(self):
        # Restore from state if available
        if self.app.app_state.tagged_responses and not self._tagged_data:
            self._tagged_data = self.app.app_state.tagged_responses
            self._populate_question_list()

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.BG)
        self._build()
