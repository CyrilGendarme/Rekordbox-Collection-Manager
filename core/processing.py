from pathlib import Path
import tkinter as tk
from tkinter import messagebox, simpledialog
from core import actions, user_config, detection
from data.repositories import RekordboxRepository
import numpy as np
import os
import re
import string
import time

from config import REKORDBOX_COLLECTION_TRACKS_XML_FILE_PATH


def load_tracks():
    repo = RekordboxRepository(
        custom_path=Path(REKORDBOX_COLLECTION_TRACKS_XML_FILE_PATH)
    )
    tracks = repo.load_all_tracks()
    tracks.reverse() # TODO : to be removed, For dev purposes
    return list(
        filter(
            lambda track: (
                not re.search(r"Sample", str(track.genre), re.IGNORECASE)
                and track.genre != "Loop Samples"
                and track.genre != "Sample"
                and track.genre != "Religious"
                and track.genre != "Traditional"
                and track.genre != "Reggae"
                and not any(
                    pm.get("Num") == "-1" for pm in getattr(track, "position_marks", [])
                )
            ),
            tracks,
        )
    )


def process_loaded_track():

    last_text = None
    last_track_waveform = None

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

    def has_to_set_cue(text, last_text):
        print(
            f"Checking if cue should be set for text '{text}' with last_text '{last_text}'"
        )

        if text == "INTRO" and last_text != "INTRO":
            return True

        if text == "UP" and last_text != "UP":
            return True

        if text == "CHORUS" and last_text != "CHORUS":
            return True

        if (
            text == "VERSE"
            and last_text != "VERSE"
            and last_text != "CHORUS"
            and last_text != "UP"
        ):
            return True

        if text == "BRIDGE" and last_text != "BRIDGE" and last_text != "UP":
            return True

        return False

    def are_img_np_same(img1_np, img2_np, rgb_threshold=0.1, pixel_threshold=0.1):
        # Compare average RGB
        avg1 = img1_np.mean(axis=(0, 1))
        avg2 = img2_np.mean(axis=(0, 1))
        rgb_delta = np.abs(avg1 - avg2).sum()
        # Compare pixel-wise difference
        pixel_delta = np.abs(img1_np.astype(np.int16) - img2_np.astype(np.int16)).mean()
        return rgb_delta < rgb_threshold and pixel_delta < pixel_threshold

    def detect_phrase_and_set_cue_if_needed():
        nonlocal last_text
        (_, text_rgb) = detection.detect_phrase()
        trimmed_text = "".join(
            c for c in text_rgb if not c.isdigit() and c not in string.punctuation
        ).strip()
        print(f"Detected last_text: '{text_rgb} (trimmed: {trimmed_text})")

        if any(
            re.search(pattern, trimmed_text, re.IGNORECASE)
            for pattern in possible_texts
        ):
            if has_to_set_cue(trimmed_text, last_text):
                print(f"----- Setting memory cue -----")
                actions.set_memory_cues()
            last_text = trimmed_text

    if detection.detect_if_memory_cue_exists():
        print(f"Memory cue already exists for the loaded track. Skipping.")
        return

    # Once at start for intro
    actions.ensure_cue_on_beat()
    detect_phrase_and_set_cue_if_needed()

    # Advance one beat until on a measure start
    while True: 
        actions.advance_one_beat()
        if detection.detect_start_of_mesure():
            print("Start of measure detected.")
            break

    while True:
        detect_phrase_and_set_cue_if_needed()

        actions.advance_one_measure()
        track_waveform = detection.capture_track_waveform()

        if last_track_waveform is not None and are_img_np_same(
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

    actions.switch_to_memory_cue_mode()

    actions.search_and_load_track(track_name)
    actions.switch_focus()

    process_loaded_track()


def process_track_per_track_gui(root):
    filtered_tracks = load_tracks()

    actions.ensure_search_is_cleared()
    actions.switch_to_memory_cue_mode()

    for track in filtered_tracks:
        actions.search_and_load_track(track.name)
        actions.switch_focus()
        process_loaded_track()
        messagebox.showinfo("Done", f"Memory cues set for {track.name}.", parent=root)


def process_all_tracks_gui(root):
    filtered_tracks = load_tracks()

    actions.ensure_search_is_cleared()
    actions.switch_to_memory_cue_mode()
    time.sleep(2)

    print(f"Total tracks to process: {len(filtered_tracks)}")

    for track in filtered_tracks:
        print(f"--- Processing track: {track.name}")
        actions.search_and_load_track(track.name)
        time.sleep(0.5)
        actions.switch_focus()
        time.sleep(0.2)
        process_loaded_track()

    messagebox.showinfo(
        "Done", f"Memory cues set for {len(filtered_tracks)} tracks.", parent=root
    )


def setup_config_tab(config_frame):
    config_vars = {}
    config = user_config.load_config()

    def save_config():
        for key, var in config_vars.items():
            config[key] = var.get()
        user_config.save_config(config)
        messagebox.showinfo(
            "Config Saved", "Configuration saved successfully.", parent=config_frame
        )

    row = 0
    for key, default in user_config.DEFAULTS.items():
        tk.Label(config_frame, text=key).grid(
            row=row, column=0, sticky="e", padx=10, pady=5
        )
        var = tk.StringVar(value=config.get(key, default))
        entry = tk.Entry(config_frame, textvariable=var, width=40)
        entry.grid(row=row, column=1, padx=10, pady=5)
        config_vars[key] = var
        row += 1
    save_btn = tk.Button(config_frame, text="Save Configuration", command=save_config)
    save_btn.grid(row=row, column=0, columnspan=2, pady=15)
