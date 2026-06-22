import tkinter as tk
from tkinter import ttk
from typing import List, Tuple, Callable, Optional, Any, Dict


class SortableTreeview(ttk.Frame):
    """Reusable treeview with sorting and scrollbar."""

    def __init__(
        self,
        parent,
        columns: List[Tuple[str, int]],
        show: str = "headings",
        height: int = 15,
        on_sort: Optional[Callable[[str], None]] = None,
    ):
        """
        Initialize sortable treeview.

        Args:
            parent: Parent widget
            columns: List of (column_name, width) tuples
            show: What to show ('headings', 'tree', 'tree headings')
            height: Number of visible rows
            on_sort: Callback when column is clicked for sorting
        """
        super().__init__(parent)
        self.columns = {col[0]: col[1] for col in columns}
        self.on_sort = on_sort
        self.sort_column = None
        self.sort_reverse = False
        self._sort_functions: Dict[str, Callable] = {}

        # Create treeview
        self.tree = ttk.Treeview(
            self,
            columns=list(self.columns.keys()),
            show=show,
            height=height,
            selectmode="browse",
        )

        # Configure tree column if showing tree
        if "tree" in show:
            self.tree.heading("#0", text="#")
            self.tree.column("#0", width=40, minwidth=40)

        # Configure columns
        for col_name, col_width in columns:
            self.tree.heading(
                col_name, text=col_name, command=lambda c=col_name: self._on_sort(c)
            )
            self.tree.column(col_name, width=col_width)

        # Scrollbar
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.scrollbar.set)

        # Layout
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    def _on_sort(self, column: str):
        """Handle column header click for sorting."""
        # Update sort state
        if self.sort_column == column:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = column
            self.sort_reverse = False

        # Update headers to show sort direction
        for col_name in self.columns.keys():
            header_text = col_name
            if col_name == column:
                header_text += " ▼" if self.sort_reverse else " ▲"
            self.tree.heading(
                col_name,
                text=header_text,
                command=lambda c=col_name: self._on_sort(c),
            )

        # Call external sort handler if provided
        if self.on_sort:
            self.on_sort(column)

    def set_sort_function(self, column: str, sort_func: Callable):
        """Set custom sort function for a column."""
        self._sort_functions[column] = sort_func

    def get_sort_function(self, column: str) -> Optional[Callable]:
        """Get custom sort function for a column."""
        return self._sort_functions.get(column)

    def clear(self):
        """Clear all items."""
        children = self.tree.get_children()
        if children:
            self.tree.delete(*children)

    def insert(
        self, values: Tuple[Any, ...], tags: Tuple[str, ...] = (), text: str = ""
    ):
        """Insert a row into the treeview."""
        return self.tree.insert("", tk.END, text=text, values=values, tags=tags)

    def get_selection(self) -> List[str]:
        """Get selected item IDs."""
        return self.tree.selection()

    def selection_set(self, items: List[str]):
        """Set selection."""
        self.tree.selection_set(items)

    def selection_remove(self, *items):
        """Remove items from selection."""
        self.tree.selection_remove(*items)

    def get_children(self):
        """Get all child items."""
        return self.tree.get_children()

    def item(self, item_id: str, option: str = None):
        """Get item data."""
        if option:
            return self.tree.item(item_id, option)
        return self.tree.item(item_id)

    def bind(self, sequence: str, func: Callable):
        """Bind event to treeview."""
        self.tree.bind(sequence, func)
