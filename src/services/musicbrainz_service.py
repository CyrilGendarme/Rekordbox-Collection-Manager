from typing import Optional

import logging
import time
import requests
from datetime import date


logger = logging.getLogger(__name__)
_MUSICBRAINZ_RECORDING_URL = "https://musicbrainz.org/ws/2/recording"
_RETRIABLE_STATUS_CODES = {429, 500, 502, 503, 504}


def _get_with_retry(*, params: dict, timeout: float, max_retries: int = 3) -> requests.Response:
    """GET MusicBrainz endpoint with basic retry/backoff for transient failures."""
    wait_seconds = 1.0
    for attempt in range(max_retries + 1):
        try:
            response = requests.get(
                _MUSICBRAINZ_RECORDING_URL,
                params=params,
                headers={
                    "User-Agent": "record-info-tool/1.0 (https://example.local; contact@example.local)"
                },
                timeout=timeout,
            )
            if (
                response.status_code in _RETRIABLE_STATUS_CODES
                and attempt < max_retries
            ):
                retry_after = response.headers.get("Retry-After")
                if retry_after is not None:
                    try:
                        wait_seconds = max(wait_seconds, float(retry_after))
                    except ValueError:
                        pass
                logger.warning(
                    "MusicBrainz transient HTTP %s (attempt %d/%d), retrying in %.1fs",
                    response.status_code,
                    attempt + 1,
                    max_retries + 1,
                    wait_seconds,
                )
                time.sleep(wait_seconds)
                wait_seconds = min(wait_seconds * 2, 10.0)
                continue

            response.raise_for_status()
            return response
        except requests.RequestException as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            should_retry = status_code in _RETRIABLE_STATUS_CODES or status_code is None
            if attempt >= max_retries or not should_retry:
                raise

            logger.warning(
                "MusicBrainz request failed (attempt %d/%d), retrying in %.1fs: %s",
                attempt + 1,
                max_retries + 1,
                wait_seconds,
                exc,
            )
            time.sleep(wait_seconds)
            wait_seconds = min(wait_seconds * 2, 10.0)

    raise RuntimeError("Unreachable retry state while querying MusicBrainz")


def _split_query(query: str) -> tuple[str, str]:
    if " - " in query:
        artist, name = query.split(" - ", 1)
        return artist.strip(), name.strip()
    return "", query.strip()


def _build_mb_query(artist: str, title: str) -> str:
    parts = []
    if artist:
        parts.append(f'artist:"{artist}"')
    if title:
        parts.append(f'recording:"{title}"')
    return " AND ".join(parts) if parts else title


def _best_release_group(recording: dict) -> tuple[str, str]:

    # if not _has_eligible_release(rec):

    rg = recording.get("release-group") or {}
    rg_title = rg.get("title", "")
    rg_id = rg.get("id", "")
    if rg_title and rg_id:
        return rg_title, f"https://musicbrainz.org/release-group/{rg_id}"

    releases = recording.get("releases") or []
    if releases:
        rel = releases[0]
        rel_title = rel.get("title", "")
        rel_id = rel.get("id", "")
        if rel_title and rel_id:
            return rel_title, f"https://musicbrainz.org/release/{rel_id}"

    return "", ""


def lookup_musicbrainz_album(query: str, limit: int = 5) -> Optional[dict]:
    """
    Retrieve album-like media links from MusicBrainz for an "Artist - Track" query.

    Returns a dictionary with album information.
    """
    logger.info("MusicBrainz search | query=%r limit=%d", query, limit)

    artist_q, title_q = _split_query(query)
    mb_query = _build_mb_query(artist_q, title_q)

    try:
        response = _get_with_retry(
            params={
                "query": mb_query,
                "fmt": "json",
                "limit": max(1, min(limit * 4, 100)),
            },
            timeout=25,
        )
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning(
            "MusicBrainz lookup failed for query=%r; returning no result: %s",
            query,
            exc,
        )
        return None

    recordings = payload.get("recordings", [])
    
    if len(recordings) == 0:
        return None

    favorite_release = {
        "album_title": "",
        "url": "",
        "album_release_date": date.max.isoformat(),
    }

    for rec in recordings:

        track_title = rec.get("title", "")

        # Store full artists names and main artist name str
        artist_credit = rec.get("artist-credit") or []
        artist_name = ""
        for artist_credit_items in artist_credit:
            artist_name += artist_credit_items.get("name", "") + " "
            artist_name += artist_credit_items.get("joinphrase", "") + " "
        artist_name = artist_name.replace("  ", " ").strip()

        main_artist_name = ""
        if artist_credit and isinstance(artist_credit[0], dict):
            main_artist_name = artist_credit[0].get("name", "")

        # Ensure that the artist and title match the query if specified
        if artist_q and main_artist_name.lower() != artist_q.lower():
            continue

        if title_q and track_title.lower() != title_q.lower():
            continue

        for release in rec.get("releases", []):
            album_title = release.get("title", "")
            album_release_date = release.get("date", "")
            album_track_count = release.get("track-count", 0)

            if album_track_count < 3:
                continue
            if album_release_date > favorite_release["album_release_date"]:
                continue

            favorite_release = {
                "album_title": album_title,
                "url": f"https://musicbrainz.org/release/{release.get('id', '')}",
                "album_release_date": album_release_date,
            }

    if not favorite_release["album_title"]:
        return None

    return favorite_release


def main():
    # query = "Anoraak - Magnifique"
    # results = search_musicbrainz(query, limit=5)
    # if not results:
    #     print("No MusicBrainz results returned for query.")
    # for link in results:
    #     print(
    #         f"Title: {link.title}, Artist: {link.channel}, URL: {link.url}, Price: {link.price}"
    #     )

    artist = "Anoraak"
    title = "Magnifique"

    query = f"{artist} - {title}" if artist else title

    album = lookup_musicbrainz_album(query, limit=3)
    print(f"Resolved album name: {album}")


if __name__ == "__main__":
    main()
