import tkinter as tk
from tkinter import ttk
from ..theme import BG


class ScrollableFrame(ttk.Frame):
    """A scrollable frame container."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)

        self.canvas = tk.Canvas(self, bg=BG, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self._inner = ttk.Frame(self.canvas)
        self._inner_id = self.canvas.create_window((0, 0), window=self._inner, anchor="nw")

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self._inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        # Only scroll when mouse is over THIS canvas — no bind_all
        self.canvas.bind("<Enter>", self._bind_mousewheel)
        self.canvas.bind("<Leave>", self._unbind_mousewheel)
        self._inner.bind("<Enter>", self._bind_mousewheel)
        self._inner.bind("<Leave>", self._unbind_mousewheel)

    def _bind_mousewheel(self, _=None):
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)

    def _unbind_mousewheel(self, _=None):
        self.canvas.unbind_all("<MouseWheel>")

    def _on_inner_configure(self, _):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, e):
        self.canvas.itemconfig(self._inner_id, width=e.width)

    def _on_mousewheel(self, e):
        self.canvas.yview_scroll(int(-1 * (e.delta / 120)), "units")

    def get_frame(self) -> ttk.Frame:
        return self._inner
