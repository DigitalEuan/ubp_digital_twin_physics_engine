#!/usr/bin/env python3
"""
fetch_solar_data.py — Comprehensive solar data fetcher
=======================================================
Fetches and merges:
  1. NASA OMNI2 daily data (1963-2024) via SPDF FTP
     - Solar wind speed, IMF Bz, proton density, flow pressure
     - Kp sum, Ap index, Dst index, F10.7 flux, sunspot number
  2. GFZ Potsdam Kp definitive data (1932-2024)
     - 3-hourly Kp values, daily Kp max, Kp mean
     - Storm window flags
  3. SIDC/SILSO daily sunspot numbers (1818-present)
     - International Sunspot Number v2

Output: data/solar_daily.csv

All fill values replaced with NaN.
Solar cycle phase computed from smoothed SSN.
"""

import requests
import pandas as pd
import numpy as np
import os
import time
import re
from datetime import datetime, timedelta

# ─────────────────────────────────────────────────────────────
# OMNI2 FTP DATA
# ─────────────────────────────────────────────────────────────

OMNI_FTP_BASE = "https://spdf.gsfc.nasa.gov/pub/data/omni/low_res_omni"

# OMNI2 hourly file column indices (0-indexed)
# Full spec: https://omniweb.gsfc.nasa.gov/html/ow_data.html
# Col 0: year, 1: doy, 2: hour
# Col 9:  |B| avg (nT)
# Col 17: Bz GSM (nT)
# Col 22: SW speed (km/s)
# Col 25: proton density (n/cc)
# Col 27: flow pressure (nPa)
# Col 28: electric field (mV/m)
# Col 31: Kp*10 (3-hourly)
# Col 32: sunspot number
# Col 33: Dst index (nT)
# Col 34: Ap index
# Col 36: F10.7 adjusted (sfu)

OMNI_FILL = {
    "IMF_B_mag": 999.9,
    "IMF_Bz_GSM": 999.9,
    "SW_speed": 9999.0,
    "Proton_density": 999.9,
    "Flow_pressure": 99.99,
    "Electric_field": 999.99,
    "Kp_x10": 99,      # Kp*10 fill = 99 (= Kp 9.9)
    "Sunspot_num_omni": 999,
    "Dst_index": 99999,
    "Ap_index": 999,
    "F10_7_adj": 999.9,
}


def fetch_omni_year(year: int) -> pd.DataFrame | None:
    """Download and parse one year of OMNI2 hourly data."""
    url = f"{OMNI_FTP_BASE}/omni2_{year}.dat"
    try:
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        time.sleep(0.3)
    except Exception as e:
        print(f"  [WARN] OMNI {year}: {e}")
        return None

    rows = []
    for line in r.text.strip().split("\n"):
        parts = line.split()
        if len(parts) < 51:
            continue
        try:
            row = {
                "year": int(parts[0]),
                "doy": int(parts[1]),
                "hour": int(parts[2]),
                # Word 9 (index 8): |B| field magnitude (nT)
                "IMF_B_mag": float(parts[8]),
                # Word 17 (index 16): Bz GSM (nT)
                "IMF_Bz_GSM": float(parts[16]),
                # Word 25 (index 24): Plasma flow speed (km/s)
                "SW_speed": float(parts[24]),
                # Word 24 (index 23): Proton density (N/cm^3)
                "Proton_density": float(parts[23]),
                # Word 29 (index 28): Flow pressure (nPa)
                "Flow_pressure": float(parts[28]),
                # Word 36 (index 35): Electric field (mV/m)
                "Electric_field": float(parts[35]),
                # Word 39 (index 38): Kp*10
                "Kp_x10": float(parts[38]),
                # Word 40 (index 39): Sunspot number
                "Sunspot_num_omni": float(parts[39]),
                # Word 41 (index 40): Dst index (nT)
                "Dst_index": float(parts[40]),
                # Word 50 (index 49): ap index
                "Ap_index": float(parts[49]),
                # Word 51 (index 50): F10.7 adjusted (sfu)
                "F10_7_adj": float(parts[50]),
            }
            rows.append(row)
        except (ValueError, IndexError):
            continue

    if not rows:
        return None

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(
        df["year"].astype(str) + df["doy"].astype(str).str.zfill(3),
        format="%Y%j", errors="coerce"
    )

    # Replace fill values
    for col, fill in OMNI_FILL.items():
        if col in df.columns:
            df[col] = df[col].replace(fill, np.nan)

    # Kp: stored as Kp*10 in hourly files
    df["Kp_3hr"] = df["Kp_x10"] / 10.0

    # Aggregate hourly → daily
    daily = df.groupby("date").agg(
        IMF_B_mag=("IMF_B_mag", "mean"),
        IMF_Bz_GSM_mean=("IMF_Bz_GSM", "mean"),
        IMF_Bz_GSM_min=("IMF_Bz_GSM", "min"),
        SW_speed_mean=("SW_speed", "mean"),
        SW_speed_max=("SW_speed", "max"),
        Proton_density=("Proton_density", "mean"),
        Flow_pressure=("Flow_pressure", "mean"),
        Electric_field=("Electric_field", "mean"),
        Kp_sum=("Kp_3hr", "sum"),
        Kp_max=("Kp_3hr", "max"),
        Kp_mean=("Kp_3hr", "mean"),
        Sunspot_num_omni=("Sunspot_num_omni", "first"),
        Dst_min=("Dst_index", "min"),
        Dst_mean=("Dst_index", "mean"),
        Ap_index=("Ap_index", "mean"),
        F10_7_adj=("F10_7_adj", "first"),
    ).reset_index()

    return daily


def fetch_omni_all(start_year: int, end_year: int) -> pd.DataFrame:
    """Fetch all OMNI years and concatenate."""
    print(f"Fetching NASA OMNI2 data {start_year}-{end_year}...")
    dfs = []
    for year in range(start_year, end_year + 1):
        print(f"  OMNI {year}...", end=" ", flush=True)
        df = fetch_omni_year(year)
        if df is not None:
            dfs.append(df)
            print(f"{len(df)} days")
        else:
            print("failed")

    if not dfs:
        raise RuntimeError("Could not fetch any OMNI data")

    result = pd.concat(dfs, ignore_index=True)
    result = result.sort_values("date").reset_index(drop=True)
    print(f"  OMNI total: {len(result)} daily rows ({result['date'].min().date()} to {result['date'].max().date()})")
    return result


# ─────────────────────────────────────────────────────────────
# GFZ POTSDAM Kp DATA
# ─────────────────────────────────────────────────────────────

GFZ_KP_URL = "https://kp.gfz.de/app/files/Kp_ap_Ap_SN_F107_since_1932.txt"


def kp_to_ap(kp: float) -> float:
    """Convert Kp to ap index."""
    kp_ap = {0: 0, 0.3: 2, 0.7: 3, 1: 4, 1.3: 5, 1.7: 6, 2: 7, 2.3: 9,
              2.7: 12, 3: 15, 3.3: 18, 3.7: 22, 4: 27, 4.3: 32, 4.7: 39,
              5: 48, 5.3: 56, 5.7: 67, 6: 80, 6.3: 94, 6.7: 111, 7: 132,
              7.3: 154, 7.7: 179, 8: 207, 8.3: 236, 8.7: 300, 9: 400}
    closest = min(kp_ap.keys(), key=lambda x: abs(x - kp))
    return kp_ap[closest]


def kp_to_g_storm(kp_max: float) -> int:
    """Convert max Kp to NOAA G-storm level (0-5)."""
    if pd.isna(kp_max): return 0
    if kp_max >= 9: return 5
    if kp_max >= 8: return 4
    if kp_max >= 7: return 3
    if kp_max >= 6: return 2
    if kp_max >= 5: return 1
    return 0


def fetch_gfz_kp() -> pd.DataFrame:
    """Download and parse GFZ Potsdam definitive Kp data."""
    print(f"Fetching GFZ Potsdam Kp data...")
    try:
        r = requests.get(GFZ_KP_URL, timeout=120)
        r.raise_for_status()
    except Exception as e:
        print(f"  [WARN] GFZ Kp fetch failed: {e}")
        return pd.DataFrame()

    lines = r.text.strip().split("\n")
    rows = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue

        parts = line.split()
        # Actual GFZ format (verified 2024):
        # YYYY MM DD  days  days_m  Bsr  dB  Kp1 Kp2 Kp3 Kp4 Kp5 Kp6 Kp7 Kp8
        #   ap1 ap2 ap3 ap4 ap5 ap6 ap7 ap8  Ap  SN  F10.7obs  F10.7adj  D
        # parts[0]=YYYY, [1]=MM, [2]=DD, [3]=days, [4]=days_m, [5]=Bsr, [6]=dB
        # parts[7-14]=Kp1-Kp8 (0-9 scale), [15-22]=ap1-ap8
        # parts[23]=Ap, [24]=SN, [25]=F10.7obs, [26]=F10.7adj, [27]=D
        if len(parts) < 25:
            continue

        try:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            date = pd.Timestamp(y, m, d)

            # 8 three-hourly Kp values (parts 7-14, already in 0-9 scale)
            kp_vals = []
            for i in range(7, 15):
                val = float(parts[i])
                if val < 0:
                    val = np.nan
                kp_vals.append(val)

            # 8 three-hourly ap values (parts 15-22)
            ap_vals = []
            for i in range(15, 23):
                val = float(parts[i]) if i < len(parts) else np.nan
                if val < 0:
                    val = np.nan
                ap_vals.append(val)

            # Daily Ap (part 23)
            ap_daily = float(parts[23]) if len(parts) > 23 else np.nan
            if ap_daily < 0: ap_daily = np.nan

            # Sunspot number (part 24)
            ssn = float(parts[24]) if len(parts) > 24 else np.nan
            if ssn < 0:
                ssn = np.nan

            # F10.7 adjusted (part 26)
            f107 = float(parts[26]) if len(parts) > 26 else np.nan
            if f107 < 0:
                f107 = np.nan

            # Definitive flag (part 27)
            definitive = parts[27] if len(parts) > 27 else "0"

            # Compute daily Kp stats from 3-hourly values
            valid_kp = [k for k in kp_vals if not (isinstance(k, float) and np.isnan(k))]
            kp_sum = sum(valid_kp) if valid_kp else np.nan
            kp_max = max(valid_kp) if valid_kp else np.nan
            kp_mean = np.mean(valid_kp) if valid_kp else np.nan

            row = {
                "date": date,
                "Kp_1": kp_vals[0], "Kp_2": kp_vals[1],
                "Kp_3": kp_vals[2], "Kp_4": kp_vals[3],
                "Kp_5": kp_vals[4], "Kp_6": kp_vals[5],
                "Kp_7": kp_vals[6], "Kp_8": kp_vals[7],
                "Kp_sum_gfz": kp_sum,
                "Kp_max_gfz": kp_max,
                "Kp_mean_gfz": kp_mean,
                "Ap_daily_gfz": ap_daily,
                "SSN_gfz": ssn,
                "F10_7_gfz": f107,
                "kp_definitive": definitive,
            }
            rows.append(row)

        except (ValueError, IndexError):
            continue

    if not rows:
        print("  [WARN] No GFZ Kp data parsed")
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["G_storm_level"] = df["Kp_max_gfz"].apply(kp_to_g_storm)
    print(f"  GFZ Kp: {len(df)} days ({df['date'].min().date()} to {df['date'].max().date()})")
    return df


# ─────────────────────────────────────────────────────────────
# SIDC/SILSO SUNSPOT DATA
# ─────────────────────────────────────────────────────────────

SIDC_URL = "https://sidc.be/SILSO/DATA/SN_d_tot_V2.0.txt"


def fetch_sidc_sunspots() -> pd.DataFrame:
    """Download SIDC daily sunspot numbers (1818-present)."""
    print(f"Fetching SIDC/SILSO sunspot data...")
    try:
        r = requests.get(SIDC_URL, timeout=30)
        r.raise_for_status()
    except Exception as e:
        print(f"  [WARN] SIDC fetch failed: {e}")
        return pd.DataFrame()

    rows = []
    for line in r.text.strip().split("\n"):
        parts = line.split()
        if len(parts) < 5:
            continue
        try:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            ssn = float(parts[4]) if parts[4] != "-1" else np.nan
            std = float(parts[5]) if len(parts) > 5 and parts[5] != "-1" else np.nan
            rows.append({
                "date": pd.Timestamp(y, m, d),
                "SIDC_SSN": ssn,
                "SIDC_SSN_std": std,
            })
        except (ValueError, IndexError):
            continue

    df = pd.DataFrame(rows)
    print(f"  SIDC SSN: {len(df)} days ({df['date'].min().date()} to {df['date'].max().date()})")
    return df


# ─────────────────────────────────────────────────────────────
# SOLAR CYCLE PHASE
# ─────────────────────────────────────────────────────────────

# Solar cycle minima (approximate dates)
SOLAR_CYCLE_MINIMA = [
    ("1954-04-01", 19), ("1964-10-01", 20), ("1976-03-01", 21),
    ("1986-09-01", 22), ("1996-08-01", 23), ("2008-12-01", 24),
    ("2019-12-01", 25),
]


def compute_solar_cycle_phase(dates: pd.Series) -> tuple[pd.Series, pd.Series]:
    """
    Compute solar cycle phase (0-1) and cycle number for each date.
    Phase 0 = solar minimum, 0.5 = solar maximum.
    """
    minima = [(pd.Timestamp(d), n) for d, n in SOLAR_CYCLE_MINIMA]
    phases = []
    cycle_nums = []

    for date in dates:
        if pd.isna(date):
            phases.append(np.nan)
            cycle_nums.append(np.nan)
            continue

        # Find which cycle this date falls in
        cycle_start = None
        cycle_num = None
        cycle_end = None

        for i, (min_date, num) in enumerate(minima):
            if date >= min_date:
                cycle_start = min_date
                cycle_num = num
                if i + 1 < len(minima):
                    cycle_end = minima[i + 1][0]
                else:
                    # Estimate next minimum ~11 years after last known
                    cycle_end = min_date + pd.Timedelta(days=365.25 * 11)

        if cycle_start is None:
            # Before first known minimum
            phases.append(np.nan)
            cycle_nums.append(np.nan)
        else:
            cycle_length = (cycle_end - cycle_start).days
            days_into_cycle = (date - cycle_start).days
            phase = (days_into_cycle % cycle_length) / cycle_length
            phases.append(round(phase, 4))
            cycle_nums.append(cycle_num)

    return pd.Series(phases, index=dates.index), pd.Series(cycle_nums, index=dates.index)


# ─────────────────────────────────────────────────────────────
# STORM WINDOW FLAGS
# ─────────────────────────────────────────────────────────────

def add_storm_windows(df: pd.DataFrame, window_days: int = 3) -> pd.DataFrame:
    """
    Add boolean columns indicating if a date falls within N days of a
    geomagnetic storm of each G-level.
    """
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df_indexed = df.set_index("date")

    for g_level in [1, 2, 3]:
        col = f"in_G{g_level}_window_{window_days}d"
        storm_dates = df_indexed[df_indexed["G_storm_level"] >= g_level].index

        in_window = pd.Series(False, index=df_indexed.index)
        for sd in storm_dates:
            mask = (df_indexed.index >= sd - pd.Timedelta(days=window_days)) & \
                   (df_indexed.index <= sd + pd.Timedelta(days=window_days))
            in_window = in_window | mask

        df_indexed[col] = in_window

    return df_indexed.reset_index()


# ─────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────

def build_solar_database(start_year: int, end_year: int, output_file: str):
    """Build the complete solar daily database."""
    os.makedirs(os.path.dirname(output_file), exist_ok=True)

    # 1. Fetch OMNI data
    df_omni = fetch_omni_all(start_year, end_year)

    # 2. Fetch GFZ Kp (longer baseline, more precise)
    df_gfz = fetch_gfz_kp()

    # 3. Fetch SIDC sunspots
    df_sidc = fetch_sidc_sunspots()

    # 4. Merge all on date
    print("\nMerging solar datasets...")
    df = df_omni.copy()
    df["date"] = pd.to_datetime(df["date"])

    if not df_gfz.empty:
        df_gfz["date"] = pd.to_datetime(df_gfz["date"])
        df = df.merge(df_gfz[[
            "date", "Kp_sum_gfz", "Kp_max_gfz", "Kp_mean_gfz",
            "Ap_daily_gfz", "SSN_gfz", "F10_7_gfz", "G_storm_level", "kp_definitive"
        ]], on="date", how="left")

    if not df_sidc.empty:
        df_sidc["date"] = pd.to_datetime(df_sidc["date"])
        df = df.merge(df_sidc, on="date", how="left")

    # 5. Create best-available columns (prefer GFZ/SIDC over OMNI where available)
    # Best Kp: prefer GFZ (more precise) over OMNI
    df["Kp_sum_best"] = df["Kp_sum_gfz"].fillna(df["Kp_sum"])
    df["Kp_max_best"] = df["Kp_max_gfz"].fillna(df["Kp_max"])
    df["Kp_mean_best"] = df["Kp_mean_gfz"].fillna(df["Kp_mean"])

    # Best SSN: prefer SIDC over OMNI
    df["SSN_best"] = df["SIDC_SSN"].fillna(df["Sunspot_num_omni"])

    # Best F10.7: prefer GFZ over OMNI
    df["F10_7_best"] = df["F10_7_gfz"].fillna(df["F10_7_adj"])

    # G storm level (from GFZ Kp max)
    if "G_storm_level" not in df.columns:
        df["G_storm_level"] = df["Kp_max_best"].apply(kp_to_g_storm)

    # 6. Solar cycle phase
    print("Computing solar cycle phase...")
    df["solar_cycle_phase"], df["solar_cycle_num"] = compute_solar_cycle_phase(df["date"])

    # 7. Storm window flags
    print("Computing storm window flags...")
    df = add_storm_windows(df, window_days=3)

    # 8. Sort and save
    df = df.sort_values("date").reset_index(drop=True)
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    df.to_csv(output_file, index=False)
    print(f"\nSolar database saved: {output_file}")
    print(f"  Rows: {len(df)}")
    print(f"  Columns: {len(df.columns)}")
    print(f"  Date range: {df['date'].min()} to {df['date'].max()}")
    print(f"  Columns: {list(df.columns)}")

    return df


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, default=1963)
    parser.add_argument("--end", type=int, default=2024)
    parser.add_argument("--output", default="/home/ubuntu/crop_circle_db/data/solar_daily.csv")
    args = parser.parse_args()
    build_solar_database(args.start, args.end, args.output)
