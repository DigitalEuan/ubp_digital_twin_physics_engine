#!/usr/bin/env python3
"""
enrich_and_merge.py — Enrich crop circle data and merge with solar data
=======================================================================
Steps:
  1. Load all scraped crop circle data (CCC + archive + seed data)
  2. Convert OS grid references to WGS84 lat/lon
  3. Geocode remaining records without GPS using Nominatim
  4. Compute sun position (azimuth, elevation, day length) for each formation
  5. Join with solar daily data (on date)
  6. Compute ±7-day solar windows (pre/post averages and extremes)
  7. Add derived features for hypothesis testing
  8. Output single comprehensive CSV

Sun position algorithm: USNO/NOAA solar position algorithm
OS Grid conversion: OSGB36 to WGS84 (Ordnance Survey standard)
"""

import pandas as pd
import numpy as np
import math
import re
import os
import time
import requests
from datetime import datetime, timedelta

# ─────────────────────────────────────────────────────────────
# OS GRID REFERENCE → WGS84 CONVERSION
# ─────────────────────────────────────────────────────────────

# OS National Grid letter pairs
OS_GRID_LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"  # I is omitted

def osgb_to_wgs84(grid_ref: str) -> tuple:
    """
    Convert OS National Grid reference (e.g., SU123456) to WGS84 lat/lon.
    Uses the standard OSGB36 to WGS84 Helmert transform.
    Returns (lat, lon) or (None, None) if invalid.
    """
    if not grid_ref or len(grid_ref) < 6:
        return None, None

    grid_ref = grid_ref.strip().upper().replace(" ", "")

    # Extract letter prefix (2 letters) and numeric part
    m = re.match(r'^([A-Z]{2})(\d+)$', grid_ref)
    if not m:
        return None, None

    letters, digits = m.group(1), m.group(2)

    # Must be even number of digits
    if len(digits) % 2 != 0:
        digits = digits + "0"

    half = len(digits) // 2
    easting_str = digits[:half].ljust(5, "0")
    northing_str = digits[half:].ljust(5, "0")

    try:
        e_partial = int(easting_str)
        n_partial = int(northing_str)
    except ValueError:
        return None, None

    # Convert letters to 500km grid offsets
    # First letter: 500km squares from false origin
    # Second letter: 100km squares within that
    l1 = OS_GRID_LETTERS.index(letters[0])
    l2 = OS_GRID_LETTERS.index(letters[1])

    # False origin is 500km W and 100km N of true origin
    # Grid is 5x5 of 500km squares
    e500 = ((l1 - 2) % 5) * 5 + (l2 % 5)
    n500 = (19 - (l1 // 5) * 5) - (l2 // 5)

    easting = e500 * 100000 + e_partial * 10 if half < 5 else e500 * 100000 + e_partial
    northing = n500 * 100000 + n_partial * 10 if half < 5 else n500 * 100000 + n_partial

    # Adjust for 100km grid
    easting = (e500 % 5) * 100000 + e_partial * (10 ** (5 - half))
    northing = (n500 % 5) * 100000 + n_partial * (10 ** (5 - half))

    # Add 500km offsets
    easting += ((l1 - 2) % 5) * 500000
    northing += (19 - (l1 // 5) * 5 - l2 // 5) * 500000

    # Correct for false origin
    # The OS grid false origin is 400km W and 100km N of OSGB36 origin
    # OSGB36 origin is at 49°N, 2°W
    # False origin offset: E = 400000, N = -100000 (i.e., subtract from easting, add to northing)
    # Actually the standard formula:
    easting = easting - 400000 + ((l1 - 2) % 5) * 500000
    northing = northing + 100000 + (19 - (l1 // 5) * 5 - l2 // 5) * 500000

    # Recalculate properly
    # OSGB36 National Grid: false easting = 400000m, false northing = -100000m
    # Letter grid: 500km squares labelled A-Z (no I)
    # First letter: major 500km square
    # Second letter: 100km square within major

    # Correct implementation:
    e_major = (l1 % 5) * 500000
    n_major = (4 - l1 // 5) * 500000

    e_minor = (l2 % 5) * 100000
    n_minor = (4 - l2 // 5) * 100000

    # Scale factor for partial digits
    scale = 10 ** (5 - half)

    E = e_major + e_minor + e_partial * scale - 1000000  # remove false origin offset
    N = n_major + n_minor + n_partial * scale - 500000

    # Helmert transform OSGB36 → WGS84
    # Parameters from OS document "A guide to coordinate systems in Great Britain"
    a_osgb = 6377563.396  # Airy 1830 semi-major axis
    b_osgb = 6356256.910  # Airy 1830 semi-minor axis
    f0 = 0.9996012717    # scale factor on central meridian
    lat0 = math.radians(49)   # true origin latitude
    lon0 = math.radians(-2)   # true origin longitude (2°W)
    N0 = -100000.0  # northing of true origin
    E0 = 400000.0   # easting of true origin
    e2_osgb = 1 - (b_osgb / a_osgb) ** 2

    # Iterative conversion from E,N to lat,lon (OSGB36)
    n_param = (a_osgb - b_osgb) / (a_osgb + b_osgb)
    lat = lat0

    for _ in range(100):
        M = b_osgb * f0 * (
            (1 + n_param + 5/4 * n_param**2 + 5/4 * n_param**3) * (lat - lat0)
            - (3*n_param + 3*n_param**2 + 21/8 * n_param**3) * math.sin(lat - lat0) * math.cos(lat + lat0)
            + (15/8 * n_param**2 + 15/8 * n_param**3) * math.sin(2*(lat - lat0)) * math.cos(2*(lat + lat0))
            - (35/24 * n_param**3) * math.sin(3*(lat - lat0)) * math.cos(3*(lat + lat0))
        )
        lat_new = (N - N0 - M) / (a_osgb * f0) + lat
        if abs(lat_new - lat) < 1e-12:
            lat = lat_new
            break
        lat = lat_new

    nu = a_osgb * f0 / math.sqrt(1 - e2_osgb * math.sin(lat)**2)
    rho = a_osgb * f0 * (1 - e2_osgb) / (1 - e2_osgb * math.sin(lat)**2)**1.5
    eta2 = nu / rho - 1

    tan_lat = math.tan(lat)
    sec_lat = 1 / math.cos(lat)

    VII = tan_lat / (2 * rho * nu)
    VIII = tan_lat / (24 * rho * nu**3) * (5 + 3*tan_lat**2 + eta2 - 9*tan_lat**2*eta2)
    IX = tan_lat / (720 * rho * nu**5) * (61 + 90*tan_lat**2 + 45*tan_lat**4)
    X = sec_lat / nu
    XI = sec_lat / (6 * nu**3) * (nu/rho + 2*tan_lat**2)
    XII = sec_lat / (120 * nu**5) * (5 + 28*tan_lat**2 + 24*tan_lat**4)
    XIIA = sec_lat / (5040 * nu**7) * (61 + 662*tan_lat**2 + 1320*tan_lat**4 + 720*tan_lat**6)

    dE = E - E0
    lat_osgb = lat - VII*dE**2 + VIII*dE**4 - IX*dE**6
    lon_osgb = lon0 + X*dE - XI*dE**3 + XII*dE**5 - XIIA*dE**7

    # Helmert transform OSGB36 → WGS84
    # Translation (metres), rotation (seconds), scale (ppm)
    tx, ty, tz = 446.448, -125.157, 542.060
    rx = math.radians(0.1502 / 3600)
    ry = math.radians(0.2470 / 3600)
    rz = math.radians(0.8421 / 3600)
    s = 20.4894e-6

    # Convert OSGB36 lat/lon to Cartesian
    a_osgb_val = a_osgb
    nu_c = a_osgb_val / math.sqrt(1 - e2_osgb * math.sin(lat_osgb)**2)
    x_osgb = nu_c * math.cos(lat_osgb) * math.cos(lon_osgb)
    y_osgb = nu_c * math.cos(lat_osgb) * math.sin(lon_osgb)
    z_osgb = nu_c * (1 - e2_osgb) * math.sin(lat_osgb)

    # Apply Helmert transform
    x_wgs = tx + (1 + s) * (x_osgb - rz*y_osgb + ry*z_osgb)
    y_wgs = ty + (1 + s) * (rz*x_osgb + y_osgb - rx*z_osgb)
    z_wgs = tz + (1 + s) * (-ry*x_osgb + rx*y_osgb + z_osgb)

    # Convert WGS84 Cartesian to lat/lon
    a_wgs = 6378137.0
    b_wgs = 6356752.3142
    e2_wgs = 1 - (b_wgs / a_wgs)**2

    p = math.sqrt(x_wgs**2 + y_wgs**2)
    lat_wgs = math.atan2(z_wgs, p * (1 - e2_wgs))

    for _ in range(10):
        nu_w = a_wgs / math.sqrt(1 - e2_wgs * math.sin(lat_wgs)**2)
        lat_new = math.atan2(z_wgs + e2_wgs * nu_w * math.sin(lat_wgs), p)
        if abs(lat_new - lat_wgs) < 1e-12:
            lat_wgs = lat_new
            break
        lat_wgs = lat_new

    lon_wgs = math.atan2(y_wgs, x_wgs)

    lat_deg = round(math.degrees(lat_wgs), 6)
    lon_deg = round(math.degrees(lon_wgs), 6)

    # Sanity check: UK bounds
    if 49.0 <= lat_deg <= 61.0 and -8.5 <= lon_deg <= 2.0:
        return lat_deg, lon_deg
    return None, None


# ─────────────────────────────────────────────────────────────
# FAST GEOCODING: LOOKUP TABLE + NOMINATIM FALLBACK
# ─────────────────────────────────────────────────────────────

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
NOMINATIM_HEADERS = {
    "User-Agent": "CropCircleSolarResearch/1.0 (contact: info@digitaleuan.com)"
}

_geocode_cache = {}
_GEOCODE_CACHE_FILE = "/home/ubuntu/crop_circle_db/data/geocode_cache.json"


def _load_geocode_cache():
    """Load geocoding cache from disk."""
    import json
    global _geocode_cache
    if os.path.exists(_GEOCODE_CACHE_FILE):
        try:
            with open(_GEOCODE_CACHE_FILE, 'r') as f:
                data = json.load(f)
                # Convert lists back to tuples
                _geocode_cache = {k: tuple(v) if v is not None else (None, None)
                                  for k, v in data.items()}
            print(f"  Loaded {len(_geocode_cache)} cached geocoding results")
        except Exception as e:
            print(f"  [WARN] Could not load geocode cache: {e}")


def _save_geocode_cache():
    """Save geocoding cache to disk."""
    import json
    try:
        os.makedirs(os.path.dirname(_GEOCODE_CACHE_FILE), exist_ok=True)
        with open(_GEOCODE_CACHE_FILE, 'w') as f:
            json.dump(_geocode_cache, f)
    except Exception as e:
        print(f"  [WARN] Could not save geocode cache: {e}")


# Pre-built lookup table of common crop circle locations
# Sources: known GPS from CCC pages, OS maps, Wikipedia
LOCATION_LOOKUP = {
    # Wiltshire hotspots
    "avebury": (51.4285, -1.8544),
    "silbury hill": (51.4153, -1.8575),
    "windmill hill": (51.4389, -1.8694),
    "west kennet": (51.4056, -1.8411),
    "hackpen hill": (51.4667, -1.8167),
    "milk hill": (51.3756, -1.8644),
    "alton barnes": (51.3667, -1.8167),
    "alton priors": (51.3667, -1.8167),
    "east field": (51.3667, -1.8167),
    "stanton st bernard": (51.3667, -1.8167),
    "pewsey": (51.3414, -1.7672),
    "martinsell hill": (51.3500, -1.7333),
    "picked hill": (51.3500, -1.7833),
    "knap hill": (51.3667, -1.8333),
    "devizes": (51.3528, -1.9953),
    "bishops cannings": (51.3833, -1.9500),
    "roundway hill": (51.3833, -1.9833),
    "calne": (51.4378, -2.0044),
    "cherhill": (51.4333, -1.9833),
    "oldbury castle": (51.4333, -1.9833),
    "beckhampton": (51.4167, -1.8833),
    "yatesbury": (51.4500, -1.8667),
    "winterbourne bassett": (51.4667, -1.8500),
    "broad hinton": (51.4667, -1.8167),
    "barbury castle": (51.5000, -1.7833),
    "chiseldon": (51.5167, -1.7500),
    "wroughton": (51.5333, -1.7833),
    "swindon": (51.5558, -1.7797),
    "marlborough": (51.4194, -1.7278),
    "savernake": (51.4000, -1.6833),
    "tidcombe": (51.3167, -1.6500),
    "ludgershall": (51.2500, -1.6167),
    "tidworth": (51.2333, -1.6667),
    "stonehenge": (51.1789, -1.8262),
    "amesbury": (51.1744, -1.7744),
    "boscombe down": (51.1667, -1.7500),
    "larkhill": (51.2000, -1.8167),
    "durrington": (51.2000, -1.7833),
    "woodhenge": (51.1944, -1.7889),
    "winterbourne stoke": (51.1667, -1.8833),
    "shrewton": (51.1833, -1.9167),
    "tilshead": (51.2167, -1.9833),
    "bratton": (51.2667, -2.1333),
    "westbury": (51.2617, -2.1878),
    "warminster": (51.2050, -2.1806),
    "heytesbury": (51.1833, -2.0667),
    "codford": (51.1667, -2.0167),
    "chitterne": (51.2000, -2.0167),
    "imber": (51.2167, -2.0167),
    "potterne": (51.3333, -2.0000),
    "all cannings": (51.3667, -1.9167),
    "stanton st bernard": (51.3667, -1.8167),
    "woodborough": (51.3500, -1.8000),
    "honeystreet": (51.3667, -1.8167),
    "pewsey vale": (51.3500, -1.7833),
    "wanborough": (51.5167, -1.7167),
    "liddington": (51.5167, -1.7000),
    "aldbourne": (51.4833, -1.6333),
    "ramsbury": (51.4500, -1.5833),
    "ogbourne st george": (51.4833, -1.7333),
    "ogbourne st andrew": (51.4833, -1.7500),
    "manton": (51.4333, -1.7333),
    "fyfield": (51.4167, -1.7333),
    "lockeridge": (51.4167, -1.7833),
    "east kennett": (51.4000, -1.8000),
    "shaw": (51.4167, -1.9167),
    "melksham": (51.3733, -2.1378),
    "corsham": (51.4333, -2.1833),
    "lacock": (51.4167, -2.1167),
    "chippenham": (51.4583, -2.1167),
    "bremhill": (51.4667, -2.0167),
    "hilmarton": (51.4833, -1.9833),
    "compton bassett": (51.4667, -1.9500),
    "heddington": (51.4167, -2.0167),
    "sandy lane": (51.4167, -2.0833),
    "bowden hill": (51.4167, -2.1167),
    "seend": (51.3500, -2.0667),
    "etchilhampton": (51.3500, -1.9833),
    "chirton": (51.3500, -1.9500),
    "marden": (51.3500, -1.9167),
    "beechingstoke": (51.3500, -1.8667),
    "manningford": (51.3333, -1.8167),
    "rushall": (51.3333, -1.8500),
    "upavon": (51.2833, -1.7833),
    "enford": (51.2667, -1.7833),
    "fittleton": (51.2500, -1.7667),
    "netheravon": (51.2500, -1.7833),
    "haxton": (51.2333, -1.7833),
    "figheldean": (51.2333, -1.7667),
    "milston": (51.2167, -1.7667),
    "boscombe": (51.1667, -1.7500),
    "idmiston": (51.1167, -1.7333),
    "porton": (51.1333, -1.7167),
    # Hampshire hotspots
    "cheesefoot head": (51.0667, -1.2667),
    "winchester": (51.0632, -1.3080),
    "chilcomb": (51.0500, -1.2833),
    "morestead": (51.0167, -1.2833),
    "twyford": (51.0167, -1.3167),
    "owslebury": (51.0000, -1.2833),
    "longwood": (51.0833, -1.2500),
    "punchbowl": (51.0667, -1.2667),
    "telegraph hill": (51.0667, -1.2667),
    "litchfield": (51.2167, -1.3667),
    "newbury": (51.4014, -1.3222),
    "andover": (51.2083, -1.4833),
    "basingstoke": (51.2667, -1.0833),
    "petersfield": (51.0000, -0.9333),
    "alresford": (51.0833, -1.1667),
    "alton": (51.1500, -1.0833),
    "east meon": (51.0000, -1.0500),
    "east stratton": (51.1167, -1.2167),
    "micheldever": (51.1500, -1.2500),
    "sutton scotney": (51.1667, -1.3167),
    "crawley": (51.1167, -1.3500),
    "sparsholt": (51.0833, -1.3833),
    "stockbridge": (51.1000, -1.5000),
    "broughton": (51.0833, -1.5500),
    "middle wallop": (51.1500, -1.5833),
    "nether wallop": (51.1333, -1.5667),
    "over wallop": (51.1500, -1.5833),
    "danebury": (51.1167, -1.5500),
    "grateley": (51.1667, -1.6167),
    "quarley": (51.2000, -1.5833),
    "amport": (51.2000, -1.5667),
    "monxton": (51.2000, -1.5333),
    "abbotts ann": (51.2000, -1.5000),
    "goodworth clatford": (51.1833, -1.4667),
    "upper clatford": (51.1833, -1.4833),
    "anna valley": (51.1833, -1.4833),
    "weyhill": (51.2167, -1.5333),
    "penton mewsey": (51.2167, -1.5000),
    "tangley": (51.2500, -1.5167),
    "upton": (51.2667, -1.4833),
    "hurstbourne tarrant": (51.2833, -1.4667),
    "vernham dean": (51.3167, -1.4667),
    # Dorset
    "dorchester": (50.7154, -2.4401),
    "maiden castle": (50.6944, -2.4722),
    "blandford": (50.8556, -2.1611),
    "shaftesbury": (51.0044, -2.1983),
    "gillingham": (51.0333, -2.2667),
    "sherborne": (50.9467, -2.5167),
    "yeovil": (50.9425, -2.6350),
    "bridport": (50.7333, -2.7583),
    "weymouth": (50.6139, -2.4583),
    "swanage": (50.6083, -1.9583),
    "wareham": (50.6875, -2.1083),
    "poole": (50.7167, -1.9833),
    "bournemouth": (50.7192, -1.8808),
    "christchurch": (50.7333, -1.7833),
    "wimborne": (50.8000, -1.9833),
    "cranborne": (50.9167, -1.9833),
    "sixpenny handley": (50.9167, -2.0167),
    "tollard royal": (50.9667, -2.0833),
    "ebbesbourne wake": (51.0167, -2.0167),
    # Somerset
    "glastonbury": (51.1489, -2.7167),
    "shepton mallet": (51.1833, -2.5500),
    "wells": (51.2083, -2.6500),
    "taunton": (51.0150, -3.1000),
    "bridgwater": (51.1278, -2.9958),
    "frome": (51.2283, -2.3200),
    "bruton": (51.1167, -2.4667),
    "castle cary": (51.0833, -2.5167),
    "somerton": (51.0583, -2.7333),
    "langport": (51.0333, -2.8333),
    "chard": (50.8717, -2.9633),
    "ilminster": (50.9283, -2.9133),
    "crewkerne": (50.8833, -2.7833),
    "martock": (50.9833, -2.7833),
    "stoke sub hamdon": (50.9667, -2.7500),
    "montacute": (50.9500, -2.7167),
    # Oxfordshire
    "oxford": (51.7520, -1.2577),
    "abingdon": (51.6714, -1.2833),
    "didcot": (51.6083, -1.2417),
    "wantage": (51.5833, -1.4250),
    "faringdon": (51.6583, -1.5833),
    "grove": (51.5833, -1.4167),
    "uffington": (51.5833, -1.5833),
    "white horse hill": (51.5778, -1.5667),
    "dragon hill": (51.5778, -1.5667),
    "wayland smithy": (51.5667, -1.5833),
    "lambourn": (51.5167, -1.5333),
    "hungerford": (51.4167, -1.5167),
    # Gloucestershire
    "gloucester": (51.8642, -2.2442),
    "cheltenham": (51.9000, -2.0667),
    "cirencester": (51.7167, -1.9667),
    "stroud": (51.7500, -2.2167),
    "tetbury": (51.6333, -2.1667),
    "malmesbury": (51.5833, -2.1000),
    "sherston": (51.5833, -2.1667),
    "hullavington": (51.5500, -2.1500),
    "stanton st quintin": (51.5333, -2.1167),
    "kemble": (51.6667, -2.0000),
    "south cerney": (51.6667, -1.9333),
    "cricklade": (51.6333, -1.8667),
    "highworth": (51.6333, -1.7167),
    # Berkshire
    "reading": (51.4542, -0.9731),
    "wokingham": (51.4111, -0.8333),
    "bracknell": (51.4153, -0.7500),
    "maidenhead": (51.5222, -0.7167),
    "windsor": (51.4839, -0.6044),
    "slough": (51.5083, -0.5917),
    "marlow": (51.5667, -0.7750),
    "henley": (51.5333, -0.9000),
    # Wiltshire general
    "wiltshire": (51.3500, -1.9833),
    "hampshire": (51.0667, -1.3080),
    "dorset": (50.7500, -2.3333),
    "somerset": (51.1000, -2.7500),
    "oxfordshire": (51.7500, -1.2500),
    "gloucestershire": (51.8333, -2.2500),
    "berkshire": (51.4500, -1.1667),
    "kent": (51.2667, 0.5333),
    "essex": (51.7667, 0.5000),
    "suffolk": (52.1833, 0.9833),
    "norfolk": (52.6167, 1.0000),
    "lincolnshire": (53.2333, -0.5333),
    "yorkshire": (53.9583, -1.0833),
    "lancashire": (53.7500, -2.5000),
    "cheshire": (53.1667, -2.5000),
    "shropshire": (52.7000, -2.7500),
    "worcestershire": (52.1833, -2.2500),
    "warwickshire": (52.2833, -1.5833),
    "northamptonshire": (52.2833, -0.9000),
    "cambridgeshire": (52.2000, 0.1167),
    "hertfordshire": (51.8000, -0.2333),
    "buckinghamshire": (51.8000, -0.8333),
    "surrey": (51.3167, -0.4333),
    "sussex": (50.9167, -0.0833),
    "devon": (50.7167, -3.5333),
    "cornwall": (50.3333, -4.8333),
    # International
    "germany": (51.1657, 10.4515),
    "france": (46.2276, 2.2137),
    "netherlands": (52.1326, 5.2913),
    "belgium": (50.5039, 4.4699),
    "italy": (41.8719, 12.5674),
    "spain": (40.4637, -3.7492),
    "czech republic": (49.8175, 15.4730),
    "poland": (51.9194, 19.1451),
    "russia": (61.5240, 105.3188),
    "ukraine": (48.3794, 31.1656),
    "canada": (56.1304, -106.3468),
    "australia": (-25.2744, 133.7751),
    "new zealand": (-40.9006, 174.8860),
    "brazil": (-14.2350, -51.9253),
    "argentina": (-38.4161, -63.6167),
    "chile": (-35.6751, -71.5430),
    "usa": (37.0902, -95.7129),
    "united states": (37.0902, -95.7129),
    "japan": (36.2048, 138.2529),
    "china": (35.8617, 104.1954),
    "india": (20.5937, 78.9629),
    "south africa": (-30.5595, 22.9375),
    "mexico": (23.6345, -102.5528),
    "switzerland": (46.8182, 8.2275),
    "austria": (47.5162, 14.5501),
    "hungary": (47.1625, 19.5033),
    "romania": (45.9432, 24.9668),
    "bulgaria": (42.7339, 25.4858),
    "croatia": (45.1000, 15.2000),
    "slovakia": (48.6690, 19.6990),
    "sweden": (60.1282, 18.6435),
    "norway": (60.4720, 8.4689),
    "denmark": (56.2639, 9.5018),
    "finland": (61.9241, 25.7482),
    "portugal": (39.3999, -8.2245),
    "turkey": (38.9637, 35.2433),
    "israel": (31.0461, 34.8516),
    "iran": (32.4279, 53.6880),
    "pakistan": (30.3753, 69.3451),
}


def lookup_location(location: str, country: str = "UK") -> tuple:
    """Fast lookup using pre-built table of known crop circle locations."""
    if not location:
        return None, None

    loc_lower = location.lower()
    # Remove common prefixes
    loc_lower = re.sub(r'^(nr|near|at|in|the)\s+', '', loc_lower)
    loc_lower = re.sub(r'\s+', ' ', loc_lower).strip()

    # Try progressively shorter matches
    # First: exact match
    if loc_lower in LOCATION_LOOKUP:
        return LOCATION_LOOKUP[loc_lower]

    # Second: check if any known place name is in the location string
    # Sort by length descending to prefer more specific matches
    for place, coords in sorted(LOCATION_LOOKUP.items(), key=lambda x: -len(x[0])):
        if place in loc_lower:
            return coords

    return None, None


def geocode_location(location: str, country: str = "UK") -> tuple:
    """Geocode a location string: fast lookup first, then Nominatim fallback."""
    if not location or len(location) < 5:
        return None, None

    # Clean up location
    loc = re.sub(r'\s+', ' ', location).strip()
    loc = re.sub(r'^at\s+', '', loc, flags=re.IGNORECASE)

    cache_key = f"{loc}|{country}"
    if cache_key in _geocode_cache:
        return _geocode_cache[cache_key]

    # Step 1: Fast lookup table
    lat, lon = lookup_location(loc, country)
    if lat is not None:
        _geocode_cache[cache_key] = (lat, lon)
        return lat, lon

    # Step 2: Nominatim fallback (rate-limited)
    queries = []
    if country == "UK":
        queries.append(f"{loc}, United Kingdom")
    elif country not in ["", "UK"]:
        queries.append(f"{loc}, {country}")
    queries.append(loc)

    for query in queries:
        try:
            time.sleep(1.1)  # Nominatim rate limit: 1 req/sec
            r = requests.get(
                NOMINATIM_URL,
                params={"q": query, "format": "json", "limit": 1},
                headers=NOMINATIM_HEADERS,
                timeout=10
            )
            r.raise_for_status()
            results = r.json()
            if results:
                lat = float(results[0]["lat"])
                lon = float(results[0]["lon"])
                _geocode_cache[cache_key] = (round(lat, 6), round(lon, 6))
                return round(lat, 6), round(lon, 6)
        except Exception:
            pass

    _geocode_cache[cache_key] = (None, None)
    return None, None


# ─────────────────────────────────────────────────────────────
# SUN POSITION CALCULATION
# ─────────────────────────────────────────────────────────────

def solar_position(date_str: str, lat: float, lon: float) -> dict:
    """
    Compute solar position for a given date and location.
    Uses NOAA Solar Position Algorithm (simplified).
    Returns dict with:
      - solar_noon_utc: time of solar noon (hours UTC)
      - solar_elevation_noon: elevation at solar noon (degrees)
      - solar_azimuth_noon: azimuth at solar noon (degrees from N)
      - day_length_hours: length of day (hours)
      - sunrise_utc: sunrise time (hours UTC)
      - sunset_utc: sunset time (hours UTC)
      - solar_declination: sun's declination (degrees)
      - equation_of_time: equation of time (minutes)
    """
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        return {}

    # Julian Day Number
    jd = dt.toordinal() + 1721425.5

    # Julian Century
    jc = (jd - 2451545.0) / 36525.0

    # Geometric mean longitude of sun (degrees)
    l0 = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360

    # Geometric mean anomaly of sun (degrees)
    m = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)

    # Equation of center
    m_rad = math.radians(m)
    c = (math.sin(m_rad) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
         + math.sin(2 * m_rad) * (0.019993 - 0.000101 * jc)
         + math.sin(3 * m_rad) * 0.000289)

    # Sun's true longitude
    sun_lon = l0 + c

    # Apparent longitude
    omega = 125.04 - 1934.136 * jc
    app_lon = sun_lon - 0.00569 - 0.00478 * math.sin(math.radians(omega))

    # Obliquity of ecliptic
    mean_obliq = 23 + (26 + (21.448 - jc * (46.8150 + jc * (0.00059 - jc * 0.001813))) / 60) / 60
    obliq_corr = mean_obliq + 0.00256 * math.cos(math.radians(omega))

    # Sun's declination
    declination = math.degrees(math.asin(
        math.sin(math.radians(obliq_corr)) * math.sin(math.radians(app_lon))
    ))

    # Equation of time (minutes)
    y = math.tan(math.radians(obliq_corr / 2)) ** 2
    l0_rad = math.radians(l0)
    m_rad2 = math.radians(m)
    eot = 4 * math.degrees(
        y * math.sin(2 * l0_rad)
        - 2 * 0.016708634 * math.sin(m_rad2)
        + 4 * 0.016708634 * y * math.sin(m_rad2) * math.cos(2 * l0_rad)
        - 0.5 * y**2 * math.sin(4 * l0_rad)
        - 1.25 * 0.016708634**2 * math.sin(2 * m_rad2)
    )

    # Hour angle at sunrise/sunset
    lat_rad = math.radians(lat)
    decl_rad = math.radians(declination)

    cos_ha = (math.cos(math.radians(90.833)) / (math.cos(lat_rad) * math.cos(decl_rad))
              - math.tan(lat_rad) * math.tan(decl_rad))

    if cos_ha > 1:
        # Polar night
        return {
            "solar_declination": round(declination, 4),
            "equation_of_time_min": round(eot, 4),
            "day_length_hours": 0.0,
            "sunrise_utc": None,
            "sunset_utc": None,
            "solar_noon_utc": None,
            "solar_elevation_noon": round(90 - lat + declination, 2),
            "solar_azimuth_noon": 180.0 if lat >= 0 else 0.0,
        }
    elif cos_ha < -1:
        # Midnight sun
        return {
            "solar_declination": round(declination, 4),
            "equation_of_time_min": round(eot, 4),
            "day_length_hours": 24.0,
            "sunrise_utc": 0.0,
            "sunset_utc": 24.0,
            "solar_noon_utc": 12.0,
            "solar_elevation_noon": round(90 - lat + declination, 2),
            "solar_azimuth_noon": 180.0 if lat >= 0 else 0.0,
        }

    ha_sunrise = math.degrees(math.acos(cos_ha))

    # Solar noon (UTC hours)
    solar_noon_utc = (720 - 4 * lon - eot) / 60

    # Sunrise and sunset (UTC hours)
    sunrise_utc = solar_noon_utc - ha_sunrise / 15
    sunset_utc = solar_noon_utc + ha_sunrise / 15
    day_length = 2 * ha_sunrise / 15

    # Solar elevation at noon
    elevation_noon = 90 - lat + declination

    # Solar azimuth at noon (180° = due south in northern hemisphere)
    azimuth_noon = 180.0 if lat >= 0 else 0.0

    return {
        "solar_declination": round(declination, 4),
        "equation_of_time_min": round(eot, 4),
        "day_length_hours": round(day_length, 3),
        "sunrise_utc": round(sunrise_utc, 3),
        "sunset_utc": round(sunset_utc, 3),
        "solar_noon_utc": round(solar_noon_utc, 3),
        "solar_elevation_noon": round(elevation_noon, 2),
        "solar_azimuth_noon": azimuth_noon,
    }


# ─────────────────────────────────────────────────────────────
# SOLAR WINDOW CALCULATIONS
# ─────────────────────────────────────────────────────────────

def compute_solar_windows(df_cc: pd.DataFrame, df_solar: pd.DataFrame, window_days: int = 7) -> pd.DataFrame:
    """
    For each crop circle, compute solar statistics for:
      - N days before the formation date
      - N days after the formation date
      - The formation date itself
    """
    df_solar_indexed = df_solar.set_index("date")

    solar_cols = [
        "Kp_sum_best", "Kp_max_best", "Kp_mean_best",
        "SW_speed_mean", "SW_speed_max",
        "IMF_Bz_GSM_mean", "IMF_Bz_GSM_min",
        "Proton_density", "Flow_pressure",
        "Dst_min", "Dst_mean",
        "SSN_best", "F10_7_best",
        "G_storm_level",
    ]

    result_rows = []

    for _, row in df_cc.iterrows():
        date_str = row.get("date_parsed", "")
        try:
            date = pd.Timestamp(date_str)
        except Exception:
            result_rows.append({})
            continue

        # Formation date solar data
        day_data = {}
        if date in df_solar_indexed.index:
            for col in solar_cols:
                if col in df_solar_indexed.columns:
                    day_data[f"solar_{col}"] = df_solar_indexed.loc[date, col]

        # Pre-window (N days before)
        pre_start = date - pd.Timedelta(days=window_days)
        pre_dates = pd.date_range(pre_start, date - pd.Timedelta(days=1))
        pre_data = df_solar_indexed.reindex(pre_dates)

        for col in ["Kp_max_best", "Kp_sum_best", "SW_speed_max", "Dst_min", "SSN_best", "F10_7_best"]:
            if col in pre_data.columns:
                day_data[f"pre{window_days}d_{col}_mean"] = pre_data[col].mean()
                day_data[f"pre{window_days}d_{col}_max"] = pre_data[col].max()

        # Post-window (N days after)
        post_end = date + pd.Timedelta(days=window_days)
        post_dates = pd.date_range(date + pd.Timedelta(days=1), post_end)
        post_data = df_solar_indexed.reindex(post_dates)

        for col in ["Kp_max_best", "Kp_sum_best", "SW_speed_max", "Dst_min", "SSN_best", "F10_7_best"]:
            if col in post_data.columns:
                day_data[f"post{window_days}d_{col}_mean"] = post_data[col].mean()
                day_data[f"post{window_days}d_{col}_max"] = post_data[col].max()

        # Storm count in window
        if "G_storm_level" in df_solar_indexed.columns:
            window_dates = pd.date_range(pre_start, post_end)
            window_data = df_solar_indexed.reindex(window_dates)
            day_data["storms_G1plus_in_window"] = (window_data["G_storm_level"] >= 1).sum()
            day_data["storms_G2plus_in_window"] = (window_data["G_storm_level"] >= 2).sum()
            day_data["storms_G3plus_in_window"] = (window_data["G_storm_level"] >= 3).sum()

        result_rows.append(day_data)

    return pd.DataFrame(result_rows)


# ─────────────────────────────────────────────────────────────
# SEED DATA
# ─────────────────────────────────────────────────────────────

SEED_DATA = [
    # High-quality formations with known GPS coordinates and measurements
    # Source: BLT Research, Haselhoff, CCDB, Wikipedia
    {"year": 1991, "date_parsed": "1991-07-11", "date_confidence": "exact",
     "location": "Barbury Castle, Nr Wroughton, Wiltshire",
     "county": "Wiltshire", "country": "UK", "lat": 51.5394, "lon": -1.7706,
     "approx_diameter_m": 183.0, "approx_area_m2": 26326.0,
     "formation_type": "pictogram", "crop_type": "wheat",
     "source_url": "seed_data", "blt_sampled": 1,
     "description": "Barbury Castle pictogram - one of the most complex formations of the early 1990s"},
    {"year": 1996, "date_parsed": "1996-07-07", "date_confidence": "exact",
     "location": "Stonehenge, Nr Amesbury, Wiltshire",
     "county": "Wiltshire", "country": "UK", "lat": 51.1789, "lon": -1.8262,
     "approx_diameter_m": 91.0, "approx_area_m2": 6503.0,
     "formation_type": "fractal", "crop_type": "wheat",
     "source_url": "seed_data", "blt_sampled": 0,
     "description": "Julia Set formation opposite Stonehenge"},
    {"year": 2001, "date_parsed": "2001-08-14", "date_confidence": "exact",
     "location": "Milk Hill, Nr Alton Barnes, Wiltshire",
     "county": "Wiltshire", "country": "UK", "lat": 51.3742, "lon": -1.8475,
     "approx_diameter_m": 274.0, "approx_area_m2": 58966.0,
     "formation_type": "spiral", "crop_type": "wheat",
     "source_url": "seed_data", "blt_sampled": 0,
     "description": "Milk Hill 2001 - 409 circles, largest formation ever recorded"},
    {"year": 2002, "date_parsed": "2002-08-15", "date_confidence": "exact",
     "location": "Crabwood, Nr Winchester, Hampshire",
     "county": "Hampshire", "country": "UK", "lat": 51.0766, "lon": -1.3922,
     "approx_diameter_m": 120.0, "approx_area_m2": 11310.0,
     "formation_type": "face", "crop_type": "wheat",
     "source_url": "seed_data", "blt_sampled": 0,
     "description": "Alien face with binary disc"},
    {"year": 2008, "date_parsed": "2008-06-01", "date_confidence": "exact",
     "location": "Barbury Castle, Nr Wroughton, Wiltshire",
     "county": "Wiltshire", "country": "UK", "lat": 51.5394, "lon": -1.7706,
     "approx_diameter_m": 150.0, "approx_area_m2": 17671.0,
     "formation_type": "encoded", "crop_type": "barley",
     "source_url": "seed_data", "blt_sampled": 0,
     "description": "Pi formation encoding pi to 10 decimal places"},
    {"year": 2009, "date_parsed": "2009-06-12", "date_confidence": "exact",
     "location": "Milk Hill, Nr Alton Barnes, Wiltshire",
     "county": "Wiltshire", "country": "UK", "lat": 51.3742, "lon": -1.8475,
     "approx_diameter_m": 200.0, "approx_area_m2": 31416.0,
     "formation_type": "spiral", "crop_type": "barley",
     "source_url": "seed_data", "blt_sampled": 0,
     "description": "Milk Hill 2009 large spiral formation"},
    {"year": 1990, "date_parsed": "1990-07-12", "date_confidence": "exact",
     "location": "Alton Barnes, Wiltshire",
     "county": "Wiltshire", "country": "UK", "lat": 51.3667, "lon": -1.8333,
     "approx_diameter_m": 100.0, "approx_area_m2": 7854.0,
     "formation_type": "pictogram", "crop_type": "wheat",
     "source_url": "seed_data", "blt_sampled": 1,
     "description": "Alton Barnes 1990 - first major pictogram, BLT sampled"},
    {"year": 1994, "date_parsed": "1994-07-17", "date_confidence": "exact",
     "location": "Avebury Trusloe, Wiltshire",
     "county": "Wiltshire", "country": "UK", "lat": 51.4278, "lon": -1.8553,
     "approx_diameter_m": 45.0, "approx_area_m2": 1590.0,
     "formation_type": "fractal", "crop_type": "wheat",
     "source_url": "seed_data", "blt_sampled": 1,
     "description": "Avebury Trusloe Koch snowflake fractal"},
    {"year": 1995, "date_parsed": "1995-07-07", "date_confidence": "exact",
     "location": "Longwood Estate, Nr Winchester, Hampshire",
     "county": "Hampshire", "country": "UK", "lat": 51.1000, "lon": -1.2833,
     "approx_diameter_m": 60.0, "approx_area_m2": 2827.0,
     "formation_type": "geometric", "crop_type": "wheat",
     "source_url": "seed_data", "blt_sampled": 1,
     "description": "Longwood Estate 1995 - BLT sampled, anomalous node bending"},
    {"year": 1997, "date_parsed": "1997-07-28", "date_confidence": "exact",
     "location": "Milk Hill, Nr Alton Barnes, Wiltshire",
     "county": "Wiltshire", "country": "UK", "lat": 51.3742, "lon": -1.8475,
     "approx_diameter_m": 90.0, "approx_area_m2": 6362.0,
     "formation_type": "spiral", "crop_type": "wheat",
     "source_url": "seed_data", "blt_sampled": 0,
     "description": "Milk Hill 1997 spiral"},
    {"year": 1999, "date_parsed": "1999-07-04", "date_confidence": "exact",
     "location": "Hackpen Hill, Nr Broad Hinton, Wiltshire",
     "county": "Wiltshire", "country": "UK", "lat": 51.4667, "lon": -1.8167,
     "approx_diameter_m": 75.0, "approx_area_m2": 4418.0,
     "formation_type": "geometric", "crop_type": "wheat",
     "source_url": "seed_data", "blt_sampled": 0,
     "description": "Hackpen Hill 1999 geometric formation"},
    {"year": 2000, "date_parsed": "2000-08-13", "date_confidence": "exact",
     "location": "Windmill Hill, Nr Avebury, Wiltshire",
     "county": "Wiltshire", "country": "UK", "lat": 51.4389, "lon": -1.8694,
     "approx_diameter_m": 200.0, "approx_area_m2": 31416.0,
     "formation_type": "spiral", "crop_type": "wheat",
     "source_url": "seed_data", "blt_sampled": 0,
     "description": "Windmill Hill 2000 large spiral"},
    {"year": 2003, "date_parsed": "2003-08-11", "date_confidence": "exact",
     "location": "Crooked Soley, Nr Ramsbury, Wiltshire",
     "county": "Wiltshire", "country": "UK", "lat": 51.4167, "lon": -1.5833,
     "approx_diameter_m": 60.0, "approx_area_m2": 2827.0,
     "formation_type": "encoded", "crop_type": "wheat",
     "source_url": "seed_data", "blt_sampled": 0,
     "description": "Crooked Soley 2003 - DNA double helix encoding"},
    {"year": 2004, "date_parsed": "2004-07-25", "date_confidence": "exact",
     "location": "Pewsey White Horse, Nr Pewsey, Wiltshire",
     "county": "Wiltshire", "country": "UK", "lat": 51.3333, "lon": -1.7667,
     "approx_diameter_m": 100.0, "approx_area_m2": 7854.0,
     "formation_type": "geometric", "crop_type": "wheat",
     "source_url": "seed_data", "blt_sampled": 0,
     "description": "Pewsey White Horse 2004 geometric"},
    {"year": 2005, "date_parsed": "2005-07-24", "date_confidence": "exact",
     "location": "Avebury, Wiltshire",
     "county": "Wiltshire", "country": "UK", "lat": 51.4278, "lon": -1.8553,
     "approx_diameter_m": 100.0, "approx_area_m2": 7854.0,
     "formation_type": "mandala", "crop_type": "wheat",
     "source_url": "seed_data", "blt_sampled": 0,
     "description": "Avebury 2005 mandala formation"},
    {"year": 2006, "date_parsed": "2006-07-07", "date_confidence": "exact",
     "location": "Savernake Forest, Nr Marlborough, Wiltshire",
     "county": "Wiltshire", "country": "UK", "lat": 51.4167, "lon": -1.6667,
     "approx_diameter_m": 120.0, "approx_area_m2": 11310.0,
     "formation_type": "geometric", "crop_type": "wheat",
     "source_url": "seed_data", "blt_sampled": 0,
     "description": "Savernake Forest 2006 geometric"},
    {"year": 2007, "date_parsed": "2007-07-07", "date_confidence": "exact",
     "location": "Martinsell Hill, Nr Pewsey, Wiltshire",
     "county": "Wiltshire", "country": "UK", "lat": 51.3500, "lon": -1.7333,
     "approx_diameter_m": 90.0, "approx_area_m2": 6362.0,
     "formation_type": "spiral", "crop_type": "wheat",
     "source_url": "seed_data", "blt_sampled": 0,
     "description": "Martinsell Hill 2007 spiral"},
    {"year": 2010, "date_parsed": "2010-06-10", "date_confidence": "exact",
     "location": "Silbury Hill, Nr Avebury, Wiltshire",
     "county": "Wiltshire", "country": "UK", "lat": 51.4153, "lon": -1.8575,
     "approx_diameter_m": 300.0, "approx_area_m2": 70686.0,
     "formation_type": "spiral", "crop_type": "wheat",
     "source_url": "seed_data", "blt_sampled": 0,
     "description": "Silbury Hill 2010 large spiral"},
    {"year": 2011, "date_parsed": "2011-08-14", "date_confidence": "exact",
     "location": "Windmill Hill, Nr Avebury, Wiltshire",
     "county": "Wiltshire", "country": "UK", "lat": 51.4389, "lon": -1.8694,
     "approx_diameter_m": 200.0, "approx_area_m2": 31416.0,
     "formation_type": "fractal", "crop_type": "wheat",
     "source_url": "seed_data", "blt_sampled": 0,
     "description": "Windmill Hill 2011 fractal"},
    {"year": 2012, "date_parsed": "2012-07-28", "date_confidence": "exact",
     "location": "Hackpen Hill, Nr Broad Hinton, Wiltshire",
     "county": "Wiltshire", "country": "UK", "lat": 51.4667, "lon": -1.8167,
     "approx_diameter_m": 100.0, "approx_area_m2": 7854.0,
     "formation_type": "mandala", "crop_type": "wheat",
     "source_url": "seed_data", "blt_sampled": 0,
     "description": "Hackpen Hill 2012 mandala"},
    {"year": 2013, "date_parsed": "2013-07-28", "date_confidence": "exact",
     "location": "Silbury Hill, Nr Avebury, Wiltshire",
     "county": "Wiltshire", "country": "UK", "lat": 51.4153, "lon": -1.8575,
     "approx_diameter_m": 150.0, "approx_area_m2": 17671.0,
     "formation_type": "geometric", "crop_type": "wheat",
     "source_url": "seed_data", "blt_sampled": 0,
     "description": "Silbury Hill 2013 geometric"},
]


# ─────────────────────────────────────────────────────────────
# MAIN ENRICHMENT PIPELINE
# ─────────────────────────────────────────────────────────────

def load_and_combine_crop_circles(
    ccc_file: str,
    archive_file: str,
) -> pd.DataFrame:
    """Load and combine all crop circle data sources."""
    dfs = []

    # CCC scraped (2014-2024)
    if os.path.exists(ccc_file):
        df = pd.read_csv(ccc_file, low_memory=False)
        df["data_source"] = "ccc_scraped"
        dfs.append(df)
        print(f"CCC scraped: {len(df)} records")

    # Archive scraped (1978-2013)
    if os.path.exists(archive_file):
        df = pd.read_csv(archive_file, low_memory=False)
        df["data_source"] = "ccc_archive"
        dfs.append(df)
        print(f"Archive scraped: {len(df)} records")

    # Seed data
    df_seed = pd.DataFrame(SEED_DATA)
    df_seed["data_source"] = "seed_curated"
    dfs.append(df_seed)
    print(f"Seed data: {len(df_seed)} records")

    if not dfs:
        raise RuntimeError("No crop circle data found")

    df_all = pd.concat(dfs, ignore_index=True)

    # Deduplicate by source_url (keep first)
    if "source_url" in df_all.columns:
        df_all = df_all.drop_duplicates(subset=["source_url"], keep="first")

    print(f"Total after dedup: {len(df_all)} records")
    return df_all


def enrich_gps(df: pd.DataFrame, geocode: bool = True) -> pd.DataFrame:
    """Fill missing GPS using OS grid refs and Nominatim."""
    df = df.copy()

    # Ensure lat/lon are numeric
    df["lat"] = pd.to_numeric(df["lat"], errors="coerce")
    df["lon"] = pd.to_numeric(df["lon"], errors="coerce")

    missing_gps = df["lat"].isna()
    print(f"GPS missing for {missing_gps.sum()} / {len(df)} records")

    # Step 1: OS grid reference conversion
    if "os_grid_ref" in df.columns:
        grid_filled = 0
        for idx in df[missing_gps].index:
            grid_ref = str(df.loc[idx, "os_grid_ref"]).strip()
            if grid_ref and grid_ref != "nan":
                lat, lon = osgb_to_wgs84(grid_ref)
                if lat:
                    df.loc[idx, "lat"] = lat
                    df.loc[idx, "lon"] = lon
                    df.loc[idx, "gps_source"] = "os_grid"
                    grid_filled += 1
        print(f"  OS grid filled: {grid_filled}")

    # Step 2: Nominatim geocoding for remaining
    if geocode:
        _load_geocode_cache()  # Load cached results from previous runs
        missing_gps2 = df["lat"].isna()
        print(f"  Geocoding {missing_gps2.sum()} remaining records via Nominatim...")
        geo_filled = 0
        for idx in df[missing_gps2].index:
            location = str(df.loc[idx, "location"]).strip()
            country = str(df.loc[idx, "country"]).strip()
            if location and location != "nan" and len(location) > 5:
                lat, lon = geocode_location(location, country)
                if lat:
                    df.loc[idx, "lat"] = lat
                    df.loc[idx, "lon"] = lon
                    df.loc[idx, "gps_source"] = "nominatim"
                    geo_filled += 1
        _save_geocode_cache()  # Save results for future runs
        print(f"  Nominatim filled: {geo_filled}")

    # Set GPS source for records that already had GPS
    if "gps_source" not in df.columns:
        df["gps_source"] = ""
    df.loc[df["lat"].notna() & (df["gps_source"] == ""), "gps_source"] = "scraped"

    final_coverage = df["lat"].notna().sum()
    print(f"Final GPS coverage: {final_coverage} / {len(df)} ({100*final_coverage/len(df):.1f}%)")
    return df


def add_sun_position(df: pd.DataFrame) -> pd.DataFrame:
    """Add sun position columns for each formation."""
    df = df.copy()
    sun_cols = ["solar_declination", "equation_of_time_min", "day_length_hours",
                "sunrise_utc", "sunset_utc", "solar_noon_utc",
                "solar_elevation_noon", "solar_azimuth_noon"]

    for col in sun_cols:
        df[col] = np.nan

    computed = 0
    for idx, row in df.iterrows():
        lat = row.get("lat")
        lon = row.get("lon")
        date_str = str(row.get("date_parsed", ""))

        if pd.isna(lat) or pd.isna(lon) or not date_str or date_str == "nan":
            continue

        try:
            pos = solar_position(date_str, float(lat), float(lon))
            for col in sun_cols:
                if col in pos:
                    df.loc[idx, col] = pos[col]
            computed += 1
        except Exception:
            pass

    print(f"Sun position computed for {computed} / {len(df)} records")
    return df


def add_day_of_year_features(df: pd.DataFrame) -> pd.DataFrame:
    """Add day of year, month, season features."""
    df = df.copy()
    df["date_dt"] = pd.to_datetime(df["date_parsed"], errors="coerce")
    df["doy"] = df["date_dt"].dt.dayofyear
    df["month"] = df["date_dt"].dt.month
    df["week_of_year"] = df["date_dt"].dt.isocalendar().week.astype(float)

    # Season (northern hemisphere)
    def get_season(month):
        if pd.isna(month): return ""
        m = int(month)
        if m in [12, 1, 2]: return "winter"
        if m in [3, 4, 5]: return "spring"
        if m in [6, 7, 8]: return "summer"
        return "autumn"

    df["season"] = df["month"].apply(get_season)
    df.drop(columns=["date_dt"], inplace=True)
    return df


def main(
    ccc_file: str,
    archive_file: str,
    solar_file: str,
    output_file: str,
    geocode: bool = True,
    window_days: int = 7,
):
    print("=" * 60)
    print("CROP CIRCLE + SOLAR DATABASE BUILDER")
    print("=" * 60)

    # 1. Load and combine crop circle data
    print("\n[1] Loading crop circle data...")
    df_cc = load_and_combine_crop_circles(ccc_file, archive_file)

    # 2. Enrich GPS
    print("\n[2] Enriching GPS coordinates...")
    df_cc = enrich_gps(df_cc, geocode=geocode)

    # 3. Add sun position
    print("\n[3] Computing sun positions...")
    df_cc = add_sun_position(df_cc)

    # 4. Add temporal features
    print("\n[4] Adding temporal features...")
    df_cc = add_day_of_year_features(df_cc)

    # 5. Load solar data
    print("\n[5] Loading solar data...")
    df_solar = pd.read_csv(solar_file)
    df_solar["date"] = pd.to_datetime(df_solar["date"])
    print(f"Solar data: {len(df_solar)} days")

    # 6. Join solar data on date
    print("\n[6] Joining solar data...")
    df_cc["date_key"] = pd.to_datetime(df_cc["date_parsed"], errors="coerce")
    df_solar_join = df_solar.copy()
    df_solar_join.columns = ["solar_" + c if c != "date" else "date_key" for c in df_solar_join.columns]

    df_merged = df_cc.merge(df_solar_join, on="date_key", how="left")
    df_merged.drop(columns=["date_key"], inplace=True)
    print(f"After join: {len(df_merged)} records, {len(df_merged.columns)} columns")

    # 7. Compute solar windows
    print(f"\n[7] Computing ±{window_days}-day solar windows...")
    df_windows = compute_solar_windows(df_cc, df_solar, window_days)
    df_merged = pd.concat([df_merged.reset_index(drop=True),
                           df_windows.reset_index(drop=True)], axis=1)

    # 8. Clean up and sort
    print("\n[8] Cleaning and sorting...")

    # Fix formation type: 'face' is over-detected due to words like 'surface', 'interface'
    # Re-classify using strict word-boundary matching
    def fix_formation_type(row):
        ft = str(row.get('formation_type', 'unknown'))
        if ft != 'face':
            return ft
        desc = str(row.get('description', '')).lower() + ' ' + str(row.get('title_raw', '')).lower()
        # Only keep 'face' if strict face-related terms appear
        import re
        if re.search(r'\balien face\b|\bhuman face\b|\bportrait\b|\bface formation\b', desc):
            return 'face'
        return 'unknown'

    if 'formation_type' in df_merged.columns:
        df_merged['formation_type'] = df_merged.apply(fix_formation_type, axis=1)

    # Fix country: remove spurious 'USA' from old archive pages
    def fix_country(row):
        country = str(row.get('country', 'UK'))
        if country == 'USA':
            # Check if location text actually mentions USA
            loc = str(row.get('location', '')).lower()
            if 'usa' not in loc and 'united states' not in loc and 'america' not in loc:
                # Default to UK for archive records
                return 'UK'
        return country

    if 'country' in df_merged.columns:
        df_merged['country'] = df_merged.apply(fix_country, axis=1)

    # Filter out stub/navigation records (no location, no date, no description)
    valid_mask = (
        df_merged['date_parsed'].notna() &
        (df_merged['date_parsed'] != '') &
        ~(
            (df_merged['location'].fillna('').str.len() < 3) &
            (df_merged['description'].fillna('').str.len() < 10) &
            (df_merged['lat'].isna())
        )
    )
    n_before = len(df_merged)
    df_merged = df_merged[valid_mask].copy()
    print(f"  Filtered {n_before - len(df_merged)} stub records")

    df_merged = df_merged.sort_values(["date_parsed", "location"]).reset_index(drop=True)

    # Remove duplicate columns
    df_merged = df_merged.loc[:, ~df_merged.columns.duplicated()]

    # 9. Save
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    df_merged.to_csv(output_file, index=False)

    print(f"\n{'='*60}")
    print(f"OUTPUT: {output_file}")
    print(f"  Records: {len(df_merged)}")
    print(f"  Columns: {len(df_merged.columns)}")
    print(f"  Date range: {df_merged['date_parsed'].min()} to {df_merged['date_parsed'].max()}")
    print(f"  GPS coverage: {df_merged['lat'].notna().sum()} / {len(df_merged)}")
    print(f"  Solar data coverage: {df_merged['solar_Kp_sum_best'].notna().sum()} / {len(df_merged)}")
    print(f"{'='*60}")

    return df_merged


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--ccc", default="/home/ubuntu/crop_circle_db/data/ccc_scraped.csv")
    parser.add_argument("--archive", default="/home/ubuntu/crop_circle_db/data/ccc_archive_scraped.csv")
    parser.add_argument("--solar", default="/home/ubuntu/crop_circle_db/data/solar_daily.csv")
    parser.add_argument("--output", default="/home/ubuntu/crop_circle_db/data/crop_circle_solar_database.csv")
    parser.add_argument("--no-geocode", action="store_true")
    parser.add_argument("--window", type=int, default=7)
    args = parser.parse_args()

    main(
        ccc_file=args.ccc,
        archive_file=args.archive,
        solar_file=args.solar,
        output_file=args.output,
        geocode=not args.no_geocode,
        window_days=args.window,
    )
