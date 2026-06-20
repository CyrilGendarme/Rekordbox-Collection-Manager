"""
Tab definitions for the Rekordbox Phrase-to-Memory Cue app.
Each function builds and registers a tab in the notebook.
"""

import tkinter as tk
from tkinter import ttk

from core.memory_cues import processing

# -----------------------------
# MEMORY CUES TAB
# -----------------------------
def build_main_tab(notebook: ttk.Notebook, root: tk.Tk):
    main_frame = ttk.Frame(notebook)
    notebook.add(main_frame, text="Main")

    def process_specific_track():
        processing.process_specific_track_gui(root)

    def process_track_per_track():
        processing.process_track_per_track_gui(root)

    def process_all_tracks():
        processing.process_all_tracks_gui(root)

    ttk.Button(
        main_frame,
        text="Track per Track",
        command=process_track_per_track
    ).pack(fill="x", padx=20, pady=10)

    ttk.Button(
        main_frame,
        text="Specific Track",
        command=process_specific_track
    ).pack(fill="x", padx=20, pady=10)

    ttk.Button(
        main_frame,
        text="All Tracks",
        command=process_all_tracks
    ).pack(fill="x", padx=20, pady=10)

    ttk.Button(
        main_frame,
        text="Remove memory cues on tracks with less than two",
        command=processing.remove_memory_cues_if_less_than_two,
    ).pack(fill="x", padx=20, pady=10)

    ttk.Button(
        main_frame,
        text="Remove '1.1 bars' cues",
        command=processing.remove_1_1_bars_cues_from_all_tracks,
    ).pack(fill="x", padx=20, pady=10)


# -----------------------------


# -----------------------------
# CONFIG TAB
# -----------------------------
def build_config_tab(notebook: ttk.Notebook, root: tk.Tk):
    config_frame = ttk.Frame(notebook)
    notebook.add(config_frame, text="Configuration")

    # placeholder (easy to extend later)
    ttk.Label(
        config_frame,
        text="Configuration settings coming soon..."
    ).pack(padx=20, pady=20)
