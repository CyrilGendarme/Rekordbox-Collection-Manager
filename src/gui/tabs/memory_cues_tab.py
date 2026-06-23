"""
Tab definitions for the Rekordbox Phrase-to-Memory Cue app.
This module now exposes a pluggable feature object for the generic tab system.
"""

import tkinter as tk
from tkinter import ttk

from src.core.memory_cues import processing
from src.gui.tab_system import ConfigSubtabFeature, FeatureContext


class MemoryCuesFeature(ConfigSubtabFeature):
    name = "memory_cues"
    config_tab_title = "Memory Cues"

    def __init__(self):
        pass
    
    # -----------------------------
    # MEMORY CUES TAB
    # -----------------------------
    def build_main_tab(self, context: FeatureContext):
        main_frame = ttk.Frame(context.notebook)
        context.notebook.add(main_frame, text="Memory Cues")
        self._create_widgets(context, main_frame)
        return main_frame

    def _create_widgets(self, context: FeatureContext, parent: ttk.Frame):
        ttk.Button(
            parent,
            text="Track per Track",
            command=lambda: processing.process_track_per_track_gui(message_box_callback=context.controller.show_message_box),
        ).pack(fill="x", padx=20, pady=10)

        ttk.Button(
            parent,
            text="All Tracks",
            command=lambda: processing.process_all_tracks_gui(message_box_callback=context.controller.show_message_box),
        ).pack(fill="x", padx=20, pady=10)

        ttk.Button(
            parent,
            text="Remove memory cues on tracks with less than two",
            command=lambda: processing.remove_memory_cues_if_less_than_two()    ,
        ).pack(fill="x", padx=20, pady=10)

        ttk.Button(
            parent,
            text="Remove '1.1 bars' cues",
            command=lambda: processing.remove_1_1_bars_cues_from_all_tracks(),
        ).pack(fill="x", padx=20, pady=10)

    # -----------------------------
    # CONFIG TAB
    # -----------------------------
    def _create_config_widgets(self, context: FeatureContext, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="Configuration settings coming soon...",
        ).pack(padx=20, pady=20)
