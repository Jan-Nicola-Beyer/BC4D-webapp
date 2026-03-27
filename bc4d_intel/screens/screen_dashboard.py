"""Dashboard screen — quantitative analysis with 6 chart types."""

from __future__ import annotations
import customtkinter as ctk
from bc4d_intel import constants as C
from bc4d_intel.ui import widgets as W


class DashboardScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C.BG, corner_radius=0)
        self.app = app
        self._build()

    def _build(self):
        top = W.make_toolbar(self, height=80)
        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=30, pady=12)
        W.heading(inner, "Dashboard", size=22).pack(anchor="w")
        W.muted_label(inner, "Quantitative analysis and charts").pack(anchor="w")

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=30, pady=20)

        W.muted_label(body,
            "Import data first to see charts.\n\n"
            "Available chart types:\n"
            "  - Likert stacked bar charts\n"
            "  - Pre/post grouped comparisons\n"
            "  - Change histograms\n"
            "  - Staffel trend lines\n"
            "  - Practical transfer analysis\n"
            "  - Demographic pie/donut charts",
            size=12).pack(padx=20, pady=40)

    def refresh(self):
        pass

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.BG)
        self._build()
