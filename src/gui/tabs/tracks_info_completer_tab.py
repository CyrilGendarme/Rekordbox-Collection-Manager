import tkinter as tk
from tkinter import ttk
from typing import List, Optional, Callable

from ..widgets import InfoLabel, TracksList
from ...data.models import Track
from ..tab_system import ConfigSubtabFeature, FeatureContext

from src.core.tracks_info_completer.helpers import standardize_name
from src.core.tracks_info_completer.actions import update_track_rekordbox_metadata
from src.services import complete_track_metadata

class TracksInfoCompleterFeature(ConfigSubtabFeature):
    """Tracks info completer feature."""

    name = "tracks_info_completer"
    config_tab_title = "Tracks Info Completer"

    _EDITABLE_COLS = {"name", "artist", "album", "year", "label", "genre", "bpm"}

    def __init__(self):
        self.filtered_tracks: List[Track] = []
        self.selected_track: Optional[Track] = None
        self.selected_tracks: List[Track] = []
        self.controller = None
        self.status_var = tk.StringVar(
            value="Select one or more tracks, then complete metadata or validate changes."
        )

        self._edited_values: dict = {}
        self._original_names: dict = {}

    # ------------------------------------------------------------------
    # TabFeature API
    # ------------------------------------------------------------------

    def build_main_tab(self, context: FeatureContext):
        self.controller = context.controller
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
            text="Browse your library, multi-select tracks, then enrich Album/Year/Label before validating.",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        # ── TracksList ───────────────────────────────────────────────────
        self.tracks_list = TracksList(
            container,
            columns=[
                ("name", 260),
                ("artist", 200),
                ("album", 160),
                ("year", 80),
                ("label", 180),
                ("genre", 140),
                ("bpm", 70),
            ],
            on_select=self._on_track_selected,
            on_filter_changed=self.on_filter_changed,
            on_cell_edited=self._on_cell_edited,
            multiselect=True,
            editable_columns=self._EDITABLE_COLS,
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
            text="Complete Tracks Info",
            command=self._on_complete_tracks_info,
        ).pack(side=tk.LEFT, padx=(0, 8))

        ttk.Button(
            btn_frame,
            text="Validate",
            command=self._on_validate,
            style="Accent.TButton",
        ).pack(side=tk.LEFT)

        ttk.Label(container, textvariable=self.status_var).grid(
            row=3,
            column=0,
            sticky="w",
            pady=(8, 0),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def on_filter_changed(self, tracks: List[Track]) -> None:
        self.filtered_tracks = list(tracks)
        # Snapshot original names for Standardize
        self._original_names = {str(t.id): t.name or "" for t in tracks}
        self._edited_values = {
            str(t.id): {
                "name": t.name or "",
                "artist": t.artist or "",
                "album": t.album or "",
                "year": t.year,
                "label": t.label or "",
                "genre": t.genre or "",
                "bpm": t.bpm,
            }
            for t in tracks
        }

    def _on_track_selected(self, track: Optional[Track]) -> None:
        self.selected_track = track
        self.selected_tracks = self.tracks_list.get_selected_tracks()

    def _get_target_tracks(self) -> List[Track]:
        selected_tracks = self.tracks_list.get_selected_tracks()
        return selected_tracks or list(self.filtered_tracks)

    def _on_cell_edited(self, track: Track, attr: str, value) -> None:
        self._edited_values.setdefault(str(track.id), {}).update({attr: value})
        self.status_var.set(f"Edited {attr} for {track.display_name}.")

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def _on_standardize(self) -> None:
        """Apply standardize_name to every track and refresh the list."""
        target_tracks = self._get_target_tracks()
        if not target_tracks:
            self.status_var.set("No tracks available to standardize.")
            return

        for track in target_tracks:
            original = self._original_names.get(str(track.id)) or track.name or ""
            new_name, new_artist, new_album = standardize_name(original)
            track.name = new_name
            track.artist = new_artist
            track.album = new_album
            self._edited_values.setdefault(str(track.id), {}).update(
                {"name": new_name, "artist": new_artist, "album": new_album}
            )
        self.tracks_list.set_tracks(self.tracks_list.get_tracks())
        self.status_var.set(f"Standardized {len(target_tracks)} track(s).")

    def _on_complete_tracks_info(self) -> None:
        target_tracks = self._get_target_tracks()
        if not target_tracks:
            self.status_var.set("No tracks available to complete.")
            return

        changed_tracks = 0
        for track in target_tracks:
            completion = complete_track_metadata(
                title=track.name or "",
                artist=track.artist or "",
                album=track.album or "",
            )

            track_changed = False
            edited = self._edited_values.setdefault(str(track.id), {})

            if completion.album and completion.album != track.album:
                track.album = completion.album
                edited["album"] = completion.album
                track_changed = True

            if completion.year is not None and completion.year != track.year:
                track.year = completion.year
                edited["year"] = completion.year
                track_changed = True

            if completion.label and completion.label != track.label:
                track.label = completion.label
                edited["label"] = completion.label
                track_changed = True

            if track_changed:
                changed_tracks += 1

        self.tracks_list.set_tracks(self.tracks_list.get_tracks())
        self.status_var.set(f"Completed metadata for {changed_tracks} track(s).")

    def _on_validate(self) -> None:
        """Emit the on_validate callback with (track_id, name, artist, album) tuples."""
        target_tracks = self._get_target_tracks()
        if not target_tracks:
            self.status_var.set("No tracks available to validate.")
            return

        updates = [
            (
                track.id,
                self._edited_values.get(str(track.id), {}).get("name"),
                self._edited_values.get(str(track.id), {}).get("artist"),
                self._edited_values.get(str(track.id), {}).get("album"),
                self._edited_values.get(str(track.id), {}).get("year"),
                self._edited_values.get(str(track.id), {}).get("label"),
                self._edited_values.get(str(track.id), {}).get("genre"),
                self._edited_values.get(str(track.id), {}).get("bpm"),
            )
            for track in target_tracks
        ]
        update_track_rekordbox_metadata(
            target_tracks,
            updates,
            set_status_callback=self.status_var.set,
        )
        if self.controller is not None:
            self.controller.refresh_collection()
