from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List

from src.core.ripped_records_to_tracks.rtt.pipeline import SplitOutput, split_audio_file
from src.core.ripped_records_to_tracks.rtt.segmentation import SegmentationConfig
from src.gui.tab_system import FeatureContext, TabFeature


class RippedRecordsToTracksFeature(TabFeature):
    """Feature tab for splitting long ripped recordings into individual tracks."""

    name = "ripped_records_to_tracks"

    def __init__(self):
        self.input_path = tk.StringVar()
        self.input_files: List[Path] = []
        self.output_dir = tk.StringVar(value=str(Path.cwd() / "output_tracks"))
        self.status_var = tk.StringVar(value="Select one or more audio files to start.")

        self.min_track = tk.DoubleVar(value=40.0)
        self.silence_db = tk.DoubleVar(value=-36.0)
        self.silence_min = tk.DoubleVar(value=2.0)
        self.music_low_hz = tk.DoubleVar(value=200.0)
        self.music_high_hz = tk.DoubleVar(value=400.0)
        self.trim_silence_db = tk.DoubleVar(value=-52.0)
        self.input_trim_min_active_s = tk.DoubleVar(value=0.10)

        self.root: tk.Tk | None = None
        self.tree: ttk.Treeview | None = None

    def build_main_tab(self, context: FeatureContext):
        self.root = context.root

        main_frame = ttk.Frame(context.notebook)
        context.notebook.add(main_frame, text="Ripped Records")
        self._create_widgets(main_frame)
        return main_frame

    def _create_widgets(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        wrapper = ttk.Frame(parent, padding=14)
        wrapper.grid(row=0, column=0, sticky="nsew")
        wrapper.columnconfigure(0, weight=1)
        wrapper.rowconfigure(2, weight=1)

        title = ttk.Label(
            wrapper,
            text="Ripped Records to Tracks",
            font=("Segoe UI", 14, "bold"),
        )
        title.grid(row=0, column=0, sticky="w", pady=(0, 8))

        picker = ttk.LabelFrame(wrapper, text="Audio and Output", padding=12)
        picker.grid(row=1, column=0, sticky="ew", pady=(0, 10))

        self._path_row(
            picker,
            "Input audio",
            self.input_path,
            self._pick_input,
            "Choose Files",
            0,
        )
        self._path_row(
            picker,
            "Output folder",
            self.output_dir,
            self._pick_output,
            "Choose Folder",
            1,
        )

        body = ttk.Frame(wrapper)
        body.grid(row=2, column=0, sticky="nsew")
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        controls = ttk.LabelFrame(body, text="Segmentation Rules", padding=12)
        controls.grid(row=0, column=0, sticky="ns", padx=(0, 10))

        self._slider(controls, "Min track length (s)", self.min_track, 10.0, 240.0, 0)
        self._slider(controls, "Silence threshold (dB)", self.silence_db, -70.0, -10.0, 1)
        self._slider(controls, "Min silence window (s)", self.silence_min, 0.2, 6.0, 2)
        self._slider(controls, "Music low freq (Hz)", self.music_low_hz, 20.0, 1000.0, 3)
        self._slider(controls, "Music high freq (Hz)", self.music_high_hz, 100.0, 5000.0, 4)
        self._slider(
            controls,
            "Trim start/end silence (dB)",
            self.trim_silence_db,
            -80.0,
            -20.0,
            5,
        )
        self._slider(
            controls,
            "Ignore non-silence shorter than (s)",
            self.input_trim_min_active_s,
            0.02,
            0.50,
            6,
        )

        run_btn = ttk.Button(
            controls,
            text="Split Into Tracks",
            style="Accent.TButton",
            command=self._start_split,
        )
        run_btn.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(14, 4))

        self.open_btn = ttk.Button(
            controls,
            text="Open Output Folder",
            command=self._open_output_dir,
        )
        self.open_btn.grid(row=8, column=0, columnspan=2, sticky="ew")

        result = ttk.LabelFrame(body, text="Detected Timeline", padding=10)
        result.grid(row=0, column=1, sticky="nsew")
        result.columnconfigure(0, weight=1)
        result.rowconfigure(0, weight=1)

        columns = ("source", "track", "meta", "start", "end", "duration")
        self.tree = ttk.Treeview(result, columns=columns, show="headings", height=20)
        self.tree.heading("source", text="Source File")
        self.tree.heading("track", text="#")
        self.tree.heading("meta", text="Artist - Track - Album - Record Ref")
        self.tree.heading("start", text="Start (s)")
        self.tree.heading("end", text="End (s)")
        self.tree.heading("duration", text="Duration (s)")

        self.tree.column("source", width=220, anchor="w")
        self.tree.column("track", width=40, anchor="center")
        self.tree.column("meta", width=360, anchor="w")
        self.tree.column("start", width=80, anchor="e")
        self.tree.column("end", width=80, anchor="e")
        self.tree.column("duration", width=90, anchor="e")
        self.tree.grid(row=0, column=0, sticky="nsew")

        status = ttk.Label(wrapper, textvariable=self.status_var, font=("Consolas", 10))
        status.grid(row=3, column=0, sticky="w", pady=(10, 0))

    def _path_row(
        self,
        parent: ttk.LabelFrame,
        label: str,
        var: tk.StringVar,
        callback,
        button_text: str,
        row: int,
    ) -> None:
        ttk.Label(parent, text=label).grid(
            row=row,
            column=0,
            sticky="w",
            padx=(0, 8),
            pady=4,
        )
        entry = ttk.Entry(parent, textvariable=var, width=92)
        entry.grid(row=row, column=1, sticky="ew", pady=4)
        btn = ttk.Button(parent, text=button_text, command=callback)
        btn.grid(row=row, column=2, padx=(8, 0), pady=4)
        parent.columnconfigure(1, weight=1)

    def _slider(
        self,
        parent: ttk.LabelFrame,
        label: str,
        var: tk.DoubleVar,
        frm: float,
        to: float,
        row: int,
    ) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w")
        scale = ttk.Scale(parent, variable=var, from_=frm, to=to)
        scale.grid(row=row, column=1, sticky="ew", padx=(10, 0), pady=4)
        parent.columnconfigure(1, weight=1)

    def _pick_input(self) -> None:
        selected = filedialog.askopenfilenames(
            title="Select audio files",
            filetypes=[
                ("Audio", "*.mp3 *.wav *.flac *.ogg *.m4a"),
                ("All files", "*.*"),
            ],
        )
        if selected:
            self.input_files = [Path(path) for path in selected]
            if len(self.input_files) == 1:
                self.input_path.set(str(self.input_files[0]))
            else:
                self.input_path.set(f"{len(self.input_files)} files selected")

    def _pick_output(self) -> None:
        selected = filedialog.askdirectory(title="Select output folder")
        if selected:
            self.output_dir.set(selected)

    def _open_output_dir(self) -> None:
        path = Path(self.output_dir.get())
        if path.exists():
            os.startfile(path)
        else:
            messagebox.showwarning(
                "Missing folder",
                "Output folder does not exist yet.",
                parent=self.root,
            )

    def _start_split(self) -> None:
        output_folder = Path(self.output_dir.get())

        if not self.input_files:
            messagebox.showerror(
                "Input missing",
                "Please choose one or more valid input audio files.",
                parent=self.root,
            )
            return

        missing = [path for path in self.input_files if not path.exists()]
        if missing:
            messagebox.showerror(
                "Input missing",
                f"Some selected files are missing.\nFirst missing: {missing[0]}",
                parent=self.root,
            )
            return

        self.status_var.set(
            f"Analyzing {len(self.input_files)} file(s)... this can take a while for long recordings."
        )

        worker = threading.Thread(
            target=self._run_split,
            args=(list(self.input_files), output_folder),
            daemon=True,
        )
        worker.start()

    def _run_split(self, input_files: List[Path], output_folder: Path) -> None:
        try:
            cfg = SegmentationConfig(
                min_track_len_s=float(self.min_track.get()),
                silence_db_threshold=float(self.silence_db.get()),
                silence_min_len_s=float(self.silence_min.get()),
                music_low_hz=float(self.music_low_hz.get()),
                music_high_hz=float(self.music_high_hz.get()),
                trim_silence_db_threshold=float(self.trim_silence_db.get()),
                input_trim_min_active_s=float(self.input_trim_min_active_s.get()),
            )

            results: List[tuple[Path, SplitOutput]] = []
            for idx, input_file in enumerate(input_files, start=1):
                if self.root is not None:
                    self.root.after(
                        0,
                        lambda i=idx, n=len(input_files), p=input_file: self.status_var.set(
                            f"[{i}/{n}] Splitting {p.name}..."
                        ),
                    )

                result = split_audio_file(
                    file_path=input_file,
                    output_dir=output_folder,
                    cfg=cfg,
                )
                results.append((input_file, result))

            if not results:
                if self.root is not None:
                    self.root.after(0, lambda: self.status_var.set("No files processed."))
                return

            total_tracks = sum(
                max(0, len(r.segmentation.boundaries_s) - 1) for _, r in results
            )

            if self.root is not None:
                self.root.after(0, lambda: self._render_results(results))
                self.root.after(
                    0,
                    lambda: self.status_var.set(
                        f"Done. Processed {len(results)} file(s), created {total_tracks} tracks total."
                    ),
                )
                self.root.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Split complete",
                        (
                            f"Processed {len(results)} file(s).\n"
                            f"Total tracks exported: {total_tracks}\n\n"
                            f"Output folder: {output_folder}"
                        ),
                        parent=self.root,
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            if self.root is not None:
                self.root.after(
                    0,
                    lambda: messagebox.showerror("Split failed", str(exc), parent=self.root),
                )
                self.root.after(
                    0,
                    lambda: self.status_var.set("Split failed. Adjust parameters and retry."),
                )

    def _render_results(self, results: List[tuple[Path, SplitOutput]]) -> None:
        if self.tree is None:
            return

        for item in self.tree.get_children():
            self.tree.delete(item)

        total_tracks = 0
        for input_file, result in results:
            boundaries = result.segmentation.boundaries_s
            for idx in range(len(boundaries) - 1):
                start_s = boundaries[idx]
                end_s = boundaries[idx + 1]
                meta = result.track_metadata[idx] if idx < len(result.track_metadata) else None
                artist = meta.artist if meta and meta.artist else "?"
                title = meta.title if meta and meta.title else f"Track {idx + 1:02d}"
                album = meta.album if meta and meta.album else "?"
                record_ref = meta.record_ref if meta and meta.record_ref else "?"
                meta_text = f"{artist} - {title} - {album} - {record_ref}"

                self.tree.insert(
                    "",
                    "end",
                    values=(
                        input_file.name,
                        idx + 1,
                        meta_text,
                        f"{start_s:.2f}",
                        f"{end_s:.2f}",
                        f"{(end_s - start_s):.2f}",
                    ),
                )
                total_tracks += 1

        self.status_var.set(f"Done. Created {total_tracks} tracks.")
