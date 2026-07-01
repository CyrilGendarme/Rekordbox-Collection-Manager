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
        self._original_values: dict = {}
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
        # Snapshot original names for Standardize.
        # Keep already-known originals so validation remains dirty-aware across
        # search/filter refreshes.
        for track in tracks:
            track_id = str(track.id)
            if track_id not in self._original_names:
                self._original_names[track_id] = track.name or ""
            if track_id not in self._original_values:
                self._original_values[track_id] = {
                    "name": track.name or "",
                    "artist": track.artist or "",
                    "album": track.album or "",
                    "year": track.year,
                    "label": track.label or "",
                    "genre": track.genre or "",
                    "bpm": track.bpm,
                }
            self._edited_values.setdefault(track_id, {
                "name": track.name or "",
                "artist": track.artist or "",
                "album": track.album or "",
                "year": track.year,
                "label": track.label or "",
                "genre": track.genre or "",
                "bpm": track.bpm,
            })

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
            if track.album and track.label and track.year and track.year != 0:
                continue  # Skip tracks that already have all metadata.
            
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

        editable_fields = ("name", "artist", "album", "year", "label", "genre", "bpm")
        updates = []
        for track in target_tracks:
            track_id = str(track.id)
            current_values = {
                "name": track.name or "",
                "artist": track.artist or "",
                "album": track.album or "",
                "year": track.year,
                "label": track.label or "",
                "genre": track.genre or "",
                "bpm": track.bpm,
            }

            if any(
                current_values[field]
                != self._original_values.get(track_id, {}).get(field)
                for field in editable_fields
            ):
                updates.append(
                    (
                        track.id,
                        current_values["name"],
                        current_values["artist"],
                        current_values["album"],
                        current_values["year"],
                        current_values["label"],
                        current_values["genre"],
                        current_values["bpm"],
                    )
                )
                self._edited_values[track_id] = dict(current_values)

        if not updates:
            self.status_var.set("No modified tracks to save.")
            return

        update_track_rekordbox_metadata(
            target_tracks,
            updates,
            set_status_callback=self.status_var.set,
        )

        # Mark the submitted rows as clean so a follow-up Validate does not
        # re-send the same values if the view refreshes before the database reloads.
        for track_id, *_rest in updates:
            track_key = str(track_id)
            current_track = next((track for track in target_tracks if str(track.id) == track_key), None)
            if current_track is None:
                continue
            snapshot = {
                "name": current_track.name or "",
                "artist": current_track.artist or "",
                "album": current_track.album or "",
                "year": current_track.year,
                "label": current_track.label or "",
                "genre": current_track.genre or "",
                "bpm": current_track.bpm,
            }
            self._original_values[track_key] = snapshot
            self._edited_values[track_key] = dict(snapshot)
        if self.controller is not None:
            self.controller.refresh_collection()
