import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def update_mp3_tags(
    file_path: str,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    album: Optional[str] = None,
) -> bool:
    """
    Write ID3 tags to an MP3 file using mutagen.

    Returns True on success, False if the file cannot be updated
    (wrong format, missing file, etc.).
    """
    try:
        from mutagen.easyid3 import EasyID3
        from mutagen.mp3 import MP3
        from mutagen.id3 import ID3NoHeaderError
    except ImportError:
        logger.error("mutagen is not installed; cannot update ID3 tags")
        return False

    path = Path(file_path)
    if not path.is_file():
        logger.warning("File not found, skipping tag update: %s", file_path)
        return False

    if path.suffix.lower() != ".mp3":
        logger.debug("Non-MP3 file, skipping tag update: %s", file_path)
        return False

    try:
        try:
            audio = MP3(file_path, ID3=EasyID3)
        except ID3NoHeaderError:
            audio = MP3(file_path)
            audio.add_tags()
            audio = MP3(file_path, ID3=EasyID3)

        if title is not None:
            audio["title"] = title
        if artist is not None:
            audio["artist"] = artist
        if album is not None:
            audio["album"] = album

        audio.save()
        logger.info("ID3 tags updated: %s", file_path)
        return True

    except Exception:
        logger.exception("Failed to update ID3 tags for: %s", file_path)
        return False
