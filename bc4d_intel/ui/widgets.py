"""Shared UI widgets for BC4D Intel — adapted from ISD Intel."""

from __future__ import annotations
import customtkinter as ctk
from bc4d_intel import constants as C


class Tooltip:
    """Lightweight hover tooltip."""

    def __init__(self, widget, text: str, delay: int = 650, wraplength: int = 300):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.wraplength = wraplength
        self._tw = None
        self._after_id = None
        widget.bind("<Enter>", self._schedule)
        widget.bind("<Leave>", self._hide)

    def _schedule(self, event=None):
        self._after_id = self.widget.after(self.delay, self._show)

    def _show(self):
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        tw = ctk.CTkToplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)
        lbl = ctk.CTkLabel(
            tw, text=self.text, wraplength=self.wraplength,
            fg_color=C.PANEL, text_color=C.TEXT,
            corner_radius=6, padx=10, pady=6,
            font=ctk.CTkFont(family="Segoe UI", size=11),
        )
        lbl.pack()
        self._tw = tw

    def _hide(self, event=None):
        if self._after_id:
            self.widget.after_cancel(self._after_id)
            self._after_id = None
        if self._tw:
            self._tw.destroy()
            self._tw = None


def tip(widget, text: str, wraplength: int = 300):
    """Convenience: attach a tooltip."""
    Tooltip(widget, text, wraplength=wraplength)


def make_card(parent, **kw) -> ctk.CTkFrame:
    return ctk.CTkFrame(parent, fg_color=C.CARD, corner_radius=10, **kw)


def make_toolbar(parent, height: int = 52) -> ctk.CTkFrame:
    tb = ctk.CTkFrame(parent, fg_color=C.PANEL, corner_radius=0, height=height)
    tb.pack(fill="x")
    tb.pack_propagate(False)
    return tb


def heading(parent, text: str, size: int = 28) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        parent, text=text, text_color=C.TEXT,
        font=ctk.CTkFont(family="Segoe UI", size=size, weight="bold"),
    )


def muted_label(parent, text: str, size: int = 11) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        parent, text=text, text_color=C.MUTED,
        font=ctk.CTkFont(family="Segoe UI", size=size),
    )


def accent_button(parent, text: str, command=None, width: int = 140, **kw) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent, text=text, command=command, width=width,
        fg_color=C.ACCENT, hover_color=C.SELECT,
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        height=36, corner_radius=6, **kw,
    )


def secondary_button(parent, text: str, command=None, width: int = 120, **kw) -> ctk.CTkButton:
    return ctk.CTkButton(
        parent, text=text, command=command, width=width,
        fg_color=C.BTN, hover_color=C.SELECT,
        font=ctk.CTkFont(family="Segoe UI", size=12),
        height=36, corner_radius=6, **kw,
    )


def status_badge(parent, text: str, color: str = None) -> ctk.CTkLabel:
    """Small colored status badge (e.g., 'Matched', 'Pending', 'Error')."""
    return ctk.CTkLabel(
        parent, text=text,
        fg_color=color or C.DIM,
        text_color="#ffffff",
        font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
        corner_radius=4, padx=8, pady=2,
    )
