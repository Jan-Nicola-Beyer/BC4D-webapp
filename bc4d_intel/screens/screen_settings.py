"""Settings screen — API config, model info, export preferences."""

from __future__ import annotations
import threading
import customtkinter as ctk
from bc4d_intel import constants as C
from bc4d_intel.ui import widgets as W


class SettingsScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C.BG, corner_radius=0)
        self.app = app
        self._build()

    def _build(self):
        top = W.make_toolbar(self, height=80)
        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=30, pady=12)
        W.heading(inner, "Settings", size=22).pack(anchor="w")
        W.muted_label(inner, "API configuration and preferences").pack(anchor="w")

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=10)

        # ── API Key ──
        api_card = W.make_card(body)
        api_card.pack(fill="x", pady=8)
        api_inner = ctk.CTkFrame(api_card, fg_color="transparent")
        api_inner.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(api_inner, text="Anthropic API Key",
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                     text_color=C.TEXT).pack(anchor="w")
        W.muted_label(api_inner,
            "Required for AI tagging (Haiku) and report generation (Sonnet)."
        ).pack(anchor="w")

        key_row = ctk.CTkFrame(api_inner, fg_color="transparent")
        key_row.pack(fill="x", pady=(8, 0))

        self._api_key_entry = ctk.CTkEntry(
            key_row, placeholder_text="sk-ant-...", show="*",
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=C.ENTRY_BG, border_color=C.ENTRY_BORDER, height=36,
        )
        self._api_key_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        W.accent_button(key_row, text="Save & Test", width=120,
                        command=self._save_and_test_key).pack(side="right")

        self._api_status = W.muted_label(api_inner, "", size=10)
        self._api_status.pack(anchor="w", pady=(6, 0))

        # ── Model Routing ──
        model_card = W.make_card(body)
        model_card.pack(fill="x", pady=8)
        model_inner = ctk.CTkFrame(model_card, fg_color="transparent")
        model_inner.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(model_inner, text="Model Routing",
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                     text_color=C.TEXT).pack(anchor="w")
        W.muted_label(model_inner,
            "Fixed routing — optimized for cost and quality. Cannot be changed."
        ).pack(anchor="w", pady=(0, 8))

        for task, model in C.AI_MODELS.items():
            row = ctk.CTkFrame(model_inner, fg_color=C.PANEL, corner_radius=4)
            row.pack(fill="x", pady=2)
            ctk.CTkLabel(row, text=task.title(),
                         font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                         text_color=C.TEXT, width=100).pack(side="left", padx=10, pady=6)
            ctk.CTkLabel(row, text=model,
                         font=ctk.CTkFont(family="Consolas", size=10),
                         text_color=C.MUTED).pack(side="left", padx=4)

        W.muted_label(model_inner,
            "\nEstimated cost per staffel:\n"
            "  Tagging (~700 responses): $0.05-0.15\n"
            "  Report (7 sections): $0.15-0.40\n"
            "  Total: $0.20-0.55"
        ).pack(anchor="w", pady=(8, 0))

        # ── Session Info ──
        session_card = W.make_card(body)
        session_card.pack(fill="x", pady=8)
        session_inner = ctk.CTkFrame(session_card, fg_color="transparent")
        session_inner.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(session_inner, text="Session",
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                     text_color=C.TEXT).pack(anchor="w")

        state = self.app.app_state
        info = (
            f"Pre-survey: {state.n_pre} respondents\n"
            f"Post-survey: {state.n_post} respondents\n"
            f"Matched pairs: {state.matched_pairs}\n"
            f"Tagged questions: {len(state.tagged_responses)}\n"
            f"Report sections: {len(state.report_sections)}\n"
            f"Staffel: {state.staffel_name or '(not set)'}"
        )
        W.muted_label(session_inner, info, size=11).pack(anchor="w", pady=(4, 0))

        btn_row = ctk.CTkFrame(session_inner, fg_color="transparent")
        btn_row.pack(fill="x", pady=(10, 0))

        W.secondary_button(btn_row, text="Clear Session", width=120,
                           command=self._clear_session).pack(side="left", padx=(0, 8))

        self._session_status = W.muted_label(session_inner, "", size=10)
        self._session_status.pack(anchor="w", pady=(6, 0))

        # ── Staffel Name ──
        staffel_card = W.make_card(body)
        staffel_card.pack(fill="x", pady=8)
        staffel_inner = ctk.CTkFrame(staffel_card, fg_color="transparent")
        staffel_inner.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(staffel_inner, text="Staffel Configuration",
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                     text_color=C.TEXT).pack(anchor="w")

        name_row = ctk.CTkFrame(staffel_inner, fg_color="transparent")
        name_row.pack(fill="x", pady=(8, 0))

        ctk.CTkLabel(name_row, text="Name:",
                     font=ctk.CTkFont(family="Segoe UI", size=11),
                     text_color=C.MUTED).pack(side="left", padx=(0, 8))
        self._staffel_entry = ctk.CTkEntry(
            name_row, placeholder_text="e.g., Staffel 13",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=C.ENTRY_BG, border_color=C.ENTRY_BORDER, height=32, width=200,
        )
        self._staffel_entry.pack(side="left", padx=(0, 8))
        W.secondary_button(name_row, text="Save", width=60,
                           command=self._save_staffel).pack(side="left")

    def _save_and_test_key(self):
        """Save API key and test connectivity."""
        key = self._api_key_entry.get().strip()
        if not key:
            self._api_status.configure(text="Enter an API key first.", text_color=C.DANGER)
            return

        self.app.app_state.api_key = key
        self.app.app_state.save()
        self._api_status.configure(text="Testing...", text_color=C.ACCENT)

        def test():
            try:
                from bc4d_intel.ai.claude_client import call_claude
                response = call_claude(
                    system="Say OK",
                    user_msg="Test",
                    task="tagging",
                    api_key=key,
                    max_tokens=10,
                )
                self.after(0, lambda: self._api_status.configure(
                    text=f"Connected. Response: {response[:20]}", text_color=C.SUCCESS))
            except Exception as e:
                self.after(0, lambda: self._api_status.configure(
                    text=f"Failed: {e}", text_color=C.DANGER))

        threading.Thread(target=test, daemon=True).start()

    def _save_staffel(self):
        name = self._staffel_entry.get().strip()
        if name:
            self.app.app_state.staffel_name = name
            self.app.app_state.save()

    def _clear_session(self):
        """Reset session to empty state."""
        from bc4d_intel.app_state import AppState
        # Keep API key
        api_key = self.app.app_state.api_key
        theme = self.app.app_state.theme
        self.app.app_state = AppState(api_key=api_key, theme=theme)
        self.app.app_state.save()
        self._session_status.configure(text="Session cleared.", text_color=C.SUCCESS)

    def refresh(self):
        # Load API key into entry
        if self.app.app_state.api_key and self._api_key_entry.get() == "":
            self._api_key_entry.insert(0, self.app.app_state.api_key)
        # Load staffel name
        if self.app.app_state.staffel_name and hasattr(self, "_staffel_entry"):
            self._staffel_entry.delete(0, "end")
            self._staffel_entry.insert(0, self.app.app_state.staffel_name)

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.BG)
        self._build()
