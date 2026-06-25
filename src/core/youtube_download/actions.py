from __future__ import annotations

import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL

from src.data import RekordboxDAO

TAG_CATEGORY_ORDER = ["Situation", "Set Basis", "Set Build", "Component"]
OTHER_TAG_CATEGORY = "Other"

TAG_CATEGORY_TAGS: dict[str, set[str]] = {
    "Situation": {
        "Morning",
        "Lounge",
        "Teuf",
        "Hard Groove",
        "Bar Background",
        "Commercial",
    },
    "Set Basis": {
        "Groovy",
        "French Touch",
        "Belgian Touch",
        "UK Touch",
        "Latin Touch",
        "Porn",
        "Wooble",
        "Goth",
        "Tropical",
    },
    "Set Build": {
        "Build Up",
        "Peak Time",
        "Build Down",
        "Background",
        "Styles Transitions",
        "Set Opener",
        "Set Closer",
        "Vocal",
        "Copyright Ok",
        "Vinyl Rip",
        "Not Tagged",
    },
    "Component": {
        "Mdma",
        "Dark",
        "Chill",
        "Acid",
        "Minimal",
        "Dub",
        "Progressive",
        "Organic",
        "Good Message",
        "Nostalgia",
        "Hypnotic",
        "Retro",
        "Classic",
    },
}


def sanitize_filename(value: str) -> str:
    raw = (value or "").strip() or "download"
    cleaned = re.sub(r"[\\/:*?\"<>|]", "_", raw)
    cleaned = re.sub(r"\s+", " ", cleaned).strip().rstrip(".")
    return cleaned or "download"


def remove_playlist_param(url: str) -> str:
    if "&list=" in url:
        return url.split("&list=", 1)[0]
    return url


def fetch_youtube_info(url: str) -> dict[str, Any]:
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
    }
    with YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(url, download=False)


def download_audio_as_mp3(url: str, output_dir: str) -> str:
    outtmpl = str(Path(output_dir) / "%(title)s.%(ext)s")
    ydl_opts = {
        "format": "bestaudio/best",
        "noplaylist": True,
        "quiet": True,
        "outtmpl": outtmpl,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
    }

    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        title = info.get("title") or "download"

    return str(Path(output_dir) / f"{sanitize_filename(str(title))}.mp3")


def get_rekordbox_taxonomy() -> tuple[list[str], list[str]]:
    try:
        with RekordboxDAO() as dao:
            genres = dao.get_all_genres_from_collection()
            tags = dao.get_all_tags_from_collection()
        return genres, tags
    except Exception:
        return [], []


def normalize_tag_name(tag_name: str) -> str:
    raw = "" if tag_name is None else str(tag_name)
    deaccented = "".join(
        c
        for c in unicodedata.normalize("NFKD", raw)
        if not unicodedata.combining(c)
    )
    return " ".join(deaccented.lower().replace("_", " ").split())


def category_for_tag(tag_name: str) -> str:
    normalized = normalize_tag_name(tag_name)
    for category, names in TAG_CATEGORY_TAGS.items():
        normalized_names = {normalize_tag_name(name) for name in names}
        if normalized in normalized_names:
            return category
    return OTHER_TAG_CATEGORY


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
    from mutagen.easyid3 import EasyID3

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


def lookup_discogs_metadata(title: str, artist: str, album: str = "") -> dict[str, Any]:
    try:
        from src.services.discogs_service import search_releases
    except Exception:
        return {}

    try:
        results = search_releases(
            artist=artist,
            track=title,
            album=album or None,
            limit=5,
        )
    except Exception:
        return {}

    if not results:
        return {}

    best = results[0]
    album_name = album
    result_title = (getattr(best, "title", "") or "").strip()
    if " - " in result_title:
        left, right = result_title.split(" - ", 1)
        if artist.lower() in left.lower():
            album_name = right.strip()
    elif not album_name:
        album_name = result_title

    year_val = getattr(best, "year", None)
    try:
        year_int = int(year_val) if year_val else None
    except (TypeError, ValueError):
        year_int = None

    label_val = getattr(best, "label", None)
    if isinstance(label_val, list):
        label_val = label_val[0] if label_val else None

    return {
        "album": album_name,
        "year": year_int,
        "label": label_val,
        "catno": getattr(best, "catno", None),
    }


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


def lookup_bandcamp_album(title: str, artist: str) -> str:
    try:
        from src.services.bandcamp_service import search_bandcamp
    except Exception:
        return ""

    query = f"{artist} - {title}" if artist else title
    try:
        results = search_bandcamp(query, limit=3)
    except Exception:
        return ""

    if not results:
        return ""

    first_title = getattr(results[0], "title", "") or ""
    if " - " in first_title:
        return first_title.split(" - ", 1)[0].strip()
    if " — " in first_title:
        return first_title.split(" — ", 1)[0].strip()
    return first_title.strip()


def extract_year_from_youtube_info(youtube_info: dict[str, Any]) -> int | None:
    release_year = youtube_info.get("release_year")
    if release_year is not None:
        try:
            return int(release_year)
        except (TypeError, ValueError):
            pass

    upload_date = str(youtube_info.get("upload_date", ""))
    if len(upload_date) >= 4 and upload_date[:4].isdigit():
        return int(upload_date[:4])
    return None


def resolve_downloaded_path(
    downloaded_path: str | None,
    title: str,
    youtube_title: str,
    youtube_dir: str,
    started_at: float | None = None,
) -> str:
    if downloaded_path and os.path.exists(downloaded_path):
        return downloaded_path

    fallback_name = sanitize_filename(title)
    fallback_path = os.path.join(youtube_dir, f"{fallback_name}.mp3")
    if os.path.exists(fallback_path):
        return fallback_path

    youtube_title_name = sanitize_filename(youtube_title)
    youtube_title_path = os.path.join(youtube_dir, f"{youtube_title_name}.mp3")
    if os.path.exists(youtube_title_path):
        return youtube_title_path

    candidates: list[str] = []
    try:
        for name in os.listdir(youtube_dir):
            if not name.lower().endswith(".mp3"):
                continue
            normalized = name.lower()
            if (
                fallback_name.lower() in normalized
                or youtube_title_name.lower() in normalized
            ):
                candidates.append(os.path.join(youtube_dir, name))
    except OSError:
        return fallback_path

    if candidates:
        candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
        return candidates[0]

    try:
        all_mp3 = [
            os.path.join(youtube_dir, name)
            for name in os.listdir(youtube_dir)
            if name.lower().endswith(".mp3")
        ]
    except OSError:
        all_mp3 = []

    if all_mp3:
        if started_at is not None:
            recent_mp3 = [
                path for path in all_mp3 if os.path.getmtime(path) >= started_at - 5
            ]
            if recent_mp3:
                recent_mp3.sort(key=os.path.getmtime, reverse=True)
                return recent_mp3[0]

        all_mp3.sort(key=os.path.getmtime, reverse=True)
        return all_mp3[0]

    return fallback_path


def set_track_metadata_in_rekordbox(
    track_id: int | str,
    title: str,
    artist: str,
    album: str = "",
    label: str = "",
    year: int | None = None,
    genre: str = "",
    tags: list[str] | None = None,
) -> None:
    with RekordboxDAO() as dao:
        core_payload: dict[str, Any] = {
            "title": title,
            "artist": artist,
        }
        if album:
            core_payload["album"] = album
        if label:
            core_payload["label"] = label
        if year is not None:
            core_payload["year"] = year

        dao.update_info_of_track(track_id, **core_payload)

        if genre:
            dao.update_info_of_track(track_id, genre=genre)

        dao.set_track_tags(track_id, tags or [])


def save_sidecar_json(
    path: str,
    source_url: str,
    youtube_info: dict[str, Any],
    track_title: str,
    artist: str,
    album: str,
    year: str,
    label: str,
    genre: str,
    tags: list[str],
) -> None:
    payload = {
        "source_url": source_url,
        "youtube_title": youtube_info.get("title"),
        "track_title": track_title,
        "artist": artist,
        "album": album,
        "year": year,
        "label": label,
        "genre": genre,
        "tags": tags,
    }
    with open(path, "w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
