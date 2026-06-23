from __future__ import annotations

import os
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List

from src.core.samples_magnifier.audio import (
    normalize_audio_peak,
    read_audiosegment,
    truncate_silence,
    write_audiosegment,
)
from src.gui.tab_system import FeatureContext, TabFeature
from src.services.audio_metadata_service import copy_mp3_metadata
from src.user_config import settings


class SamplesMagnifierFeature(TabFeature):
    """Feature tab for normalizing/trimming sample files and exporting them."""

    name = "samples_magnifier"

    def __init__(self):
        self.input_path = tk.StringVar()
        self.input_files: List[Path] = []
        self.output_dir = tk.StringVar(value=str(Path.cwd() / "samples_magnified"))
        self.status_var = tk.StringVar(value="Select one or more audio files to start.")

        self.root: tk.Tk | None = None
        self.tree: ttk.Treeview | None = None
        self.run_btn: ttk.Button | None = None
        self._is_running = False

    def build_main_tab(self, context: FeatureContext):
        self.root = context.root

        main_frame = ttk.Frame(context.notebook)
        context.notebook.add(main_frame, text="Samples Magnifier")
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
            text="Samples Magnifier",
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

        controls = ttk.LabelFrame(body, text="Processing", padding=12)
        controls.grid(row=0, column=0, sticky="ns", padx=(0, 10))

        ttk.Label(
            controls,
            text=(
                "Normalize each file to -1.0 dB peak\n"
                "and trim surrounding silence using configured thresholds."
            ),
            justify="left",
        ).grid(row=0, column=0, sticky="w", pady=(0, 12))

        self.run_btn = ttk.Button(
            controls,
            text="Process Samples",
            style="Accent.TButton",
            command=self._start_processing,
        )
        self.run_btn.grid(row=1, column=0, sticky="ew", pady=(0, 6))

        open_btn = ttk.Button(
            controls,
            text="Open Output Folder",
            command=self._open_output_dir,
        )
        open_btn.grid(row=2, column=0, sticky="ew")

        result = ttk.LabelFrame(body, text="Processing Results", padding=10)
        result.grid(row=0, column=1, sticky="nsew")
        result.columnconfigure(0, weight=1)
        result.rowconfigure(0, weight=1)

        columns = ("source", "export", "status")
        self.tree = ttk.Treeview(result, columns=columns, show="headings", height=20)
        self.tree.heading("source", text="Source File")
        self.tree.heading("export", text="Exported File")
        self.tree.heading("status", text="Status")

        self.tree.column("source", width=260, anchor="w")
        self.tree.column("export", width=280, anchor="w")
        self.tree.column("status", width=120, anchor="center")
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

    def _pick_input(self) -> None:
        selected = filedialog.askopenfilenames(
            title="Select audio files",
            filetypes=[
                ("Audio", "*.mp3 *.wav *.flac *.ogg *.m4a *.aac"),
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

    def _start_processing(self) -> None:
        if self._is_running:
            return

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

        self.status_var.set(f"Processing {len(self.input_files)} file(s)...")
        self._set_running(True)
        worker = threading.Thread(
            target=self._run_processing,
            args=(list(self.input_files), output_folder),
            daemon=True,
        )
        worker.start()

    def _run_processing(self, input_files: List[Path], output_folder: Path) -> None:
        try:
            output_folder.mkdir(parents=True, exist_ok=True)

            processed: list[tuple[str, str, str]] = []
            exported_count = 0
            skipped_count = 0

            for idx, input_file in enumerate(input_files, start=1):
                if self.root is not None:
                    self.root.after(
                        0,
                        lambda i=idx, n=len(input_files), p=input_file: self.status_var.set(
                            f"[{i}/{n}] Processing {p.name}..."
                        ),
                    )

                if input_file.suffix.lower() not in settings.AUDIO_FILES_EXTENSIOINS:
                    processed.append((input_file.name, "-", "unsupported"))
                    skipped_count += 1
                    continue

                target_ext = f".{settings.AUDIO_EXPORT_FORMAT.lower()}"
                new_file_name = input_file.stem.split("__")[-1]
                output_file = output_folder / f"{new_file_name}{target_ext}"

                if output_file.exists():
                    processed.append((input_file.name, output_file.name, "skipped (exists)"))
                    skipped_count += 1
                    continue

                audio = read_audiosegment(str(input_file))
                normalized_audio = normalize_audio_peak(audio, target_peak_db=-1.0)
                truncated_audio = truncate_silence(
                    normalized_audio,
                    silence_threshold=settings.TRUNCATE_SILENCE_TRESHOLD,
                    chunk_size=settings.TRUNCATE_SILENCE_CHUNK_SIZE,
                )
                write_audiosegment(
                    audio=truncated_audio,
                    output_path=str(output_file),
                    format=settings.AUDIO_EXPORT_FORMAT,
                    source_path=str(input_file),
                )

                if (
                    input_file.suffix.lower() == ".mp3"
                    and output_file.suffix.lower() == ".mp3"
                ):
                    copy_mp3_metadata(
                        source_path=str(input_file),
                        target_path=str(output_file),
                    )

                processed.append((input_file.name, output_file.name, "exported"))
                exported_count += 1

            if self.root is not None:
                self.root.after(0, lambda: self._render_results(processed))
                self.root.after(
                    0,
                    lambda: self.status_var.set(
                        f"Done. Exported {exported_count} file(s), skipped {skipped_count}."
                    ),
                )
                self.root.after(
                    0,
                    lambda: messagebox.showinfo(
                        "Samples processing complete",
                        (
                            f"Input files: {len(input_files)}\n"
                            f"Exported: {exported_count}\n"
                            f"Skipped: {skipped_count}\n\n"
                            f"Output folder: {output_folder}"
                        ),
                        parent=self.root,
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            if self.root is not None:
                self.root.after(
                    0,
                    lambda: messagebox.showerror(
                        "Samples processing failed",
                        str(exc),
                        parent=self.root,
                    ),
                )
                self.root.after(
                    0,
                    lambda: self.status_var.set(
                        "Processing failed. Check inputs and settings, then retry."
                    ),
                )
        finally:
            if self.root is not None:
                self.root.after(0, lambda: self._set_running(False))

    def _set_running(self, is_running: bool) -> None:
        self._is_running = is_running
        if self.run_btn is not None:
            self.run_btn.configure(state="disabled" if is_running else "normal")

    def _render_results(self, rows: list[tuple[str, str, str]]) -> None:
        if self.tree is None:
            return
        for item in self.tree.get_children():
            self.tree.delete(item)
        for source, exported, status in rows:
            self.tree.insert("", "end", values=(source, exported, status))
