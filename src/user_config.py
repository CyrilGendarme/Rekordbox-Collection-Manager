from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

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
    REKORDBOX_EXE_PATH: str = r"C:\Program Files\rekordbox\rekordbox 7.2.16\rekordbox.exe"
    REKORDBOX_COLLECTION_TRACKS_XML_FILE_PATH: str = r"C:/Users\User\Professional DJ team Dropbox\Cyril Gendarme\rekordbox\xml\rekordbox.xml"

    # Value retrieve from .env file
    DISCOGS_TOKEN: str = ""

    # vars specific to samples magnifier
    DURATION_BETWEEN_TTS_CHUNKS: int = 200  # Duration between each TTS chunk in millseconds
    DURATION_BETWEEN_TTS_SEGMENT: int = 35  # in milliseconds
    DURATION_BETWEEN_MAIN_SEQUENCES: int = 800  # ex: time between Web page and captions
    SAMPLES_FOLDER: str = "C:\\Users\\User\\Desktop\\musique\\records rip\\tracks"
    MODIFIED_SAMPLES_FOLDER: str = "C:\\Users\\User\\Desktop\\temp\\Nouveau dossier"
    AUDIO_FILES_EXTENSIOINS: tuple[str, ...] = (".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac")
    TRUNCATE_SILENCE_TRESHOLD: float = -35.0  # in dBFS
    TRUNCATE_SILENCE_CHUNK_SIZE: int = 10  # in ms
    AUDIO_EXPORT_FORMAT: str = "mp3"
    TO_33RPM_OUTPUT_DIR: str = str(Path.cwd() / "to_33rpm_outputs")


settings = Settings()


def _serialize_env_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def persist_setting(key: str, value: Any) -> None:
    """Persist a setting to in-memory settings and local .env file."""
    setattr(settings, key, value)

    env_path = Path.cwd() / ".env"
    new_line = f"{key}={_serialize_env_value(value)}"

    lines: list[str] = []
    replaced = False

    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        for idx, line in enumerate(lines):
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if stripped.startswith(f"{key}="):
                lines[idx] = new_line
                replaced = True
                break

    if not replaced:
        lines.append(new_line)

    env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
