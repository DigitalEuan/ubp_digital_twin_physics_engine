#!/usr/bin/env python3
"""
scrape_ccc_final.py — Final Production Crop Circle Connector scraper
=====================================================================
Correctly handles CCC's structure:
  - Year page (/{year}/{year}.html) links to month group pages
  - Month group pages link to individual formation pages
  - Formation pages contain date, location, GPS, size data

Key features:
  - Extracts GPS from streetmap.co.uk sv= parameter
  - Extracts OS grid reference
  - Handles all year/month page naming variations
  - Resume-safe incremental output
  - Polite crawling with delays
"""

import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import csv
import os
import math
from datetime import datetime

BASE_URL = "https://www.cropcircleconnector.com"

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
COUNTIES_UK = list(dict.fromkeys(COUNTIES_UK))

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


def fetch_page(url: str, delay: float = 1.2) -> BeautifulSoup | None:
    time.sleep(delay)
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        print(f"  [WARN] Failed: {url}: {e}")
        return None


def extract_gps_from_streetmap(soup_str: str) -> tuple:
    """Extract GPS from streetmap.co.uk sv= parameter — most reliable for UK."""
    m = re.search(r"sv=(-?\d+\.\d+),\+?(-?\d+\.\d+)", soup_str)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return round(lat, 6), round(lon, 6)

    # Google Maps @lat,lon
    m = re.search(r"@(-?\d+\.\d+),(-?\d+\.\d+)", soup_str)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return round(lat, 6), round(lon, 6)

    # Google Maps q=lat,lon
    m = re.search(r"[?&]q=(-?\d+\.\d+),(-?\d+\.\d+)", soup_str)
    if m:
        lat, lon = float(m.group(1)), float(m.group(2))
        if -90 <= lat <= 90 and -180 <= lon <= 180:
            return round(lat, 6), round(lon, 6)

    return None, None


def extract_os_grid(soup_str: str) -> str:
    """Extract OS grid reference."""
    m = re.search(r'\b([A-Z]{2}\d{6,10})\b', soup_str)
    return m.group(1) if m else ""


def parse_date_from_text(text: str, year: int) -> tuple:
    """Parse date from text. Returns (date_parsed, date_raw, confidence)."""
    patterns = [
        (r"[Rr]eported\s+(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", "dmy"),
        (r"(\d{1,2})(?:st|nd|rd|th)?\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})", "dmy"),
        (r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(\d{4})", "mdy"),
        (r"(\d{1,2})/(\d{1,2})/(\d{4})", "dmy_slash"),
    ]

    for pattern, fmt in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            raw = m.group(0)
            try:
                if fmt == "dmy":
                    d, mon_str, y = int(m.group(1)), m.group(2).lower(), int(m.group(3))
                    mon = MONTH_MAP.get(mon_str, 0)
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
    for c_name in COUNTRIES_FOREIGN:
        if c_name.lower() in text.lower():
            return c_name, c_name
    for c in COUNTIES_UK:
        if c.lower() in text.lower():
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


def get_section_pages_from_year(year: int, delay: float) -> list[str]:
    """
    Get the actual section page URLs from the year index page.
    CCC uses relative href links (e.g., 'May2022.html') to month-group pages.
    """
    url = f"{BASE_URL}/{year}/{year}.html"
    print(f"Fetching year index: {url}")
    soup = fetch_page(url, delay)
    if not soup:
        return []

    section_pages = []
    seen = set()
    base_dir = f"{BASE_URL}/{year}/"  # base for relative URLs

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]

        # Skip navigation and non-formation links
        if any(skip in href.lower() for skip in [
            "rumours", "forum", "report", "faq", "contact", "search",
            "advertise", "membership", "weather", "conduct", "policy",
            "news", "conferences", "archives", "state", "researchers",
            "bibliography", "dvds", "videos", "circleshop", "magazines",
            "travelogue", "gallery", "research", "interface", "anasazi",
            "hengeshop", "vitalsigns", "freecounterstat", "youtube",
            "skyhigh", "insight", "sinauctor", "librecad", "bbc",
            "#", "javascript",
        ]):
            continue

        # Build full URL
        if href.startswith("http"):
            full_url = href
        elif href.startswith("/"):
            full_url = f"https://www.cropcircleconnector.com{href}"
        else:
            # Relative URL — resolve against year directory
            full_url = f"{base_dir}{href}"

        # Must be a .html page in the year directory
        if not full_url.endswith(".html"):
            continue
        if f"/{year}/" not in full_url:
            continue
        # Must NOT be the year index itself
        if full_url.endswith(f"/{year}/{year}.html"):
            continue
        # Must be a section page (2 levels: /year/page.html), not a formation sub-page
        path_after_year = full_url.split(f"/{year}/")[-1]
        if "/" in path_after_year:  # formation sub-pages have another /
            continue

        if full_url not in seen:
            seen.add(full_url)
            section_pages.append(full_url)

    print(f"  Found {len(section_pages)} section pages for {year}: {[p.split('/')[-1] for p in section_pages]}")
    return section_pages


def get_formation_links_from_section(section_url: str, year: int, delay: float) -> list[dict]:
    """Get formation links from a section/month page."""
    soup = fetch_page(section_url, delay * 0.4)
    if not soup:
        return []

    records = []
    seen = set()
    # Base directory for resolving relative URLs
    # section_url is like https://www.cropcircleconnector.com/2022/May2022.html
    base_dir = "/".join(section_url.split("/")[:-1]) + "/"  # .../2022/

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        title = a_tag.get_text(strip=True)

        # Skip navigation and non-formation links
        if any(skip in href.lower() for skip in [
            "rumours", "forum", "report", "faq", "contact", "search",
            "advertise", "membership", "weather", "conduct", "policy",
            "news", "conferences", "archives", "state", "researchers",
            "bibliography", "dvds", "videos", "circleshop", "magazines",
            "travelogue", "gallery", "research", "interface", "anasazi",
            "hengeshop", "vitalsigns", "freecounterstat", "youtube",
            "skyhigh", "insight", "sinauctor", "librecad", "bbc",
            "#", "javascript", "groundshots", "diagrams", "fieldreports",
            "comments", "articles", "video",
        ]):
            continue

        # Build full URL
        if href.startswith("http"):
            full_url = href
        elif href.startswith("/"):
            full_url = f"https://www.cropcircleconnector.com{href}"
        else:
            # Relative URL — resolve against section page directory
            full_url = f"{base_dir}{href}"

        if not full_url.endswith(".html"):
            continue

        # Must be a formation sub-page: /year/FormationName/page.html
        # i.e., has a subdirectory under the year
        if f"/{year}/" not in full_url:
            continue
        path_after_year = full_url.split(f"/{year}/")[-1]
        if "/" not in path_after_year:  # must have a subdirectory
            continue

        # Sanity check: the subdirectory name should look like a formation name
        # (not a year like 2020, not a navigation keyword)
        subdir = path_after_year.split("/")[0]
        if re.match(r'^\d{4}$', subdir):  # skip year-only subdirs
            continue
        if any(nav in subdir.lower() for nav in [
            "september", "october", "november", "december", "january",
            "february", "march", "april", "may", "june", "july", "august",
        ]):
            continue

        if full_url not in seen:
            seen.add(full_url)
            records.append({
                "year": year,
                "source_url": full_url,
                "title_raw": title if len(title) > 3 else "",
            })

    return records


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

    # GPS from streetmap
    lat, lon = extract_gps_from_streetmap(soup_str)
    if lat is not None:
        record["lat"] = lat
        record["lon"] = lon

    # OS Grid Reference
    record["os_grid_ref"] = extract_os_grid(soup_str)

    # Date (title first, then body)
    combined_text = page_title + " " + body_text[:3000]
    date_parsed, date_raw, confidence = parse_date_from_text(combined_text, stub["year"])
    record["date_parsed"] = date_parsed
    record["date_raw"] = date_raw
    record["date_confidence"] = confidence

    # County/Country
    county, country = extract_county_country(page_title + " " + body_text[:2000])
    record["county"] = county
    record["country"] = country

    # Location from title
    loc_match = re.search(r"[Cc]rop [Cc]ircle (?:at|near|in)\s+(.+?)\.\s+[Rr]eported", page_title)
    if loc_match:
        record["location"] = loc_match.group(1).strip()[:120]
    else:
        loc = re.sub(r"[Cc]rop [Cc]ircle(?: [Cc]onnector)?", "", page_title)
        loc = re.sub(r"[Rr]eported.*", "", loc)
        loc = loc.strip(" .-|,")
        record["location"] = loc[:120] if loc else ""

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
                                         "free to view", "crop circle connector"]):
            record["description"] = text[:600]
            break

    # First image
    for img in soup.find_all("img", src=True):
        src = img["src"]
        if any(ext in src.lower() for ext in [".jpg", ".jpeg", ".png"]):
            if not any(skip in src.lower() for skip in ["logo", "banner", "button", "nav", "icon"]):
                record["image_url"] = src if src.startswith("http") else f"{BASE_URL}/{src.lstrip('/')}"
                break

    return record


def scrape_all_years(start: int, end: int, delay: float, output_file: str):
    """Main scraping loop with resume support."""
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
            print(f"Processing year {year}")
            print(f"{'='*50}")

            # Get section pages from year index
            section_pages = get_section_pages_from_year(year, delay)

            # Collect formation stubs from all section pages
            all_stubs = []
            seen_urls = set()
            for sp in section_pages:
                stubs = get_formation_links_from_section(sp, year, delay)
                for stub in stubs:
                    if stub["source_url"] not in seen_urls:
                        seen_urls.add(stub["source_url"])
                        all_stubs.append(stub)

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
    print(f"Scraping complete. {total_new} new records added to {output_file}")
    return output_file


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1990)
    parser.add_argument("--end", type=int, default=2024)
    parser.add_argument("--delay", type=float, default=1.2)
    parser.add_argument("--output", default="/home/ubuntu/crop_circle_db/data/ccc_scraped.csv")
    args = parser.parse_args()
    scrape_all_years(args.start, args.end, args.delay, args.output)
