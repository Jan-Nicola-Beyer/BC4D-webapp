"""Validation screen — AI tagging of free text + human override."""

from __future__ import annotations
import customtkinter as ctk
from bc4d_intel import constants as C
from bc4d_intel.ui import widgets as W


class ValidationScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C.BG, corner_radius=0)
        self.app = app
        self._build()

    def _build(self):
        top = W.make_toolbar(self, height=80)
        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=30, pady=12)
        W.heading(inner, "Validation", size=22).pack(anchor="w")
        W.muted_label(inner, "Review and validate AI-tagged free-text responses").pack(anchor="w")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=30, pady=20)

        W.muted_label(body,
            "Import data and run AI tagging first.\n\n"
            "This screen allows you to:\n"
            "  - Review AI-generated tags for each free-text response\n"
            "  - Override tags with human judgement (3-level system)\n"
            "  - Filter by confidence level or tag category\n"
            "  - Export validated tags for reporting",
            size=12).pack(padx=20, pady=40)

    def refresh(self):
        pass

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.BG)
        self._build()
