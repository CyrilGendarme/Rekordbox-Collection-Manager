
import logging
from pathlib import Path
from typing import Optional

from src.data import RekordboxDAO
from src.services.audio_metadata_service import write_audio_metadata

logger = logging.getLogger(__name__)


def update_local_audio_tags(
    file_path: str,
    title: Optional[str] = None,
    artist: Optional[str] = None,
    album: Optional[str] = None,
    year: Optional[int] = None,
    label: Optional[str] = None,
    genre: Optional[str] = None,
    bpm: Optional[float] = None,
) -> bool:
    """
    Write metadata to a local audio file using mutagen.

    Returns True on success, False if the file cannot be updated
    (wrong format, missing file, etc.).
    """
    path = Path(file_path)
    if not path.is_file():
        logger.warning("File not found, skipping tag update: %s", file_path)
        return False

    ok = write_audio_metadata(
        file_path=file_path,
        title=title,
        artist=artist,
        album=album,
        year=year,
        label=label,
        genre=genre,
        bpm=bpm,
    )
    if ok:
        logger.info("Audio metadata updated: %s", file_path)
    return ok


def update_track_rekordbox_metadata(
    tracks: list,
    updates: list,
    set_status_callback: Optional[callable] = None,
) -> None:
    """Push edited metadata to Rekordbox and write tags to local audio files.

    Covers are not handled here: Complete Tracks Info embeds them directly
    into the local audio files.
    """
    track_by_id = {str(t.id): t for t in tracks}

    failed = []
    tag_failures = []
    updated = 0
    dao_error = ""
    try:
        with RekordboxDAO() as dao:
            for track_id, name, artist, album, year, label, genre, bpm in updates:
                success = dao.update_track_metadata(
                    track_id,
                    title=name or None,
                    artist=artist or None,
                    album=album or None,
                    year=year,
                    label=label or None,
                    genre=genre or None,
                    bpm=bpm,
                )
                if not success:
                    failed.append(track_id)
                    continue
                updated += 1

                track = track_by_id.get(str(track_id))
                if track and track.file_path:
                    ok = update_local_audio_tags(
                        track.file_path,
                        title=name or None,
                        artist=artist or None,
                        album=album or None,
                        year=year,
                        label=label or None,
                        genre=genre or None,
                        bpm=bpm,
                    )
                    if not ok:
                        tag_failures.append(track_id)
    except Exception as exc:
        logger.exception("Failed to update Rekordbox during batch validate")
        dao_error = str(exc)

    if set_status_callback is not None:
        if dao_error:
            status = f"Rekordbox update failed: {dao_error}."
        elif not updates:
            status = "No metadata changes submitted."
        elif tag_failures and failed:
            status = (
                f"{updated} updated, {len(failed)} failed; "
                f"{len(tag_failures)} audio metadata write(s) failed."
            )
        elif tag_failures:
            status = (
                f"{updated} updated; "
                f"{len(tag_failures)} audio metadata write(s) failed."
            )
        elif failed:
            status = f"{updated} updated, {len(failed)} failed."
        else:
            status = f"{updated} track(s) updated successfully."

        set_status_callback(status)
