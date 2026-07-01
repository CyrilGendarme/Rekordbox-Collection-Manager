import re
import tkinter as tk
from tkinter import Frame, ttk
from typing import Any, Callable, Dict, List, Optional, Tuple

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


def _sort_key_value(value):
    """Return a stable sort key that preserves numeric ordering when possible."""
    if value is None:
        return (2, "")

    if isinstance(value, (int, float)):
        return (0, float(value))

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return (2, "")
        try:
            return (0, float(stripped))
        except ValueError:
            return (1, stripped.lower())

    return (1, str(value).lower())


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
        on_cell_edited: Optional[Callable[[Track, str, Any], None]] = None,
        multiselect: bool = False,
        editable_columns: Optional[set[str]] = None,
        **kwargs,
    ):
        super().__init__(parent, **kwargs)

        self._column_defs: List[Tuple[str, int]] = self._parse_columns(columns)
        self._filter: Dict[str, str] = dict(filter) if filter else {}
        self.on_select = on_select
        self.on_filter_changed = on_filter_changed
        self.on_cell_edited = on_cell_edited
        self._multiselect = multiselect
        self._editable_columns = set(editable_columns or set())

        self._all_tracks: List[Track] = []
        self._filtered_tracks: List[Track] = []
        self._item_to_track: Dict[str, Track] = {}
        self._track_to_item: Dict[str, str] = {}
        self.selected_track: Optional[Track] = None
        self.selected_tracks: List[Track] = []
        self._active_editor: ttk.Entry | None = None
        self._active_edit_item: str | None = None
        self._active_edit_attr: str | None = None

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
        self._scroll = Frame(self)
        self._scroll.grid(row=1, column=0, sticky="nsew")

        self._tree = SortableTreeview(
            self._scroll,
            columns=self._column_defs,
            show="headings",
            height=20,
            on_sort=self._on_sort,
            selectmode="extended" if self._multiselect else "browse",
        )
        self._tree.pack(fill=tk.BOTH, expand=True)
        self._tree.bind("<<TreeviewSelect>>", self._on_row_selected)
        self._tree.bind("<Double-1>", self._on_cell_double_click)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_tracks(self, tracks: List[Track]) -> None:
        """Replace the full track list and refresh the view."""
        self._all_tracks = tracks
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

    def get_selected_tracks(self) -> List[Track]:
        """Return the currently selected tracks in display order."""
        return list(self.selected_tracks)

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
        self._track_to_item.clear()
        # The tree rows are rebuilt from scratch, so any previous selection may
        # point to stale/non-visible items.
        self.selected_track = None
        self.selected_tracks = []

        sort_col = self._tree.sort_column
        if sort_col:
            attr = sort_col  # column name == Track attribute name
            reverse = self._tree.sort_reverse

            def _key(t: Track):
                return _sort_key_value(getattr(t, attr, None))

            tracks = sorted(tracks, key=_key, reverse=reverse)

        rows = [(track, self._row_values(track)) for track in tracks]

        for track, values in rows:
            item_id = self._tree.insert(values=values)
            self._item_to_track[item_id] = track
            self._track_to_item[str(track.id)] = item_id

        if self.on_select:
            self.on_select(None)

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_global_search(self, _text: str) -> None:
        self._apply_filter_and_search()

    def _on_sort(self, _column: str) -> None:
        self._render(self._filtered_tracks)

    def _on_row_selected(self, _event=None) -> None:
        sel = self._tree.get_selection()
        self.selected_tracks = [
            self._item_to_track[item_id]
            for item_id in sel
            if item_id in self._item_to_track
        ]
        self.selected_track = self.selected_tracks[0] if self.selected_tracks else None
        if self.on_select:
            self.on_select(self.selected_track)

    def _on_cell_double_click(self, event) -> None:
        if not self._editable_columns:
            return

        region = self._tree.identify_region(event.x, event.y)
        if region != "cell":
            return

        item_id = self._tree.identify_row(event.y)
        column_id = self._tree.identify_column(event.x)
        if not item_id or not column_id:
            return

        column_index = int(column_id.replace("#", "")) - 1
        if column_index < 0 or column_index >= len(self._column_defs):
            return

        attr, _width = self._column_defs[column_index]
        if attr not in self._editable_columns:
            return

        bbox = self._tree.bbox(item_id, column_id)
        if not bbox:
            return

        self._destroy_editor(commit=False)
        x, y, width, height = bbox
        current_track = self._item_to_track.get(item_id)
        if current_track is None:
            return

        current_value = _attr_as_str(getattr(current_track, attr, None))
        editor = ttk.Entry(self._tree)
        editor.insert(0, current_value)
        editor.select_range(0, tk.END)
        editor.place(x=x, y=y, width=width, height=height)
        editor.focus_set()
        editor.bind("<Return>", lambda _e: self._commit_editor())
        editor.bind("<Escape>", lambda _e: self._destroy_editor(commit=False))
        editor.bind("<FocusOut>", lambda _e: self._commit_editor())

        self._active_editor = editor
        self._active_edit_item = item_id
        self._active_edit_attr = attr

    def _commit_editor(self) -> None:
        if (
            self._active_editor is None
            or self._active_edit_item is None
            or self._active_edit_attr is None
        ):
            return

        item_id = self._active_edit_item
        attr = self._active_edit_attr
        track = self._item_to_track.get(item_id)
        if track is None:
            self._destroy_editor(commit=False)
            return

        raw_value = self._active_editor.get()
        coerced_value = self._coerce_attr_value(track, attr, raw_value)
        setattr(track, attr, coerced_value)
        if self.on_cell_edited:
            self.on_cell_edited(track, attr, coerced_value)

        self._tree.update_item(item_id, values=self._row_values(track))
        self._destroy_editor(commit=False)
        self._tree.focus_set()

    def _destroy_editor(self, commit: bool) -> None:
        if commit:
            self._commit_editor()
            return
        if self._active_editor is not None:
            self._active_editor.destroy()
        self._active_editor = None
        self._active_edit_item = None
        self._active_edit_attr = None

    @staticmethod
    def _coerce_attr_value(track: Track, attr: str, raw_value: str) -> Any:
        text = raw_value.strip()
        current_value = getattr(track, attr, None)

        if attr == "year":
            return int(text) if text else None
        if attr == "bpm":
            return float(text) if text else None
        if isinstance(current_value, list):
            return [part.strip() for part in text.split(",") if part.strip()]
        return text
