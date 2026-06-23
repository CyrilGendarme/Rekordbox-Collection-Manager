



import logging
from pathlib import Path
from typing import Optional

from src.data import RekordboxDAO
from src.services.audio_metadata_service import write_audio_metadata

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
    path = Path(file_path)
    if not path.is_file():
        logger.warning("File not found, skipping tag update: %s", file_path)
        return False

    if path.suffix.lower() != ".mp3":
        logger.debug("Non-MP3 file, skipping tag update: %s", file_path)
        return False

    ok = write_audio_metadata(
        file_path=file_path,
        title=title,
        artist=artist,
        album=album,
    )
    if ok:
        logger.info("ID3 tags updated: %s", file_path)
    return ok



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