import xml.etree.ElementTree as ET
import os

CONFIG_XML_PATH = os.path.join(os.path.dirname(__file__), "user_config.xml")

DEFAULTS = {
    "NEXT_PHRASE_KEY": "]",
    "MEMORY_CUE_KEY": "m",
    "SWITCH_FOCUS_KEY": "tab",
    "LOAD_TRACK_KEY": "n",
    "SET_CUE": "-",
    "SAVE_CUE_AS_MEMORY_CUE": "f1",
    "ADVANCE_ONE_MESURE": "f2",
    "ADVANCE_ONE_BEAT": "f3",
    "OPEN_SEARCH_TRACK_DIALOG": "*",
    "PLAY_PAUSE_TRACK": "M",
    "LAYOUT_2_DECKS_HORIZONTAL": ")",
    "REKORDBOX_EXE_PATH": r"C:\Program Files\rekordbox\rekordbox 7.2.11\rekordbox.exe",
    "REKORDBOX_COLLECTION_TRACKS_XML_FILE_PATH": r"C:/Users/User/Desktop/musique/misc/rekordbox.xml",
}


def save_config(config_dict):
    root = ET.Element("config")
    for k, v in config_dict.items():
        child = ET.SubElement(root, k)
        child.text = str(v)
    tree = ET.ElementTree(root)
    tree.write(CONFIG_XML_PATH)


def load_config():
    if not os.path.exists(CONFIG_XML_PATH):
        return DEFAULTS.copy()
    tree = ET.parse(CONFIG_XML_PATH)
    root = tree.getroot()
    config = DEFAULTS.copy()
    for child in root:
        config[child.tag] = child.text
    return config
