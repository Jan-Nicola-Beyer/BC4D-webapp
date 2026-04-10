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


class GlobalMagnifier:
    """Global Ctrl+Click magnifier — works on any text in the app.

    Ctrl+Click on any label, button, or entry to see it enlarged.
    Click anywhere or press Escape to dismiss.
    """

    def __init__(self, root):
        self.root = root
        self._popup = None
        root.bind_all("<Control-Button-1>", self._on_ctrl_click)
        root.bind_all("<Escape>", self._dismiss)

    def _on_ctrl_click(self, event):
        self._dismiss()

        widget = event.widget
        text = ""

        # Try to extract text from the widget under the cursor
        try:
            text = widget.cget("text")
        except Exception:
            pass

        if not text:
            try:
                # CTkLabel stores text differently
                text = widget._text_label.cget("text") if hasattr(widget, "_text_label") else ""
            except Exception:
                pass

        if not text:
            try:
                # CTkEntry / tk.Text
                text = widget.get("1.0", "end-1c") if hasattr(widget, "get") else ""
            except Exception:
                try:
                    text = widget.get()
                except Exception:
                    pass

        if not text or len(text.strip()) < 3:
            return

        text = text.strip()

        # Position popup near cursor
        x = event.x_root + 10
        y = event.y_root - 60
        if y < 10:
            y = event.y_root + 20

        # Clamp to screen
        sw = self.root.winfo_screenwidth()
        if x + 500 > sw:
            x = sw - 520

        popup = ctk.CTkToplevel(self.root)
        popup.wm_overrideredirect(True)
        popup.wm_geometry(f"+{x}+{y}")
        popup.attributes("-topmost", True)
        popup.configure(fg_color="#0f172a")

        frame = ctk.CTkFrame(popup, fg_color="#1e293b", corner_radius=10,
                              border_width=2, border_color="#C7074D")
        frame.pack(padx=2, pady=2)

        ctk.CTkLabel(
            frame, text=text,
            wraplength=480,
            fg_color="transparent", text_color="#f1f5f9",
            font=ctk.CTkFont(family="Segoe UI", size=16),
            padx=16, pady=12, justify="left",
        ).pack()

        # Click anywhere on popup to close
        popup.bind("<Button-1>", lambda e: self._dismiss())

        self._popup = popup

    def _dismiss(self, event=None):
        if self._popup:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None


def magnify(widget, text: str = "", font_size: int = 15):
    """Legacy per-widget magnifier — kept for compatibility but GlobalMagnifier is preferred."""
    tip(widget, text or "(Ctrl+Click to magnify)")


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
