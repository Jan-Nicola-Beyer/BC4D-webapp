"""Reliability Checker — test if the answer cache classifies correctly.

The user can:
  1. Select a question from the dropdown
  2. Type a test response
  3. See if the cache matches it and what category it assigns
  4. View cache statistics (hit rates, coverage)

This builds trust before relying on the cache for classification.
"""

from __future__ import annotations
import customtkinter as ctk
from bc4d_intel import constants as C
from bc4d_intel.ui import widgets as W


class ReliabilityScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C.BG, corner_radius=0)
        self.app = app
        self._build()

    def _build(self):
        from bc4d_intel.ui.guide import workflow_steps, info_banner

        top = W.make_toolbar(self, height=100)
        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=30, pady=8)
        workflow_steps(inner, current_step=2).pack(anchor="w", pady=(0, 4))
        W.heading(inner, "Reliability Checker", size=22).pack(anchor="w")

        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=30, pady=10)

        info_banner(body,
            "How the Answer Cache Works",
            "The system learns from past classifications. After the first staffel, "
            "it builds a database of responses and their categories.\n\n"
            "For future staffels, it checks each new response against the cache:\n"
            "  - If a very similar response was seen before → reuses the classification (free)\n"
            "  - If the response is new → sends to AI for classification (costs money)\n\n"
            "Use this screen to test if the cache correctly classifies specific responses. "
            "This helps verify the system before running a full analysis.\n\n"
            "The cache grows with each staffel — more data = higher hit rate = lower cost.",
            icon="\U0001F50D",
        ).pack(fill="x", pady=(0, 12))

        # Cache stats
        stats_card = W.make_card(body)
        stats_card.pack(fill="x", pady=8)
        stats_inner = ctk.CTkFrame(stats_card, fg_color="transparent")
        stats_inner.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(stats_inner, text="Cache Statistics",
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                     text_color=C.TEXT).pack(anchor="w")
        self._stats_lbl = ctk.CTkLabel(stats_inner, text="Loading...",
                                        font=ctk.CTkFont(family="Consolas", size=11),
                                        text_color=C.MUTED, justify="left")
        self._stats_lbl.pack(anchor="w", pady=(4, 0))

        # Test area
        test_card = W.make_card(body)
        test_card.pack(fill="x", pady=8)
        test_inner = ctk.CTkFrame(test_card, fg_color="transparent")
        test_inner.pack(fill="x", padx=16, pady=12)

        ctk.CTkLabel(test_inner, text="Test a Response",
                     font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
                     text_color=C.TEXT).pack(anchor="w")

        # Question selector
        q_row = ctk.CTkFrame(test_inner, fg_color="transparent")
        q_row.pack(fill="x", pady=(8, 4))

        ctk.CTkLabel(q_row, text="Question:",
                     font=ctk.CTkFont(size=11), text_color=C.MUTED).pack(side="left", padx=(0, 8))
        self._question_var = ctk.StringVar(value="Select a question...")
        self._question_menu = ctk.CTkOptionMenu(
            q_row, variable=self._question_var,
            values=["(run AI Analysis first to populate)"],
            font=ctk.CTkFont(size=11), fg_color=C.BTN, button_color=C.DIM,
            height=30, width=400, corner_radius=6,
        )
        self._question_menu.pack(side="left")

        # Test input
        input_row = ctk.CTkFrame(test_inner, fg_color="transparent")
        input_row.pack(fill="x", pady=4)

        self._test_entry = ctk.CTkEntry(
            input_row, placeholder_text="Type a test response (e.g., 'Austausch war sehr wertvoll')",
            font=ctk.CTkFont(size=12), fg_color=C.ENTRY_BG, border_color=C.ENTRY_BORDER,
            height=38,
        )
        self._test_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self._test_entry.bind("<Return>", lambda e: self._test_response())

        W.accent_button(input_row, text="Test", width=80,
                        command=self._test_response).pack(side="right")

        # Result area
        self._result_frame = ctk.CTkFrame(test_inner, fg_color="transparent")
        self._result_frame.pack(fill="x", pady=(8, 0))

    def refresh(self):
        # Update cache stats
        try:
            from bc4d_intel.core.answer_cache import get_cache_stats
            stats = get_cache_stats()
            self._stats_lbl.configure(
                text=f"Cached answers: {stats['total_answers']}\n"
                     f"Questions covered: {stats['questions']}\n"
                     f"Staffels learned: {stats['staffels']}",
                text_color=C.TEXT)
        except Exception:
            self._stats_lbl.configure(text="Cache not yet built. Run AI Analysis first.",
                                       text_color=C.MUTED)

        # Update question dropdown
        results = getattr(self.app, "_analysis_results", {})
        if results:
            self._question_menu.configure(values=list(results.keys()))

    def _test_response(self):
        """Test a single response against the cache."""
        question = self._question_var.get()
        text = self._test_entry.get().strip()

        if not text:
            return
        if question in ("Select a question...", "(run AI Analysis first to populate)"):
            return

        # Clear previous result
        for w in self._result_frame.winfo_children():
            w.destroy()

        try:
            from bc4d_intel.core.answer_cache import test_reliability

            result = test_reliability(question, text)

            if result.get("matched"):
                # Cache hit — show green
                card = ctk.CTkFrame(self._result_frame, fg_color=C.SUCCESS, corner_radius=8)
                card.pack(fill="x", pady=4)
                card_inner = ctk.CTkFrame(card, fg_color="transparent")
                card_inner.pack(fill="x", padx=14, pady=10)

                ctk.CTkLabel(card_inner, text="CACHE HIT (free classification)",
                             font=ctk.CTkFont(size=14, weight="bold"),
                             text_color="#ffffff").pack(anchor="w")

                ctk.CTkLabel(card_inner,
                    text=f"Category: {result['main_category']} > {result['cluster_title']}\n"
                         f"Similarity: {result['score']:.1%} (threshold: {result['threshold']:.0%})\n"
                         f"Matched to: \"{result['cache_match'][:80]}\"\n"
                         f"Cache size: {result['n_cached']} answers",
                    font=ctk.CTkFont(size=11),
                    text_color="#e0e0e0", justify="left").pack(anchor="w", pady=(4, 0))

            else:
                # Cache miss — show amber
                card = ctk.CTkFrame(self._result_frame, fg_color=C.WARN, corner_radius=8)
                card.pack(fill="x", pady=4)
                card_inner = ctk.CTkFrame(card, fg_color="transparent")
                card_inner.pack(fill="x", padx=14, pady=10)

                ctk.CTkLabel(card_inner, text="CACHE MISS (AI needed)",
                             font=ctk.CTkFont(size=14, weight="bold"),
                             text_color="#ffffff").pack(anchor="w")

                reason = result.get("reason", "")
                if result.get("score"):
                    ctk.CTkLabel(card_inner,
                        text=f"Best match similarity: {result['score']:.1%} "
                             f"(below threshold: {result.get('threshold', 0.9):.0%})\n"
                             f"Closest cached: \"{result.get('cache_match', 'N/A')[:80]}\"\n"
                             f"This response would need AI classification (~$0.001)",
                        font=ctk.CTkFont(size=11),
                        text_color="#e0e0e0", justify="left").pack(anchor="w", pady=(4, 0))
                elif reason:
                    ctk.CTkLabel(card_inner, text=reason,
                                 font=ctk.CTkFont(size=11),
                                 text_color="#e0e0e0").pack(anchor="w", pady=(4, 0))

        except Exception as e:
            ctk.CTkLabel(self._result_frame, text=f"Error: {e}",
                         font=ctk.CTkFont(size=11), text_color=C.DANGER).pack(anchor="w")

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.BG)
        self._build()
