"""
Entry point for Rekordbox Phrase Cue Setter app.
"""

from gui.app import main
from os_utils import rekordbox_process
from tkinter import messagebox
import threading
import keyboard
import os


def close_app():
    os._exit(0)


def listen_for_ctrl_c():
    keyboard.add_hotkey("ctrl+c", close_app)
    keyboard.wait()  # Keep the thread alive to listen for hotkeys


if __name__ == "__main__":

    # Start global hotkey listener in a background thread
    threading.Thread(target=listen_for_ctrl_c, daemon=True).start()

    if not rekordbox_process.is_rekordbox_running():
        rekordbox_process.launch_rekordbox()
        if not rekordbox_process.wait_for_rekordbox():
            messagebox.showerror("Error", "Failed to launch Rekordbox.")
            exit(1)

    rekordbox_process.make_rekordbox_fullscreen_on_main_screen()
    rekordbox_process.focus_rekordbox_window()

    main()
