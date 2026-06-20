"""
Tab definitions for the Rekordbox Phrase-to-Memory Cue app.
This module now exposes a pluggable feature object for the generic tab system.
"""

import tkinter as tk
from tkinter import ttk

from src.core.memory_cues import processing
from src.gui.tab_system import FeatureContext, TabFeature


class MemoryCuesFeature(TabFeature):
    name = "memory_cues"

    def __init__(self):
        self._main_frame = None
        self._config_frame = None

    # -----------------------------
    # MEMORY CUES TAB
    # -----------------------------
    def build_main_tab(self, context: FeatureContext):
        main_frame = ttk.Frame(context.notebook)
        context.notebook.add(main_frame, text="Main")
        self._main_frame = main_frame
        self._create_widgets(main_frame, context.root)
        return main_frame

    def _create_widgets(self, parent: ttk.Frame, root: tk.Tk):
        ttk.Button(
            parent,
            text="Track per Track",
            command=lambda: processing.process_track_per_track_gui(root),
        ).pack(fill="x", padx=20, pady=10)

        ttk.Button(
            parent,
            text="Specific Track",
            command=lambda: processing.process_specific_track_gui(root),
        ).pack(fill="x", padx=20, pady=10)

        ttk.Button(
            parent,
            text="All Tracks",
            command=lambda: processing.process_all_tracks_gui(root),
        ).pack(fill="x", padx=20, pady=10)

        ttk.Button(
            parent,
            text="Remove memory cues on tracks with less than two",
            command=processing.remove_memory_cues_if_less_than_two,
        ).pack(fill="x", padx=20, pady=10)

        ttk.Button(
            parent,
            text="Remove '1.1 bars' cues",
            command=processing.remove_1_1_bars_cues_from_all_tracks,
        ).pack(fill="x", padx=20, pady=10)

    # -----------------------------
    # CONFIG TAB
    # -----------------------------
    def build_config_tab(self, context: FeatureContext):
        config_frame = ttk.Frame(context.notebook)
        context.notebook.add(config_frame, text="Configuration")
        self._config_frame = config_frame

        ttk.Label(
            config_frame,
            text="Configuration settings coming soon...",
        ).pack(padx=20, pady=20)
        return config_frame
