import pyautogui

pyautogui.FAILSAFE = False
from os_utils.rekordbox_process import focus_rekordbox_window

PADS_MODE_DROPDOWN = (50, 465)  # x, y
MEMORY_CUES_DROPDOWN_OPTION = (50, 747)  # x, y

TOP_MENU_FEATURE_1 = (200, 54)  # x, y
TOP_MENU_FEATURE_2 = (237, 54)  # x, y
TOP_MENU_FEATURE_3 = (274, 54)  # x, y
TOP_MENU_FEATURE_4 = (311, 54)  # x, y
TOP_MENU_FEATURE_5 = (348, 54)  # x, y


def send_key_to_rekordbox(
    key, delay_after: float = 0, hold_time: float = 0, shall_refocus_on_rekordbox=False
):
    if shall_refocus_on_rekordbox:
        focus_rekordbox_window()

    if hold_time > 0:
        pyautogui.keyDown(key)
        pyautogui.sleep(hold_time)

        pyautogui.keyUp(key)
    else:
        pyautogui.press(key)

    pyautogui.sleep(delay_after)


def click_on_rekordbox(x, y, delay_after: int = 0.2):
    focus_rekordbox_window()
    pyautogui.click(x=x, y=y)
    pyautogui.sleep(delay_after)
