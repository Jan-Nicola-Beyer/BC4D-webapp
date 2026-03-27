"""Report screen — AI-drafted report with 7 sections + manual editing.

Each section can be:
  - Generated via Sonnet (streamed to UI)
  - Manually edited after generation
  - Re-generated if edits are unsatisfactory
  - Exported as DOCX
"""

from __future__ import annotations
import threading, tkinter as tk
import customtkinter as ctk
from bc4d_intel import constants as C
from bc4d_intel.ui import widgets as W
from bc4d_intel.ai.prompts import REPORT_SECTIONS

SECTION_LABELS = {
    "executive_summary": "1. Executive Summary",
    "method_sample": "2. Method & Sample",
    "quantitative_results": "3. Quantitative Results",
    "qualitative_findings": "4. Qualitative Findings",
    "pre_post_comparison": "5. Pre/Post Comparison",
    "recommendations": "6. Recommendations",
    "appendix": "7. Appendix",
}


class ReportScreen(ctk.CTkFrame):
    def __init__(self, master, app):
        super().__init__(master, fg_color=C.BG, corner_radius=0)
        self.app = app
        self._sections = {}  # {section_name: text}
        self._current_section = None
        self._build()

    def _build(self):
        # ── Top bar ──
        top = W.make_toolbar(self, height=80)
        inner = ctk.CTkFrame(top, fg_color="transparent")
        inner.pack(fill="x", padx=30, pady=12)

        W.heading(inner, "Report", size=22).pack(side="left")

        btn_row = ctk.CTkFrame(inner, fg_color="transparent")
        btn_row.pack(side="right")

        self._generate_all_btn = W.accent_button(
            btn_row, text="Generate All Sections",
            command=self._generate_all, width=180)
        self._generate_all_btn.pack(side="left", padx=(0, 8))

        W.secondary_button(
            btn_row, text="Export DOCX",
            command=self._export_docx, width=120).pack(side="left", padx=(0, 8))

        self._status_lbl = ctk.CTkLabel(btn_row, text="",
                                         font=ctk.CTkFont(family="Segoe UI", size=11),
                                         text_color=C.MUTED)
        self._status_lbl.pack(side="left")

        # ── Body: section list (left) + editor (right) ──
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=10)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=3)
        body.rowconfigure(0, weight=1)

        # Left: section list
        left = W.make_card(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 5))

        ctk.CTkLabel(left, text="Report Sections",
                     font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
                     text_color=C.TEXT).pack(anchor="w", padx=12, pady=(10, 4))

        self._section_frame = ctk.CTkFrame(left, fg_color="transparent")
        self._section_frame.pack(fill="both", expand=True, padx=6, pady=6)

        for key, label in SECTION_LABELS.items():
            btn = ctk.CTkButton(
                self._section_frame,
                text=label, anchor="w", height=36,
                fg_color=C.PANEL, hover_color=C.SELECT,
                text_color=C.TEXT,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                corner_radius=6,
                command=lambda k=key: self._select_section(k),
            )
            btn.pack(fill="x", padx=4, pady=2)

        # Right: editor
        right = W.make_card(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(5, 0))

        editor_header = ctk.CTkFrame(right, fg_color="transparent")
        editor_header.pack(fill="x", padx=12, pady=(10, 4))

        self._section_title = ctk.CTkLabel(
            editor_header, text="Select a section to edit",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=C.TEXT)
        self._section_title.pack(side="left")

        self._gen_btn = ctk.CTkButton(
            editor_header, text="Generate", width=100, height=28,
            fg_color=C.ACCENT, hover_color=C.SELECT,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            corner_radius=4,
            command=self._generate_current)
        self._gen_btn.pack(side="right")

        # Text editor
        text_container = ctk.CTkFrame(right, fg_color=C.ENTRY_BG, corner_radius=6)
        text_container.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self._editor = tk.Text(
            text_container, wrap="word", relief="flat", borderwidth=0,
            bg=C.ENTRY_BG, fg=C.TEXT, insertbackground=C.TEXT,
            font=("Segoe UI", 11), padx=14, pady=10,
            selectbackground=C.SELECT, selectforeground=C.TEXT,
            undo=True,
        )
        scrollbar = tk.Scrollbar(text_container, command=self._editor.yview)
        self._editor.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._editor.pack(side="left", fill="both", expand=True)

    def _select_section(self, section_key):
        """Load a section into the editor."""
        self._current_section = section_key
        label = SECTION_LABELS.get(section_key, section_key)
        self._section_title.configure(text=label)

        self._editor.delete("1.0", "end")
        text = self._sections.get(section_key, "")
        if text:
            self._editor.insert("1.0", text)
        else:
            self._editor.insert("1.0", f"Click 'Generate' to create this section via AI.\n\n"
                                        f"Or type your own content here.")

    def _generate_current(self):
        """Generate the current section via Sonnet."""
        if not self._current_section:
            return
        api_key = self.app.app_state.api_key
        if not api_key:
            self._status_lbl.configure(text="Set API key in Settings.", text_color=C.DANGER)
            return

        section = self._current_section
        self._gen_btn.configure(state="disabled", text="Generating...")
        self._editor.delete("1.0", "end")
        self._editor.insert("1.0", "Generating...\n")

        def work():
            from bc4d_intel.ai.report_writer import generate_section

            context = self._build_context()

            def on_stream(chunk):
                self.after(0, lambda c=chunk: self._append_text(c))

            # Clear editor before streaming
            self.after(0, lambda: self._editor.delete("1.0", "end"))

            text = generate_section(section, context, api_key, stream_cb=on_stream)
            self._sections[section] = text

            # Save to app state
            self.app.app_state.report_sections[section] = text
            self.app.app_state.save()

            self.after(0, lambda: self._gen_btn.configure(state="normal", text="Generate"))
            self.after(0, lambda: self._status_lbl.configure(
                text=f"Section generated.", text_color=C.SUCCESS))

        threading.Thread(target=work, daemon=True).start()

    def _append_text(self, chunk):
        """Append streamed text to editor."""
        self._editor.insert("end", chunk)
        self._editor.see("end")

    def _generate_all(self):
        """Generate all 7 sections sequentially."""
        api_key = self.app.app_state.api_key
        if not api_key:
            self._status_lbl.configure(text="Set API key in Settings.", text_color=C.DANGER)
            return

        self._generate_all_btn.configure(state="disabled", text="Generating...")

        def work():
            from bc4d_intel.ai.report_writer import generate_section, build_data_context

            context = self._build_context()

            for i, (section, label) in enumerate(SECTION_LABELS.items()):
                self.after(0, lambda l=label, n=i+1: self._status_lbl.configure(
                    text=f"Generating {n}/7: {l}...", text_color=C.ACCENT))

                text = generate_section(section, context, api_key)
                self._sections[section] = text
                self.app.app_state.report_sections[section] = text

            self.app.app_state.save()

            self.after(0, lambda: self._generate_all_btn.configure(
                state="normal", text="Generate All Sections"))
            self.after(0, lambda: self._status_lbl.configure(
                text="All 7 sections generated.", text_color=C.SUCCESS))
            # Show first section
            self.after(0, lambda: self._select_section("executive_summary"))

        threading.Thread(target=work, daemon=True).start()

    def _build_context(self) -> str:
        """Build rich data context with actual statistics for Sonnet."""
        from bc4d_intel.ai.report_writer import build_data_context
        match_result = getattr(self.app, "_match_result", None)
        validation_screen = self.app._frames.get("validation")
        tagged_data = validation_screen._tagged_data if validation_screen else None
        import_screen = self.app._frames.get("import")

        pre_roles = import_screen._pre_roles if import_screen else None
        post_roles = import_screen._post_roles if import_screen else None
        pre_df = import_screen._pre_df if import_screen else None
        post_df = import_screen._post_df if import_screen else None

        return build_data_context(
            self.app.app_state, match_result, tagged_data,
            pre_roles=pre_roles, post_roles=post_roles,
            pre_df=pre_df, post_df=post_df,
        )

    def _export_docx(self):
        """Export all sections to a DOCX file."""
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            title="Export Report",
            defaultextension=".docx",
            filetypes=[("Word Document", "*.docx"), ("All files", "*.*")],
            initialfile="BC4D_Staffel13_Evaluation.docx",
        )
        if not path:
            return

        try:
            from docx import Document
            from docx.shared import Pt, Inches
            from docx.enum.text import WD_ALIGN_PARAGRAPH

            doc = Document()

            # Title page
            staffel = self.app.app_state.staffel_name or "13"
            title = doc.add_heading(f"Evaluierungsbericht BC4D Staffel {staffel}", level=0)
            title.alignment = WD_ALIGN_PARAGRAPH.CENTER

            meta = doc.add_paragraph()
            meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
            meta.add_run("ISD Deutschland\n").bold = True
            meta.add_run(f"Erstellt mit BC4D Intel\n")
            import datetime
            meta.add_run(f"{datetime.date.today().strftime('%d.%m.%Y')}")

            doc.add_page_break()

            for section, label in SECTION_LABELS.items():
                text = self._sections.get(section, "")
                if not text:
                    continue

                doc.add_heading(label, level=1)

                for para_text in text.split("\n"):
                    stripped = para_text.strip()
                    if not stripped:
                        continue

                    # Detect markdown-style headings
                    if stripped.startswith("### "):
                        doc.add_heading(stripped[4:], level=3)
                    elif stripped.startswith("## "):
                        doc.add_heading(stripped[3:], level=2)
                    elif stripped.startswith("- ") or stripped.startswith("* "):
                        p = doc.add_paragraph(stripped[2:], style="List Bullet")
                    elif stripped.startswith("1. ") or stripped.startswith("2. ") or stripped.startswith("3. "):
                        p = doc.add_paragraph(stripped[3:], style="List Number")
                    else:
                        # Handle bold markers
                        p = doc.add_paragraph()
                        parts = stripped.split("**")
                        for i, part in enumerate(parts):
                            if part:
                                run = p.add_run(part)
                                if i % 2 == 1:  # odd parts are bold
                                    run.bold = True

            doc.save(path)
            self._status_lbl.configure(
                text=f"Exported to {path.split('/')[-1]}", text_color=C.SUCCESS)
        except ImportError:
            self._status_lbl.configure(
                text="python-docx not installed. Run: pip install python-docx",
                text_color=C.DANGER)
        except Exception as e:
            self._status_lbl.configure(text=f"Export error: {e}", text_color=C.DANGER)

    def refresh(self):
        # Restore sections from state
        if self.app.app_state.report_sections and not self._sections:
            self._sections = dict(self.app.app_state.report_sections)

    def rebuild(self):
        for w in self.winfo_children():
            w.destroy()
        self.configure(fg_color=C.BG)
        self._build()
