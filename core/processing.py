from pathlib import Path
from tkinter import messagebox, simpledialog
from core import actions, detection
import numpy as np
import re
import string
from data import RekordboxDAO
from pyrekordbox.db6.database import DjmdContent

from core.user_config import REKORDBOX_COLLECTION_TRACKS_XML_FILE_PATH
from os_utils.rekordbox_process import focus_rekordbox_window

dao = RekordboxDAO()


def common_actions():
    focus_rekordbox_window()

    actions.ensure_2_decks_display()

    if detection.is_fx_active():
        actions.click_top_menu_feature(1)
    if detection.is_mix_point_link_active():
        actions.click_top_menu_feature(2)
    if detection.is_sampler_active():
        actions.click_top_menu_feature(3)
    if detection.is_mixer_active():
        actions.click_top_menu_feature(4)
    if detection.is_recording_active():
        actions.click_top_menu_feature(5)

    actions.switch_to_memory_cue_mode()
    actions.ensure_search_is_cleared()


def process_loaded_track():

    last_text = None
    last_track_waveform = None
    last_img_np_with_phrase_change = None

    possible_texts = (
        "INTRO",
        "VERSE",
        "BRIDGE",
        "CHORUS",
        "DROP",
        "UP",
        "BREAK",
        "OUTRO",
        "DOWN",
    )

    def _has_to_set_cue(text, last_text):
        if text.startswith("INTRO") and last_text != "INTRO":
            return True

        if text.startswith("UP") and last_text != "UP":
            return True

        if text.startswith("CHORUS") and last_text != "CHORUS":
            return True

        if (
            text.startswith("VERSE")
            and last_text != "VERSE"
            and last_text != "CHORUS"
            and last_text != "UP"
        ):
            return True

        if text.startswith("BRIDGE") and last_text != "BRIDGE" and last_text != "UP":
            return True

        return False

    def _get_imgs_np_rgb_delta(img_np_1, img_np_2) -> float:
        avg1 = img_np_1.mean(axis=(0, 1))
        avg2 = img_np_2.mean(axis=(0, 1))
        return np.abs(avg1 - avg2).sum()

    def _are_img_np_same(img1_np, img2_np, rgb_threshold=0.1, pixel_threshold=0.1):
        # Compare average RGB
        rgb_delta = _get_imgs_np_rgb_delta(img1_np, img2_np)
        # Compare pixel-wise difference
        pixel_delta = np.abs(img1_np.astype(np.int16) - img2_np.astype(np.int16)).mean()
        return rgb_delta < rgb_threshold and pixel_delta < pixel_threshold

    def _detect_phrase_and_set_cue_if_needed():
        nonlocal last_text, last_img_np_with_phrase_change

        for _ in range(4):
            img_np, raw_text = detection.detect_phrase()

            if (
                last_img_np_with_phrase_change is not None
                and _get_imgs_np_rgb_delta(img_np, last_img_np_with_phrase_change) < 10
            ):
                return False

            last_img_np_with_phrase_change = img_np

            trimmed_text = "".join(
                c for c in raw_text if not c.isdigit() and c not in string.punctuation
            ).strip()

            if any(
                re.search(pattern, trimmed_text, re.IGNORECASE)
                for pattern in possible_texts
            ):
                if _has_to_set_cue(trimmed_text, last_text):
                    actions.set_memory_cues()

                last_text = trimmed_text
                return True

            # Shall just be noise
            if len(trimmed_text) <= 2:
                return False

        return False

    if detection.detect_if_memory_cue_exists():
        print(f"Memory cue already exists for the loaded track. Skipping.")
        return

    was_on_phrase_start = _detect_phrase_and_set_cue_if_needed()

    # Once at start for intro
    if not was_on_phrase_start:
        actions.ensure_cue_on_beat()

    # Advance one beat until on a measure start
    start_of_mesure_detected = False
    for _ in range(10):
        actions.advance_one_beat()
        if detection.detect_start_of_mesure():
            start_of_mesure_detected = True
            break

    if not start_of_mesure_detected:
        print("Failed to detect start of measure after advancing one beat 4 times...")
        return

    while True:
        _detect_phrase_and_set_cue_if_needed()

        actions.advance_one_measure()
        track_waveform = detection.capture_track_waveform()

        if last_track_waveform is not None and _are_img_np_same(
            track_waveform, last_track_waveform
        ):
            print("End of track.")
            break

        last_track_waveform = track_waveform


def process_specific_track_gui(root):
    track_name = simpledialog.askstring(
        "Track Name", "Enter the track name:", parent=root
    )
    if not track_name:
        messagebox.showwarning("Input required", "Track name is required.", parent=root)
        return

    focus_rekordbox_window()
    actions.search_and_load_track(track_name)
    actions.switch_focus()

    process_loaded_track()


def is_valid_tracks_without_memory_cues(track: DjmdContent):
    if track.GenreName in {
        # if track.Genre.Name in {
        # if track.Genre.Name in {
        "Loop Samples",
        "Sample",
        "Religious",
        "Traditional",
    }:
        return False

    # only apply this when requested
    if any(c.Kind == 0 for c in getattr(track, "Cues", [])):
        return False

    return True


def process_track_per_track_gui(root):
    filtered_tracks = dao.get_tracks(is_valid=is_valid_tracks_without_memory_cues)

    focus_rekordbox_window()

    for track in filtered_tracks:
        actions.search_and_load_track(track.name)
        actions.switch_focus()
        process_loaded_track()
        messagebox.showinfo("Done", f"Memory cues set for {track.name}.", parent=root)


def process_all_tracks_gui(root):
    filtered_tracks = dao.get_tracks(is_valid=is_valid_tracks_without_memory_cues)

    focus_rekordbox_window()

    import random

    random.shuffle(filtered_tracks)

    for track in filtered_tracks:

        print(f"Processing track: {track.name}")

        actions.search_and_load_track(track.name)
        actions.go_to_top_of_collection()

        for _ in range(5):
            actions.switch_focus()
            process_loaded_track()
            actions.switch_focus()
            print("----- will now load next track in collection -----")
            actions.next_track_in_collection()
            print("----- has loaded next track -----")

    messagebox.showwarning("Done", "Memory cues set for all tracks", parent=root)


def remove_memory_cues_if_less_than_two():

    def is_valid(track: DjmdContent):
        cues = [c for c in getattr(track, "Cues", []) if c.Kind == 0]
        if len(cues) > 3 or len(cues) == 0:
            return False

        return True

    tracks = dao.get_tracks(is_valid=is_valid)

    for track in tracks:
        """Remove all memory cues from a track, leaving hot cues intact."""

        original_cues = getattr(track, "Cues", [])
        if not original_cues:
            continue

        remaining_cues = [cue for cue in original_cues if getattr(cue, "Kind", 0) != 0]
        to_be_removed = [cue for cue in original_cues if getattr(cue, "Kind", 0) == 0]

        track.Cues = remaining_cues

        for cue in to_be_removed:
            dao.db.delete(cue)

    dao.db.commit()


def remove_1_1_bars_cues_from_all_tracks():

    def is_valid(track: DjmdContent):
        if any(
            getattr(c, "Comment", "") == "1.1Bars" for c in getattr(track, "Cues", [])
        ):
            return True
        return False

    tracks = dao.get_tracks(is_valid=is_valid)

    for track in tracks:

        original_cues = getattr(track, "Cues", [])
        if not original_cues:
            continue

        remaining_cues = [
            cue for cue in original_cues if getattr(cue, "Comment", "") != "1.1Bars"
        ]
        to_be_removed = [
            cue for cue in original_cues if getattr(cue, "Comment", "") == "1.1Bars"
        ]

        track.Cues = remaining_cues

        for cue in to_be_removed:
            dao.db.delete(cue)

    dao.db.commit()
