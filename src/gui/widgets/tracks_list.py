import re
import tkinter as tk
from tkinter import ttk
from typing import Callable, Dict, List, Optional, Tuple

from src.data.models import Track
from .scrollable_frame import ScrollableFrame
from .search_bar import SearchBar
from .sortable_treeview import SortableTreeview


# Default column width when not specified.
_DEFAULT_WIDTH = 200

# Track attributes that are rendered as strings for display.
_LIST_ATTRS = {"tags", "position_marks"}


def _attr_as_str(value) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    return str(value)


class TracksList(ttk.Frame):
    """Generic UI component that displays a list of Track objects.

    Parameters
    ----------
    parent
        Parent widget.
    columns
        Ordered list of Track attribute names to display, each optionally
        paired with a pixel width: ``[("name", 260), "artist", ("album", 160)]``.
        Plain strings get ``_DEFAULT_WIDTH``.
    filter
        Initial filter mapping ``{attribute_name: regex_pattern}``.
        Every track is tested against all patterns simultaneously (AND).
    on_select
        Optional callback called with the selected ``Track`` when a row
        is clicked.
    """

    def __init__(
        self,
        parent,
        columns: List[str | Tuple[str, int]],
        filter: Optional[Dict[str, str]] = None,
        on_select: Optional[Callable[[Optional[Track]], None]] = None,
        on_filter_changed: Optional[Callable[[List[Track]], None]] = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)

        self._column_defs: List[Tuple[str, int]] = self._parse_columns(columns)
        self._filter: Dict[str, str] = dict(filter) if filter else {}
        self.on_select = on_select
        self.on_filter_changed = on_filter_changed

        self._all_tracks: List[Track] = []
        self._filtered_tracks: List[Track] = []
        self._item_to_track: Dict[str, Track] = {}
        self.selected_track: Optional[Track] = None

        self._create_widgets()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_columns(columns) -> List[Tuple[str, int]]:
        result = []
        for col in columns:
            if isinstance(col, tuple):
                result.append((col[0], col[1]))
            else:
                result.append((col, _DEFAULT_WIDTH))
        return result

    def _matches_filter(self, track: Track) -> bool:
        for attr, pattern in self._filter.items():
            if not pattern:
                continue
            value = _attr_as_str(getattr(track, attr, None))
            try:
                if not re.search(pattern, value, re.IGNORECASE):
                    return False
            except re.error:
                # Treat malformed regex as a plain substring match.
                if pattern.lower() not in value.lower():
                    return False
        return True

    def _row_values(self, track: Track) -> Tuple:
        return tuple(
            _attr_as_str(getattr(track, attr, None))
            for attr, _ in self._column_defs
        )

    # ------------------------------------------------------------------
    # Widget construction
    # ------------------------------------------------------------------

    def _create_widgets(self):
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # ── Search bar ───────────────────────────────────────────────────
        search_frame = ttk.Frame(self)
        search_frame.grid(row=0, column=0, sticky="ew", padx=6, pady=(6, 2))

        self._search_bar = SearchBar(
            search_frame,
            on_search=self._on_global_search,
            placeholder="Search all columns…",
        )
        self._search_bar.pack(side=tk.LEFT, fill=tk.X, expand=True)

        # ── Scrollable frame hosting the treeview ───────────────────────
        self._scroll = ScrollableFrame(self)
        self._scroll.grid(row=1, column=0, sticky="nsew")

        self._tree = SortableTreeview(
            self._scroll.get_frame(),
            columns=self._column_defs,
            show="headings",
            height=20,
            on_sort=self._on_sort,
        )
        self._tree.pack(fill=tk.BOTH, expand=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_row_selected)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_tracks(self, tracks: List[Track]) -> None:
        """Replace the full track list and refresh the view."""
        self._all_tracks = list(tracks)
        self._apply_filter_and_search()

    def get_tracks(self) -> List[Track]:
        """Return the full (unfiltered) track list."""
        return list(self._all_tracks)

    def set_filter(self, filter: Dict[str, str]) -> None:
        """Replace the attribute filter dict and refresh.

        Each value is treated as a regex pattern; empty string = no filter.
        """
        self._filter = dict(filter)
        self._apply_filter_and_search()

    def update_filter(self, **kwargs: str) -> None:
        """Update individual filter attributes without replacing the whole dict."""
        self._filter.update(kwargs)
        self._apply_filter_and_search()

    def clear_filter(self) -> None:
        """Remove all attribute filters and refresh."""
        self._filter.clear()
        self._apply_filter_and_search()

    # ------------------------------------------------------------------
    # Internal display logic
    # ------------------------------------------------------------------

    def _apply_filter_and_search(self) -> None:
        """Combine attribute filter + search bar text, then render."""
        search_text = self._search_bar.get_text().strip().lower()

        result: List[Track] = []
        for track in self._all_tracks:
            if not self._matches_filter(track):
                continue
            if search_text and not self._matches_search(track, search_text):
                continue
            result.append(track)

        self._filtered_tracks = result
        self._render(result)
        if self.on_filter_changed:
            self.on_filter_changed(list(result))

    def _matches_search(self, track: Track, query: str) -> bool:
        """Return True if ``query`` appears in any displayed column value."""
        for attr, _ in self._column_defs:
            if query in _attr_as_str(getattr(track, attr, None)).lower():
                return True
        return False

    def _render(self, tracks: List[Track]) -> None:
        self._tree.clear()
        self._item_to_track.clear()

        sort_col = self._tree.sort_column
        if sort_col:
            attr = sort_col  # column name == Track attribute name
            reverse = self._tree.sort_reverse

            def _key(t: Track):
                v = _attr_as_str(getattr(t, attr, None))
                return v.lower()

            tracks = sorted(tracks, key=_key, reverse=reverse)

        for track in tracks:
            item_id = self._tree.insert(values=self._row_values(track))
            self._item_to_track[item_id] = track

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_global_search(self, _text: str) -> None:
        self._apply_filter_and_search()

    def _on_sort(self, _column: str) -> None:
        self._render(self._filtered_tracks)

    def _on_row_selected(self, _event=None) -> None:
        sel = self._tree.get_selection()
        self.selected_track = self._item_to_track.get(sel[0]) if sel else None
        if self.on_select:
            self.on_select(self.selected_track)
