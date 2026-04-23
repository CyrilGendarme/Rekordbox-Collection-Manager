from pathlib import Path
import os
import pyautogui

pyautogui.FAILSAFE = False
import re
import unicodedata
from config import (
    LOAD_TRACK_KEY,
    SWITCH_FOCUS_KEY,
    OPEN_SEARCH_TRACK_DIALOG,
    ADVANCE_ONE_MESURE,
    SET_CUE,
    SAVE_CUE_AS_MEMORY_CUE,
    ADVANCE_ONE_BEAT,
    PLAY_PAUSE_TRACK,
    LAYOUT_2_DECKS_HORIZONTAL,
)
from os_utils.rekordbox_process import focus_rekordbox_window
from data.repositories import RekordboxRepository
from utils import screenshot_and_show

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

    print(
        f"Sent key '{key}' to Rekordbox with delay_after={delay_after} and hold_time={hold_time}"
    )


def click_on_rekordbox(x, y, delay_after: int = 0.2):
    focus_rekordbox_window()
    pyautogui.click(x=x, y=y)
    pyautogui.sleep(delay_after)


def set_memory_cues():
    """
    Set memory cues at the start of each unique phrase in Rekordbox.
    Skips tracks with genre 'Sample' or 'Loop Samples'.
    Prints the track name when setting a cue.
    """
    send_key_to_rekordbox(SET_CUE, 0.1, 0.05)
    send_key_to_rekordbox(SAVE_CUE_AS_MEMORY_CUE, 0.1, 0.05)


def switch_focus():
    """
    Use UI automation to switch Rekordbox to the Collection tab.
    """
    send_key_to_rekordbox(SWITCH_FOCUS_KEY)
    pass


def load_tracks_from_collection(xml_path=None):
    """
    Load all tracks from the Rekordbox collection using the repository.
    If xml_path is None, use the default detection logic.
    Returns: List[Track]
    """
    repo = RekordboxRepository(custom_path=Path(xml_path) if xml_path else None)
    return repo.load_all_tracks()


def search_and_load_track(track_name):
    """
    Use UI automation to type and search for a specific track in Rekordbox's Collection tab.
    """

    def normalize_track_name(name: str) -> str:
        # Remove accents
        name = unicodedata.normalize("NFKD", name)
        name = name.encode("ASCII", "ignore").decode("utf-8")

        # Replace symbols/punctuation with space
        name = re.sub(r"[^\w\s]", " ", name, flags=re.UNICODE)

        # Collapse multiple spaces
        name = re.sub(r"\s+", " ", name).strip()

        return name

    track_name = normalize_track_name(track_name)

    send_key_to_rekordbox(OPEN_SEARCH_TRACK_DIALOG, 0.1, 0.1)

    for char in track_name:
        send_key_to_rekordbox(char)

    send_key_to_rekordbox(SWITCH_FOCUS_KEY, 1)
    send_key_to_rekordbox(LOAD_TRACK_KEY, delay_after=0.3, hold_time=0.1)


def ensure_search_is_cleared():
    """
    Ensure the search field in Rekordbox is cleared after loading a track.
    """
    send_key_to_rekordbox(OPEN_SEARCH_TRACK_DIALOG, 0.1, 0.1)
    send_key_to_rekordbox("backspace", 0.2)
    send_key_to_rekordbox(SWITCH_FOCUS_KEY, 0.2)


def advance_one_beat():
    """
    Use UI automation to move the playhead one beat forward in the track.
    """
    send_key_to_rekordbox(ADVANCE_ONE_BEAT, 0, 0.01)


def advance_one_measure():
    """
    Use UI automation to move the playhead one measure forward in the track.
    """
    send_key_to_rekordbox(ADVANCE_ONE_MESURE, 0, 0.01)


def ensure_2_decks_display():
    """
    Use UI automation to ensure that 2 decks are displayed in Rekordbox.
    """
    send_key_to_rekordbox(LAYOUT_2_DECKS_HORIZONTAL, 0.5, 0.01)


def switch_to_memory_cue_mode():
    """
    Use UI automation to switch Rekordbox deck to Memory Cue mode (last option in dropdown below track).
    """
    click_on_rekordbox(PADS_MODE_DROPDOWN[0], PADS_MODE_DROPDOWN[1], delay_after=0.2)
    click_on_rekordbox(
        MEMORY_CUES_DROPDOWN_OPTION[0], MEMORY_CUES_DROPDOWN_OPTION[1], delay_after=0.2
    )


def ensure_cue_on_beat():
    """
    Use UI automation to toggle play/pause in Rekordbox.
    """
    send_key_to_rekordbox(PLAY_PAUSE_TRACK, 0, 0.01)
    send_key_to_rekordbox(PLAY_PAUSE_TRACK, 0.5, 0.01)
    send_key_to_rekordbox(SET_CUE, 0.2, 0.1)


def click_top_menu_feature(feature_number: int):
    if feature_number == 1:
        click_on_rekordbox(TOP_MENU_FEATURE_1[0], TOP_MENU_FEATURE_1[1])
    elif feature_number == 2:
        click_on_rekordbox(TOP_MENU_FEATURE_2[0], TOP_MENU_FEATURE_2[1])
    elif feature_number == 3:
        click_on_rekordbox(TOP_MENU_FEATURE_3[0], TOP_MENU_FEATURE_3[1])
    elif feature_number == 4:
        click_on_rekordbox(TOP_MENU_FEATURE_4[0], TOP_MENU_FEATURE_4[1])
    elif feature_number == 5:
        click_on_rekordbox(TOP_MENU_FEATURE_5[0], TOP_MENU_FEATURE_5[1])
