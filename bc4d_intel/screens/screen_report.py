"""Report screen — AI-drafted report with 7 sections + manual editing."""

from __future__ import annotations
import customtkinter as ctk
from bc4d_intel import constants as C
from bc4d_intel.ui import widgets as W


class ReportScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C.BG, corner_radius=0)
        self.app = app
        self._build()

    def _build(self):
        top = W.make_toolbar(self, height=80)
        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=30, pady=12)
        W.heading(inner, "Report", size=22).pack(anchor="w")
        W.muted_label(inner, "AI-drafted evaluation report with manual editing").pack(anchor="w")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=30, pady=20)

        W.muted_label(body,
            "Complete the analysis pipeline first.\n\n"
            "Report sections (AI-generated via Sonnet):\n"
            "  1. Executive Summary\n"
            "  2. Method & Sample\n"
            "  3. Quantitative Results\n"
            "  4. Qualitative Findings\n"
            "  5. Pre/Post Comparison\n"
            "  6. Recommendations\n"
            "  7. Appendix (tables, charts)\n\n"
            "Each section can be manually edited after generation.",
            size=12).pack(padx=20, pady=40)

    def refresh(self):
        pass

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.BG)
        self._build()
