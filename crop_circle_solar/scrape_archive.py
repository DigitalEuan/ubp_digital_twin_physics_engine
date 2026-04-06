#!/usr/bin/env python3
"""
scrape_archive.py — Scraper for cropcirclearchives.co.uk (1978-2013)
=====================================================================
Handles two different site structures:
  - Old (1978-2009): Formation links directly on year page (flat structure)
    e.g., /archives/1990/Punchbowl90.html
  - New (2010-2013): Month sub-pages with formation links
    e.g., /archives/2010/june2010.html → /archives/2010/oldsarum/oldsarum2010a.html
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import csv
import os
import math

ARCHIVE_BASE = "https://www.cropcirclearchives.co.uk/archives"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Research bot; crop circle solar study; contact via digitaleuan.com)"
}

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

COUNTIES_UK = [
    "Wiltshire", "Hampshire", "Oxfordshire", "Berkshire", "Dorset",
    "Somerset", "Gloucestershire", "Cambridgeshire", "Yorkshire",
    "Kent", "Surrey", "Hertfordshire", "Lincolnshire", "Norfolk",
    "Suffolk", "Essex", "Warwickshire", "Shropshire", "Staffordshire",
    "Herefordshire", "Worcestershire", "Buckinghamshire", "Bedfordshire",
    "Northamptonshire", "Leicestershire", "Nottinghamshire", "Derbyshire",
    "Cheshire", "Lancashire", "Cumbria", "Durham", "Northumberland",
    "East Sussex", "West Sussex", "Devon", "Cornwall",
]

COUNTRIES_FOREIGN = [
    "Netherlands", "Germany", "France", "Italy", "Czech Republic", "Czech",
    "Switzerland", "Belgium", "Austria", "Poland", "Hungary", "Slovakia",
    "USA", "Canada", "Australia", "Russia", "Japan", "India",
    "Argentina", "Brazil", "Mexico", "Spain", "Portugal", "Sweden",
    "Norway", "Denmark", "Finland", "New Zealand",
]

CROPS = [
    "wheat", "barley", "oilseed rape", "rapeseed", "canola", "maize", "corn",
    "rye", "oats", "grass", "flax", "sunflower", "soybean", "soya",
    "linseed", "peas", "potato",
]

FORMATION_KEYWORDS = {
    "pictogram": ["pictogram", "glyph"],
    "mandala": ["mandala", "flower of life"],
    "fractal": ["fractal", "julia set", "mandelbrot", "sierpinski", "koch"],
    "spiral": ["spiral", "nautilus", "fibonacci"],
    "geometric": ["pentagon", "hexagon", "octagon", "triangle", "square", "star"],
    "simple_circle": ["single circle", "simple circle"],
    "ring": ["concentric ring"],
    "face": ["face", "portrait", "alien"],
    "encoded": ["binary", "ascii", "arecibo", "encoded"],
}

NAV_SKIP_KEYWORDS = [
    "rumours", "forum", "report", "faq", "contact", "search",
    "advertise", "membership", "weather", "conduct", "policy",
    "news", "conferences", "archives", "state", "researchers",
    "bibliography", "dvds", "videos", "circleshop", "magazines",
    "travelogue", "gallery", "research", "interface", "anasazi",
    "hengeshop", "vitalsigns", "freecounterstat", "youtube",
    "skyhigh", "insight", "sinauctor", "librecad", "bbc",
    "javascript", "worldrumours", "cccvault", "trailer", "privacy",
    "connect.html", "mainframe", "cpri", "file://",
]

# Image extensions to skip
IMG_EXTS = [".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff", ".webp"]

# Navigation text patterns
NAV_TEXT = [
    "continue", "return to", "mark fussell", "stuart dike",
    "go to", "home", "next", "previous", "back",
]


def fetch_page(url: str, delay: float = 1.2) -> BeautifulSoup | None:
    time.sleep(delay)
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"  [WARN] Failed: {url}: {e}")
        return None


def should_skip_href(href: str) -> bool:
    """Return True if this href should be skipped."""
    href_lower = href.lower()
    # Skip navigation keywords
    if any(kw in href_lower for kw in NAV_SKIP_KEYWORDS):
        return True
    # Skip image files
    if any(href_lower.endswith(ext) for ext in IMG_EXTS):
        return True
    # Skip anchors
    if href.startswith("#"):
        return True
    # Skip external sites
    if href.startswith("http") and "cropcircle" not in href_lower:
        return True
    return False


def resolve_url(href: str, base_url: str) -> str:
    """Resolve relative URL against base."""
    if href.startswith("http"):
        return href
    if href.startswith("/"):
        return f"https://www.cropcirclearchives.co.uk{href}"
    # Relative to base directory
    base_dir = "/".join(base_url.split("/")[:-1]) + "/"
    # Handle ../ navigation
    parts = (base_dir + href).split("/")
    resolved = []
    for part in parts:
        if part == "..":
            if resolved:
                resolved.pop()
        elif part != ".":
            resolved.append(part)
    return "/".join(resolved)


def extract_gps_from_streetmap(soup_str: str) -> tuple:
    m = re.search(r"sv=(-?\d+\.\d+),\+?(-?\d+\.\d+)", soup_str)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return round(lat, 6), round(lon, 6)
    m = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", soup_str)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return round(lat, 6), round(lon, 6)
    m = re.search(r"[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)", soup_str)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return round(lat, 6), round(lon, 6)
    return None, None


def extract_os_grid(soup_str: str) -> str:
    m = re.search(r'\b([A-Z]{2}\d{6,10})\b', soup_str)
    return m.group(1) if m else ""


def parse_date_from_text(text: str, year: int) -> tuple:
    patterns = [
        (r"[Rr]eported\s+(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", "dmy"),
        (r"[Ff]ormed\s+(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", "dmy"),
        (r"[Rr]eported\s+(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)", "dmy_noyear"),
        (r"[Ff]ormed\s+(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)", "dmy_noyear"),
        (r"(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", "dmy"),
        (r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})", "mdy"),
        (r"(\d{1,2})/(\d{1,2})/(\d{4})", "dmy_slash"),
        # Shorthand: "28/29th May" → use day 28
        (r"(\d{1,2})(?:/\d{1,2})?(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)", "dmy_noyear"),
    ]

    for pattern, fmt in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            raw = m.group(0)
            try:
                if fmt == "dmy":
                    d, mon_str, y = int(m.group(1)), m.group(2).lower(), int(m.group(3))
                    mon = MONTH_MAP.get(mon_str, 0)
                elif fmt == "dmy_noyear":
                    d, mon_str = int(m.group(1)), m.group(2).lower()
                    mon = MONTH_MAP.get(mon_str, 0)
                    y = year
                elif fmt == "mdy":
                    mon_str, d, y = m.group(1).lower(), int(m.group(2)), int(m.group(3))
                    mon = MONTH_MAP.get(mon_str, 0)
                elif fmt == "dmy_slash":
                    d, mon, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                else:
                    continue

                if 1 <= d <= 31 and 1 <= mon <= 12 and 1900 <= y <= 2030:
                    return f"{y:04d}-{mon:02d}-{d:02d}", raw, "exact"
            except Exception:
                continue

    # Month-only fallback
    m = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
        text, re.IGNORECASE
    )
    if m:
        mon = MONTH_MAP.get(m.group(1).lower(), 7)
        y = int(m.group(2))
        if 1900 <= y <= 2030:
            return f"{y:04d}-{mon:02d}-15", m.group(0), "approximate"

    return f"{year}-07-01", "", "year_only"


def extract_county_country(text: str) -> tuple:
    # Only look at first 500 chars to avoid navigation text pollution
    text_short = text[:500]
    # USA is too common in nav links; require more specific patterns
    for c_name in COUNTRIES_FOREIGN:
        if c_name.lower() == "usa":
            # Only match USA if it appears as a location context
            if re.search(r'(?:nr|near|in|,)\s*(?:usa|united states)', text_short, re.IGNORECASE):
                return "USA", "USA"
            continue
        if c_name.lower() in text_short.lower():
            return c_name, c_name
    for c in COUNTIES_UK:
        if c.lower() in text_short.lower():
            return c, "UK"
    return "", "UK"


def extract_size(text: str) -> tuple:
    diameter = None
    size_patterns = [
        (r"(\d+(?:\.\d+)?)\s*(?:metres?|meters?|m)\s+(?:in\s+)?(?:diameter|wide|across|in\s+width)", "m"),
        (r"diameter\s+(?:of\s+)?(?:approximately\s+)?(\d+(?:\.\d+)?)\s*(?:m|metres?|meters?)", "m"),
        (r"approximately\s+(\d+(?:\.\d+)?)\s*(?:m|metres?)\s+(?:in\s+)?(?:diameter|wide)", "m"),
        (r"(\d+(?:\.\d+)?)\s*(?:feet|ft)\s+(?:in\s+)?(?:diameter|wide|across)", "ft"),
        (r"(?:size|measures?|measuring)\s+(?:approximately\s+)?(\d+(?:\.\d+)?)\s*(?:m|metres?)", "m"),
        (r"(\d+)\s*m\s+(?:diameter|wide|across)", "m"),
    ]
    for pattern, unit in size_patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            val = float(m.group(1))
            if unit == "ft":
                val = round(val * 0.3048, 1)
            if 1 < val < 2000:
                diameter = val
                break
    area = round(math.pi * (diameter / 2) ** 2, 1) if diameter else None
    return diameter, area


def extract_formation_type(text: str) -> str:
    text_lower = text.lower()
    for ftype, keywords in FORMATION_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return ftype
    return "unknown"


def get_formation_links_old_style(year: int, delay: float) -> list[dict]:
    """
    Old style (1978-2009): Formation links directly on year page.
    May also have continuation pages (1990a.html, 1990b.html etc.)
    """
    stubs = []
    seen_urls = set()

    # Pages to scan: year page + continuation pages
    pages_to_scan = [f"{ARCHIVE_BASE}/{year}/{year}.html"]

    # Also check for continuation pages
    for suffix in ["a", "b", "c", "d", "e"]:
        pages_to_scan.append(f"{ARCHIVE_BASE}/{year}/{year}{suffix}.html")

    for page_url in pages_to_scan:
        soup = fetch_page(page_url, delay * 0.5)
        if not soup:
            continue

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"]
            title = a_tag.get_text(strip=True)

            if should_skip_href(href):
                continue

            # Skip nav text
            if any(nav in title.lower() for nav in NAV_TEXT):
                continue

            full_url = resolve_url(href, page_url)

            if not full_url.endswith(".html"):
                continue

            # Must be in the year directory
            if f"/archives/{year}/" not in full_url:
                continue

            # Must NOT be the year index or continuation pages
            filename = full_url.split("/")[-1]
            if re.match(rf'^{year}[a-z]?\.html$', filename):
                continue

            # Must be a formation page (not a section page)
            # Old style: flat files like Punchbowl90.html
            path_after_year = full_url.split(f"/archives/{year}/")[-1]
            # Old style: no subdirectory
            # New style: has subdirectory

            if full_url not in seen_urls and len(title) > 3:
                seen_urls.add(full_url)
                stubs.append({
                    "year": year,
                    "source_url": full_url,
                    "title_raw": title[:200],
                })

    return stubs


def get_formation_links_new_style(year: int, delay: float) -> list[dict]:
    """
    New style (2010-2013): Month sub-pages with formation subdirectories.
    """
    # Get section pages from year index
    year_url = f"{ARCHIVE_BASE}/{year}/{year}.html"
    soup = fetch_page(year_url, delay)
    if not soup:
        return []

    section_pages = []
    seen_section = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        if should_skip_href(href):
            continue

        full_url = resolve_url(href, year_url)
        if not full_url.endswith(".html"):
            continue
        if f"/archives/{year}/" not in full_url:
            continue
        if full_url.endswith(f"/{year}.html"):
            continue

        path_after_year = full_url.split(f"/archives/{year}/")[-1]
        if "/" in path_after_year:  # skip subdirectory pages
            continue

        if full_url not in seen_section:
            seen_section.add(full_url)
            section_pages.append(full_url)

    # Get formation links from section pages
    stubs = []
    seen_urls = set()

    for sp in section_pages:
        soup_sp = fetch_page(sp, delay * 0.4)
        if not soup_sp:
            continue

        for a_tag in soup_sp.find_all("a", href=True):
            href = a_tag["href"]
            title = a_tag.get_text(strip=True)

            if should_skip_href(href):
                continue
            if any(nav in title.lower() for nav in NAV_TEXT):
                continue

            full_url = resolve_url(href, sp)

            if not full_url.endswith(".html"):
                continue

            # Must be in year directory with subdirectory
            if f"/archives/{year}/" not in full_url:
                continue

            path_after_year = full_url.split(f"/archives/{year}/")[-1]
            if "/" not in path_after_year:  # must have subdirectory
                continue

            # Sanity check: subdirectory not a year or month name
            subdir = path_after_year.split("/")[0]
            if re.match(r'^\d{4}$', subdir):
                continue
            if any(nav in subdir.lower() for nav in [
                "september", "october", "november", "december", "january",
                "february", "march", "april", "may", "june", "july", "august",
            ]):
                continue

            if full_url not in seen_urls:
                seen_urls.add(full_url)
                stubs.append({
                    "year": year,
                    "source_url": full_url,
                    "title_raw": title[:200] if len(title) > 3 else "",
                })

    return stubs


def parse_formation_page(stub: dict, delay: float) -> dict:
    """Parse individual formation page."""
    record = {
        "year": stub["year"],
        "source_url": stub["source_url"],
        "title_raw": stub.get("title_raw", ""),
        "date_parsed": f"{stub['year']}-07-01",
        "date_raw": "",
        "date_confidence": "year_only",
        "location": "",
        "county": "",
        "country": "UK",
        "lat": "",
        "lon": "",
        "os_grid_ref": "",
        "crop_type": "",
        "approx_diameter_m": "",
        "approx_area_m2": "",
        "formation_type": "unknown",
        "description": "",
        "image_url": "",
        "blt_sampled": 0,
        "hoax_flag": 0,
        "notes": "",
    }

    soup = fetch_page(stub["source_url"], delay)
    if not soup:
        record["notes"] = "fetch_failed;"
        return record

    soup_str = str(soup)
    body_text = soup.get_text(separator=" ", strip=True)

    # Page title
    title_tag = soup.find("title")
    page_title = title_tag.get_text(strip=True) if title_tag else stub.get("title_raw", "")
    record["title_raw"] = page_title

    # GPS
    lat, lon = extract_gps_from_streetmap(soup_str)
    if lat is not None:
        record["lat"] = lat
        record["lon"] = lon

    # OS Grid
    record["os_grid_ref"] = extract_os_grid(soup_str)

    # Date: use title_raw from section page (often has "Reported Xth Month")
    # then page title, then body
    combined = stub.get("title_raw", "") + " " + page_title + " " + body_text[:3000]
    date_parsed, date_raw, confidence = parse_date_from_text(combined, stub["year"])
    record["date_parsed"] = date_parsed
    record["date_raw"] = date_raw
    record["date_confidence"] = confidence

    # County/Country
    county, country = extract_county_country(page_title + " " + stub.get("title_raw", "") + " " + body_text[:2000])
    record["county"] = county
    record["country"] = country

    # Location
    # For old-style pages, title_raw from section page is the best location source
    title_raw = stub.get("title_raw", "")
    if title_raw and len(title_raw) > 5:
        # Remove date part
        loc = re.sub(r"[Rr]eported.*|[Ff]ormed.*|\d{1,2}(?:st|nd|rd|th)?\s+\w+\s*\.", "", title_raw)
        loc = loc.strip(" .,\n\r\t")
        if loc:
            record["location"] = loc[:120]

    if not record["location"]:
        loc_match = re.search(r"[Cc]rop [Cc]ircle (?:at|near|in)\s+(.+?)\.\s+[Rr]eported", page_title)
        if loc_match:
            record["location"] = loc_match.group(1).strip()[:120]
        else:
            loc = re.sub(r"[Cc]rop [Cc]ircle(?: [Cc]onnector)?", "", page_title)
            loc = re.sub(r"[Rr]eported.*|[Ff]ormed.*", "", loc)
            record["location"] = loc.strip(" .-|,")[:120]

    # Size
    diameter, area = extract_size(body_text)
    record["approx_diameter_m"] = diameter if diameter else ""
    record["approx_area_m2"] = area if area else ""

    # Crop type
    for crop in CROPS:
        if crop in body_text.lower():
            record["crop_type"] = crop
            break

    # Formation type
    record["formation_type"] = extract_formation_type(body_text + " " + page_title)

    # BLT flag
    if "blt" in body_text.lower() and ("sampled" in body_text.lower() or "research" in body_text.lower()):
        record["blt_sampled"] = 1

    # Hoax flag
    if any(w in body_text.lower() for w in ["admitted", "confessed", "man-made", "manmade", "hoax confirmed"]):
        record["hoax_flag"] = 1

    # Description
    for tag in soup.find_all(["p", "td", "div"]):
        text = tag.get_text(strip=True)
        if len(text) > 100 and not any(nav in text.lower() for nav in
                                        ["click here", "make a donation", "membership", "copyright",
                                         "free to view", "crop circle connector", "return to"]):
            record["description"] = text[:600]
            break

    # First image
    for img in soup.find_all("img", src=True):
        src = img["src"]
        if any(ext in src.lower() for ext in [".jpg", ".jpeg", ".png"]):
            if not any(skip in src.lower() for skip in ["logo", "banner", "button", "nav", "icon", "maze"]):
                record["image_url"] = resolve_url(src, stub["source_url"])
                break

    return record


def scrape_archive_years(start: int, end: int, delay: float, output_file: str):
    """Main scraping loop."""
    fieldnames = [
        "year", "date_parsed", "date_raw", "date_confidence",
        "location", "county", "country", "lat", "lon", "os_grid_ref",
        "crop_type", "approx_diameter_m", "approx_area_m2",
        "formation_type", "description", "image_url", "source_url",
        "title_raw", "blt_sampled", "hoax_flag", "notes"
    ]

    # Resume support
    existing_urls = set()
    if os.path.exists(output_file):
        try:
            existing_df = pd.read_csv(output_file)
            existing_urls = set(existing_df["source_url"].dropna().tolist())
            print(f"Resuming: {len(existing_urls)} records already scraped")
        except Exception:
            pass

    write_header = not os.path.exists(output_file) or os.path.getsize(output_file) == 0
    total_new = 0

    with open(output_file, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        if write_header:
            writer.writeheader()

        for year in range(start, end + 1):
            print(f"\n{'='*50}")
            print(f"Processing archive year {year}")
            print(f"{'='*50}")

            # Choose scraping strategy based on year
            if year >= 2010:
                all_stubs = get_formation_links_new_style(year, delay)
            else:
                all_stubs = get_formation_links_old_style(year, delay)

            print(f"  Total formation stubs for {year}: {len(all_stubs)}")

            year_count = 0
            for i, stub in enumerate(all_stubs):
                if stub["source_url"] in existing_urls:
                    continue
                print(f"  [{i+1}/{len(all_stubs)}] {stub['source_url']}")
                record = parse_formation_page(stub, delay)
                writer.writerow(record)
                f.flush()
                existing_urls.add(stub["source_url"])
                year_count += 1
                total_new += 1

            print(f"  Year {year}: {year_count} new records scraped")

    print(f"\n{'='*50}")
    print(f"Archive scraping complete. {total_new} new records added to {output_file}")
    return output_file


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1978)
    parser.add_argument("--end", type=int, default=2013)
    parser.add_argument("--delay", type=float, default=1.2)
    parser.add_argument("--output", default="/home/ubuntu/crop_circle_db/data/ccc_archive_scraped.csv")
    args = parser.parse_args()
    scrape_archive_years(args.start, args.end, args.delay, args.output)
