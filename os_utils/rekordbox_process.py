"""
Handles OS-level interactions: process checking, launching applications, waiting for windows, etc.
"""

import subprocess
import time
import psutil
import pygetwindow as gw
import pyautogui
import win32gui
import win32con
from screeninfo import get_monitors

pyautogui.FAILSAFE = False
import os

from core.user_config import REKORDBOX_EXE_PATH

def _get_primary_monitor():
    for m in get_monitors():
        if m.is_primary:
            return m
    return get_monitors()[0]


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
            hwnd = win._hWnd
            win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
            win32gui.BringWindowToTop(hwnd)
            win32gui.SetForegroundWindow(hwnd)
        except Exception as e:
            raise Exception(f"Error focusing Rekordbox window: {e}")


def make_rekordbox_fullscreen_on_main_screen():
    rekordbox_win = _find_rekordbox_window(timeout=60)
    if not rekordbox_win:
        raise Exception("Rekordbox window not found or not ready.")

    try:
        monitor = _get_primary_monitor()

        # Step 1: restore (VERY important)
        rekordbox_win.restore()
        time.sleep(0.5)

        rekordbox_win.moveTo(monitor.x, monitor.y)
        time.sleep(0.5)
        rekordbox_win.maximize()
        hwnd = rekordbox_win._hWnd
        win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        time.sleep(0.2)
        win32gui.BringWindowToTop(hwnd)
        time.sleep(0.2)
        win32gui.SetForegroundWindow(hwnd)

        print("Rekordbox moved and maximized on main screen.")

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
