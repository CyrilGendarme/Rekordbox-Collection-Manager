"""Official cover art lookup.

"Official" means artwork supplied by the label/distributor, as served by the
music stores (iTunes, Deezer), or the release artwork archived on MusicBrainz's
Cover Art Archive. Results are only accepted when both artist and title match,
so a wrong cover is less likely than no cover.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Iterator

import requests

from src.services.musicbrainz_service import _build_mb_query, _get_with_retry

logger = logging.getLogger(__name__)

_TIMEOUT = 20
_ITUNES_SEARCH_URL = "https://itunes.apple.com/search"
_DEEZER_SEARCH_URL = "https://api.deezer.com/search"
_COVER_ART_ARCHIVE_URL = "https://coverartarchive.org"
_MAX_CAA_RELEASES = 3


def _normalize(text: str) -> str:
    """Lowercase, strip accents, bracketed parts (mix names, catalog refs),
    featured artists and punctuation."""
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = text.lower()
    text = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", text)
    text = re.sub(r"\b(feat|ft|featuring)\b.*", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return " ".join(text.split())


def _artist_matches(wanted: str, candidate: str) -> bool:
    wanted_tokens = set(_normalize(wanted).split())
    candidate_tokens = set(_normalize(candidate).split())
    if not wanted_tokens or not candidate_tokens:
        return False
    # Accept collaborations listed on either side ("A" vs "A & B").
    return wanted_tokens <= candidate_tokens or candidate_tokens <= wanted_tokens


def _title_matches(wanted: str, candidate: str) -> bool:
    wanted_norm = _normalize(wanted)
    return bool(wanted_norm) and wanted_norm == _normalize(candidate)


def _album_matches(wanted: str, candidate: str) -> bool:
    wanted_norm = _normalize(wanted)
    return bool(wanted_norm) and wanted_norm == _normalize(candidate)


def _pick_best(matches: list[dict], album: str) -> dict | None:
    """First match on the wanted album if any, otherwise the first match."""
    for match in matches:
        if _album_matches(album, match["album"]):
            return match
    return matches[0] if matches else None


def _itunes_cover_url(title: str, artist: str, album: str) -> str:
    response = requests.get(
        _ITUNES_SEARCH_URL,
        params={"term": f"{artist} {title}", "entity": "song", "limit": 25},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    matches = [
        {"album": r.get("collectionName", ""), "url": r.get("artworkUrl100", "")}
        for r in response.json().get("results", [])
        if r.get("artworkUrl100")
        and _artist_matches(artist, r.get("artistName", ""))
        and _title_matches(title, r.get("trackName", ""))
    ]
    best = _pick_best(matches, album)
    # Artwork URLs embed their size; ask for a high-resolution version.
    return best["url"].replace("100x100bb", "1200x1200bb") if best else ""


def _deezer_cover_url(title: str, artist: str, album: str) -> str:
    response = requests.get(
        _DEEZER_SEARCH_URL,
        params={"q": f"{artist} {title}", "limit": 25},
        timeout=_TIMEOUT,
    )
    response.raise_for_status()
    matches = [
        {
            "album": (r.get("album") or {}).get("title", ""),
            "url": (r.get("album") or {}).get("cover_xl", ""),
        }
        for r in response.json().get("data", [])
        if (r.get("album") or {}).get("cover_xl")
        and _artist_matches(artist, (r.get("artist") or {}).get("name", ""))
        and _title_matches(title, r.get("title", ""))
    ]
    best = _pick_best(matches, album)
    return best["url"] if best else ""


def _cover_art_archive_urls(title: str, artist: str, album: str) -> list[str]:
    response = _get_with_retry(
        params={"query": _build_mb_query(artist, title), "fmt": "json", "limit": 25},
        timeout=_TIMEOUT,
    )
    matches: list[dict] = []
    for recording in response.json().get("recordings", []):
        credits = recording.get("artist-credit") or []
        credited = " ".join(
            c.get("name", "") for c in credits if isinstance(c, dict)
        )
        if not _artist_matches(artist, credited):
            continue
        if not _title_matches(title, recording.get("title", "")):
            continue
        for release in recording.get("releases") or []:
            if release.get("id"):
                matches.append({"album": release.get("title", ""), "id": release["id"]})

    # Releases on the wanted album first; the archive 404s when a release has no front cover.
    matches.sort(key=lambda m: not _album_matches(album, m["album"]))
    seen: set[str] = set()
    urls: list[str] = []
    for match in matches:
        if match["id"] in seen:
            continue
        seen.add(match["id"])
        urls.append(f"{_COVER_ART_ARCHIVE_URL}/release/{match['id']}/front-1200")
        if len(urls) >= _MAX_CAA_RELEASES:
            break
    return urls


def official_cover_candidates(
    title: str, artist: str, album: str = ""
) -> Iterator[tuple[str, str]]:
    """Yield (image_url, source) candidates, best first.

    Lazy: later providers are only queried if the caller keeps iterating,
    i.e. if the previous candidate could not be downloaded.
    """
    title = (title or "").strip()
    artist = (artist or "").strip()
    album = (album or "").strip()
    if not title or not artist:
        return

    for source, lookup in (
        ("iTunes", _itunes_cover_url),
        ("Deezer", _deezer_cover_url),
    ):
        try:
            url = lookup(title, artist, album)
        except Exception:
            logger.warning("%s cover lookup failed", source, exc_info=True)
            continue
        if url:
            yield url, source

    try:
        for url in _cover_art_archive_urls(title, artist, album):
            yield url, "Cover Art Archive"
    except Exception:
        logger.warning("Cover Art Archive lookup failed", exc_info=True)
