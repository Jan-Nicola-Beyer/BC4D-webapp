"""BC4D Intel splash screen — preloads dependencies with survey jargon."""

from __future__ import annotations
import logging, random, threading, time
import customtkinter as ctk

log = logging.getLogger("bc4d_intel.ui.splash")

# ── Fake survey operations that sound official but are nonsense ──

_JARGON = [
    "Calibrating Likert scale harmonic resonance...",
    "Defragmenting respondent pseudokey lattice...",
    "Triangulating pre-post sentiment vectors...",
    "Warming up qualitative coding engine...",
    "Reticulating evaluation splines...",
    "Inflating statistical significance balloons...",
    "Synchronising cohort matching algorithms...",
    "Polishing Cronbach's alpha coefficients...",
    "Deconvolving survey fatigue noise floor...",
    "Fermenting response categorisation cultures...",
    "Untangling drop-out attribution spaghetti...",
    "Pressurising feedback loop valves...",
    "Crystallising thematic cluster centroids...",
    "Composting deprecated questionnaire items...",
    "Excavating buried evaluation insights...",
    "Seasoning effect size reduction sauce...",
    "Hydrating respondent engagement metrics...",
    "Rendering training satisfaction heatmaps...",
    "Inoculating against acquiescence bias...",
    "Distilling participant voice extract...",
    "Buffering constructive criticism queue...",
    "Marinating cross-staffel comparison broth...",
    "Equilibrating evaluation rigour harmonics...",
    "Percolating open-ended response filters...",
    "Carbonating real-time feedback bubbles...",
    "Braiding mixed-methods analysis fibres...",
    "Tempering response rate correction rods...",
    "Searing raw data with analytical flame...",
    "Decanting vintage baseline assessments...",
    "Churning programme impact butter...",
    "Kneading stakeholder expectation dough...",
    "Germinating evidence-based practice spores...",
    "Photosynthesising evaluation sunlight...",
    "Levitating outcome indicator orbs...",
    "Forging causal attribution alloys...",
    "Irrigating capacity building seeds...",
    "Unfreezing archived staffel core samples...",
    "Composing evaluation symphony overture...",
    "Tuning beneficiary feedback frequency...",
    "Weaving theory-of-change tapestry...",
    "Summoning the ghost of missing data...",
    "Herding open-ended response categories...",
    "Sharpening Occam's evaluation razor...",
    "Polishing the all-seeing eye of M&E...",
    "Quantum-entangling analyst coffee supply...",
    "Defrosting legacy programme datasets...",
    "Assembling participatory evaluation quorum...",
    "Distorting social desirability noise floor...",
    "Compressing evaluation fatigue eigenvalues...",
    "Activating deep learning satisfaction index...",
    "Encrypting confidential respondent data...",
    "Normalising trainer effectiveness tensors...",
    "Spinning up knowledge transfer centrifuge...",
    "Mapping competence acquisition topology...",
    "Caching behavioural change indicators...",
    "Resolving attribution gap singularities...",
    "Projecting sustainability outcome vectors...",
    "Deploying impact measurement probes...",
    "Collating stakeholder perception residuals...",
    "Aligning programme logic model wavelengths...",
]


class SplashScreen(ctk.CTkToplevel):
    """Loading screen that preloads dependencies while showing survey jargon."""

    def __init__(self, parent, on_complete=None):
        super().__init__(parent)

        self.on_complete = on_complete
        self._done = False
        self._tasks_done = 0
        self._total_tasks = 4

        # Window setup
        self.title("BC4D Intel")
        self.geometry("480x300")
        self.resizable(False, False)
        self.overrideredirect(True)

        # Center on screen
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - 480) // 2
        y = (sh - 300) // 2
        self.geometry(f"480x300+{x}+{y}")

        self.lift()
        self.attributes("-topmost", True)

        # ── UI ──
        bg = "#0d1117"
        self.configure(fg_color=bg)

        ctk.CTkLabel(
            self, text="BC4D INTEL",
            font=ctk.CTkFont(family="Segoe UI", size=26, weight="bold"),
            text_color="#C7074D",
        ).pack(pady=(35, 2))

        ctk.CTkLabel(
            self, text="Survey Evaluation System",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color="#6b7280",
        ).pack()

        self._jargon_lbl = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(family="Consolas", size=10),
            text_color="#059669",
        )
        self._jargon_lbl.pack(pady=(28, 8))

        self._progress = ctk.CTkProgressBar(
            self, width=380, height=8,
            progress_color="#C7074D",
            fg_color="#1c2333",
        )
        self._progress.pack(pady=(0, 8))
        self._progress.set(0)

        self._status_lbl = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color="#374151",
        )
        self._status_lbl.pack()

        ctk.CTkLabel(
            self, text="Institute for Strategic Dialogue",
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color="#374151",
        ).pack(side="bottom", pady=(0, 12))

        # Shuffle jargon
        self._pool = list(_JARGON)
        random.shuffle(self._pool)
        self._idx = 0

        self._cycle_jargon()
        self._start_preloading()

    def _cycle_jargon(self):
        if self._done:
            return
        self._jargon_lbl.configure(text=self._pool[self._idx % len(self._pool)])
        self._idx += 1
        self.after(random.randint(250, 550), self._cycle_jargon)

    def _update(self, status: str):
        self._tasks_done += 1
        p = self._tasks_done / self._total_tasks
        self.after(0, lambda: self._progress.set(p))
        self.after(0, lambda s=status: self._status_lbl.configure(text=s))

    def _start_preloading(self):
        self._total_tasks = 5

        def _work():
            # 1. Database + SQLite
            self.after(0, lambda: self._status_lbl.configure(text="Database..."))
            try:
                from bc4d_intel.core.answer_cache import _get_conn
                conn = _get_conn()
                conn.close()
            except Exception as e:
                log.warning("Splash: DB init failed: %s", e)
            self._update("Database ready")

            # 2. Pandas + data loader (heavy: ~3.8s first import)
            self.after(0, lambda: self._status_lbl.configure(text="Data engine..."))
            try:
                import pandas  # noqa: F401
                from bc4d_intel.core.data_loader import load_survey  # noqa: F401
            except Exception as e:
                log.warning("Splash: pandas failed: %s", e)
            self._update("Data engine ready")

            # 3. Matplotlib (heavy: ~1.4s first import)
            self.after(0, lambda: self._status_lbl.configure(text="Chart engine..."))
            try:
                from bc4d_intel.core.chart_builder import _ensure_mpl
                _ensure_mpl()
                import matplotlib.pyplot as plt  # noqa: F401
            except Exception as e:
                log.warning("Splash: matplotlib failed: %s", e)
            self._update("Charts ready")

            # 4. Scipy / stats engine (heavy: ~1s first import)
            self.after(0, lambda: self._status_lbl.configure(text="Statistics engine..."))
            try:
                from scipy import stats as _  # noqa: F401
                from bc4d_intel.core.stats_engine import descriptive_stats  # noqa: F401
            except Exception as e:
                log.warning("Splash: scipy failed: %s", e)
            self._update("Statistics ready")

            # 5. Final
            self.after(0, lambda: self._status_lbl.configure(text="Finalising..."))
            time.sleep(0.2)
            self._update("Ready")

            # Finish
            self.after(0, self._finish)

        threading.Thread(target=_work, daemon=True).start()

    def _finish(self):
        self._done = True
        self._jargon_lbl.configure(
            text="All systems operational.",
            text_color="#059669",
        )
        self._status_lbl.configure(text="")
        self._progress.set(1.0)
        self.after(600, self._close)

    def _close(self):
        if self.on_complete:
            self.on_complete()
        self.withdraw()
