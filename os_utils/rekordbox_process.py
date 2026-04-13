"""
Handles OS-level interactions: process checking, launching applications, waiting for windows, etc.
"""

import subprocess
import time
import psutil
import pygetwindow as gw
import pyautogui

pyautogui.FAILSAFE = False
import os

from config import REKORDBOX_EXE_PATH


def _find_rekordbox_window(timeout=0):
    """
    Find the main Rekordbox window, optionally waiting up to timeout seconds.
    Returns the window object or None if not found.
    """
    poll_interval = 1
    waited = 0
    while waited <= timeout:
        windows = gw.getWindowsWithTitle("rekordbox")
        for win in windows:
            title = win.title.lower()
            if "vscode" not in title and (
                title == "rekordbox" or title.startswith("rekordbox - ")
            ):
                if win.visible and win.width > 400 and win.height > 300:
                    return win
        if timeout == 0:
            break
        time.sleep(poll_interval)
        waited += poll_interval
    return None


def focus_rekordbox_window():
    """
    Brings the Rekordbox window to the foreground and ensures it is focused.
    Returns True if successful, False otherwise.
    """
    win = _find_rekordbox_window()
    if win:
        try:
            win.activate()
        except Exception as e:
            raise Exception(f"Error focusing Rekordbox window: {e}")


def make_rekordbox_fullscreen_on_main_screen():
    """
    Finds the Rekordbox window and makes it full screen on the main screen (monitor 0).
    Handles multi-monitor setups.
    """
    rekordbox_win = _find_rekordbox_window(timeout=60)
    if not rekordbox_win:
        raise Exception("Rekordbox window not found or not ready.")
    try:
        rekordbox_win.moveTo(0, 0)
        screen_w, screen_h = pyautogui.size()
        rekordbox_win.resizeTo(screen_w, screen_h)
        rekordbox_win.activate()
        print("Rekordbox window maximized on main screen.")
    except Exception as e:
        raise Exception(f"Error maximizing Rekordbox window: {e}")


def is_rekordbox_running():
    """Check if rekordbox.exe is running."""
    for proc in psutil.process_iter(["name"]):
        if (
            proc.info["name"]
            and "rekordbox" in proc.info["name"].lower()
            and not "code" in proc.info["name"].lower() # For dev in VS Code
        ):
            return True
    return False


def launch_rekordbox():
    """Launch rekordbox if not running."""
    if not os.path.exists(REKORDBOX_EXE_PATH):
        raise FileNotFoundError(f"Rekordbox not found at {REKORDBOX_EXE_PATH}")
    subprocess.Popen([REKORDBOX_EXE_PATH])


def wait_for_rekordbox(timeout=60):
    """Wait until rekordbox is running or timeout (seconds)."""
    start = time.time()
    while time.time() - start < timeout:
        if is_rekordbox_running():
            return True
        time.sleep(1)
    return False
