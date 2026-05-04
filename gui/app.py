"""
Minimal GUI entry point for the Rekordbox Phrase-to-Memory Cue app.
"""

import tkinter as tk
from tkinter import messagebox, simpledialog
from tkinter import ttk

from core import processing
from gui.theme import apply_theme

def main():

    root = tk.Tk()
    root.title("Rekordbox Phrase Cue Setter")
    root.geometry("500x300")
    apply_theme(root)

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True)

    # --- Main Tab ---
    main_frame = ttk.Frame(notebook)
    notebook.add(main_frame, text="Main")

    def process_specific_track():
        processing.process_specific_track_gui(root)

    def process_track_per_track():
        processing.process_track_per_track_gui(root)

    def process_all_tracks():
        processing.process_all_tracks_gui(root)

    btn1 = ttk.Button(
        main_frame, text="Track per Track", command=process_track_per_track
    )
    btn1.pack(fill="x", padx=20, pady=10)

    btn2 = ttk.Button(main_frame, text="Specific Track", command=process_specific_track)
    btn2.pack(fill="x", padx=20, pady=10)

    btn3 = ttk.Button(main_frame, text="All Tracks", command=process_all_tracks)
    btn3.pack(fill="x", padx=20, pady=10)

    # --- Configuration Tab ---
    config_frame = ttk.Frame(notebook)
    notebook.add(config_frame, text="Configuration")

    processing.common_actions()

    root.mainloop()


if __name__ == "__main__":
    main()
