



import logging
from pathlib import Path
from typing import Optional

from src.data import RekordboxDAO

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



def update_track_rekordbox_metadata(tracks: list,updates: list, set_status_callback: Optional[callable] = None):
    """Push edited metadata for every track to the Rekordbox SQLCipher database
    and write ID3 tags to the physical MP3 files."""
    try:
        dao = RekordboxDAO()

        # Build a quick lookup from track_id -> Track for file-path access
        track_by_id = {str(t.id): t for t in tracks}

        failed = []
        tag_failures = []
        for track_id, name, artist, album in updates:
            success = dao.update_track_metadata(
                track_id,
                title=name or None,
                artist=artist or None,
                album=album or None,
            )
            if not success:
                failed.append(track_id)
                continue

            # Update ID3 tags on the physical file
            track = track_by_id.get(str(track_id))
            if track and track.file_path:
                ok = update_mp3_tags(
                    track.file_path,
                    title=name or None,
                    artist=artist or None,
                    album=album or None,
                )
                if not ok:
                    tag_failures.append(track_id)

        updated = len(updates) - len(failed)
        if not failed and not tag_failures:
            set_status_callback(f"{updated} track(s) updated successfully.")
        elif tag_failures and not failed:
            set_status_callback(
                f"{updated} updated; {len(tag_failures)} ID3 tag write(s) skipped."
            )
        else:
            set_status_callback(f"{updated} updated, {len(failed)} failed.")
    except Exception as exc:
        if set_status_callback:
            set_status_callback(f"Error during batch validate: {exc}")