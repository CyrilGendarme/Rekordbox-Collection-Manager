from __future__ import annotations

import importlib
import logging
import threading
from pathlib import Path

import numpy as np
import tkinter as tk
from tkinter import ttk

from src.core.to_33rpm.io_audio import read_audio

logger = logging.getLogger(__name__)


class AudioPreviewPlayer:
    def __init__(self, parent: ttk.Widget, title: str = "Preview player") -> None:
        self.root = parent.winfo_toplevel()
        self.frame = ttk.LabelFrame(parent, text=title)

        self.play_btn: ttk.Button | None = None
        self.stop_btn: ttk.Button | None = None
        self.seek_scale: ttk.Scale | None = None
        self.time_var = tk.StringVar(value="00:00 / 00:00")
        self.status_var = tk.StringVar(value="No audio loaded.")

        self._sd = None
        self._backend_available = False
        self._player_audio: np.ndarray | None = None
        self._player_sample_rate = 0
        self._player_total_frames = 0
        self._player_frame_pos = 0
        self._player_duration_seconds = 0.0
        self._player_stream = None
        self._player_after_id: str | None = None
        self._is_dragging_seek = False
        self._player_state_lock = threading.Lock()
        self._loaded_path = ""

        self._init_backend()
        self._build_widgets()

    def _build_widgets(self) -> None:
        self.frame.columnconfigure(0, weight=1)

        controls = ttk.Frame(self.frame)
        controls.grid(row=0, column=0, sticky="ew")
        controls.columnconfigure(0, weight=1)
        controls.columnconfigure(1, weight=1)

        self.play_btn = ttk.Button(
            controls,
            text="Play",
            command=self.play_selected,
        )
        self.play_btn.grid(row=0, column=0, sticky="w")

        self.stop_btn = ttk.Button(controls, text="Stop", command=self.stop)
        self.stop_btn.grid(row=0, column=1, sticky="w", padx=(8, 0))

        self.seek_scale = ttk.Scale(self.frame, from_=0, to=100, orient=tk.HORIZONTAL)
        self.seek_scale.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.seek_scale.bind("<ButtonPress-1>", self._on_seek_press)
        self.seek_scale.bind("<ButtonRelease-1>", self._on_seek_release)

        ttk.Label(
            self.frame,
            textvariable=self.time_var,
            style="Dim.TLabel",
            anchor="e",
        ).grid(row=2, column=0, sticky="e", pady=(4, 0))

        ttk.Label(
            self.frame,
            textvariable=self.status_var,
            style="Dim.TLabel",
            anchor="w",
        ).grid(row=3, column=0, sticky="ew", pady=(4, 0))

    def _init_backend(self) -> None:
        try:
            self._sd = importlib.import_module("sounddevice")
            self._backend_available = True
        except Exception:
            self._sd = None
            self._backend_available = False
            self.status_var.set("Preview backend unavailable; install sounddevice.")

    def load_audio(self, file_path: str | Path) -> bool:
        source_path = Path(file_path)
        try:
            audio, meta = read_audio(source_path)
        except Exception:
            logger.exception("Failed to read preview audio: %s", source_path)
            self.status_var.set(f"Failed to load preview audio: {source_path.name}")
            return False

        if audio.size == 0:
            self.status_var.set("Audio file is empty.")
            return False

        work = np.asarray(audio, dtype=np.float32)
        if work.ndim == 1:
            work = np.expand_dims(work, axis=1)

        self.stop()
        self._player_audio = work
        self._player_sample_rate = int(meta.sample_rate)
        self._player_total_frames = int(work.shape[0])
        self._player_duration_seconds = (
            float(self._player_total_frames) / float(self._player_sample_rate)
            if self._player_sample_rate > 0
            else 0.0
        )
        self._player_frame_pos = 0
        self._loaded_path = str(source_path)

        self._set_seek_position(0.0)
        self._update_time_label(0.0)
        self.status_var.set(f"Loaded: {source_path.name}")
        return True

    def play_selected(self) -> None:
        self.play(0.0)

    def play(self, start_seconds: float = 0.0) -> None:
        if not self._backend_available or self._sd is None:
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
        self.status_var.set(
            f"Playing: {Path(self._loaded_path).name if self._loaded_path else 'preview'}"
        )
        self._start_player_clock()

    def stop(self) -> None:
        self._stop_preview_stream()
        self._stop_player_clock()
        self._player_frame_pos = 0
        self._set_seek_position(0.0)
        self._update_time_label(0.0)
        if self._loaded_path:
            self.status_var.set(f"Loaded: {Path(self._loaded_path).name}")
        else:
            self.status_var.set("No audio loaded.")

    def seek_to(self, target_seconds: float) -> None:
        if self._player_audio is None or self._player_sample_rate <= 0:
            return

        target_frame = int(round(max(0.0, target_seconds) * self._player_sample_rate))
        target_frame = max(0, min(target_frame, self._player_total_frames))
        with self._player_state_lock:
            self._player_frame_pos = target_frame

    def _set_seek_position(self, seconds: float) -> None:
        if self.seek_scale is None:
            return

        max_seconds = max(1.0, self._player_duration_seconds)
        clamped = max(0.0, min(seconds, max_seconds))
        self.seek_scale.configure(to=max_seconds)
        self.seek_scale.set(clamped)

    def _update_time_label(self, current_seconds: float) -> None:
        current = self._format_timestamp(current_seconds)
        total = self._format_timestamp(self._player_duration_seconds)
        self.time_var.set(f"{current} / {total}")

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        safe = max(0, int(round(seconds)))
        mins = safe // 60
        secs = safe % 60
        return f"{mins:02d}:{secs:02d}"

    def _start_player_clock(self) -> None:
        self._stop_player_clock()

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
                self._update_time_label(current)

            if self._is_preview_stream_active():
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
        if self.seek_scale is None:
            return

        target = float(self.seek_scale.get())
        self.seek_to(target)

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