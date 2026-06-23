import tkinter as tk
from tkinter import ttk
from typing import List

from ...data.models import Track
from ..tab_system import FeatureContext, TabFeature
from ..widgets import InfoLabel, TracksList


class CollectionFilteringFeature(TabFeature):
    """Feature tab that provides filtered collection views in subtabs."""

    name = "collection_filtering"

    def __init__(self):
        self._all_tracks: List[Track] = []
        self._minimal_tags_var = tk.StringVar(value="1")

    def build_main_tab(self, context: FeatureContext):
        main_frame = ttk.Frame(context.notebook)
        context.notebook.add(main_frame, text="Collection Filtering")

        self._create_widgets(context, main_frame)
        return main_frame

    def _create_widgets(self, context: FeatureContext, parent: ttk.Frame):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        subtabs = ttk.Notebook(parent)
        subtabs.grid(row=0, column=0, sticky="nsew")

        tags_tab = ttk.Frame(subtabs)
        tags_tab.columnconfigure(0, weight=1)
        tags_tab.rowconfigure(2, weight=1)
        subtabs.add(tags_tab, text="List tracks with n tags")

        less_played_tab = ttk.Frame(subtabs)
        less_played_tab.columnconfigure(0, weight=1)
        less_played_tab.rowconfigure(1, weight=1)
        subtabs.add(less_played_tab, text="Order tracks by less played")

        self._build_tags_filter_subtab(tags_tab)
        self._build_less_played_subtab(less_played_tab)

        context.controller.register_collection_loaded_callbacks(
            self._on_collection_loaded
        )

    def _build_tags_filter_subtab(self, parent: ttk.Frame) -> None:
        InfoLabel(
            parent,
            text="Show tracks having at least N tags.",
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 6))

        controls = ttk.Frame(parent)
        controls.grid(row=1, column=0, sticky="w", padx=10, pady=(0, 8))

        ttk.Label(controls, text="Minimal number of tags:").pack(
            side=tk.LEFT, padx=(0, 8)
        )
        ttk.Entry(
            controls,
            textvariable=self._minimal_tags_var,
            width=6,
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            controls,
            text="Apply",
            command=self._refresh_tags_subtab,
            style="Accent.TButton",
        ).pack(side=tk.LEFT)

        self._tags_tracks_list = TracksList(
            parent,
            columns=[
                ("name", 260),
                ("artist", 200),
                ("album", 160),
                ("genre", 140),
                ("tags_count", 90),
            ],
        )
        self._tags_tracks_list.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))

    def _build_less_played_subtab(self, parent: ttk.Frame) -> None:
        InfoLabel(
            parent,
            text="Tracks ordered by play count (ascending).",
        ).grid(row=0, column=0, sticky="w", padx=10, pady=(10, 6))

        self._less_played_tracks_list = TracksList(
            parent,
            columns=[
                ("name", 260),
                ("artist", 200),
                ("album", 120),
                ("genre", 100),
                ("play_count", 20),
            ],
        )
        self._less_played_tracks_list.grid(
            row=1, column=0, sticky="nsew", padx=10, pady=(0, 10)
        )

    def _on_collection_loaded(self, tracks: List[Track]) -> None:
        self._all_tracks = list(tracks)
        self._prepare_track_metrics(self._all_tracks)
        self._refresh_tags_subtab()
        self._refresh_less_played_subtab()

    def _refresh_tags_subtab(self) -> None:
        minimal_tags = self._get_minimal_tags_value()
        filtered = [
            track
            for track in self._all_tracks
            if len(getattr(track, "tags", [])) >= minimal_tags
        ]
        self._tags_tracks_list.set_tracks(filtered)

    def _refresh_less_played_subtab(self) -> None:
        ordered = sorted(
            self._all_tracks,
            key=lambda track: (getattr(track, "play_count", 0), (track.name or "").lower()),
        )
        self._less_played_tracks_list.set_tracks(ordered)

    def _get_minimal_tags_value(self) -> int:
        value = self._minimal_tags_var.get().strip()
        try:
            return max(0, int(value))
        except ValueError:
            self._minimal_tags_var.set("0")
            return 0

    @staticmethod
    def _prepare_track_metrics(tracks: List[Track]) -> None:
        for track in tracks:
            setattr(track, "tags_count", CollectionFilteringFeature._derive_tags_count(track))
            setattr(track, "play_count", CollectionFilteringFeature._derive_play_count(track))

    @staticmethod
    def _derive_tags_count(track: Track) -> int:
        tags = getattr(track, "tags", [])
        if tags is None:
            return 0
        if isinstance(tags, list):
            return len(tags)
        if isinstance(tags, str):
            values = [part.strip() for part in tags.replace(";", ",").split(",") if part.strip()]
            return len(values)
        return 0

    @staticmethod
    def _derive_play_count(track: Track) -> int:
        for attr in ("play_count", "played_count", "plays", "played", "PlayCount"):
            value = getattr(track, attr, None)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
        return 0