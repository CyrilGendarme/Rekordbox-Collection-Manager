import cv2
import numpy as np
import pytesseract
import pyautogui

from utils import screenshot_and_show

pyautogui.FAILSAFE = False


START_OF_MESURE_REGION = (962, 129, 5, 15)  # x, y, w, h
PHRASE_REGION = (962, 113, 60, 12)  # x, y, w, h
TRACK_WAVEFORM_REGION = (0, 50, 1920, 80)  # x, y, w, h
MEMORY_CUES_CONTENT_REGION = (50, 365, 540, 90)  # x, y, w, h
FIST_TRACK_LINE_GENERIC_ZONE = (1250, 530, 5, 12)  # x, y, w, h


# START_OF_MESURE_REGION = (962, 139, 5, 15)  # x, y, w, h
# PHRASE_REGION = (962, 119, 60, 15)  # x, y, w, h
# TRACK_WAVEFORM_REGION = (0, 60, 1920, 80)  # x, y, w, h
# MEMORY_CUES_CONTENT_REGION = (50, 375, 540, 90)  # x, y, w, h

WHITE_PIXEL_BRIGHTNESS_THRESHOLD = 220
RED_MIN_VALUE_FOR_RED_PIXEL = 200
GREEN_BLUE_MAX_VALUE_FOR_RED_PIXEL = 80


def detect_start_of_mesure():
    # screenshot_and_show(START_OF_MESURE_REGION, "START_OF_MESURE_REGION")
    screenshot = pyautogui.screenshot(region=START_OF_MESURE_REGION)
    img_np = np.array(screenshot)

    # Check for red pixels: R > 200, G < 80, B < 80
    if (
        (img_np[..., 0] > RED_MIN_VALUE_FOR_RED_PIXEL).any()
        and (img_np[..., 1] < GREEN_BLUE_MAX_VALUE_FOR_RED_PIXEL).any()
        and (img_np[..., 2] < GREEN_BLUE_MAX_VALUE_FOR_RED_PIXEL).any()
    ):
        red_pixels = (
            (img_np[..., 0] > RED_MIN_VALUE_FOR_RED_PIXEL)
            & (img_np[..., 1] < GREEN_BLUE_MAX_VALUE_FOR_RED_PIXEL)
            & (img_np[..., 2] < GREEN_BLUE_MAX_VALUE_FOR_RED_PIXEL)
        )
        if np.any(red_pixels):
            return True
    return False

def detect_phrase():
    """
    Detect phrase changes by OCR on Rekordbox UI.
    Returns a list of (index, phrase_label) tuples.
    """
    # screenshot_and_show(PHRASE_REGION, "PHRASE_REGION")
    screenshot = pyautogui.screenshot(region=PHRASE_REGION)

    img_np = np.array(screenshot)

    # Convert to help OCR run quicker
    img_gray = cv2.cvtColor(img_np, cv2.COLOR_BGR2GRAY)
    _, img_thresh = cv2.threshold(img_gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    text_img_thresh = pytesseract.image_to_string(
        img_thresh,
        lang="eng",
        config="--psm 7 --oem 1 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
    )

    return text_img_thresh


def capture_track_waveform() -> np.ndarray:
    # screenshot_and_show(TRACK_WAVEFORM_REGION, title="TRACK_WAVEFORM_REGION")
    screenshot = pyautogui.screenshot(region=TRACK_WAVEFORM_REGION)
    return np.array(screenshot)


def detect_if_memory_cue_exists() -> bool:
    """
    Detect if a memory cue already exists at the current position by checking for the presence of the cue icon.
    Returns True if a cue is detected, False otherwise.
    """
    # screenshot_and_show(MEMORY_CUES_CONTENT_REGION, title="MEMORY_CUES_CONTENT_REGION")
    screenshot = pyautogui.screenshot(region=MEMORY_CUES_CONTENT_REGION)
    img = np.array(screenshot.convert("L"))

    # If any pixel is above the threshold, assume a memory cue is present
    if np.any(img > WHITE_PIXEL_BRIGHTNESS_THRESHOLD):
        print("Memory cue detected at current position.")
        return True
    return False
