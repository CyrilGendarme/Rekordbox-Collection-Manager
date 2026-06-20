#!/usr/bin/env python3
"""Unified application entry point.

This file consolidates startup features previously split between `main.py`
and the old root `app.py`.
"""

import logging
import os
import sys
import threading
from tkinter import messagebox

from src.app_controller import AppController
from src.utils import rekordbox_process


def setup_logging() -> None:
    """Configure application logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler("your_sets.log", encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def close_app() -> None:
    os._exit(0)


def _listen_for_ctrl_c() -> None:
    """Optional global hotkey listener to force-close the app."""
    try:
        import keyboard  # Imported lazily because this dependency is optional.
    except Exception:
        logging.getLogger(__name__).warning(
            "Global hotkey disabled: package 'keyboard' is not available."
        )
        return

    keyboard.add_hotkey("ctrl+c", close_app)
    keyboard.wait()


def _bootstrap_rekordbox() -> bool:
    """Ensure Rekordbox is running and focused before launching the GUI."""
    if not rekordbox_process.is_rekordbox_running():
        rekordbox_process.launch_rekordbox()
        if not rekordbox_process.wait_for_rekordbox():
            messagebox.showerror("Error", "Failed to launch Rekordbox.")
            return False

    rekordbox_process.make_rekordbox_fullscreen_on_main_screen()
    rekordbox_process.focus_rekordbox_window()
    return True


def main() -> None:
    """Main application entry point."""
    try:
        setup_logging()
        logger = logging.getLogger(__name__)
        logger.info("Starting application")

        # Enable these features by environment variable when needed.
        enable_hotkey = os.getenv("APP_ENABLE_CTRL_C_HOTKEY", "0") == "1"
        ensure_rekordbox = os.getenv("APP_ENSURE_REKORDBOX", "0") == "1"

        if enable_hotkey:
            threading.Thread(target=_listen_for_ctrl_c, daemon=True).start()

        if ensure_rekordbox and not _bootstrap_rekordbox():
            sys.exit(1)

        controller = AppController.get_instance()
        controller.run()

    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Application terminated by user")
    except Exception as exc:
        logging.getLogger(__name__).exception("Fatal error: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
