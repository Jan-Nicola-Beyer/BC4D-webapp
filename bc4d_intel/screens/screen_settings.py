"""Settings screen — API config, model selection, preferences."""

from __future__ import annotations
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

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=30, pady=20)

        # API Key section
        api_card = W.make_card(body)
        api_card.pack(fill="x", pady=8)

        api_inner = ctk.CTkFrame(api_card, fg_color="transparent")
        api_inner.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(api_inner, text="Anthropic API Key",
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                     text_color=C.TEXT).pack(anchor="w")
        W.muted_label(api_inner, "Required for AI tagging (Haiku) and report generation (Sonnet)").pack(anchor="w")

        key_row = ctk.CTkFrame(api_inner, fg_color="transparent")
        key_row.pack(fill="x", pady=(8, 0))

        self._api_key_entry = ctk.CTkEntry(
            key_row, placeholder_text="sk-ant-...", show="*",
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color=C.ENTRY_BG, border_color=C.ENTRY_BORDER, height=36,
        )
        self._api_key_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        W.accent_button(key_row, text="Save Key", width=100,
                        command=self._save_api_key).pack(side="right")

        # Model info
        model_card = W.make_card(body)
        model_card.pack(fill="x", pady=8)
        model_inner = ctk.CTkFrame(model_card, fg_color="transparent")
        model_inner.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(model_inner, text="Model Routing (fixed)",
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                     text_color=C.TEXT).pack(anchor="w")

        for task, model in C.AI_MODELS.items():
            ctk.CTkLabel(model_inner, text=f"  {task}: {model}",
                         font=ctk.CTkFont(family="Consolas", size=11),
                         text_color=C.MUTED).pack(anchor="w")

        # Cost estimate
        W.muted_label(model_inner,
                      "\nEstimated cost per staffel: $0.20-0.55 USD").pack(anchor="w")

    def _save_api_key(self):
        key = self._api_key_entry.get().strip()
        if key:
            self.app.app_state.api_key = key
            self.app.app_state.save()
            # TODO: also save to keyring for security

    def refresh(self):
        # Load API key into entry if available
        if self.app.app_state.api_key:
            self._api_key_entry.delete(0, "end")
            self._api_key_entry.insert(0, self.app.app_state.api_key)

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.BG)
        self._build()
