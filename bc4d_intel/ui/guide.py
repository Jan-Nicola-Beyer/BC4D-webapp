"""Workflow guidance — contextual help panels for each screen.

Shows the user: where they are, what to do, what happens next.
"""

from __future__ import annotations
import customtkinter as ctk
from bc4d_intel import constants as C


def workflow_steps(parent, current_step: int = 0) -> ctk.CTkFrame:
    """Show a horizontal step indicator matching the actual nav order.

    Args:
        current_step: 0=Import, 1=Dashboard, 2=AI Analysis,
                      3=Clusters, 4=Responses, 5=Report
    """
    frame = ctk.CTkFrame(parent, fg_color="transparent", height=30)
    steps = ["1. Import", "2. Dashboard", "3. AI Analysis",
             "4. Clusters", "5. Responses", "6. Report"]

    for i, label in enumerate(steps):
        if i < current_step:
            color, weight = C.SUCCESS, "normal"
            prefix = "\u2714 "  # checkmark
        elif i == current_step:
            color, weight = C.ACCENT, "bold"
            prefix = "\u25B6 "  # triangle
        else:
            color, weight = C.MUTED, "normal"
            prefix = "  "

        ctk.CTkLabel(
            frame, text=f"{prefix}{label}",
            font=ctk.CTkFont(family="Segoe UI", size=10, weight=weight),
            text_color=color,
        ).pack(side="left", padx=6)

        if i < len(steps) - 1:
            ctk.CTkLabel(frame, text="\u2192",
                         font=ctk.CTkFont(size=10), text_color=C.DIM
                         ).pack(side="left", padx=2)

    return frame


def info_banner(parent, title: str, body: str, icon: str = "\u2139",
                color: str = None) -> ctk.CTkFrame:
    """Contextual info banner explaining what the user should do.

    Args:
        title: Bold heading (e.g., "What happens next")
        body: Explanation text
        icon: Unicode icon
        color: Background color (default: blue tint)
    """
    is_dark = C.current_theme() == "dark"
    if color:
        bg = color
    else:
        bg = "#1e293b" if is_dark else "#e8f0fe"
    title_color = "#f1f5f9" if is_dark else "#1e3a5f"
    body_color = "#e2e8f0" if is_dark else "#374151"

    frame = ctk.CTkFrame(parent, fg_color=bg, corner_radius=8)

    inner = ctk.CTkFrame(frame, fg_color="transparent")
    inner.pack(fill="x", padx=16, pady=12)

    ctk.CTkLabel(
        inner, text=f"{icon} {title}",
        font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        text_color=title_color,
    ).pack(anchor="w", pady=(0, 6))

    ctk.CTkLabel(
        inner, text=body,
        font=ctk.CTkFont(family="Segoe UI", size=11),
        text_color=body_color, wraplength=700, justify="left",
    ).pack(anchor="w")

    return frame


def progress_panel(parent) -> dict:
    """Create a progress panel with bar, percentage, ETA, and detail text.

    Returns dict with: frame, bar, pct_label, detail_label, eta_label
    for the caller to update during processing.
    """
    frame = ctk.CTkFrame(parent, fg_color=C.PANEL, corner_radius=8)

    inner = ctk.CTkFrame(frame, fg_color="transparent")
    inner.pack(fill="x", padx=14, pady=10)

    # Progress bar
    bar = ctk.CTkProgressBar(inner, width=400, height=14,
                              progress_color=C.ACCENT, fg_color=C.ENTRY_BG)
    bar.pack(fill="x", pady=(0, 6))
    bar.set(0)

    row = ctk.CTkFrame(inner, fg_color="transparent")
    row.pack(fill="x")

    pct_label = ctk.CTkLabel(
        row, text="0%",
        font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
        text_color=C.ACCENT,
    )
    pct_label.pack(side="left")

    eta_label = ctk.CTkLabel(
        row, text="",
        font=ctk.CTkFont(family="Segoe UI", size=10),
        text_color=C.MUTED,
    )
    eta_label.pack(side="right")

    detail_label = ctk.CTkLabel(
        inner, text="Starting...",
        font=ctk.CTkFont(family="Segoe UI", size=10),
        text_color=C.MUTED, anchor="w",
    )
    detail_label.pack(fill="x", pady=(4, 0))

    return {
        "frame": frame,
        "bar": bar,
        "pct_label": pct_label,
        "eta_label": eta_label,
        "detail_label": detail_label,
    }
