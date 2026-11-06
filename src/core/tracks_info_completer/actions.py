
import logging
from pathlib import Path
from typing import Optional

from src.data import RekordboxDAO
from src.services.audio_metadata_service import (
    embed_cover_art,
    has_embedded_cover,
    write_audio_metadata,
)

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
    covers: Optional[dict] = None,
) -> set[str]:
    """Push edited metadata to Rekordbox and write tags to local audio files.

    `covers` maps track id -> image bytes. Covers are embedded in audio files
    independently of Rekordbox, and added to Rekordbox where it has no artwork.
    Returns the IDs whose audio files have an embedded cover after processing.
    """
    track_by_id = {str(t.id): t for t in tracks}
    covers = covers or {}
    audio_cover_ids: set[str] = set()
    audio_cover_failures: list[str] = []

    for track_id, image_bytes in covers.items():
        track = track_by_id.get(str(track_id))
        if track is None or not image_bytes:
            audio_cover_failures.append(str(track_id))
            continue

        if not track.file_path or not Path(track.file_path).is_file():
            logger.warning(
                "Cannot embed cover for track_id=%s: audio file is missing: %s",
                track_id,
                track.file_path,
            )
            audio_cover_failures.append(str(track_id))
            continue

        if has_embedded_cover(track.file_path):
            audio_cover_ids.add(str(track_id))
        elif embed_cover_art(track.file_path, image_bytes) and has_embedded_cover(
            track.file_path
        ):
            audio_cover_ids.add(str(track_id))
        else:
            logger.error(
                "Could not verify embedded cover for track_id=%s at %s",
                track_id,
                track.file_path,
            )
            audio_cover_failures.append(str(track_id))

    failed = []
    tag_failures = []
    updated = 0
    rekordbox_cover_count = 0
    rekordbox_cover_failures = 0
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

            for track_id, image_bytes in covers.items():
                track = track_by_id.get(str(track_id))
                if track is None or not image_bytes or track.image_path:
                    continue
                if dao.set_track_artwork(track_id, image_bytes):
                    rekordbox_cover_count += 1
                else:
                    rekordbox_cover_failures += 1
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

        if covers:
            status += (
                f" Audio covers embedded: {len(audio_cover_ids)}/{len(covers)}."
            )
            if audio_cover_failures:
                status += f" Audio cover failures: {len(audio_cover_failures)}."
            if rekordbox_cover_count or rekordbox_cover_failures:
                status += f" Rekordbox artwork updated: {rekordbox_cover_count}."
                if rekordbox_cover_failures:
                    status += (
                        f" Rekordbox artwork failures: {rekordbox_cover_failures}."
                    )
        set_status_callback(status)

    return audio_cover_ids