from __future__ import annotations

import os
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from src.core.youtube_download.actions import (
    OTHER_TAG_CATEGORY,
    TAG_CATEGORY_ORDER,
    append_album_ref,
    category_for_tag,
    download_audio_as_mp3,
    extract_year_from_youtube_info,
    fetch_youtube_info,
    get_rekordbox_taxonomy,
    lookup_bandcamp_album,
    lookup_discogs_metadata,
    remove_playlist_param,
    resolve_downloaded_path,
    save_sidecar_json,
    set_track_metadata_in_rekordbox,
    write_metadata_to_mp3,
)
from src.data import RekordboxDAO
from src.gui.tab_system import FeatureContext, TabFeature
from src.gui.theme import BG_CARD


class YoutubeDownloadFeature(TabFeature):
    name = "youtube_download"

    def __init__(self):
        self.root: tk.Tk | None = None

        self.selected_file = ""
        self.youtube_info: dict = {}

        self.url_var = tk.StringVar()
        self.youtube_dir_var = tk.StringVar(value=str(Path.cwd() / "youtube_downloads"))

        self.file_var = tk.StringVar(value="No file selected")
        self.video_title_var = tk.StringVar()
        self.track_title_var = tk.StringVar()
        self.artist_var = tk.StringVar()
        self.album_var = tk.StringVar()
        self.year_var = tk.StringVar()
        self.label_var = tk.StringVar()
        self.genre_var = tk.StringVar()

        self.available_genres: list[str] = []
        self.available_tags: list[str] = []
        self.tag_vars: dict[str, tk.BooleanVar] = {}
        self.tag_category_frames: dict[str, ttk.Frame] = {}

        self.tags_frame: ttk.LabelFrame | None = None
        self.genre_combobox: ttk.Combobox | None = None

        self._is_busy = False
        self.status_var = tk.StringVar(value="Ready")

    def build_main_tab(self, context: FeatureContext) -> Optional[ttk.Frame]:
        self.root = context.root

        main_frame = ttk.Frame(context.notebook)
        context.notebook.add(main_frame, text="YouTube Download")

        self._load_rekordbox_taxonomy()
        self._create_widgets(main_frame)
        return main_frame

    def _create_widgets(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        wrapper = ttk.Frame(parent, padding=12)
        wrapper.grid(row=0, column=0, sticky="nsew")
        wrapper.columnconfigure(1, weight=1)

        ttk.Label(wrapper, text="YouTube URL (required):").grid(
            row=0, column=0, sticky="w", padx=8, pady=(8, 4)
        )
        ttk.Entry(wrapper, textvariable=self.url_var).grid(
            row=0, column=1, sticky="ew", padx=8, pady=(8, 4)
        )
        ttk.Button(wrapper, text="Load YouTube data", command=self.load_youtube_data).grid(
            row=0, column=2, sticky="e", padx=8, pady=(8, 4)
        )

        ttk.Label(wrapper, text="Download folder:").grid(
            row=1, column=0, sticky="w", padx=8, pady=4
        )
        ttk.Entry(wrapper, textvariable=self.youtube_dir_var).grid(
            row=1, column=1, sticky="ew", padx=8, pady=4
        )
        ttk.Button(wrapper, text="Choose folder", command=self._choose_youtube_dir).grid(
            row=1, column=2, sticky="e", padx=8, pady=4
        )

        ttk.Label(wrapper, text="Loaded file:").grid(
            row=2, column=0, sticky="w", padx=8, pady=4
        )
        ttk.Label(wrapper, textvariable=self.file_var, anchor="w").grid(
            row=2, column=1, sticky="ew", padx=8, pady=4
        )
        ttk.Button(wrapper, text="Choose file", command=self.select_file).grid(
            row=2, column=2, sticky="e", padx=8, pady=4
        )

        ttk.Label(wrapper, text="YouTube title:").grid(
            row=3, column=0, sticky="w", padx=8, pady=(14, 4)
        )
        ttk.Entry(wrapper, textvariable=self.video_title_var, state="readonly").grid(
            row=3, column=1, columnspan=2, sticky="ew", padx=8, pady=(14, 4)
        )

        ttk.Label(wrapper, text="Track title:").grid(
            row=4, column=0, sticky="w", padx=8, pady=4
        )
        ttk.Entry(wrapper, textvariable=self.track_title_var).grid(
            row=4, column=1, columnspan=2, sticky="ew", padx=8, pady=4
        )

        ttk.Label(wrapper, text="Artist name:").grid(
            row=5, column=0, sticky="w", padx=8, pady=4
        )
        ttk.Entry(wrapper, textvariable=self.artist_var).grid(
            row=5, column=1, columnspan=2, sticky="ew", padx=8, pady=4
        )

        ttk.Label(wrapper, text="Album name:").grid(
            row=6, column=0, sticky="w", padx=8, pady=4
        )
        ttk.Entry(wrapper, textvariable=self.album_var).grid(
            row=6, column=1, columnspan=2, sticky="ew", padx=8, pady=4
        )

        ttk.Label(wrapper, text="Year:").grid(row=7, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(wrapper, textvariable=self.year_var).grid(
            row=7, column=1, columnspan=2, sticky="ew", padx=8, pady=4
        )

        ttk.Label(wrapper, text="Label:").grid(row=8, column=0, sticky="w", padx=8, pady=4)
        ttk.Entry(wrapper, textvariable=self.label_var).grid(
            row=8, column=1, columnspan=2, sticky="ew", padx=8, pady=4
        )

        ttk.Label(wrapper, text="Genre:").grid(row=9, column=0, sticky="w", padx=8, pady=4)
        self.genre_combobox = ttk.Combobox(
            wrapper,
            textvariable=self.genre_var,
            values=self.available_genres,
            state="readonly" if self.available_genres else "normal",
        )
        self.genre_combobox.grid(row=9, column=1, columnspan=2, sticky="ew", padx=8, pady=4)

        self.tags_frame = ttk.LabelFrame(wrapper, text="Tags from Rekordbox")
        self.tags_frame.grid(row=10, column=0, columnspan=3, sticky="ew", padx=8, pady=8)
        self.tags_frame.columnconfigure(0, weight=1)
        self.tags_frame.columnconfigure(1, weight=1)
        self._build_tag_checkboxes()

        btn_row = ttk.Frame(wrapper)
        btn_row.grid(row=11, column=0, columnspan=3, sticky="ew", padx=8, pady=(10, 2))
        btn_row.columnconfigure(0, weight=1)
        btn_row.columnconfigure(1, weight=1)
        btn_row.columnconfigure(2, weight=1)

        ttk.Button(
            btn_row,
            text="Validate + Enrich metadata",
            command=self.validate_and_enrich_metadata,
        ).grid(row=0, column=0, sticky="w")

        ttk.Button(btn_row, text="Save metadata", command=self.save_metadata).grid(
            row=0, column=1, sticky="w"
        )

        ttk.Button(
            btn_row,
            text="Download + Add to Rekordbox",
            style="Accent.TButton",
            command=self.download_and_add_to_rekordbox,
        ).grid(row=0, column=2, sticky="e")

        help_text = (
            "Flow: 1) Enter one URL  2) Load YouTube data  3) Validate title+artist "
            "4) Enrich metadata  5) Download + Add to Rekordbox"
        )
        ttk.Label(wrapper, text=help_text, anchor="w", style="Dim.TLabel").grid(
            row=12, column=0, columnspan=3, sticky="ew", padx=8, pady=(2, 6)
        )

        ttk.Label(wrapper, textvariable=self.status_var, style="Dim.TLabel", anchor="w").grid(
            row=13, column=0, columnspan=3, sticky="ew", padx=8, pady=(0, 8)
        )

    def _set_busy(self, value: bool, status: str = "") -> None:
        self._is_busy = value
        if status:
            self.status_var.set(status)

    def _load_rekordbox_taxonomy(self) -> None:
        self.available_genres, self.available_tags = get_rekordbox_taxonomy()

    def _build_tag_checkboxes(self) -> None:
        if self.tags_frame is None:
            return

        for child in self.tags_frame.winfo_children():
            child.destroy()
        self.tag_category_frames = {}
        self.tag_vars = {}

        if not self.available_tags:
            ttk.Label(
                self.tags_frame,
                text="No tags found in Rekordbox collection.",
                anchor="w",
                style="Dim.TLabel",
            ).grid(row=0, column=0, sticky="w", padx=8, pady=6)
            return

        grouped: dict[str, list[str]] = {
            name: [] for name in (TAG_CATEGORY_ORDER + [OTHER_TAG_CATEGORY])
        }
        for tag_name in self.available_tags:
            grouped[category_for_tag(tag_name)].append(tag_name)

        categories = list(TAG_CATEGORY_ORDER)
        if grouped[OTHER_TAG_CATEGORY]:
            categories.append(OTHER_TAG_CATEGORY)

        for index, category in enumerate(categories):
            row = index // 2
            column = index % 2
            self._create_category_tag_panel(category, row, column)

        for category in categories:
            host = self.tag_category_frames[category]
            for idx, tag_name in enumerate(sorted(grouped[category], key=str.lower)):
                var = tk.BooleanVar(value=False)
                self.tag_vars[tag_name] = var
                ttk.Checkbutton(host, text=tag_name, variable=var).grid(
                    row=idx, column=0, sticky="w", padx=8, pady=2
                )

    def _create_category_tag_panel(self, category: str, row: int, column: int) -> None:
        if self.tags_frame is None:
            return

        wrapper = ttk.Frame(self.tags_frame)
        wrapper.grid(row=row, column=column, sticky="nsew", padx=8, pady=6)
        wrapper.columnconfigure(0, weight=1)
        wrapper.rowconfigure(1, weight=1)

        ttk.Label(wrapper, text=category, style="Accent.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 4)
        )

        list_wrapper = ttk.Frame(wrapper)
        list_wrapper.grid(row=1, column=0, sticky="nsew")
        list_wrapper.columnconfigure(0, weight=1)
        list_wrapper.rowconfigure(0, weight=1)

        canvas = tk.Canvas(
            list_wrapper,
            height=110,
            borderwidth=0,
            highlightthickness=0,
            bg=BG_CARD,
        )
        scrollbar = ttk.Scrollbar(list_wrapper, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        inner = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=inner, anchor="nw")

        inner.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))

        self.tag_category_frames[category] = inner

    def _choose_youtube_dir(self) -> None:
        path = filedialog.askdirectory(title="Select download folder")
        if path:
            self.youtube_dir_var.set(path)

    def load_youtube_data(self) -> None:
        if self._is_busy:
            return

        url = self.url_var.get().strip()
        if not url:
            self._show_error("Missing URL", "Please provide a YouTube URL.")
            return

        try:
            self._set_busy(True, "Loading YouTube metadata...")
            info = fetch_youtube_info(url)
            self.youtube_info = info

            title = (info.get("track") or info.get("title") or "").strip()
            artist = (info.get("artist") or info.get("uploader") or "").strip()
            album = (info.get("album") or "").strip()

            self.video_title_var.set(info.get("title", ""))
            self.track_title_var.set(title)
            self.artist_var.set(artist)
            self.album_var.set(album)
            self.year_var.set(str(info.get("release_year") or ""))

            if self.available_genres and not self.genre_var.get().strip():
                self.genre_var.set(self.available_genres[0])

            self.status_var.set("YouTube metadata loaded.")
        except Exception as exc:
            self._show_error("Load failed", f"Could not load YouTube data:\n{exc}")
            self.status_var.set("Failed to load YouTube metadata.")
        finally:
            self._set_busy(False)

    def validate_and_enrich_metadata(self) -> None:
        metadata = self._validate_metadata_inputs(require_album=False)
        if metadata is None:
            return

        title, artist, album = metadata
        source = ""

        discogs_data = lookup_discogs_metadata(title=title, artist=artist, album=album)
        if discogs_data:
            existing_album = self.album_var.get().strip()
            album_candidate = existing_album or (discogs_data.get("album") or "")
            album_with_ref = append_album_ref(
                album_candidate,
                str(discogs_data.get("catno") or ""),
            )
            if album_with_ref and album_with_ref != existing_album:
                self.album_var.set(album_with_ref)

            if not self.year_var.get().strip() and discogs_data.get("year"):
                self.year_var.set(str(discogs_data["year"]))
            if not self.label_var.get().strip() and discogs_data.get("label"):
                self.label_var.set(str(discogs_data["label"]))
            source = "Discogs"

        if not self.album_var.get().strip():
            bandcamp_album = lookup_bandcamp_album(title=title, artist=artist)
            if bandcamp_album:
                self.album_var.set(bandcamp_album)
                if not source:
                    source = "Bandcamp"

        if source:
            self.status_var.set(f"Metadata enriched from {source}.")
        else:
            messagebox.showwarning(
                "No enrichment found",
                "Could not retrieve extra metadata from Discogs/Bandcamp for this query.",
                parent=self.root,
            )
            self.status_var.set("No metadata enrichment found.")

    def select_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Select audio file",
            filetypes=[
                ("MP3 files", "*.mp3"),
                ("Audio files", "*.mp3 *.m4a *.aac *.wav *.flac"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return

        self.selected_file = path
        self.file_var.set(path)
        self.status_var.set("Local file selected.")

    def save_metadata(self) -> None:
        if not self.selected_file:
            self._show_error("Missing file", "Please choose a local file first.")
            return

        metadata = self._validate_metadata_inputs(require_album=True)
        if metadata is None:
            return

        title, artist, album = metadata
        year_text = self.year_var.get().strip()
        label_text = self.label_var.get().strip()
        genre_text = self.genre_var.get().strip()
        selected_tags = self._get_selected_tags()

        file_ext = Path(self.selected_file).suffix.lower()
        if file_ext != ".mp3":
            metadata_path = f"{self.selected_file}.metadata.json"
            save_sidecar_json(
                path=metadata_path,
                source_url=self.url_var.get().strip(),
                youtube_info=self.youtube_info,
                track_title=title,
                artist=artist,
                album=album,
                year=year_text,
                label=label_text,
                genre=genre_text,
                tags=selected_tags,
            )
            messagebox.showinfo(
                "Saved as JSON",
                "Selected file is not an MP3. Metadata was saved in a sidecar JSON file:\n"
                f"{metadata_path}",
                parent=self.root,
            )
            self.status_var.set("Metadata saved to sidecar JSON.")
            return

        write_metadata_to_mp3(
            self.selected_file,
            title,
            artist,
            album=album,
            year=year_text,
            label=label_text,
            genre=genre_text,
            track_tags=selected_tags,
        )
        self.status_var.set("Metadata saved to MP3 tags.")

    def download_and_add_to_rekordbox(self) -> None:
        if self._is_busy:
            return

        url = self.url_var.get().strip()
        if not url:
            self._show_error("Missing URL", "Please provide a YouTube URL.")
            return

        youtube_dir = self.youtube_dir_var.get().strip()
        if not youtube_dir:
            self._show_error("Missing folder", "Please choose a download folder.")
            return

        metadata = self._validate_metadata_inputs(require_album=False)
        if metadata is None:
            return

        worker = threading.Thread(
            target=self._download_and_add_worker,
            args=(url, youtube_dir, metadata),
            daemon=True,
        )
        self._set_busy(True, "Downloading and importing track...")
        worker.start()

    def _download_and_add_worker(
        self,
        url: str,
        youtube_dir: str,
        metadata: tuple[str, str, str],
    ) -> None:
        title, artist, album = metadata
        year_text = self.year_var.get().strip()
        label_text = self.label_var.get().strip()
        genre_text = self.genre_var.get().strip()
        selected_tags = self._get_selected_tags()

        clean_url = remove_playlist_param(url)
        os.makedirs(youtube_dir, exist_ok=True)
        started_at = time.time()

        try:
            downloaded = download_audio_as_mp3(clean_url, youtube_dir)
            downloaded_path = resolve_downloaded_path(
                downloaded_path=downloaded,
                title=title,
                youtube_title=self.video_title_var.get().strip(),
                youtube_dir=youtube_dir,
                started_at=started_at,
            )

            if not os.path.exists(downloaded_path):
                raise RuntimeError("Audio download did not return a valid local file path.")

            write_metadata_to_mp3(
                downloaded_path,
                title,
                artist,
                album=album,
                year=year_text,
                label=label_text,
                genre=genre_text,
                track_tags=selected_tags,
            )

            year = self._safe_int(year_text) or extract_year_from_youtube_info(self.youtube_info)

            with RekordboxDAO() as dao:
                track = dao.add_audio_file_as_track(downloaded_path)

            set_track_metadata_in_rekordbox(
                track_id=track.ID,
                title=title,
                artist=artist,
                album=album,
                label=label_text,
                year=year,
                genre=genre_text,
                tags=selected_tags,
            )

            with RekordboxDAO() as dao:
                actual_tags = dao.get_track_tags(track.ID)

            self.root.after(
                0,
                lambda: self._on_download_success(downloaded_path, actual_tags),
            )
        except Exception as exc:
            self.root.after(0, lambda: self._on_download_failure(str(exc)))

    def _on_download_success(self, downloaded_path: str, actual_tags: list[str]) -> None:
        self.selected_file = downloaded_path
        self.file_var.set(downloaded_path)
        self._set_selected_tags(actual_tags)
        self._set_busy(False, "Download/import completed successfully.")

        messagebox.showinfo(
            "Success",
            "Track downloaded and added to Rekordbox collection successfully.\n"
            f"Local file: {downloaded_path}",
            parent=self.root,
        )

    def _on_download_failure(self, details: str) -> None:
        self._set_busy(False, "Download/import failed.")
        self._show_error("Download or import failed", details)

    def _validate_metadata_inputs(self, require_album: bool = True) -> Optional[tuple[str, str, str]]:
        title = self.track_title_var.get().strip()
        artist = self.artist_var.get().strip()
        album = self.album_var.get().strip()

        if not title:
            self._show_error("Missing track title", "Track title is required.")
            return None
        if not artist:
            self._show_error("Missing artist", "Artist name is required.")
            return None
        if require_album and not album:
            self._show_error("Missing album", "Album name is required.")
            return None
        return title, artist, album

    def _get_selected_tags(self) -> list[str]:
        return [name for name, var in self.tag_vars.items() if var.get()]

    def _set_selected_tags(self, selected: list[str]) -> None:
        selected_set = set(selected)
        for name, var in self.tag_vars.items():
            var.set(name in selected_set)

    @staticmethod
    def _safe_int(value: str) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _show_error(self, title: str, message: str) -> None:
        messagebox.showerror(title, message, parent=self.root)
