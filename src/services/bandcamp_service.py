import os
import re
import unicodedata
import time
import logging
import random
import json
import base64
import mimetypes
from html import unescape

from src.utils.selenium_helpers import get_or_attach_driver

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logger = logging.getLogger(__name__)


def _is_truthy_env(value: str | None, default: bool = True) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _compute_backoff_seconds(attempt_index: int) -> float:
    base = 2.0 * (2**attempt_index)
    jitter = random.uniform(0.3, 1.3)
    return base + jitter


def _compute_warmup_delay_seconds() -> float:
    min_wait = float(os.environ.get("BANDCAMP_WARMUP_MIN_SECONDS", "2.0"))
    max_wait = float(os.environ.get("BANDCAMP_WARMUP_MAX_SECONDS", "4.5"))
    if max_wait < min_wait:
        min_wait, max_wait = max_wait, min_wait
    return random.uniform(min_wait, max_wait)


def _compute_html_snapshot_limit() -> int:
    return int(os.environ.get("BANDCAMP_HTML_SNAPSHOT_MAX_CHARS", "12000"))


def _format_exception_for_log(exc: Exception) -> str:
    exc_type = type(exc).__name__
    exc_message = str(exc).strip() or repr(exc)
    selenium_stack = getattr(exc, "stacktrace", None)
    if isinstance(selenium_stack, list) and selenium_stack:
        first_stack_line = selenium_stack[0].strip()
        return f"{exc_type}: {exc_message} | selenium_stack={first_stack_line}"

    return f"{exc_type}: {exc_message}"


def _normalize_bandcamp_query(name: str = "", artist: str = "", record_ref: str = "") -> str:
    query = f"{artist} {name} {record_ref}"
    query = unicodedata.normalize("NFKD", query)
    query = "".join(c for c in query if not unicodedata.combining(c))
    query = re.sub(r"[^A-Za-z0-9]+", " ", query).strip()
    query = " ".join(query.split())
    query = query.lower()
    return query.replace(" ", "%20")


def _split_search_query(query: str) -> tuple[str, str]:
    stripped_query = query.strip()
    if " - " in stripped_query:
        artist_q, name_q = stripped_query.split(" - ", 1)
        return artist_q.strip(), name_q.strip()
    return "", stripped_query


def _is_bandcamp_client_challenge(html: str, title: str = "") -> bool:
    lowered_html = html.lower()
    lowered_title = title.lower()
    return (
        "client challenge" in lowered_title
        or "_fs-ch-" in lowered_html
        or "javascript is disabled in your browser" in lowered_html
        or "please enable javascript to proceed" in lowered_html
    )


def _parse_bandcamp_search_results_from_html(html: str) -> list[dict[str, str]]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "html.parser")
    candidate_selectors = [
        # "ul.result-items li",
        "li.searchresult.data-search",
        # "li.result-item",
        # "li[data-item-typ:e='album']",
        # "li",
    ]

    items: list[dict[str, str]] = []
    seen_hrefs: set[str] = set()

    for selector in candidate_selectors:
        elements = soup.select(selector)
        logger.info(
            "Bandcamp selector probe | selector=%r count=%d", selector, len(elements)
        )

        for li in elements:
            item_type_el = li.select_one(".itemtype")
            item_type = (
                item_type_el.get_text(" ", strip=True).lower() if item_type_el else ""
            )
            if item_type and (item_type != "album" and item_type != "piste"):
                continue

            heading_link = li.select_one(".heading a")
            if heading_link is None:
                anchor_candidates = li.select("a[href*='/album/']")
                heading_link = anchor_candidates[0] if anchor_candidates else None

            if heading_link is None:
                continue

            href = (heading_link.get("href") or "").split("?from=search")[0]
            if not href or href in seen_hrefs:
                continue

            title = heading_link.get_text(" ", strip=True)
            subhead_div = li.select_one(".subhead")
            artist_info = subhead_div.get_text(" ", strip=True) if subhead_div else ""

            if not title:
                continue

            seen_hrefs.add(href)
            items.append(
                {
                    "title": title,
                    "artist": artist_info,
                    "href": href,
                    "price": "",
                }
            )

    logger.info("Bandcamp HTML parse produced %d unique items", len(items))
    return items


def _extract_price_text_from_element(element) -> str:
    candidates = [
        "span.base-text-color",
        ".base-text-color",
        ".price",
        ".buyItem .text",
        ".buyItem",
    ]

    for selector in candidates:
        try:
            if selector == ".buyItem":
                text = element.text.strip()
                if text:
                    return text
                continue

            candidate = element.find_element(By.CSS_SELECTOR, selector)
            text = candidate.text.strip()
            if text:
                return text
        except Exception:
            continue

    return ""


def _safe_json_from_attr(raw_value: str, attr_name: str) -> dict:
    if not raw_value:
        return {}

    decoded = unescape(raw_value)
    try:
        parsed = json.loads(decoded)
        return parsed if isinstance(parsed, dict) else {}
    except Exception as exc:
        logger.warning(
            "Bandcamp metadata JSON parse failed | attr=%s | %s",
            attr_name,
            _format_exception_for_log(exc),
        )
        logger.info(
            "Bandcamp metadata parse preview | attr=%s | preview=%r",
            attr_name,
            decoded[:400],
        )
        return {}


def _extract_bandcamp_metadata_script_payloads(
    page_html: str,
) -> tuple[dict, dict, dict]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(page_html, "html.parser")
    script_tag = soup.select_one("head script[data-band][data-tralbum]")
    if script_tag is None:
        script_tag = soup.select_one("script[data-band][data-tralbum]")

    if script_tag is None:
        logger.warning("Bandcamp metadata script not found")
        return {}, {}, {}

    data_band_raw = script_tag.get("data-band", "")
    data_tralbum_raw = script_tag.get("data-tralbum", "")
    data_embed_raw = script_tag.get("data-embed", "")

    logger.info(
        "Bandcamp metadata raw sizes | data-band=%d data-tralbum=%d data-embed=%d",
        len(data_band_raw),
        len(data_tralbum_raw),
        len(data_embed_raw),
    )
    print(
        "Bandcamp metadata raw preview | "
        f"data-band={unescape(data_band_raw)[:260]} | "
        f"data-tralbum={unescape(data_tralbum_raw)[:260]} | "
        f"data-embed={unescape(data_embed_raw)[:260]}"
    )

    data_band = _safe_json_from_attr(data_band_raw, "data-band")
    data_tralbum = _safe_json_from_attr(data_tralbum_raw, "data-tralbum")
    data_embed = _safe_json_from_attr(data_embed_raw, "data-embed")
    return data_band, data_tralbum, data_embed


def _extract_release_year(*date_candidates: str | None) -> str:
    for date_text in date_candidates:
        if not date_text:
            continue
        match = re.search(r"\b(19|20)\d{2}\b", str(date_text))
        if match:
            return match.group(0)
    return ""


def _extract_cover_image_url(page_html: str) -> str:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(page_html, "html.parser")

    # Preferred source from the exact HTML block provided by the user.
    popup_link = soup.select_one("#tralbumArt a.popupImage")
    if popup_link is not None:
        href = (popup_link.get("href") or "").strip()
        if href:
            return href

    img_el = soup.select_one("#tralbumArt img")
    if img_el is not None:
        src = (img_el.get("src") or "").strip()
        if src:
            return src

    source_el = soup.select_one("#tralbumArt source")
    if source_el is not None:
        srcset = (source_el.get("srcset") or "").strip()
        if srcset:
            first_candidate = srcset.split(",", 1)[0].strip().split(" ", 1)[0]
            if first_candidate:
                return first_candidate

    return ""


def _fetch_media_file_from_url(url: str) -> tuple[str, str]:
    if not url:
        return "", ""

    try:
        import requests

        response = requests.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
            timeout=25,
        )
        response.raise_for_status()

        mime_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip()
        if not mime_type:
            guessed_mime, _ = mimetypes.guess_type(url)
            mime_type = guessed_mime or "application/octet-stream"

        encoded = base64.b64encode(response.content).decode("ascii")
        return mime_type, encoded
    except Exception as exc:
        logger.warning(
            "Bandcamp thumbnail download failed | url=%s | %s",
            url,
            _format_exception_for_log(exc),
        )
        return "", ""


def _strip_artist_prefix(artist: str) -> str:
    artist = artist.strip()
    if artist.lower().startswith("by "):
        return artist[3:].strip()
    return artist


def _apply_parsed_metadata_to_item(item: dict, parsed_meta: dict[str, str]) -> None:
    field_mapping = {
        "page_type": "page_type",
        "title": "parsed_title",
        "artist_name": "artist_name",
        "label_name": "label_name",
        "release_year": "release_year",
        "album_name": "album_name",
    }
    for source_key, destination_key in field_mapping.items():
        item[destination_key] = parsed_meta.get(source_key, "")


def _extract_item_price(driver) -> str:
    wait = WebDriverWait(driver, 15)
    element = wait.until(
        EC.presence_of_element_located((By.CSS_SELECTOR, ".buyItem.digital"))
    )
    price = _extract_price_text_from_element(element)
    if not price:
        price = _extract_price_text_from_element(driver)
    return price


def _build_display_title(item: dict) -> tuple[str, str]:
    parsed_title = (item.get("parsed_title") or "").strip()
    parsed_artist = (item.get("artist_name") or "").strip()
    parsed_album = (item.get("album_name") or "").strip()
    parsed_page_type = (item.get("page_type") or "").strip().lower()

    title = (parsed_title or item.get("title", "")).strip()
    artist_val = (parsed_artist or item.get("artist", "")).strip()

    if parsed_page_type in {"track", "piste"} and parsed_album:
        display_title = (
            f"{title} ({parsed_album}) — {artist_val}"
            if artist_val
            else f"{title} ({parsed_album})"
        )
    else:
        display_title = f"{title} — {artist_val}" if artist_val else title

    return display_title, artist_val


def _build_media_link_from_item(item: dict, media_link_cls, platform_value):
    display_title, artist_val = _build_display_title(item)
    return media_link_cls(
        platform=platform_value,
        title=display_title,
        url=item["href"],
        thumbnail=item.get("thumbnail") or None,
        thumbnail_mime_type=item.get("thumbnail_mime_type") or None,
        thumbnail_media_base64=item.get("thumbnail_media_base64") or None,
        duration=None,
        channel=artist_val or None,
        price=item.get("price") or None,
        page_type=item.get("page_type") or None,
        parsed_title=item.get("parsed_title") or None,
        artist_name=item.get("artist_name") or None,
        label_name=item.get("label_name") or None,
        release_year=item.get("release_year") or None,
        album_name=item.get("album_name") or None,
    )


def _build_bandcamp_attempts(
    persistent_profile_dir: str,
) -> list[dict]:
    attempts = [
        {
            "name": "headless-persistent",
            "headless": True,
            "debug_port": 9223,
            "profile_dir": persistent_profile_dir,
            "cleanup": False,
        },
    ]
    return attempts


def _cleanup_attempt_resources(driver, attempt: dict) -> None:
    if driver:
        try:
            driver.quit()
        except Exception:
            pass


def _build_bandcamp_links(
    raw_results: list[dict],
    with_driver,
    name_q: str,
    artist_q: str,
    limit: int,
    media_link_cls,
    platform_value,
) -> list:
    for item in raw_results:
        item["artist"] = _strip_artist_prefix(item.get("artist", ""))

    results = clean_record_list_result(raw_results, name=name_q, artist=artist_q)
    sliced = results[:limit]
    get_bandcamp_page_info(with_driver, sliced)

    links = []
    for item in sliced:
        links.append(_build_media_link_from_item(item, media_link_cls, platform_value))
    return links


def _parse_bandcamp_page_metadata(
    data_band: dict,
    data_tralbum: dict,
    data_embed: dict,
    page_url: str,
) -> dict[str, str]:
    current = data_tralbum.get("current", {}) if isinstance(data_tralbum, dict) else {}
    if not isinstance(current, dict):
        current = {}

    page_type = str(current.get("type") or "").strip().lower()
    if not page_type:
        page_type = "track" if "/track/" in page_url else "album"

    page_title = (
        str(current.get("title") or "").strip()
        or str(data_tralbum.get("album_title") or "").strip()
    )
    artist_name = (
        str(current.get("artist") or "").strip()
        or str(data_tralbum.get("artist") or "").strip()
        or str(data_band.get("name") or "").strip()
    )
    label_name = (
        str(data_tralbum.get("label") or "").strip()
        or str(data_band.get("name") or "").strip()
    )
    release_year = _extract_release_year(
        str(current.get("release_date") or "").strip(),
        str(data_tralbum.get("album_release_date") or "").strip(),
        str(data_tralbum.get("release_date") or "").strip(),
        str(data_tralbum.get("publish_date") or "").strip(),
    )

    album_name = ""
    if page_type in {"track", "piste"}:
        album_embed_data = data_embed.get("album_embed_data", {})
        if not isinstance(album_embed_data, dict):
            album_embed_data = {}

        album_name = (
            str(data_embed.get("album_title") or "").strip()
            or str(album_embed_data.get("album_title") or "").strip()
            or str(data_tralbum.get("album_title") or "").strip()
            or str(data_tralbum.get("album_preorder_title") or "").strip()
            or str(data_tralbum.get("album_url") or "")
            .strip()
            .strip("/")
            .split("/")[-1]
            .replace("-", " ")
        )

    return {
        "page_type": page_type,
        "title": page_title,
        "artist_name": artist_name,
        "label_name": label_name,
        "release_year": release_year,
        "album_name": album_name,
    }


def get_bandcamp_info(
    driver, name="", artist="", record_ref=""
) -> list[dict[str, str, str, float]]:
    query = _normalize_bandcamp_query(name=name, artist=artist, record_ref=record_ref)

    # Wait for driver to be ready before navigating
    WebDriverWait(driver, 30).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

    use_warmup = _is_truthy_env(os.environ.get("BANDCAMP_WARMUP_ENABLED"), default=True)
    if use_warmup:
        driver.get("https://bandcamp.com/")
        warmup_delay = _compute_warmup_delay_seconds()
        logger.info("Bandcamp warm-up | sleeping=%.2fs", warmup_delay)
        time.sleep(warmup_delay)

    # time.sleep(5)

    driver.get(f"https://bandcamp.com/search?q={query}&item_type=")

    # time.sleep(5)

    try:
        webdriver_flag = driver.execute_script("return navigator.webdriver")
    except Exception:
        webdriver_flag = "unavailable"

    logger.info(
        "Bandcamp page loaded | title=%r | url=%r | navigator.webdriver=%r",
        driver.title,
        driver.current_url,
        webdriver_flag,
    )

    if _is_bandcamp_client_challenge(driver.page_source, driver.title):
        raise RuntimeError(
            "Bandcamp served a client challenge page to Selenium; search results are blocked"
        )

    # Wait briefly for the rendered result list if it exists, but do not fail the
    # whole scrape when the DOM shape changes; the HTML parser below can recover.
    wait = WebDriverWait(driver, 10)

    try:
        wait.until(
            lambda d: (len(d.find_elements(By.CSS_SELECTOR, "ul.result-items")) > 0)
        )
    except Exception:
        logger.info("Bandcamp result wait timed out; falling back to HTML parsing")

    results = _parse_bandcamp_search_results_from_html(driver.page_source)
    return results


def clean_record_list_result(bandcamp_info, name="", artist=""):
    if artist.strip():
        filtered_bandcamp_info = [
            item for item in bandcamp_info if artist.lower() == item["artist"].lower()
        ]
    else:
        filtered_bandcamp_info = bandcamp_info

    if name.strip():
        super_filtered_bandcamp_info = [
            item
            for item in filtered_bandcamp_info
            if name.lower() in item["title"].lower()
        ]
    else:
        super_filtered_bandcamp_info = filtered_bandcamp_info

    if super_filtered_bandcamp_info:
        return super_filtered_bandcamp_info
    if filtered_bandcamp_info:
        return filtered_bandcamp_info
    return bandcamp_info


def get_bandcamp_page_info(
    driver, bandcamp_info=list[dict[str, str, str]]
) -> list[dict[str, str, str, str]]:

    for item in bandcamp_info:
        time.sleep(2)  # Be polite and avoid hitting the server too hard
        driver.get(item["href"])
        page_html = driver.page_source

        item["thumbnail"] = _extract_cover_image_url(page_html)
        item["thumbnail_mime_type"], item["thumbnail_media_base64"] = _fetch_media_file_from_url(
            item.get("thumbnail", "")
        )

        data_band, data_tralbum, data_embed = _extract_bandcamp_metadata_script_payloads(
            page_html
        )
        parsed_meta = _parse_bandcamp_page_metadata(
            data_band=data_band,
            data_tralbum=data_tralbum,
            data_embed=data_embed,
            page_url=item.get("href", ""),
        )
        logger.info("Bandcamp parsed metadata | %s", parsed_meta)
        print(f"Bandcamp parsed metadata | {parsed_meta}")
        _apply_parsed_metadata_to_item(item, parsed_meta)

        try:
            item["price"] = _extract_item_price(driver)

        except Exception as e:
            print(
                f"Could not retrieve price for {item['title']} by {item['artist']}: {e}"
            )
            continue

    return bandcamp_info


def search_bandcamp(query: str, limit: int = 5) -> list[dict]:
    """
    Entry point called by the FastAPI route.

    Spins up a headless Chrome, scrapes Bandcamp search results, cleans
    them, and returns a list of MediaLink-compatible dicts with keys:
      title, artist, href, price
    """
    try:
        from .models import MediaLink, Platform
    except ImportError:
        from models import MediaLink, Platform
    logger.info("Bandcamp search | query=%r limit=%d", query, limit)

    # Default stays headless, but allow opt-out from environment when debugging.
    # use_headless = _is_truthy_env(os.environ.get("BANDCAMP_HEADLESS"), default=False)
    use_headless = _is_truthy_env(os.environ.get("BANDCAMP_HEADLESS"), default=True)
    use_debug_attach = _is_truthy_env(
        os.environ.get("BANDCAMP_USE_DEBUG_ATTACH"), default=False
    )
    persistent_profile_dir = os.environ.get("BANDCAMP_PROFILE_DIR") or os.path.join(
        os.path.dirname(__file__), "selenium_chrome_profile"
    )

    logger.info("Bandcamp selenium mode | headless=%s", use_headless)
    logger.info(
        "Bandcamp selenium options | debug_attach=%s profile_dir=%r",
        use_debug_attach,
        persistent_profile_dir,
    )

    artist_q, name_q = _split_search_query(query)
    attempts = _build_bandcamp_attempts(
        persistent_profile_dir=persistent_profile_dir,
    )

    last_exc = None
    for attempt_index, attempt in enumerate(attempts):
        driver = None
        try:
            driver, _ = get_or_attach_driver(
                width=1280,
                height=800,
                DEBUG_PORT=attempt["debug_port"],
                CHROME_PROFILE_DIR=attempt["profile_dir"],
                CHROME_DEV_CONSOLE=False,
                HEADLESS_MODE=use_headless,
                USE_DEBUG_ATTACH=use_debug_attach,
                shall_include_process=True,
            )

            raw = get_bandcamp_info(driver, name=name_q, artist=artist_q)
            links = _build_bandcamp_links(
                raw_results=raw,
                with_driver=driver,
                name_q=name_q,
                artist_q=artist_q,
                limit=limit,
                media_link_cls=MediaLink,
                platform_value=Platform.bandcamp,
            )
            logger.info(
                "Bandcamp search | found %d results | attempt=%s",
                len(links),
                attempt["name"],
            )
            return links

        except Exception as exc:
            last_exc = exc
            logger.warning(
                "Bandcamp attempt failed | attempt=%s | %s",
                attempt["name"],
                _format_exception_for_log(exc),
                exc_info=True,
            )
            if attempt_index < len(attempts) - 1:
                sleep_seconds = _compute_backoff_seconds(attempt_index=attempt_index)
                logger.info(
                    "Bandcamp retry backoff | attempt=%s sleeping=%.2fs",
                    attempt["name"],
                    sleep_seconds,
                )
                time.sleep(sleep_seconds)

        finally:
            _cleanup_attempt_resources(driver, attempt)
    logger.warning(
        "Bandcamp search failed after Selenium retries | selenium=%s",
        _format_exception_for_log(last_exc) if last_exc else "none",
    )
    return []




def first_result_from_bandcamp_search(title: str, artist: str) -> dict | None:
    """
    Convenience function to return the first result from a Bandcamp search.
    Returns a dict with keys: title, artist, href, price
    or None if no results are found.
    """
    query = f"{artist} - {title}" if artist else title
    results = search_bandcamp(query, limit=1)
    if results:
        return results[0]
    return None


def lookup_bandcamp_album(title: str, artist: str) -> str:
    """Resolve a likely album name from first Bandcamp match."""
    return getattr(
        first_result_from_bandcamp_search(title, artist), "album_name", ""
    ).strip()

