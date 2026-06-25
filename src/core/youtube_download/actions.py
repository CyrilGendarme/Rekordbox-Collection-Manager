from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from yt_dlp import YoutubeDL

from src.services.audio_metadata_service import write_metadata_to_mp3
from src.services.bandcamp_service import lookup_bandcamp_album
from src.services.discogs_service import lookup_discogs_metadata
from src.utils.local_files_mgmt import save_sidecar_json


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

