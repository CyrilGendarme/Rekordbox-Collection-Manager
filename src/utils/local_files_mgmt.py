from __future__ import annotations

import json
from typing import Any


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
