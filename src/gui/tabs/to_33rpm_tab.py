from __future__ import annotations

import os
import re
import threading
import tkinter as tk
import winsound
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from src.core.to_33rpm.io_audio import read_audio, write_audio
from src.core.to_33rpm.processing import ProcessConfig, emulate_45_played_at_33
from src.data import RekordboxDAO, Track
from src.gui.tab_system import ConfigSubtabFeature, FeatureContext
from src.gui.widgets import TracksList
from src.services import complete_track_metadata
from src.services.audio_metadata_service import write_audio_metadata
from src.user_config import settings

OUTPUT_SUFFIX = ".wav"


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

        self.transform_btn: ttk.Button | None = None
        self.preview_btn: ttk.Button | None = None
        self.stop_preview_btn: ttk.Button | None = None
        self.import_btn: ttk.Button | None = None

        self._is_busy = False
        self._transformed_tracks: list[TransformedTrack] = []

    def build_main_tab(self, context: FeatureContext) -> Optional[ttk.Frame]:
        self.root = context.root
        self.controller = context.controller

        main_frame = ttk.Frame(context.notebook)
        context.notebook.add(main_frame, text="To 33RPM")

        self._create_widgets(main_frame)
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

    def _choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(
            title="Select output folder for 33 RPM files"
        )
        if selected:
            cleaned = selected.strip()
            self.output_dir_var.set(cleaned)
            settings.TO_33RPM_OUTPUT_DIR = cleaned

    def _apply_output_dir_config(self) -> None:
        configured = self.output_dir_var.get().strip()
        if not configured:
            self._show_error(
                "Missing output folder",
                "Please choose a valid output folder for To 33RPM.",
            )
            return

        self.output_dir_var.set(configured)
        settings.TO_33RPM_OUTPUT_DIR = configured
        self.status_var.set("To 33RPM output folder updated.")

    def _on_collection_loaded(self, tracks: list[Track]) -> None:
        if self.tracks_list is not None:
            self.tracks_list.set_tracks(self._filter_source_tracks(tracks))

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
        if self.stop_preview_btn is not None:
            self.stop_preview_btn.configure(state="normal")

    def transform_selected_tracks(self) -> None:
        if self._is_busy:
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

                transformed_title = f"{(track.name or '').strip()} (33 rpm)".strip()
                completion = complete_track_metadata(
                    title=track.name or "",
                    artist=track.artist or "",
                    album=track.album or "",
                )

                album = (completion.album or track.album or "").strip()
                year = completion.year if completion.year is not None else track.year
                label = (completion.label or track.label or "").strip()

                output_path = self._build_output_path(
                    output_dir=Path(output_dir),
                    base_title=transformed_title,
                    track_id=track.id,
                )
                write_audio(output_path, processed, meta)

                write_audio_metadata(
                    file_path=output_path,
                    title=transformed_title,
                    artist=(track.artist or "").strip(),
                    album=album,
                    year=year,
                    label=label,
                    genre="33 rpm",
                    bpm=track.bpm,
                )

                transformed.append(
                    TransformedTrack(
                        source_track=track,
                        output_path=str(output_path),
                        title=transformed_title,
                        artist=(track.artist or "").strip(),
                        album=album,
                        year=year,
                        label=label,
                        genre="33 rpm",
                        tags=self._build_transformed_tags(track),
                    )
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{track.display_name}: {exc}")

        if self.root is not None:
            self.root.after(0, lambda: self._on_transform_done(transformed, errors))

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
        path = candidate.output_path
        if not os.path.exists(path):
            self._show_error("Missing file", f"Transformed file not found:\n{path}")
            return

        try:
            winsound.PlaySound(None, winsound.SND_PURGE)
            winsound.PlaySound(
                path,
                winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT,
            )
            self.status_var.set(f"Previewing: {candidate.title}")
        except Exception as exc:  # noqa: BLE001
            self._show_error("Preview failed", str(exc))

    def stop_preview(self) -> None:
        winsound.PlaySound(None, winsound.SND_PURGE)
        self.status_var.set("Preview stopped.")

    def import_selected_to_rekordbox(self) -> None:
        if self._is_busy:
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
                with RekordboxDAO() as dao:
                    added_track = dao.add_audio_file_as_track(item.output_path)
                    dao.set_track_metadata_in_rekordbox(
                        track_id=added_track.ID,
                        title=item.title,
                        artist=item.artist,
                        album=item.album,
                        label=item.label,
                        year=item.year,
                        genre=item.genre,
                        tags=item.tags,
                    )

                item.imported_track_id = str(added_track.ID)
                item.status = "imported"
                imported += 1
            except Exception as exc:  # noqa: BLE001
                item.status = "import failed"
                failed.append(f"{item.title}: {exc}")

        if self.root is not None:
            self.root.after(0, lambda: self._on_import_done(imported, failed))

    def _on_import_done(self, imported: int, failed: list[str]) -> None:
        self._render_transformed_rows()
        self._set_busy(False)

        failed_count = len(failed)
        self.status_var.set(
            f"Rekordbox import finished. Imported: {imported}, Failed: {failed_count}."
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

        if "vynil rip" in source_tags:
            transformed_tags.append("Vynil Rip")
        if "copyright ok" in source_tags:
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
