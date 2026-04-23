import pyautogui
pyautogui.FAILSAFE = False
from PIL import ImageTk
import tkinter as tk

def screenshot_and_show(region=None, title="Screenshot Preview"):
    """
    Take a screenshot (optionally of a region), display it in a modal window, and wait for user to click OK.
    region: (left, top, width, height) or None for full screen
    """
    screenshot = pyautogui.screenshot(region=region)
    root = tk.Toplevel()
    root.title(title)
    root.attributes('-topmost', True)
    img = ImageTk.PhotoImage(screenshot)
    panel = tk.Label(root, image=img)
    panel.image = img  # Prevent garbage collection!
    panel.pack(padx=10, pady=10)
    ok_btn = tk.Button(root, text="OK", command=root.destroy)
    ok_btn.pack(pady=10)
    root.grab_set()  # Make modal
    root.wait_window()  # Wait until closed
    return screenshot
