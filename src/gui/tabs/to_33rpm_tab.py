from __future__ import annotations

import atexit
import importlib
import json
import logging
import os
import re
import shutil
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional
from uuid import uuid4

import numpy as np
from pydub import AudioSegment

from src.core.samples_magnifier.audio import (
    normalize_audio_peak,
    read_audiosegment,
    truncate_silence,
    write_audiosegment,
)
from src.core.to_33rpm.audio_enhancer.chain import apply_enhancer_chain
from src.core.to_33rpm.io_audio import read_audio, write_audio
from src.core.to_33rpm.processing import ProcessConfig, emulate_45_played_at_33
from src.data import RekordboxDAO, Track
from src.gui.tab_system import ConfigSubtabFeature, FeatureContext
from src.gui.widgets import TracksList
from src.services.audio_metadata_service import copy_mp3_metadata, write_audio_metadata
from src.user_config import persist_setting, settings

OUTPUT_SUFFIX = ".mp3"
PENDING_33RPM_FILE = Path.cwd() / ".to33rpm_pending_cleanup.json"
logger = logging.getLogger(__name__)


@dataclass
class TransformedTrack:
    source_track: Track
    output_path: str
    title: str
    artist: str
    album: str
    year: Optional[int]
    label: str
    genre: str
    tags: list[str]
    status: str = "ready"
    imported_track_id: str = ""


@dataclass
class MagnifiedTrack:
    source_track: Optional[Track]
    source_path: str
    output_path: str
    title: str
    artist: str
    status: str = "ready"


class To33RpmFeature(ConfigSubtabFeature):
    name = "to_33rpm"
    config_tab_title = "To 33RPM"

    def __init__(self):
        self.root: tk.Tk | None = None
        self.controller = None

        configured_output_dir = (settings.TO_33RPM_OUTPUT_DIR or "").strip()
        if not configured_output_dir:
            configured_output_dir = str(Path.cwd() / "to_33rpm_outputs")
        self.output_dir_var = tk.StringVar(value=configured_output_dir)
        self.status_var = tk.StringVar(
            value="Select tracks, transform to 33 RPM, preview, then import to Rekordbox."
        )

        self.tracks_list: TracksList | None = None
        self.preview_tree: ttk.Treeview | None = None
        self.magnifier_tracks_list: TracksList | None = None
        self.magnifier_files_list: tk.Listbox | None = None
        self.magnifier_tree: ttk.Treeview | None = None
        self.magnifier_files: list[Path] = []
        self._magnified_tracks: list[MagnifiedTrack] = []

        self.transform_btn: ttk.Button | None = None
        self.preview_btn: ttk.Button | None = None
        self.stop_preview_btn: ttk.Button | None = None
        self.import_btn: ttk.Button | None = None
        self.magnify_btn: ttk.Button | None = None
        self.magnifier_import_btn: ttk.Button | None = None
        self.magnifier_busy = False
        self.player_seek_scale: ttk.Scale | None = None
        self.player_time_var = tk.StringVar(value="00:00 / 00:00")

        self._is_busy = False
        self._transformed_tracks: list[TransformedTrack] = []
        self._cleanup_lock = threading.Lock()
        self._generated_output_paths: set[str] = set()
        self._imported_output_paths: set[str] = set()
        self._shutdown_hook_registered = False
        self._player_after_id: str | None = None
        self._is_dragging_seek = False
        self._player_duration_seconds = 0.0
        self._player_current_file = ""
        self._sd = None
        self._player_backend_available = False
        self._player_audio: np.ndarray | None = None
        self._player_sample_rate = 0
        self._player_total_frames = 0
        self._player_frame_pos = 0
        self._player_stream = None
        self._player_state_lock = threading.Lock()
        self._init_preview_player_backend()

    def build_main_tab(self, context: FeatureContext) -> Optional[ttk.Frame]:
        self.root = context.root
        self.controller = context.controller

        self._register_shutdown_hook()
        self._cleanup_stale_unimported_outputs()

        main_frame = ttk.Frame(context.notebook)
        context.notebook.add(main_frame, text="To 33RPM")

        main_frame.columnconfigure(0, weight=1)
        main_frame.rowconfigure(0, weight=1)
        subtabs = ttk.Notebook(main_frame)
        subtabs.grid(row=0, column=0, sticky="nsew")
        collection_files_tab = ttk.Frame(subtabs)
        magnifier_tab = ttk.Frame(subtabs)
        subtabs.add(collection_files_tab, text="Collection files")
        subtabs.add(magnifier_tab, text="Magnify ripped 33 rpm")

        self._create_widgets(collection_files_tab)
        self._create_magnifier_widgets(magnifier_tab)
        if self.controller is not None:
            self.controller.register_collection_loaded_callbacks(
                self._on_collection_loaded
            )
            self._on_collection_loaded(self.controller.get_tracks())

        return main_frame

    def _create_config_widgets(self, context: FeatureContext, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)

        wrapper = ttk.LabelFrame(parent, text="To 33RPM Output", padding=10)
        wrapper.grid(row=0, column=0, sticky="ew", padx=10, pady=10)
        wrapper.columnconfigure(1, weight=1)

        ttk.Label(wrapper, text="Output folder:").grid(row=0, column=0, sticky="w")
        ttk.Entry(wrapper, textvariable=self.output_dir_var).grid(
            row=0, column=1, sticky="ew", padx=(8, 8)
        )
        ttk.Button(wrapper, text="Choose Folder", command=self._choose_output_dir).grid(
            row=0, column=2, sticky="e"
        )

        ttk.Button(
            wrapper,
            text="Apply",
            style="Accent.TButton",
            command=self._apply_output_dir_config,
        ).grid(row=1, column=0, columnspan=3, sticky="ew", pady=(8, 0))

    def _create_widgets(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        controls = ttk.LabelFrame(parent, text="Processing", padding=10)
        controls.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))

        ttk.Label(
            controls,
            text="Output folder is configured in Configuration > To 33RPM.",
            style="Dim.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 6))

        self.transform_btn = ttk.Button(
            controls,
            text="Transform Selected to 33 RPM",
            style="Accent.TButton",
            command=self.transform_selected_tracks,
        )
        self.transform_btn.grid(row=1, column=0, sticky="ew")

        ttk.Label(
            parent,
            text=(
                "Step 1: Select tracks from your Rekordbox collection. "
                "Step 2: Transform them. Step 3: Preview transformed tracks. "
                "Step 4: Import selected transformed tracks."
            ),
            style="Dim.TLabel",
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))

        body = ttk.Panedwindow(parent, orient=tk.VERTICAL)
        body.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 6))

        source_frame = ttk.LabelFrame(
            body, text="Rekordbox Collection (multiselect)", padding=8
        )
        source_frame.columnconfigure(0, weight=1)
        source_frame.rowconfigure(0, weight=1)

        self.tracks_list = TracksList(
            source_frame,
            columns=[
                ("name", 300),
                ("artist", 210),
                ("album", 180),
                ("genre", 120),
                ("bpm", 80),
                ("file_path", 360),
            ],
            multiselect=True,
            on_select=self._on_source_track_selected,
        )
        self.tracks_list.grid(row=0, column=0, sticky="nsew")

        transformed_frame = ttk.LabelFrame(
            body,
            text="Transformed Tracks Preview / Import (multiselect)",
            padding=8,
        )
        transformed_frame.columnconfigure(0, weight=1)
        transformed_frame.rowconfigure(0, weight=1)

        self.preview_tree = ttk.Treeview(
            transformed_frame,
            columns=(
                "title",
                "artist",
                "album",
                "genre",
                "path",
                "status",
                "rekordbox_id",
            ),
            show="headings",
            selectmode="extended",
            height=14,
        )
        self.preview_tree.heading("title", text="Transformed Title")
        self.preview_tree.heading("artist", text="Artist")
        self.preview_tree.heading("album", text="Album")
        self.preview_tree.heading("genre", text="Genre")
        self.preview_tree.heading("path", text="Output File")
        self.preview_tree.heading("status", text="Status")
        self.preview_tree.heading("rekordbox_id", text="Imported Track ID")

        self.preview_tree.column("title", width=260, anchor="w")
        self.preview_tree.column("artist", width=180, anchor="w")
        self.preview_tree.column("album", width=160, anchor="w")
        self.preview_tree.column("genre", width=90, anchor="center")
        self.preview_tree.column("path", width=350, anchor="w")
        self.preview_tree.column("status", width=120, anchor="center")
        self.preview_tree.column("rekordbox_id", width=120, anchor="center")
        self.preview_tree.grid(row=0, column=0, sticky="nsew")

        actions = ttk.Frame(transformed_frame)
        actions.grid(row=1, column=0, sticky="ew", pady=(8, 0))

        self.preview_btn = ttk.Button(
            actions,
            text="Play Selected",
            command=self.play_selected_preview,
        )
        self.preview_btn.pack(side=tk.LEFT)

        self.stop_preview_btn = ttk.Button(
            actions,
            text="Stop",
            command=self.stop_preview,
        )
        self.stop_preview_btn.pack(side=tk.LEFT, padx=(8, 0))

        self.player_seek_scale = ttk.Scale(
            transformed_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
        )
        self.player_seek_scale.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        self.player_seek_scale.bind("<ButtonPress-1>", self._on_seek_press)
        self.player_seek_scale.bind("<ButtonRelease-1>", self._on_seek_release)

        ttk.Label(
            transformed_frame,
            textvariable=self.player_time_var,
            style="Dim.TLabel",
            anchor="e",
        ).grid(row=3, column=0, sticky="e", pady=(4, 0))

        self.import_btn = ttk.Button(
            actions,
            text="Import Selected to Rekordbox",
            style="Accent.TButton",
            command=self.import_selected_to_rekordbox,
        )
        self.import_btn.pack(side=tk.RIGHT)

        body.add(source_frame, weight=3)
        body.add(transformed_frame, weight=2)

        ttk.Label(
            parent, textvariable=self.status_var, style="Dim.TLabel", anchor="w"
        ).grid(
            row=3,
            column=0,
            sticky="ew",
            padx=10,
            pady=(0, 10),
        )

    def _create_magnifier_widgets(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        parent.rowconfigure(2, weight=2)

        sources = ttk.Panedwindow(parent, orient=tk.HORIZONTAL)
        sources.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)

        collection_frame = ttk.LabelFrame(
            sources,
            text="Rekordbox collection (genre/category matching 33)",
            padding=8,
        )
        collection_frame.columnconfigure(0, weight=1)
        collection_frame.rowconfigure(0, weight=1)
        self.magnifier_tracks_list = TracksList(
            collection_frame,
            columns=[
                ("name", 230),
                ("artist", 170),
                ("genre", 120),
                ("tags", 180),
                ("file_path", 300),
            ],
            multiselect=True,
            tree_height=8,
        )
        self.magnifier_tracks_list.grid(row=0, column=0, sticky="nsew")
        sources.add(collection_frame, weight=3)

        local_frame = ttk.LabelFrame(sources, text="Local audio files", padding=8)
        local_frame.columnconfigure(0, weight=1)
        local_frame.rowconfigure(1, weight=1)
        file_actions = ttk.Frame(local_frame)
        file_actions.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        ttk.Button(
            file_actions,
            text="Choose Files",
            command=self._choose_magnifier_files,
        ).pack(side=tk.LEFT)
        ttk.Button(
            file_actions,
            text="Remove Selected",
            command=self._remove_magnifier_files,
        ).pack(side=tk.LEFT, padx=(6, 0))
        self.magnifier_files_list = tk.Listbox(
            local_frame,
            selectmode=tk.EXTENDED,
            height=8,
            exportselection=False,
        )
        self.magnifier_files_list.grid(row=1, column=0, sticky="nsew")
        sources.add(local_frame, weight=2)

        select_actions = ttk.Frame(parent)
        select_actions.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 8))
        self.magnify_btn = ttk.Button(
            select_actions,
            text="Magnify Selected",
            style="Accent.TButton",
            command=self.magnify_selected,
        )
        self.magnify_btn.pack(side=tk.LEFT)
        ttk.Label(
            select_actions,
            text="Select collection tracks and/or local files above.",
            style="Dim.TLabel",
        ).pack(side=tk.LEFT, padx=(10, 0))

        results_frame = ttk.LabelFrame(
            parent, text="Preview and select magnified tracks to import", padding=8
        )
        results_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 6))
        results_frame.columnconfigure(0, weight=1)
        results_frame.rowconfigure(0, weight=1)
        self.magnifier_tree = ttk.Treeview(
            results_frame,
            columns=("title", "artist", "source", "output", "status"),
            show="headings",
            selectmode="extended",
            height=7,
        )
        for column, label, width in (
            ("title", "Track", 220),
            ("artist", "Artist", 160),
            ("source", "Source File", 300),
            ("output", "Magnified File", 300),
            ("status", "Status", 130),
        ):
            self.magnifier_tree.heading(column, text=label)
            self.magnifier_tree.column(column, width=width, anchor="w")
        self.magnifier_tree.grid(row=0, column=0, sticky="nsew")

        actions = ttk.Frame(results_frame)
        actions.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(
            actions,
            text="Play Selected",
            command=self.play_selected_magnified,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            actions,
            text="Stop",
            command=self.stop_preview,
        ).pack(side=tk.LEFT, padx=(8, 0))
        self.magnifier_import_btn = ttk.Button(
            actions,
            text="Import to Rekordbox",
            command=self.import_selected_magnified,
        )
        self.magnifier_import_btn.pack(side=tk.RIGHT)

        ttk.Label(
            parent, textvariable=self.status_var, style="Dim.TLabel", anchor="w"
        ).grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))

    def _choose_magnifier_files(self) -> None:
        selected = filedialog.askopenfilenames(
            title="Select audio files to magnify",
            filetypes=[
                ("Audio", "*.mp3 *.wav *.flac *.ogg *.m4a *.aac"),
                ("All files", "*.*"),
            ],
        )
        for raw_path in selected:
            path = Path(raw_path)
            if path not in self.magnifier_files:
                self.magnifier_files.append(path)
                if self.magnifier_files_list is not None:
                    self.magnifier_files_list.insert(tk.END, str(path))

    def _remove_magnifier_files(self) -> None:
        if self.magnifier_files_list is None:
            return
        selected = list(self.magnifier_files_list.curselection())
        for index in reversed(selected):
            self.magnifier_files_list.delete(index)
            del self.magnifier_files[index]

    @staticmethod
    def _matches_33rpm_category(track: Track) -> bool:
        category_text = " ".join([track.genre or "", *(track.tags or [])])
        return re.search(r"33", category_text, flags=re.IGNORECASE) is not None

    @staticmethod
    def _audio_export_format(source_path: Path) -> str:
        formats = {".aac": "adts", ".m4a": "ipod"}
        return formats.get(source_path.suffix.lower(), source_path.suffix.lstrip("."))

    def _choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(
            title="Select output folder for 33 RPM files"
        )
        if selected:
            cleaned = selected.strip()
            self.output_dir_var.set(cleaned)
            persist_setting("TO_33RPM_OUTPUT_DIR", cleaned)

    def _apply_output_dir_config(self) -> None:
        configured = self.output_dir_var.get().strip()
        if not configured:
            self._show_error(
                "Missing output folder",
                "Please choose a valid output folder for To 33RPM.",
            )
            return

        self.output_dir_var.set(configured)
        persist_setting("TO_33RPM_OUTPUT_DIR", configured)
        self.status_var.set("To 33RPM output folder updated.")

    def _on_collection_loaded(self, tracks: list[Track]) -> None:
        if self.tracks_list is not None:
            self.tracks_list.set_tracks(self._filter_source_tracks(tracks))
        if self.magnifier_tracks_list is not None:
            self.magnifier_tracks_list.set_tracks(
                [track for track in tracks if self._matches_33rpm_category(track)]
            )

    def magnify_selected(self) -> None:
        if self.magnifier_busy or self._is_busy:
            return

        sources: list[tuple[Optional[Track], Path]] = []
        if self.magnifier_tracks_list is not None:
            selected_tracks = self.magnifier_tracks_list.get_selected_tracks()
            unresolved_tracks = [
                track.display_name
                for track in selected_tracks
                if self._resolve_source_path(track) is None
            ]
            if unresolved_tracks:
                self._show_error(
                    "Collection audio file missing",
                    "Cannot locate the audio file for:\n" + unresolved_tracks[0],
                )
                return
            for track in selected_tracks:
                source_path = self._resolve_source_path(track)
                if source_path is not None:
                    sources.append((track, Path(source_path)))

        sources.extend((None, path) for path in self.magnifier_files)
        if not sources:
            self._show_error(
                "No audio selected",
                "Select a matching collection track or choose one or more local audio files.",
            )
            return

        invalid = [
            str(path)
            for _, path in sources
            if not path.is_file()
            or path.suffix.lower() not in settings.AUDIO_FILES_EXTENSIOINS
        ]
        if invalid:
            self._show_error(
                "Invalid audio file",
                f"Selected input is missing or unsupported:\n{invalid[0]}",
            )
            return

        output_dir_value = self.output_dir_var.get().strip()
        if not output_dir_value:
            self._show_error("Missing output folder", "Please choose an output folder.")
            return
        output_dir = Path(output_dir_value)

        self._set_magnifier_busy(True)
        self.status_var.set(f"Magnifying {len(sources)} selected audio file(s)...")
        threading.Thread(
            target=self._magnify_worker,
            args=(sources, output_dir),
            daemon=True,
        ).start()

    def _magnify_worker(
        self,
        sources: list[tuple[Optional[Track], Path]],
        output_dir: Path,
    ) -> None:
        magnified: list[MagnifiedTrack] = []
        errors: list[str] = []
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            errors.append(f"Cannot create output folder {output_dir}: {exc}")

        if not errors:
            for index, (track, source_path) in enumerate(sources, start=1):
                if self.root is not None:
                    self.root.after(
                        0,
                        lambda i=index, n=len(sources), p=source_path: self.status_var.set(
                            f"[{i}/{n}] Magnifying {p.name}..."
                        ),
                    )
                output_path: Path | None = None
                try:
                    audio = read_audiosegment(str(source_path))
                    normalized = normalize_audio_peak(audio, target_peak_db=-1.0)
                    processed = truncate_silence(
                        normalized,
                        silence_threshold=settings.TRUNCATE_SILENCE_TRESHOLD,
                        chunk_size=settings.TRUNCATE_SILENCE_CHUNK_SIZE,
                    )
                    processed = self._enhance_audio_segment(processed)
                    output_path = self._new_magnified_path(output_dir, source_path)
                    write_audiosegment(
                        processed,
                        str(output_path),
                        format=self._audio_export_format(source_path),
                        source_path=str(source_path),
                    )
                    if source_path.suffix.lower() == ".mp3":
                        copy_mp3_metadata(str(source_path), str(output_path))

                    magnified.append(
                        MagnifiedTrack(
                            source_track=track,
                            source_path=str(source_path),
                            output_path=str(output_path),
                            title=track.name if track is not None else source_path.stem,
                            artist=track.artist if track is not None else "",
                        )
                    )
                except Exception as exc:
                    if output_path is not None and output_path.exists():
                        try:
                            output_path.unlink()
                        except OSError as cleanup_exc:
                            errors.append(
                                f"Could not remove incomplete output {output_path}: "
                                f"{cleanup_exc}"
                            )
                    errors.append(f"{source_path}: {exc}")

        if self.root is not None:
            self.root.after(0, lambda: self._on_magnify_done(magnified, errors))

    @staticmethod
    def _new_magnified_path(output_dir: Path, source_path: Path) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        candidate = output_dir / f"{source_path.stem}_magnified{source_path.suffix}"
        index = 1
        while candidate.exists():
            candidate = output_dir / (
                f"{source_path.stem}_magnified_{index}{source_path.suffix}"
            )
            index += 1
        return candidate

    def _on_magnify_done(
        self, magnified: list[MagnifiedTrack], errors: list[str]
    ) -> None:
        self._magnified_tracks.extend(magnified)
        self._render_magnified_rows()
        self._set_magnifier_busy(False)
        self.status_var.set(
            f"Magnification complete. Success: {len(magnified)}, Failed: {len(errors)}."
        )
        if errors:
            details = "\n".join(errors[:10])
            suffix = "\n..." if len(errors) > 10 else ""
            messagebox.showwarning(
                "Some files could not be magnified",
                f"{len(errors)} file(s) failed:\n{details}{suffix}",
                parent=self.root,
            )

    def _set_magnifier_busy(self, busy: bool) -> None:
        self.magnifier_busy = busy
        state = "disabled" if busy else "normal"
        if self.magnify_btn is not None:
            self.magnify_btn.configure(state=state)
        if self.magnifier_import_btn is not None:
            self.magnifier_import_btn.configure(state=state)
        other_state = "disabled" if busy else "normal"
        if self.transform_btn is not None:
            self.transform_btn.configure(state=other_state)
        if self.import_btn is not None:
            self.import_btn.configure(state=other_state)

    def _render_magnified_rows(self) -> None:
        if self.magnifier_tree is None:
            return
        for item_id in self.magnifier_tree.get_children():
            self.magnifier_tree.delete(item_id)
        for index, item in enumerate(self._magnified_tracks):
            self.magnifier_tree.insert(
                "",
                "end",
                iid=str(index),
                values=(
                    item.title,
                    item.artist,
                    item.source_path,
                    item.output_path,
                    item.status,
                ),
            )

    def _get_selected_magnified_items(self) -> list[MagnifiedTrack]:
        if self.magnifier_tree is None:
            return []
        selected: list[MagnifiedTrack] = []
        for item_id in self.magnifier_tree.selection():
            try:
                index = int(item_id)
            except ValueError:
                continue
            if 0 <= index < len(self._magnified_tracks):
                selected.append(self._magnified_tracks[index])
        return selected

    def play_selected_magnified(self) -> None:
        selected = self._get_selected_magnified_items()
        if not selected:
            self._show_error("No track selected", "Select a magnified track to preview.")
            return
        item = selected[0]
        self._play_preview_file(item.output_path, item.title)

    def import_selected_magnified(self) -> None:
        if self.magnifier_busy or self._is_busy:
            return
        selected = self._get_selected_magnified_items()
        if not selected:
            self._show_error(
                "No magnified tracks selected",
                "Select one or more magnified tracks to import.",
            )
            return

        replacements = [item for item in selected if item.source_track is not None]
        if replacements and not messagebox.askyesno(
            "Replace collection audio?",
            "The selected collection tracks will have their original audio files "
            "replaced in place. This cannot be undone. Continue?",
            parent=self.root,
        ):
            return

        self._set_magnifier_busy(True)
        self.status_var.set(f"Importing {len(selected)} magnified track(s)...")
        threading.Thread(
            target=self._import_magnified_worker,
            args=(selected,),
            daemon=True,
        ).start()

    def _import_magnified_worker(self, selected: list[MagnifiedTrack]) -> None:
        imported_local = 0
        replaced_collection = 0
        errors: list[str] = []
        for index, item in enumerate(selected, start=1):
            if self.root is not None:
                self.root.after(
                    0,
                    lambda i=index, n=len(selected), t=item.title: self.status_var.set(
                        f"[{i}/{n}] Importing {t}..."
                    ),
                )
            try:
                if item.source_track is None:
                    with RekordboxDAO() as dao:
                        dao.add_audio_file_as_track(item.output_path)
                    item.status = "imported"
                    imported_local += 1
                else:
                    source_path = Path(item.source_path)
                    if not source_path.is_file():
                        raise FileNotFoundError(
                            f"Collection audio file not found: {source_path}"
                        )
                    temp_path = source_path.with_name(
                        f".{source_path.stem}.{uuid4().hex}.tmp{source_path.suffix}"
                    )
                    try:
                        shutil.copy2(item.output_path, temp_path)
                        os.replace(temp_path, source_path)
                    finally:
                        if temp_path.exists():
                            temp_path.unlink()
                    item.status = "replaced"
                    replaced_collection += 1
            except Exception as exc:
                item.status = "import failed"
                errors.append(f"{item.title}: {exc}")

        if self.root is not None:
            self.root.after(
                0,
                lambda: self._on_magnified_import_done(
                    imported_local, replaced_collection, errors
                ),
            )

    def _on_magnified_import_done(
        self, imported_local: int, replaced_collection: int, errors: list[str]
    ) -> None:
        self._render_magnified_rows()
        self._set_magnifier_busy(False)
        self.status_var.set(
            f"Import complete. Added: {imported_local}, replaced: {replaced_collection}, "
            f"Failed: {len(errors)}."
        )
        if imported_local and self.controller is not None:
            self.controller.refresh_collection()
        if errors:
            details = "\n".join(errors[:10])
            suffix = "\n..." if len(errors) > 10 else ""
            messagebox.showwarning(
                "Some tracks could not be imported",
                f"{len(errors)} track(s) failed:\n{details}{suffix}",
                parent=self.root,
            )
        else:
            messagebox.showinfo(
                "Import complete",
                f"Added {imported_local} local file(s) and replaced "
                f"{replaced_collection} collection file(s).",
                parent=self.root,
            )

    @staticmethod
    def _normalize_text(value: str) -> str:
        return re.sub(r"\s+", " ", (value or "").strip()).lower()

    @classmethod
    def _extract_base_title_if_33rpm(cls, title: str) -> Optional[str]:
        raw = (title or "").strip()
        # Accept "(33rpm)" and "(33 rpm)" at end of title (case-insensitive)
        match = re.match(r"^(.*)\(\s*33\s*rpm\s*\)\s*$", raw, flags=re.IGNORECASE)
        if not match:
            return None
        base = match.group(1).strip()
        return base or None

    @classmethod
    def _filter_source_tracks(cls, tracks: list[Track]) -> list[Track]:
        # Build set of base titles that already have a "(33 rpm)" transformed version
        base_titles_with_33: set[str] = set()
        for track in tracks:
            base = cls._extract_base_title_if_33rpm(track.name or "")
            if base:
                base_titles_with_33.add(cls._normalize_text(base))

        filtered: list[Track] = []
        for track in tracks:
            title = track.name or ""
            norm_title = cls._normalize_text(title)
            norm_genre = cls._normalize_text(track.genre or "")

            # 1) Exclude tracks with genre "33 rpm"
            if norm_genre == "33 rpm":
                continue

            # 2) Exclude explicit transformed variants, e.g. "track (33rpm)"
            if cls._extract_base_title_if_33rpm(title):
                continue

            # 3) Exclude original tracks when transformed counterpart exists
            if norm_title in base_titles_with_33:
                continue

            filtered.append(track)

        return filtered

    def _on_source_track_selected(self, _track: Optional[Track]) -> None:
        if self.tracks_list is None:
            return
        selected_count = len(self.tracks_list.get_selected_tracks())
        self.status_var.set(f"Selected {selected_count} source track(s).")

    def _set_busy(self, busy: bool, status: str = "") -> None:
        self._is_busy = busy
        if status:
            self.status_var.set(status)

        state = "disabled" if busy else "normal"
        if self.transform_btn is not None:
            self.transform_btn.configure(state=state)
        if self.preview_btn is not None:
            self.preview_btn.configure(state=state)
        if self.import_btn is not None:
            self.import_btn.configure(state=state)
        if self.magnify_btn is not None:
            self.magnify_btn.configure(state=state)
        if self.magnifier_import_btn is not None:
            self.magnifier_import_btn.configure(state=state)
        if self.stop_preview_btn is not None:
            self.stop_preview_btn.configure(state="normal")

    def transform_selected_tracks(self) -> None:
        if self._is_busy or self.magnifier_busy:
            return
        if self.tracks_list is None:
            return

        selected_tracks = self.tracks_list.get_selected_tracks()
        if not selected_tracks:
            self._show_error(
                "No tracks selected", "Please select one or more tracks first."
            )
            return

        output_dir = self.output_dir_var.get().strip()
        if not output_dir:
            self._show_error("Missing output folder", "Please choose an output folder.")
            return

        self._set_busy(
            True, f"Transforming {len(selected_tracks)} track(s) to 33 RPM..."
        )
        worker = threading.Thread(
            target=self._transform_worker,
            args=(selected_tracks, output_dir),
            daemon=True,
        )
        worker.start()

    def _transform_worker(self, tracks: list[Track], output_dir: str) -> None:
        transformed: list[TransformedTrack] = []
        errors: list[str] = []

        os.makedirs(output_dir, exist_ok=True)

        for index, track in enumerate(tracks, start=1):
            source_path = self._resolve_source_path(track)
            if source_path is None:
                errors.append(f"{track.display_name}: missing local file path")
                continue

            if self.root is not None:
                self.root.after(
                    0,
                    lambda i=index, n=len(
                        tracks
                    ), name=track.display_name: self.status_var.set(
                        f"[{i}/{n}] Transforming {name}..."
                    ),
                )

            try:
                input_path = Path(source_path)
                audio, meta = read_audio(input_path)
                processed = emulate_45_played_at_33(
                    audio,
                    ProcessConfig(
                        method="polyphase", normalize=True, target_peak_dbfs=-1.0
                    ),
                )
                processed = self._apply_enhancer_chain(processed, meta.sample_rate)

                transformed_title = f"{(track.name or '').strip()} (33 rpm)".strip()
                source_title = (track.name or "").strip()
                source_artist = (track.artist or "").strip()
                source_album = (track.album or "").strip()
                source_year = track.year
                source_label = (track.label or "").strip()
                source_genre = (track.genre or "").strip()

                output_path = self._build_output_path(
                    output_dir=Path(output_dir),
                    base_title=transformed_title,
                    track_id=track.id,
                )
                write_audio(output_path, processed, meta)

                write_audio_metadata(
                    file_path=output_path,
                    title=transformed_title,
                    artist=source_artist,
                    album=source_album,
                    year=source_year,
                    label=source_label,
                    genre="33 rpm",
                    bpm=track.bpm,
                )

                transformed.append(
                    TransformedTrack(
                        source_track=track,
                        output_path=str(output_path),
                        title=transformed_title,
                        artist=source_artist,
                        album=source_album,
                        year=source_year,
                        label=source_label,
                        genre="33 rpm",
                        tags=self._build_transformed_tags(track),
                    )
                )
                self._track_generated_output(str(output_path))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{track.display_name}: {exc}")

        if self.root is not None:
            self.root.after(0, lambda: self._on_transform_done(transformed, errors))

    @staticmethod
    def _apply_enhancer_chain(audio: np.ndarray, sample_rate: int) -> np.ndarray:
        return apply_enhancer_chain(audio, sample_rate)

    @classmethod
    def _enhance_audio_segment(cls, audio: AudioSegment) -> AudioSegment:
        samples = np.array(audio.get_array_of_samples())
        channels = audio.channels
        if channels > 1:
            samples = samples.reshape((-1, channels))
        scale = float(1 << (8 * audio.sample_width - 1))
        enhanced = cls._apply_enhancer_chain(
            samples.astype(np.float64) / scale,
            audio.frame_rate,
        )
        clipped = np.clip(enhanced, -1.0, 1.0)
        pcm = (clipped * (scale - 1.0)).astype(samples.dtype)
        if channels > 1:
            pcm = pcm.reshape(-1)
        return audio._spawn(pcm.tobytes())

    def _on_transform_done(
        self,
        transformed: list[TransformedTrack],
        errors: list[str],
    ) -> None:
        self._transformed_tracks = transformed
        self._render_transformed_rows()
        self._set_busy(False)

        success_count = len(transformed)
        failed_count = len(errors)
        self.status_var.set(
            f"Transformation completed. Success: {success_count}, Failed: {failed_count}."
        )

        if failed_count > 0:
            details = "\n".join(errors[:10])
            suffix = "\n..." if len(errors) > 10 else ""
            messagebox.showwarning(
                "Some tracks failed",
                f"{failed_count} track(s) failed during transformation:\n{details}{suffix}",
                parent=self.root,
            )

    def _render_transformed_rows(self) -> None:
        if self.preview_tree is None:
            return

        for item_id in self.preview_tree.get_children():
            self.preview_tree.delete(item_id)

        for idx, item in enumerate(self._transformed_tracks):
            self.preview_tree.insert(
                "",
                "end",
                iid=str(idx),
                values=(
                    item.title,
                    item.artist,
                    item.album,
                    item.genre,
                    item.output_path,
                    item.status,
                    item.imported_track_id,
                ),
            )

    def _get_selected_transformed_items(self) -> list[TransformedTrack]:
        if self.preview_tree is None:
            return []

        selected: list[TransformedTrack] = []
        for item_id in self.preview_tree.selection():
            try:
                index = int(item_id)
            except ValueError:
                continue
            if 0 <= index < len(self._transformed_tracks):
                selected.append(self._transformed_tracks[index])
        return selected

    def play_selected_preview(self) -> None:
        selected = self._get_selected_transformed_items()
        if not selected:
            self._show_error(
                "No transformed track selected",
                "Select one transformed track to preview.",
            )
            return

        candidate = selected[0]
        self._play_preview_file(candidate.output_path, candidate.title)

    def _play_preview_file(self, path: str, title: str) -> None:
        if not os.path.exists(path):
            self._show_error("Missing file", f"Audio file not found:\n{path}")
            return

        self._player_current_file = path
        if not self._load_preview_audio(path):
            self._show_error(
                "Preview failed",
                "Unable to load this file for preview playback.",
            )
            return

        self._set_seek_position(0.0)
        self._update_player_time_label(0.0)

        try:
            self._start_preview_stream(start_seconds=0.0)
            self.status_var.set(f"Previewing: {title}")
            self._start_player_clock()
        except Exception as exc:  # noqa: BLE001
            self._show_error("Preview failed", str(exc))

    def stop_preview(self) -> None:
        self._stop_preview_stream()
        self._stop_player_clock()
        self._player_frame_pos = 0
        self._set_seek_position(0.0)
        self._update_player_time_label(0.0)
        self.status_var.set("Preview stopped.")

    def import_selected_to_rekordbox(self) -> None:
        if self._is_busy or self.magnifier_busy:
            return

        selected = self._get_selected_transformed_items()
        if not selected:
            self._show_error(
                "No transformed tracks selected",
                "Please select one or more transformed tracks to import.",
            )
            return

        self._set_busy(
            True, f"Importing {len(selected)} transformed track(s) to Rekordbox..."
        )
        worker = threading.Thread(
            target=self._import_worker,
            args=(selected,),
            daemon=True,
        )
        worker.start()

    def _import_worker(self, selected: list[TransformedTrack]) -> None:
        imported = 0
        failed: list[str] = []
        warnings: list[str] = []

        for index, item in enumerate(selected, start=1):
            if self.root is not None:
                self.root.after(
                    0,
                    lambda i=index, n=len(
                        selected
                    ), title=item.title: self.status_var.set(
                        f"[{i}/{n}] Importing {title}..."
                    ),
                )

            try:
                metadata_warning_for_item = False
                with RekordboxDAO() as dao:
                    added_track = dao.add_audio_file_as_track(item.output_path)
                    added_track_id = str(added_track.ID)
                    try:
                        dao.set_track_metadata_in_rekordbox(
                            track_id=added_track_id,
                            title=item.title,
                            artist=item.artist,
                            album=item.album,
                            label=item.label,
                            year=item.year,
                            genre=item.genre,
                            tags=item.tags,
                        )
                    except Exception as metadata_exc:  # noqa: BLE001
                        metadata_warning_for_item = True
                        warnings.append(f"{item.title}: metadata update failed ({metadata_exc})")

                item.imported_track_id = added_track_id
                item.status = (
                    "imported (metadata warning)"
                    if metadata_warning_for_item
                    else "imported"
                )
                self._track_imported_output(item.output_path)
                imported += 1
            except Exception as exc:  # noqa: BLE001
                item.status = "import failed"
                failed.append(f"{item.title}: {exc}")

        if self.root is not None:
            self.root.after(0, lambda: self._on_import_done(imported, failed, warnings))

    def _on_import_done(self, imported: int, failed: list[str], warnings: list[str]) -> None:
        self._render_transformed_rows()
        self._set_busy(False)

        failed_count = len(failed)
        warning_count = len(warnings)
        self.status_var.set(
            f"Rekordbox import finished. Imported: {imported}, Failed: {failed_count}, Warnings: {warning_count}."
        )

        if self.controller is not None:
            self.controller.refresh_collection()

        if failed_count > 0:
            details = "\n".join(failed[:10])
            suffix = "\n..." if len(failed) > 10 else ""
            messagebox.showwarning(
                "Import partially failed",
                f"{failed_count} import(s) failed:\n{details}{suffix}",
                parent=self.root,
            )
        elif warning_count > 0:
            details = "\n".join(warnings[:10])
            suffix = "\n..." if len(warnings) > 10 else ""
            messagebox.showwarning(
                "Import completed with warnings",
                f"All tracks were added to Rekordbox, but {warning_count} metadata update(s) failed:\n{details}{suffix}",
                parent=self.root,
            )
        else:
            messagebox.showinfo(
                "Import complete",
                f"Successfully imported {imported} transformed track(s) to Rekordbox.",
                parent=self.root,
            )

    @staticmethod
    def _resolve_source_path(track: Track) -> Optional[str]:
        candidates = [track.file_path, track.org_folder_path]
        for candidate in candidates:
            if not candidate:
                continue
            path = str(candidate).strip()
            if path and os.path.exists(path):
                return path
        return None

    @staticmethod
    def _sanitize_filename_part(value: str) -> str:
        raw = (value or "").strip()
        if not raw:
            return "track"
        cleaned = re.sub(r'[<>:\\"/\\|?*]+', "_", raw)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
        return cleaned or "track"

    @staticmethod
    def _build_transformed_tags(track: Track) -> list[str]:
        source_tags = {
            str(tag).strip().lower(): str(tag).strip()
            for tag in (track.tags or [])
            if str(tag).strip()
        }

        transformed_tags = ["Not Tagged"]

        if "Vinyl Rip" in source_tags:
            transformed_tags.append("Vinyl Rip")
        if "Copyright Ok" in source_tags:
            transformed_tags.append("Copyright Ok")

        return transformed_tags

    def _build_output_path(
        self, output_dir: Path, base_title: str, track_id: str
    ) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)

        stem = self._sanitize_filename_part(base_title)
        candidate = output_dir / f"{stem}{OUTPUT_SUFFIX}"
        if not candidate.exists():
            return candidate

        suffix_candidate = output_dir / f"{stem}_{track_id}{OUTPUT_SUFFIX}"
        if not suffix_candidate.exists():
            return suffix_candidate

        idx = 1
        while True:
            indexed = output_dir / f"{stem}_{track_id}_{idx}{OUTPUT_SUFFIX}"
            if not indexed.exists():
                return indexed
            idx += 1

    def _show_error(self, title: str, details: str) -> None:
        messagebox.showerror(title, details, parent=self.root)

    def _register_shutdown_hook(self) -> None:
        if self._shutdown_hook_registered:
            return
        self._shutdown_hook_registered = True

        atexit.register(self._cleanup_unimported_outputs)

        if self.root is not None:
            self.root.protocol("WM_DELETE_WINDOW", self._on_app_close)

    def _on_app_close(self) -> None:
        self.stop_preview()
        self._cleanup_unimported_outputs()
        if self.root is not None:
            self.root.destroy()

    def _load_pending_state(self) -> tuple[set[str], set[str]]:
        if not PENDING_33RPM_FILE.exists():
            return set(), set()

        try:
            payload = json.loads(PENDING_33RPM_FILE.read_text(encoding="utf-8"))
        except Exception:
            logger.exception("Failed to read pending 33rpm cleanup file")
            return set(), set()

        generated = {
            str(path).strip()
            for path in payload.get("generated", [])
            if str(path).strip()
        }
        imported = {
            str(path).strip()
            for path in payload.get("imported", [])
            if str(path).strip()
        }
        return generated, imported

    def _save_pending_state(self) -> None:
        with self._cleanup_lock:
            payload = {
                "generated": sorted(self._generated_output_paths),
                "imported": sorted(self._imported_output_paths),
            }

        PENDING_33RPM_FILE.write_text(
            json.dumps(payload, indent=2, ensure_ascii=True) + "\n",
            encoding="utf-8",
        )

    def _cleanup_stale_unimported_outputs(self) -> None:
        generated, imported = self._load_pending_state()
        pending = generated - imported
        if not pending:
            return

        for raw_path in sorted(pending):
            try:
                candidate = Path(raw_path)
                if candidate.exists() and candidate.is_file():
                    candidate.unlink()
            except Exception:
                logger.exception("Failed to remove stale 33rpm output: %s", raw_path)

        if PENDING_33RPM_FILE.exists():
            try:
                PENDING_33RPM_FILE.unlink()
            except Exception:
                logger.exception("Failed to delete pending 33rpm cleanup file")

    def _track_generated_output(self, output_path: str) -> None:
        clean = str(output_path or "").strip()
        if not clean:
            return

        with self._cleanup_lock:
            self._generated_output_paths.add(clean)

        self._save_pending_state()

    def _track_imported_output(self, output_path: str) -> None:
        clean = str(output_path or "").strip()
        if not clean:
            return

        with self._cleanup_lock:
            self._imported_output_paths.add(clean)

        self._save_pending_state()

    def _cleanup_unimported_outputs(self) -> None:
        with self._cleanup_lock:
            pending = self._generated_output_paths - self._imported_output_paths

        for raw_path in sorted(pending):
            try:
                candidate = Path(raw_path)
                if candidate.exists() and candidate.is_file():
                    candidate.unlink()
            except Exception:
                logger.exception("Failed to remove unimported 33rpm output: %s", raw_path)

        if PENDING_33RPM_FILE.exists():
            try:
                PENDING_33RPM_FILE.unlink()
            except Exception:
                logger.exception("Failed to delete pending 33rpm cleanup file")

    def _init_preview_player_backend(self) -> None:
        try:
            self._sd = importlib.import_module("sounddevice")
            self._player_backend_available = True
        except Exception:
            self._sd = None
            self._player_backend_available = False
            logger.info("sounddevice backend not available; preview disabled")

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        safe = max(0, int(round(seconds)))
        mins = safe // 60
        secs = safe % 60
        return f"{mins:02d}:{secs:02d}"

    def _set_seek_position(self, seconds: float) -> None:
        if self.player_seek_scale is None:
            return
        max_seconds = max(1.0, self._player_duration_seconds)
        clamped = max(0.0, min(seconds, max_seconds))
        self.player_seek_scale.configure(to=max_seconds)
        self.player_seek_scale.set(clamped)

    def _update_player_time_label(self, current_seconds: float) -> None:
        current = self._format_timestamp(current_seconds)
        total = self._format_timestamp(self._player_duration_seconds)
        self.player_time_var.set(f"{current} / {total}")

    def _start_player_clock(self) -> None:
        self._stop_player_clock()
        if self.root is None:
            return

        def tick() -> None:
            if self.root is None:
                return

            with self._player_state_lock:
                if self._player_sample_rate > 0:
                    current = self._player_frame_pos / float(self._player_sample_rate)
                else:
                    current = 0.0

            current = max(0.0, min(current, max(self._player_duration_seconds, 0.0)))

            if not self._is_dragging_seek:
                self._set_seek_position(current)
                self._update_player_time_label(current)

            busy = self._is_preview_stream_active()

            if busy:
                self._player_after_id = self.root.after(250, tick)
            else:
                self._player_after_id = None

        tick()

    def _stop_player_clock(self) -> None:
        if self.root is not None and self._player_after_id is not None:
            try:
                self.root.after_cancel(self._player_after_id)
            except Exception:
                logger.exception("Failed to cancel preview clock")
        self._player_after_id = None

    def _on_seek_press(self, _event) -> None:
        self._is_dragging_seek = True

    def _on_seek_release(self, _event) -> None:
        self._is_dragging_seek = False
        if self.player_seek_scale is None:
            return

        target = float(self.player_seek_scale.get())
        self._seek_to(target)

    def _seek_to(self, target_seconds: float) -> None:
        if not self._player_backend_available or self._sd is None:
            self.status_var.set("Preview backend is unavailable. Install sounddevice.")
            return

        if not self._player_current_file:
            return

        if self._player_sample_rate <= 0 or self._player_audio is None:
            return

        try:
            max_seconds = max(0.0, self._player_duration_seconds)
            clamped = max(0.0, min(target_seconds, max_seconds))
            target_frame = int(round(clamped * self._player_sample_rate))
            target_frame = max(0, min(target_frame, self._player_total_frames))

            with self._player_state_lock:
                self._player_frame_pos = target_frame

            self._set_seek_position(clamped)
            self._update_player_time_label(clamped)
            self._start_player_clock()
        except Exception:
            logger.exception("Seek failed")

    def _load_preview_audio(self, file_path: str) -> bool:
        try:
            audio, meta = read_audio(Path(file_path))
        except Exception:
            logger.exception("Failed to read preview audio: %s", file_path)
            return False

        if audio.size == 0:
            return False

        work = np.asarray(audio, dtype=np.float32)
        if work.ndim == 1:
            work = np.expand_dims(work, axis=1)

        self._player_audio = work
        self._player_sample_rate = int(meta.sample_rate)
        self._player_total_frames = int(work.shape[0])
        self._player_duration_seconds = (
            float(self._player_total_frames) / float(self._player_sample_rate)
            if self._player_sample_rate > 0
            else 0.0
        )
        self._player_frame_pos = 0
        return True

    def _audio_stream_callback(self, outdata, frames, _time, _status) -> None:
        if self._player_audio is None:
            outdata.fill(0)
            raise self._sd.CallbackStop()

        with self._player_state_lock:
            start = self._player_frame_pos
            end = min(start + frames, self._player_total_frames)
            chunk = self._player_audio[start:end]
            self._player_frame_pos = end

        outdata.fill(0)
        if len(chunk) > 0:
            outdata[: len(chunk)] = chunk

        if end >= self._player_total_frames:
            raise self._sd.CallbackStop()

    def _start_preview_stream(self, start_seconds: float = 0.0) -> None:
        if not self._player_backend_available or self._sd is None:
            raise RuntimeError("sounddevice is not available for local preview")
        if self._player_audio is None or self._player_sample_rate <= 0:
            raise RuntimeError("No audio loaded for preview")

        self._stop_preview_stream()

        start_frame = int(round(max(0.0, start_seconds) * self._player_sample_rate))
        start_frame = max(0, min(start_frame, self._player_total_frames))
        with self._player_state_lock:
            self._player_frame_pos = start_frame

        channels = int(self._player_audio.shape[1])
        self._player_stream = self._sd.OutputStream(
            samplerate=self._player_sample_rate,
            channels=channels,
            dtype="float32",
            callback=self._audio_stream_callback,
        )
        self._player_stream.start()

    def _stop_preview_stream(self) -> None:
        stream = self._player_stream
        self._player_stream = None
        if stream is None:
            return
        try:
            if stream.active:
                stream.stop()
            stream.close()
        except Exception:
            logger.exception("Failed to stop preview stream")

    def _is_preview_stream_active(self) -> bool:
        stream = self._player_stream
        return bool(stream is not None and stream.active)
