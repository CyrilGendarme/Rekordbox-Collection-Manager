import tkinter as tk
from tkinter import ttk
from typing import List, Optional, Callable

from ..widgets import SortableTreeview, InfoLabel
from ...data.models import Track
from ..tab_system import FeatureContext, TabFeature

from src.core.tracks_info_completer.helpers import standardize_name


class TracksInfoCompleterTab:
    """Tracks info completer tab for browsing, editing, and standardizing metadata."""

    _EDITABLE_COLS = {"Track", "Track Name", "Artist", "Album"}

    def __init__(self, parent_frame: ttk.Frame):
        self.parent = parent_frame
        self.all_tracks: List[Track] = []
        self.filtered_tracks: List[Track] = []
        self.selected_track: Optional[Track] = None
        self._item_to_track: dict = {}
        self._edited_values: dict = {}
        self._original_names: dict = {}
        self._edit_entry = None

        self.on_validate: Optional[Callable] = None

        self._create_widgets()

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _create_widgets(self):
        container = ttk.Frame(self.parent)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        InfoLabel(
            container,
            text="Browse your library. Double-click to edit Track Name, Artist or Album.",
        ).pack(anchor="w", pady=(0, 10))

        # Search
        search_frame = ttk.Frame(container)
        search_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0, 5))

        self.search_var = tk.StringVar()
        self.search_var.trace("w", self._on_search_changed)

        ttk.Entry(search_frame, textvariable=self.search_var).pack(
            side=tk.LEFT, fill=tk.X, expand=True
        )

        ttk.Button(search_frame, text="Clear", command=self._clear_search).pack(
            side=tk.LEFT, padx=(5, 0)
        )

        # Table
        columns = [
            ("Track", 260),
            ("Track Name", 260),
            ("Artist", 200),
            ("Album", 160),
        ]

        self.tracks_tree = SortableTreeview(
            container,
            columns=columns,
            show="headings",
            height=20,
            on_sort=self._on_sort,
        )
        self.tracks_tree.pack(fill=tk.BOTH, expand=True)

        self.tracks_tree.bind("<<TreeviewSelect>>", self._on_row_selected)
        self.tracks_tree.bind("<Double-1>", self._start_cell_edit)

        # Status
        self.status_label = ttk.Label(
            container, text="No tracks loaded", foreground="gray"
        )
        self.status_label.pack(anchor="w", pady=(5, 0))

        # Buttons
        btn_frame = ttk.Frame(container)
        btn_frame.pack(anchor="w", pady=(10, 0))

        ttk.Button(btn_frame, text="Standardize", command=self._on_standardize).pack(
            side=tk.LEFT, padx=(0, 8)
        )

        ttk.Button(
            btn_frame,
            text="Validate",
            command=self._on_validate,
            style="Accent.TButton",
        ).pack(side=tk.LEFT)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_tracks(self, tracks: List[Track]):
        self.all_tracks = tracks
        self.filtered_tracks = tracks[:]
        self._refresh_display()

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def _refresh_display(self):
        self.tracks_tree.clear()
        self._item_to_track.clear()
        self._edited_values.clear()
        self._original_names.clear()

        tracks = self.filtered_tracks[:]

        if self.tracks_tree.sort_column:
            col_attr_map = {"Track": "name", "Artist": "artist", "Album": "album"}
            attr = col_attr_map.get(self.tracks_tree.sort_column, "name")
            reverse = self.tracks_tree.sort_reverse

            def sort_key(t):
                val = getattr(t, attr, None)
                return (1, "") if val is None else (0, str(val).lower())

            tracks.sort(key=sort_key, reverse=reverse)

        for track in tracks:
            name = track.name or ""
            artist = track.artist or ""
            album = track.album or ""

            item_id = self.tracks_tree.insert(values=(name, name, artist, album))

            self._item_to_track[item_id] = track
            self._original_names[item_id] = name
            self._edited_values[item_id] = {
                "Track Name": name,
                "Artist": artist,
                "Album": album,
            }

        if self.search_var.get():
            self.status_label.config(
                text=f"Showing {len(self.filtered_tracks):,} of {len(self.all_tracks):,} tracks",
                foreground="blue",
            )
        else:
            self.status_label.config(
                text=f"{len(self.all_tracks):,} tracks loaded",
                foreground="black",
            )

    # ------------------------------------------------------------------
    # Editing
    # ------------------------------------------------------------------

    def _start_cell_edit(self, event):
        tree = self.tracks_tree.tree
        item_id = tree.identify_row(event.y)
        col_id = tree.identify_column(event.x)

        if not item_id or not col_id:
            return

        col_index = int(col_id[1:]) - 1
        col_names = list(self.tracks_tree.columns.keys())

        if col_index >= len(col_names):
            return

        col_name = col_names[col_index]
        if col_name not in self._EDITABLE_COLS:
            return

        bbox = tree.bbox(item_id, col_id)
        if not bbox:
            return

        x, y, w, h = bbox
        current = self._edited_values[item_id][col_name]

        var = tk.StringVar(value=current)
        entry = ttk.Entry(tree, textvariable=var)
        entry.place(x=x, y=y, width=w, height=h)
        entry.focus()

        def save(e=None):
            self._save_cell(item_id, col_name, col_index, var.get())
            entry.destroy()

        def cancel(e=None):
            entry.destroy()

        entry.bind("<Return>", save)
        entry.bind("<FocusOut>", save)
        entry.bind("<Escape>", cancel)

    def _save_cell(self, item_id, col_name, col_index, value):
        self._edited_values[item_id][col_name] = value

        vals = list(self.tracks_tree.tree.item(item_id, "values"))
        vals[col_index] = value
        self.tracks_tree.tree.item(item_id, values=vals)

    # ------------------------------------------------------------------
    # Selection
    # ------------------------------------------------------------------

    def _on_row_selected(self, event=None):
        sel = self.tracks_tree.tree.selection()
        self.selected_track = self._item_to_track.get(sel[0]) if sel else None

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_standardize(self):
        """Apply standardization to every track in the current view."""
        tree = self.tracks_tree.tree
        for item_id, track in self._item_to_track.items():
            original = self._original_names.get(item_id) or track.name or ""
            new_name, new_artist, new_album = standardize_name(original)

            # Mutate the Track object
            track.name = new_name
            track.artist = new_artist
            track.album = new_album

            # Keep edited_values in sync for Validate
            self._edited_values.setdefault(item_id, {}).update(
                {
                    "Track Name": new_name,
                    "Artist": new_artist,
                    "Album": new_album,
                }
            )

            # Update the row; col 0 stays as the frozen original
            vals = list(tree.item(item_id, "values"))
            vals[0] = original
            vals[1] = new_name
            vals[2] = new_artist
            vals[3] = new_album
            tree.item(item_id, values=vals)

    def _on_validate(self):
        """Push edited values for every row in the current view to Rekordbox."""
        if not self._item_to_track:
            return

        updates = [
            (
                track.id,
                self._edited_values.get(item_id, {}).get("Track Name"),
                self._edited_values.get(item_id, {}).get("Artist"),
                self._edited_values.get(item_id, {}).get("Album"),
            )
            for item_id, track in self._item_to_track.items()
        ]

        if self.on_validate:
            self.on_validate(updates)

    # ------------------------------------------------------------------
    # Search & sort
    # ------------------------------------------------------------------

    def _on_search_changed(self, *args):
        q = self.search_var.get().lower()

        self.filtered_tracks = (
            self.all_tracks
            if not q
            else [
                t
                for t in self.all_tracks
                if q in (t.name or "").lower()
                or q in (t.artist or "").lower()
                or q in (t.album or "").lower()
            ]
        )

        self._refresh_display()

    def _clear_search(self):
        self.search_var.set("")

    def _on_sort(self, column: str):
        self._refresh_display()


class TracksInfoCompleterFeature(TabFeature):
    """Adapter that plugs TracksInfoCompleterTab into the generic tab-feature lifecycle."""

    name = "tracks_info_completer"

    def __init__(self):
        self.main_tab: Optional[TracksInfoCompleterTab] = None
        self.main_frame: Optional[ttk.Frame] = None
        self.config_frame: Optional[ttk.Frame] = None

    def build_main_tab(self, context: FeatureContext):
        self.main_frame = ttk.Frame(context.notebook)
        context.notebook.add(self.main_frame, text="Tracks Info Completer")
        self.main_tab = TracksInfoCompleterTab(self.main_frame)
        return self.main_frame

    def build_config_tab(self, context: FeatureContext):
        self.config_frame = ttk.Frame(context.notebook)
        context.notebook.add(self.config_frame, text="Tracks Info Completer Config")
        self._create_widgets(self.config_frame)
        return self.config_frame

    def _create_widgets(self, parent: ttk.Frame):
        ttk.Label(
            parent,
            text="Tracks configuration settings coming soon...",
        ).pack(padx=20, pady=20)

    def _refresh_display(self):
        if self.main_tab:
            self.main_tab._refresh_display()
