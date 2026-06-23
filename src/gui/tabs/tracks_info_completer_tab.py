import tkinter as tk
from tkinter import ttk
from typing import List, Optional, Callable

from ..widgets import InfoLabel, TracksList
from ...data.models import Track
from ..tab_system import ConfigSubtabFeature, FeatureContext

from src.core.tracks_info_completer.helpers import standardize_name
from src.core.tracks_info_completer.actions import update_track_rekordbox_metadata

class TracksInfoCompleterFeature(ConfigSubtabFeature):
    """Tracks info completer feature."""

    name = "tracks_info_completer"
    config_tab_title = "Tracks Info Completer"

    _EDITABLE_COLS = {"Track", "Track Name", "Artist", "Album"}

    def __init__(self):
        self.filtered_tracks: List[Track] = []
        self.selected_track: Optional[Track] = None

        self._edited_values: dict = {}
        self._original_names: dict = {}

    # ------------------------------------------------------------------
    # TabFeature API
    # ------------------------------------------------------------------

    def build_main_tab(self, context: FeatureContext):
        main_frame = ttk.Frame(context.notebook)
        context.notebook.add(main_frame, text="Tracks Info Completer")

        self._create_widgets(context,   main_frame)

        return main_frame

    def _create_config_widgets(self, context: FeatureContext, parent: ttk.Frame) -> None:
        ttk.Label(
            parent,
            text="Tracks configuration settings coming soon...",
        ).pack(padx=20, pady=20)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _create_widgets(self, context: FeatureContext, parent: ttk.Frame):
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        InfoLabel(
            container,
            text="Browse your library. Double-click a row to edit Track Name, Artist or Album.",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        # ── TracksList ───────────────────────────────────────────────────
        self.tracks_list = TracksList(
            container,
            columns=[
                ("name", 260),
                ("artist", 200),
                ("album", 160),
                ("genre", 140),
                ("bpm", 70),
            ],
            on_select=self._on_track_selected,
            on_filter_changed=self.on_filter_changed,
        )
        self.tracks_list.grid(row=1, column=0, sticky="nsew")

        context.controller.register_collection_loaded_callbacks(
            self.tracks_list.set_tracks
        )

        # ── Buttons ──────────────────────────────────────────────────────
        btn_frame = ttk.Frame(container)
        btn_frame.grid(row=2, column=0, sticky="w", pady=(8, 0))

        ttk.Button(
            btn_frame,
            text="Standardize",
            command=self._on_standardize,
        ).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(
            btn_frame,
            text="Validate",
            command=self._on_validate,
            style="Accent.TButton",
        ).pack(side=tk.LEFT)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_filter_changed(self, tracks: List[Track]) -> None:
        self.filtered_tracks = list(tracks)
        # Snapshot original names for Standardize
        self._original_names = {str(t.id): t.name or "" for t in tracks}
        self._edited_values = {
            str(t.id): {"name": t.name or "", "artist": t.artist or "", "album": t.album or ""}
            for t in tracks
        }

    def _on_track_selected(self, track: Optional[Track]) -> None:
        self.selected_track = track

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_standardize(self) -> None:
        """Apply standardize_name to every track and refresh the list."""
        for track in self.filtered_tracks:
            original = self._original_names.get(str(track.id)) or track.name or ""
            new_name, new_artist, new_album = standardize_name(original)
            track.name = new_name
            track.artist = new_artist
            track.album = new_album
            self._edited_values.setdefault(str(track.id), {}).update(
                {"name": new_name, "artist": new_artist, "album": new_album}
            )

    def _on_validate(self) -> None:
        """Emit the on_validate callback with (track_id, name, artist, album) tuples."""
        if not self.filtered_tracks:
            return

        update_track_rekordbox_metadata(self.filtered_tracks)

        updates = [
            (
                track.id,
                self._edited_values.get(str(track.id), {}).get("name"),
                self._edited_values.get(str(track.id), {}).get("artist"),
                self._edited_values.get(str(track.id), {}).get("album"),
            )
            for track in self.filtered_tracks
        ]
        self.on_validate(updates)
