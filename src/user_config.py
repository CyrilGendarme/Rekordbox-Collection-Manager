from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):  
    NEXT_PHRASE_KEY: str = "]"
    MEMORY_CUE_KEY: str = "m"
    SWITCH_FOCUS_KEY: str = "tab"
    LOAD_TRACK_KEY: str = "n"
    NEXT_TRACK_IN_COLLECTION_KEY: str = "down"
    PREVIOUS_TRACK_IN_COLLECTION_KEY: str = "up"
    SET_CUE: str = "-"
    SAVE_CUE_AS_MEMORY_CUE: str = "f1"
    ADVANCE_ONE_MESURE: str = "f2"
    ADVANCE_ONE_BEAT: str = "f3"
    OPEN_SEARCH_TRACK_DIALOG: str = "*"
    PLAY_PAUSE_TRACK: str = "M"
    LAYOUT_2_DECKS_HORIZONTAL: str = ")"
    REKORDBOX_EXE_PATH: str = r"C:\Program Files\rekordbox\rekordbox 7.2.14\rekordbox.exe"
    REKORDBOX_COLLECTION_TRACKS_XML_FILE_PATH: str = r"C:/Users\User\Professional DJ team Dropbox\Cyril Gendarme\rekordbox\xml\rekordbox.xml"

    # Value retrieve from .env file
    DISCOGS_TOKEN: str = ""

settings = Settings()
