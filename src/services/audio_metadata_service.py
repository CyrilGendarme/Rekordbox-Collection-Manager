from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def write_audio_metadata(
    file_path: str | Path,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    record_ref: str | None = None,
) -> bool:
    """Write common metadata tags to MP3 or WAV files using mutagen."""
    path = Path(file_path)
    if not path.is_file():
        logger.warning("File not found, skipping metadata update: %s", path)
        return False

    suffix = path.suffix.lower()
    if suffix not in {".mp3", ".wav"}:
        logger.debug("Unsupported file format for metadata update: %s", path)
        return False

    try:
        from mutagen.id3 import ID3, TALB, TIT2, TPE1, TXXX
        from mutagen.mp3 import MP3
        from mutagen.wave import WAVE
    except ImportError:
        logger.error("mutagen is not installed; cannot update audio metadata")
        return False

    try:
        if suffix == ".mp3":
            audio_file = MP3(str(path))
            if audio_file.tags is None:
                audio_file.tags = ID3()
        else:
            audio_file = WAVE(str(path))
            if audio_file.tags is None:
                audio_file.add_tags()

        if title is not None:
            audio_file.tags["TIT2"] = TIT2(encoding=3, text=[title])
        if artist is not None:
            audio_file.tags["TPE1"] = TPE1(encoding=3, text=[artist])
        if album is not None:
            audio_file.tags["TALB"] = TALB(encoding=3, text=[album])
        if record_ref is not None:
            audio_file.tags["TXXX:record_ref"] = TXXX(
                encoding=3,
                desc="record_ref",
                text=[record_ref],
            )

        audio_file.save()
        return True
    except Exception:
        logger.exception("Failed to update audio metadata for: %s", path)
        return False



def copy_mp3_metadata(source_path: str, target_path: str) -> bool:
    """
    Copy all ID3 metadata frames from source MP3 to target MP3.

    This includes common text tags and advanced frames such as artwork,
    comments, lyrics, custom TXXX/WXXX fields, etc.
    """
    try:
        from mutagen.id3 import ID3, ID3NoHeaderError
    except ImportError:
        logger.error("mutagen is not installed; cannot copy MP3 metadata")
        return False

    src = Path(source_path)
    dst = Path(target_path)

    if not src.is_file():
        logger.warning("Source file not found, skipping metadata copy: %s", source_path)
        return False

    if not dst.is_file():
        logger.warning("Target file not found, skipping metadata copy: %s", target_path)
        return False

    if src.suffix.lower() != ".mp3" or dst.suffix.lower() != ".mp3":
        logger.debug(
            "Metadata copy skipped because files are not both MP3: %s -> %s",
            source_path,
            target_path,
        )
        return False

    try:
        source_id3 = ID3(source_path)
    except ID3NoHeaderError:
        logger.info("Source MP3 has no ID3 metadata, nothing to copy: %s", source_path)
        return True
    except Exception:
        logger.exception("Failed to read source metadata: %s", source_path)
        return False

    try:
        try:
            target_id3 = ID3(target_path)
            target_id3.clear()
        except ID3NoHeaderError:
            target_id3 = ID3()

        for frame in source_id3.values():
            target_id3.add(frame)

        target_id3.save(target_path, v2_version=3)
        logger.info("Copied MP3 metadata: %s -> %s", source_path, target_path)
        return True
    except Exception:
        logger.exception("Failed to copy MP3 metadata: %s -> %s", source_path, target_path)
        return False