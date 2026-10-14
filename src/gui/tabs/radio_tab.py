from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from src.core.radio_sync import SyncResult, VpsTarget, sync_to_vps
from src.gui.tab_system import FeatureContext, TabFeature
from src.user_config import persist_setting, settings


class RadioFeature(TabFeature):
    """Push tracks whose genre matches a regex (default "33") to the radio VPS."""

    name = "radio"

    # (setting key, label)
    _FIELDS = (
        ("RADIO_LOCAL_DIR", "Local music folder"),
        ("RADIO_VPS_HOST", "VPS host (user@host)"),
        ("RADIO_VPS_PORT", "SSH port"),
        ("RADIO_VPS_REMOTE_DIR", "Remote folder"),
        ("RADIO_VPS_SSH_KEY", "SSH key (optional)"),
        ("RADIO_GENRE_REGEX", "Genre regex"),
    )

    def __init__(self):
        self.root: tk.Tk | None = None
        self.vars = {key: tk.StringVar(value=str(getattr(settings, key))) for key, _ in self._FIELDS}
        self.status_var = tk.StringVar(value="Configure the VPS, then push tracks.")
        self.sync_metadata_var = tk.BooleanVar(value=True)
        self.log: tk.Text | None = None
        self._buttons: list[ttk.Button] = []

    def build_main_tab(self, context: FeatureContext) -> Optional[ttk.Frame]:
        self.root = context.root
        main_frame = ttk.Frame(context.notebook)
        context.notebook.add(main_frame, text="Radio")
        self._create_widgets(main_frame)
        return main_frame

    def _create_widgets(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)

        form = ttk.LabelFrame(parent, text="VPS Sync", padding=10)
        form.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        form.columnconfigure(1, weight=1)

        for row, (key, label) in enumerate(self._FIELDS):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(form, textvariable=self.vars[key]).grid(
                row=row, column=1, sticky="ew", padx=(8, 8), pady=3
            )
        ttk.Button(form, text="Choose Folder", command=self._choose_local_dir).grid(
            row=0, column=2, sticky="e"
        )

        actions = ttk.Frame(parent)
        actions.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 6))

        push_btn = ttk.Button(
            actions,
            text="Push matching tracks to VPS",
            style="Accent.TButton",
            command=lambda: self._start_sync(dry_run=False),
        )
        push_btn.pack(side=tk.LEFT)
        dry_btn = ttk.Button(
            actions,
            text="Dry run (list only)",
            command=lambda: self._start_sync(dry_run=True),
        )
        dry_btn.pack(side=tk.LEFT, padx=(8, 0))
        ttk.Checkbutton(
            actions,
            text="Complete metadata of files already on VPS",
            variable=self.sync_metadata_var,
        ).pack(side=tk.LEFT, padx=(16, 0))
        self._buttons = [push_btn, dry_btn]

        log_frame = ttk.LabelFrame(parent, text="Log", padding=8)
        log_frame.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 6))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log = tk.Text(log_frame, height=20, wrap="none", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient=tk.VERTICAL, command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

        ttk.Label(parent, textvariable=self.status_var, style="Dim.TLabel").grid(
            row=3, column=0, sticky="w", padx=10, pady=(0, 8)
        )

    def _choose_local_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.vars["RADIO_LOCAL_DIR"].get() or None)
        if selected:
            self.vars["RADIO_LOCAL_DIR"].set(selected)

    def _append_log(self, message: str) -> None:
        if self.log is None:
            return
        self.log.configure(state="normal")
        self.log.insert(tk.END, message + "\n")
        self.log.see(tk.END)
        self.log.configure(state="disabled")
        self.status_var.set(message)

    def _report(self, message: str) -> None:
        """Thread-safe progress callback."""
        self.root.after(0, lambda: self._append_log(message))

    def _set_running(self, running: bool) -> None:
        for button in self._buttons:
            button.configure(state="disabled" if running else "normal")

    def _start_sync(self, dry_run: bool) -> None:
        values = {key: var.get().strip() for key, var in self.vars.items()}
        if not values["RADIO_LOCAL_DIR"] or not values["RADIO_VPS_HOST"]:
            messagebox.showwarning("Radio", "Local folder and VPS host are required.")
            return
        try:
            port = int(values["RADIO_VPS_PORT"] or 22)
        except ValueError:
            messagebox.showwarning("Radio", "SSH port must be a number.")
            return

        for key, value in values.items():
            if str(getattr(settings, key)) != value:
                persist_setting(key, port if key == "RADIO_VPS_PORT" else value)

        target = VpsTarget(
            host=values["RADIO_VPS_HOST"],
            remote_dir=values["RADIO_VPS_REMOTE_DIR"] or "radio_music",
            port=port,
            ssh_key=values["RADIO_VPS_SSH_KEY"],
        )
        self._set_running(True)
        threading.Thread(
            target=self._sync_worker,
            args=(
                Path(values["RADIO_LOCAL_DIR"]),
                target,
                values["RADIO_GENRE_REGEX"] or "33",
                dry_run,
                self.sync_metadata_var.get(),
            ),
            daemon=True,
        ).start()

    def _sync_worker(
        self, local_dir: Path, target: VpsTarget, pattern: str, dry_run: bool, sync_metadata: bool
    ) -> None:
        try:
            result = sync_to_vps(
                local_dir,
                target,
                pattern,
                dry_run=dry_run,
                progress=self._report,
                sync_metadata=sync_metadata,
            )
            self.root.after(0, lambda: self._on_sync_done(result, dry_run))
        except Exception as exc:
            self.root.after(0, lambda error=str(exc): self._on_sync_failed(error))

    def _on_sync_done(self, result: SyncResult, dry_run: bool) -> None:
        self._set_running(False)
        if dry_run:
            for relative in result.pushed:
                self._append_log(f"would push: {relative}")
            self._append_log(
                f"Dry run: {len(result.pushed)} to push, {result.skipped} already on VPS."
            )
        for relative, error in result.failed:
            self._append_log(f"FAILED: {relative}: {error}")
        for relative, error in result.metadata_failed:
            self._append_log(f"METADATA FAILED: {relative}: {error}")

    def _on_sync_failed(self, error: str) -> None:
        self._set_running(False)
        self._append_log(f"ERROR: {error}")
        messagebox.showerror("Radio", error)
