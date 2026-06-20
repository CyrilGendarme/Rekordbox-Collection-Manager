import tkinter as tk
from tkinter import ttk, messagebox
from typing import Callable, Iterable, Optional

from .theme import (
    apply_theme,
    BG,
    BG_PANEL,
    ACCENT,
    FG_DIM,
    BORDER,
    FONT_TITLE,
    FONT_MONO_SM,
)
from .tab_system import FeatureContext, TabFeature, build_registered_tabs


class MainWindow:
    """Main application window for Rekordbox Collection Manager."""

    def __init__(self, controller):
        self.root = tk.Tk()
        self.root.title("Rekordbox Collection Manager")
        self.root.geometry("1280x820")
        self.root.minsize(900, 600)
        self.root.state("zoomed")  # start maximized on Windows
        self.controller = controller

        apply_theme(self.root)

        self.on_load_tracks: Optional[Callable] = None
        self.on_generate_set: Optional[Callable] = None
        self.on_add_link: Optional[Callable] = None
        self.on_delete_link: Optional[Callable] = None
        self._status_callback: Optional[Callable[[str], None]] = None
        self.tracks_tab = None

        self._create_widgets()

    def _create_widgets(self):
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        # ── Header ───────────────────────────────────────────────────────
        header = tk.Frame(self.root, bg=BG_PANEL, height=52)
        header.grid(row=0, column=0, sticky="ew")
        header.grid_propagate(False)

        tk.Label(
            header,
            text="  // REKORDBOX COLLECTION MANAGER",
            bg=BG_PANEL,
            fg=ACCENT,
            font=FONT_TITLE,
        ).pack(side=tk.LEFT, padx=(18, 0))

        ttk.Button(
            header,
            text="reload library",
            command=self.controller.refresh_collection,
            style="Accent.TButton",
        ).pack(side=tk.RIGHT, padx=(0, 18), pady=10)

        # Accent underline
        tk.Frame(self.root, bg=ACCENT, height=1).grid(row=0, column=0, sticky="sew")

        # ── Notebook content (merged from gui/app.py) ───────────────────
        content_frame = ttk.Frame(self.root)
        content_frame.grid(row=1, column=0, sticky="nsew")
        content_frame.columnconfigure(0, weight=1)
        content_frame.rowconfigure(0, weight=1)

        self.notebook = ttk.Notebook(content_frame)
        self.notebook.grid(row=0, column=0, sticky="nsew")

        # ── Status bar ───────────────────────────────────────────────────
        tk.Frame(self.root, bg=BORDER, height=1).grid(row=2, column=0, sticky="ew")

        status_bar = tk.Frame(self.root, bg=BG_PANEL, height=26)
        status_bar.grid(row=3, column=0, sticky="ew")
        status_bar.grid_propagate(False)

        self._status_var = tk.StringVar(value="ready.")
        tk.Label(
            status_bar,
            textvariable=self._status_var,
            bg=BG_PANEL,
            fg=FG_DIM,
            font=FONT_MONO_SM,
            anchor="w",
        ).pack(side=tk.LEFT, padx=14, fill=tk.Y)

        tk.Label(
            status_bar,
            text="v1.0",
            bg=BG_PANEL,
            fg=ACCENT,
            font=FONT_MONO_SM,
        ).pack(side=tk.RIGHT, padx=14)

    # ── Public API (called by AppController) ─────────────────────────────

    def register_features(self, features: Iterable[TabFeature], controller=None):
        context = FeatureContext(
            root=self.root, notebook=self.notebook, controller=controller
        )
        build_registered_tabs(context, features)

        # # Keep a stable handle for AppController's track operations.
        # self.tracks_tab = None
        # for feature in features:
        #     main_tab = getattr(feature, "main_tab", None)
        #     if main_tab is not None and hasattr(main_tab, "set_tracks"):
        #         self.tracks_tab = main_tab
        #         break

    def set_status_callback(self, callback: Callable[[str], None]):
        self._status_callback = callback

    def set_status(self, message: str):
        self._status_var.set(message)
        if self._status_callback:
            self._status_callback(message)

    def show_info(self, title: str, message: str):
        messagebox.showinfo(title, message, parent=self.root)

    def show_error(self, title: str, message: str):
        messagebox.showerror(title, message, parent=self.root)

    def show_warning(self, title: str, message: str):
        messagebox.showwarning(title, message, parent=self.root)

    def run(self):
        self.root.mainloop()
