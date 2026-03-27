"""BC4D Intel — main application shell (customtkinter)."""

from __future__ import annotations
import importlib, logging
import customtkinter as ctk

from bc4d_intel import constants as C
from bc4d_intel.ui.sidebar import Sidebar
from bc4d_intel.app_state import AppState

log = logging.getLogger("bc4d_intel.app")

# ── Lazy frame registry ──────────────────────────────────────────
_FRAME_REGISTRY = {
    "import":      ("bc4d_intel.screens.screen_import",      "ImportScreen"),
    "dashboard":   ("bc4d_intel.screens.screen_dashboard",   "DashboardScreen"),
    "analysis":    ("bc4d_intel.screens.screen_analysis",    "AnalysisScreen"),
    "clusters":    ("bc4d_intel.screens.screen_clusters",    "ClustersScreen"),
    "responses":   ("bc4d_intel.screens.screen_responses",   "ResponsesScreen"),
    "report":      ("bc4d_intel.screens.screen_report",      "ReportScreen"),
    "settings":    ("bc4d_intel.screens.screen_settings",    "SettingsScreen"),
}


class App(ctk.CTk):
    def __init__(self):
        super().__init__()

        # Load saved state
        self.app_state = AppState.load()

        # Apply saved theme
        saved_theme = self.app_state.theme or "dark"
        ctk.set_appearance_mode(saved_theme)
        C.apply_theme(saved_theme)

        self.title("BC4D Intel — Survey Evaluation")
        self.geometry("1300x800")
        self.minsize(1000, 620)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ── Layout ──
        self._sidebar = Sidebar(self, app=self)
        self._sidebar.pack(side="left", fill="y")

        self._main = ctk.CTkFrame(self, fg_color=C.BG, corner_radius=0)
        self._main.pack(side="left", fill="both", expand=True)

        # Frame cache
        self._frames = {}
        self._active_key = None

        # Show import screen by default
        self.show_frame("import")

        # Keyboard shortcuts
        self.bind("<Control-Key-1>", lambda e: self.show_frame("import"))
        self.bind("<Control-Key-2>", lambda e: self.show_frame("dashboard"))
        self.bind("<Control-Key-3>", lambda e: self.show_frame("validation"))
        self.bind("<Control-Key-4>", lambda e: self.show_frame("report"))
        self.bind("<Control-Key-5>", lambda e: self.show_frame("settings"))

    # ── Navigation ──

    def _ensure_frame(self, key):
        if key not in self._frames:
            mod_path, cls_name = _FRAME_REGISTRY[key]
            mod = importlib.import_module(mod_path)
            cls = getattr(mod, cls_name)
            frame = cls(self._main, app=self)
            self._frames[key] = frame
        return self._frames[key]

    def show_frame(self, key: str):
        if key == self._active_key:
            return
        frame = self._ensure_frame(key)
        if self._active_key and self._active_key in self._frames:
            self._frames[self._active_key].pack_forget()
        frame.pack(fill="both", expand=True)
        self._active_key = key
        self._sidebar.set_active(key)
        if hasattr(frame, "refresh"):
            frame.refresh()

    # ── Theme toggle ──

    def toggle_theme(self):
        new = "light" if C.current_theme() == "dark" else "dark"
        ctk.set_appearance_mode(new)
        C.apply_theme(new)

        self.app_state.theme = new
        self.app_state.save()

        self._sidebar.rebuild()
        self._sidebar.set_active(self._active_key or "import")
        self._main.configure(fg_color=C.BG)

        if self._active_key and self._active_key in self._frames:
            frame = self._frames[self._active_key]
            if hasattr(frame, "rebuild"):
                frame.rebuild()
            if hasattr(frame, "refresh"):
                frame.refresh()

    def _on_close(self):
        self.app_state.save()
        self.destroy()
