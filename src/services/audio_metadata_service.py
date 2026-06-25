from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import logging
from pathlib import Path

from src.services.bandcamp_service import lookup_bandcamp_album
from src.services.discogs_service import lookup_discogs_metadata

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CompletedMetadata:
    title: str
    artist: str
    album: str = ""
    year: int | None = None
    label: str = ""
    source: str = ""


def write_metadata_to_mp3(
    file_path: str,
    title: str,
    artist: str,
    album: str = "",
    year: str = "",
    label: str = "",
    genre: str = "",
    track_tags: list[str] | None = None,
) -> None:
    """Write YouTube-import metadata to an MP3 using EasyID3."""
    try:
        from mutagen.easyid3 import EasyID3
    except ImportError as exc:
        raise RuntimeError("mutagen is not installed") from exc

    try:
        id3_tags = EasyID3(file_path)
    except Exception:
        id3_tags = EasyID3()

    id3_tags["title"] = title
    id3_tags["artist"] = artist
    if album:
        id3_tags["album"] = album
    if year:
        id3_tags["date"] = year
    if label:
        id3_tags["organization"] = label
    if genre:
        id3_tags["genre"] = genre
    if track_tags:
        id3_tags["grouping"] = ", ".join(track_tags)
    id3_tags.save(file_path)


@lru_cache(maxsize=256)
def complete_track_metadata(
    title: str, artist: str, album: str = ""
) -> CompletedMetadata:
    normalized_title = (title or "").strip()
    normalized_artist = (artist or "").strip()
    normalized_album = (album or "").strip()

    if not normalized_title or not normalized_artist:
        return CompletedMetadata(
            title=normalized_title,
            artist=normalized_artist,
            album=normalized_album,
        )

    discogs_data = lookup_discogs_metadata(
        title=normalized_title,
        artist=normalized_artist,
        album=normalized_album,
    )
    if discogs_data:
        album_candidate = normalized_album or str(discogs_data.get("album") or "")
        return CompletedMetadata(
            title=normalized_title,
            artist=normalized_artist,
            album=append_album_ref(
                album_candidate,
                str(discogs_data.get("catno") or ""),
            ),
            year=_coerce_year(discogs_data.get("year")),
            label=str(discogs_data.get("label") or "").strip(),
            source="Discogs",
        )

    if not normalized_album:
        bandcamp_album = lookup_bandcamp_album(
            title=normalized_title,
            artist=normalized_artist,
        )
        if bandcamp_album:
            return CompletedMetadata(
                title=normalized_title,
                artist=normalized_artist,
                album=bandcamp_album.strip(),
                source="Bandcamp",
            )

    return CompletedMetadata(
        title=normalized_title,
        artist=normalized_artist,
        album=normalized_album,
    )


def write_audio_metadata(
    file_path: str | Path,
    title: str | None = None,
    artist: str | None = None,
    album: str | None = None,
    record_ref: str | None = None,
    year: int | str | None = None,
    label: str | None = None,
    genre: str | None = None,
    bpm: float | int | str | None = None,
) -> bool:
    """Write common metadata tags to common audio formats using mutagen."""
    path = Path(file_path)
    if not path.is_file():
        logger.warning("File not found, skipping metadata update: %s", path)
        return False

    suffix = path.suffix.lower()
    if suffix not in {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".mp4"}:
        logger.debug("Unsupported file format for metadata update: %s", path)
        return False

    try:
        from mutagen.id3 import ID3, TALB, TBPM, TCON, TDRC, TIT2, TPE1, TPUB, TXXX
        from mutagen.flac import FLAC
        from mutagen.mp4 import MP4, MP4FreeForm
        from mutagen.mp3 import MP3
        from mutagen.oggvorbis import OggVorbis
        from mutagen.wave import WAVE
    except ImportError:
        logger.error("mutagen is not installed; cannot update audio metadata")
        return False

    try:
        if suffix in {".mp3", ".wav"}:
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
            if year not in (None, ""):
                audio_file.tags["TDRC"] = TDRC(encoding=3, text=[str(year)])
            if label is not None:
                audio_file.tags["TPUB"] = TPUB(encoding=3, text=[label])
            if genre is not None:
                audio_file.tags["TCON"] = TCON(encoding=3, text=[genre])
            if bpm not in (None, ""):
                audio_file.tags["TBPM"] = TBPM(encoding=3, text=[str(bpm)])
            if record_ref is not None:
                audio_file.tags["TXXX:record_ref"] = TXXX(
                    encoding=3,
                    desc="record_ref",
                    text=[record_ref],
                )

            audio_file.save()
            return True

        if suffix == ".flac":
            audio_file = FLAC(str(path))
            if title is not None:
                audio_file["title"] = [title]
            if artist is not None:
                audio_file["artist"] = [artist]
            if album is not None:
                audio_file["album"] = [album]
            if year not in (None, ""):
                audio_file["date"] = [str(year)]
            if label is not None:
                audio_file["label"] = [label]
            if genre is not None:
                audio_file["genre"] = [genre]
            if bpm not in (None, ""):
                audio_file["bpm"] = [str(bpm)]
            if record_ref is not None:
                audio_file["record_ref"] = [record_ref]
            audio_file.save()
            return True

        if suffix == ".ogg":
            audio_file = OggVorbis(str(path))
            if title is not None:
                audio_file["title"] = [title]
            if artist is not None:
                audio_file["artist"] = [artist]
            if album is not None:
                audio_file["album"] = [album]
            if year not in (None, ""):
                audio_file["date"] = [str(year)]
            if label is not None:
                audio_file["label"] = [label]
            if genre is not None:
                audio_file["genre"] = [genre]
            if bpm not in (None, ""):
                audio_file["bpm"] = [str(bpm)]
            if record_ref is not None:
                audio_file["record_ref"] = [record_ref]
            audio_file.save()
            return True

        if suffix in {".m4a", ".mp4"}:
            audio_file = MP4(str(path))
            if title is not None:
                audio_file["\xa9nam"] = [title]
            if artist is not None:
                audio_file["\xa9ART"] = [artist]
            if album is not None:
                audio_file["\xa9alb"] = [album]
            if year not in (None, ""):
                audio_file["\xa9day"] = [str(year)]
            if genre is not None:
                audio_file["\xa9gen"] = [genre]
            if bpm not in (None, ""):
                try:
                    audio_file["tmpo"] = [int(round(float(bpm)))]
                except (TypeError, ValueError):
                    pass
            if label is not None:
                audio_file["----:com.apple.iTunes:LABEL"] = [
                    MP4FreeForm(str(label).encode("utf-8"))
                ]
            if record_ref is not None:
                audio_file["----:com.apple.iTunes:RECORD_REF"] = [
                    MP4FreeForm(str(record_ref).encode("utf-8"))
                ]
            audio_file.save()
            return True

        if suffix == ".mp3":
            audio_file = MP3(str(path))
            if audio_file.tags is None:
                audio_file.tags = ID3()

        return False
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
        logger.exception(
            "Failed to copy MP3 metadata: %s -> %s", source_path, target_path
        )
        return False


def append_album_ref(album_name: str, album_ref: str) -> str:
    album_name = (album_name or "").strip()
    album_ref = (album_ref or "").strip()
    if not album_name:
        return ""
    if not album_ref:
        return album_name

    lowered_album = album_name.lower()
    lowered_ref = album_ref.lower()
    if lowered_ref in lowered_album:
        return album_name
    return f"{album_name} [{album_ref}]"


def _coerce_year(value: object) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
