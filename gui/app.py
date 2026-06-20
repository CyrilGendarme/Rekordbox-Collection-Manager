"""
Minimal GUI entry point for the Rekordbox Phrase-to-Memory Cue app.
Generic app launcher with tab system.
"""

import tkinter as tk
from tkinter import ttk

from gui.theme import apply_theme
from gui.memory_cues_tab import build_main_tab, build_config_tab

def main():
    root = tk.Tk()
    root.title("Rekordbox Phrase Cue Setter")
    # root.geometry("500x300")

    apply_theme(root)

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True)

    # Build tabs (delegated)
    build_main_tab(notebook, root)
    build_config_tab(notebook, root)

    root.mainloop()


if __name__ == "__main__":
    main()
