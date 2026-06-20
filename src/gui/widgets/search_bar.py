import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional


class SearchBar(ttk.Frame):
    """Reusable search bar widget with icon and entry."""

    def __init__(
        self,
        parent,
        on_search: Optional[Callable[[str], None]] = None,
        placeholder: str = "Search...",
        width: int = 30,
    ):
        """
        Initialize search bar.

        Args:
            parent: Parent widget
            on_search: Callback function called when search text changes
            placeholder: Placeholder text (not implemented yet)
            width: Width of the entry widget
        """
        super().__init__(parent)
        self.on_search = on_search

        # Search icon
        ttk.Label(self, text="🔍").pack(side=tk.LEFT, padx=(0, 5))

        # Search entry
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", self._on_text_changed)
        self.entry = ttk.Entry(self, textvariable=self.search_var, width=width)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _on_text_changed(self, *args):
        """Handle text change."""
        if self.on_search:
            self.on_search(self.search_var.get())

    def get_text(self) -> str:
        """Get current search text."""
        return self.search_var.get()

    def clear(self):
        """Clear search text."""
        self.search_var.set("")
