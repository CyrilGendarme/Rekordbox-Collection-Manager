"""
Minimal GUI entry point for the Rekordbox Phrase-to-Memory Cue app.
Generic app launcher with tab system.
"""

import tkinter as tk
from tkinter import ttk

from src.gui.theme import apply_theme
from src.gui.memory_cues_tab import MemoryCuesFeature
from src.gui.tab_system import FeatureContext, FeatureRegistry, build_registered_tabs

def main():
    root = tk.Tk()
    root.title("Rekordbox Phrase Cue Setter")
    # root.geometry("500x300")

    apply_theme(root)

    notebook = ttk.Notebook(root)
    notebook.pack(fill="both", expand=True)

    # Register feature modules here to extend the app with more tabs.
    registry = FeatureRegistry()
    registry.register(MemoryCuesFeature())

    context = FeatureContext(root=root, notebook=notebook)
    build_registered_tabs(context, registry.all())

    root.mainloop()


if __name__ == "__main__":
    main()
