import os
import re
import unicodedata
import time

try:
    from src.utils.selenium_helpers import get_or_attach_driver
except ImportError:
    from src.utils.selenium_helpers import get_or_attach_driver

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


def get_bandcamp_info(
    driver, name="", artist="", record_ref=""
) -> list[dict[str, str, str, float]]:

    query = f"{artist} {name} {record_ref}"
    query = unicodedata.normalize("NFKD", query)
    query = "".join(c for c in query if not unicodedata.combining(c))
    query = re.sub(r"[^A-Za-z0-9]+", " ", query).strip()
    query = " ".join(query.split())
    query = query.lower()
    query = query.replace(" ", "%20")

    # Wait for driver to be ready before navigating
    WebDriverWait(driver, 30).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

    driver.get(f"https://bandcamp.com/search?q={query}&item_type=")

    #  Wait for page to be fully loaded (specifically the results list)
    wait = WebDriverWait(driver, 15)
    ul_element = wait.until(
        EC.presence_of_element_located((By.CLASS_NAME, "result-items"))
    )

    # Optional: ensure at least one <li> is present
    wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul.result-items li")))

    # Get all <li> elements inside the <ul>
    li_elements = ul_element.find_elements(By.TAG_NAME, "li")

    results = []

    # Iterate through each <li>
    for li in li_elements:
        try:
            item_type_div = li.find_element(By.CLASS_NAME, "itemtype")
            item_type = item_type_div.text.strip().lower()
            if item_type != "album":
                continue

            heading_div = li.find_element(By.CLASS_NAME, "heading")
            title = heading_div.text.strip()
            heading_link = heading_div.find_element(By.XPATH, "a")
            href = heading_link.get_attribute("href").split("?from=search")[0]

            subhead_div = li.find_element(By.CLASS_NAME, "subhead")
            artist_info = subhead_div.text.strip()

            results.append(
                {"title": title, "artist": artist_info, "href": href, "price": ""}
            )

        except Exception as e:
            # Skip malformed entries (ads, missing fields, etc.)
            print(f"Skipping item due to error: {e}")
            continue

    return results


def clean_record_list_result(bandcamp_info, name="", artist=""):

    filtered_bandcamp_info = []

    if artist.strip() != "":
        for item in bandcamp_info:
            if artist.lower() == item["artist"].lower():
                filtered_bandcamp_info.append(item)
    else:
        filtered_bandcamp_info = bandcamp_info

    super_filtered_bandcamp_info = []
    if name.strip() != "":
        for item in filtered_bandcamp_info:
            if name.lower() in item["title"].lower():
                super_filtered_bandcamp_info.append(item)
    else:
        super_filtered_bandcamp_info = filtered_bandcamp_info

    if len(super_filtered_bandcamp_info) != 0:
        return super_filtered_bandcamp_info
    elif len(filtered_bandcamp_info) != 0:
        return filtered_bandcamp_info
    else:
        return bandcamp_info


def add_bandcamp_record_price(
    driver, bandcamp_info=list[dict[str, str, str]]
) -> list[dict[str, str, str, str]]:

    for item in bandcamp_info:
        time.sleep(2)  # Be polite and avoid hitting the server too hard
        driver.get(item["href"])

        try:
            #  Wait for page to be fully loaded (specifically the results list)
            wait = WebDriverWait(driver, 15)
            element = wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".buyItem.digital"))
            )
            price = element.find_element(
                By.CSS_SELECTOR, "span.base-text-color"
            ).text.strip()
            item["price"] = price

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
    import logging
    try:
        from .models import MediaLink, Platform
    except ImportError:
        from models import MediaLink, Platform

    logger = logging.getLogger(__name__)
    logger.info("Bandcamp search | query=%r limit=%d", query, limit)

    # Split "Artist - Album" into separate components for better filtering.
    # If no separator is found, treat the whole string as the name.
    if " - " in query:
        parts = query.split(" - ", 1)
        artist_q = parts[0].strip()
        name_q = parts[1].strip()
    else:
        artist_q = ""
        name_q = query

    profile_dir = os.path.join(os.path.dirname(__file__), "selenium_chrome_profile")
    driver = None
    try:
        (driver, _) = get_or_attach_driver(
            width=1280,
            height=800,
            DEBUG_PORT=9223,  # use a different port from any interactive session
            CHROME_PROFILE_DIR=profile_dir,
            CHROME_DEV_CONSOLE=False,
            HEADLESS_MODE=True,
            shall_include_process=True,
        )

        raw = get_bandcamp_info(driver, name=name_q, artist=artist_q)

        # Bandcamp subhead is "by Artist Name" — strip the prefix so that
        # clean_record_list_result's exact-match and the display title are clean.
        for item in raw:
            a = item.get("artist", "")
            if a.lower().startswith("by "):
                item["artist"] = a[3:].strip()

        results = clean_record_list_result(raw, name=name_q, artist=artist_q)

        # Fetch digital prices for the items we will actually return.
        # add_bandcamp_record_price sleeps 2 s per item — apply only to the slice.
        sliced = results[:limit]
        add_bandcamp_record_price(driver, sliced)

        links: list[MediaLink] = []
        for item in sliced:
            title = item.get("title", "")
            artist_val = item.get("artist", "")
            display_title = f"{title} — {artist_val}" if artist_val else title
            price_val = item.get("price") or None

            links.append(
                MediaLink(
                    platform=Platform.bandcamp,
                    title=display_title,
                    url=item["href"],
                    thumbnail=None,
                    duration=None,
                    channel=artist_val or None,
                    price=price_val,
                )
            )

        logger.info("Bandcamp search | found %d results", len(links))
        return links

    except Exception as exc:
        logger.error("Bandcamp search failed | %s", exc)
        return []

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def lookup_bandcamp_album(title: str, artist: str) -> str:
    """Resolve a likely album name from first Bandcamp match."""
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
