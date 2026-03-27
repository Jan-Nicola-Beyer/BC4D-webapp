"""Navigation sidebar — adapted from ISD Intel."""

from __future__ import annotations
import customtkinter as ctk
from bc4d_intel import constants as C
from bc4d_intel.ui.widgets import tip


class Sidebar(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, width=200, fg_color=C.PANEL, corner_radius=0)
        self.app = app
        self.pack_propagate(False)
        self._buttons: dict[str, ctk.CTkButton] = {}
        self._build()

    def _build(self):
        # ── Logo / title ──
        logo_frame = ctk.CTkFrame(self, fg_color="transparent")
        logo_frame.pack(fill="x", padx=14, pady=(18, 4))

        ctk.CTkLabel(
            logo_frame, text="BC4D Intel",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=C.ACCENT,
        ).pack(anchor="w")

        ctk.CTkLabel(
            logo_frame, text="Survey Evaluation",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=C.MUTED,
        ).pack(anchor="w")

        ctk.CTkFrame(self, fg_color=C.BORDER, height=1).pack(fill="x", padx=14, pady=10)

        # ── Nav buttons ──
        for label, key, icon in C.NAV_ITEMS:
            btn = ctk.CTkButton(
                self,
                text=f"{icon}   {label}",
                anchor="w",
                fg_color="transparent",
                hover_color=C.SELECT,
                text_color=C.TEXT,
                font=ctk.CTkFont(family="Segoe UI", size=13),
                height=40, corner_radius=6,
                command=lambda k=key: self.app.show_frame(k),
            )
            btn.pack(fill="x", padx=10, pady=2)
            self._buttons[key] = btn

        # ── Spacer ──
        ctk.CTkFrame(self, fg_color="transparent").pack(fill="both", expand=True)

        # ── Footer ──
        ctk.CTkFrame(self, fg_color=C.BORDER, height=1).pack(fill="x", padx=14, pady=6)

        is_dark = C.current_theme() == "dark"
        theme_label = "Light Mode" if is_dark else "Dark Mode"
        theme_icon = "\u2600" if is_dark else "\u263e"

        self._theme_btn = ctk.CTkButton(
            self, text=f"{theme_icon} {theme_label}",
            fg_color=C.DIM, hover_color=C.SELECT,
            text_color=C.TEXT,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            height=32, corner_radius=6,
            command=self.app.toggle_theme,
        )
        self._theme_btn.pack(fill="x", padx=10, pady=(2, 14))
        tip(self._theme_btn, "Toggle dark / light theme")

    def set_active(self, key: str):
        for k, btn in self._buttons.items():
            btn.configure(fg_color=C.ACCENT if k == key else "transparent")

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.PANEL)
        self._buttons.clear()
        self._build()
