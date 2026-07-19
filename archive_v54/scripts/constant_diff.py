#!/usr/bin/env python3
"""
UBP v5.3 → v5.4 Constant Diff Report

Produces a JSON + Markdown report comparing every UBP constant and prediction
between the digital twin's current `ubp_core_v5_3_merged.py` backbone and the
new `ubp_unified_v5.py` v5.4 backbone. Run before and after each migration
phase to catch regressions.

Outputs:
  • docs/v5_4_migration/constant_diff_<timestamp>.json
  • docs/v5_4_migration/constant_diff_<timestamp>.md

Usage:
  python3 scripts/constant_diff.py
  python3 scripts/constant_diff.py --quick   # skip slow get_ultimate_predictions
"""
from __future__ import annotations

import argparse
import json
import sys
import importlib
import importlib.util
from datetime import datetime
from fractions import Fraction
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def to_serialisable(v):
    if isinstance(v, Fraction):
        return {"_fraction": str(v), "_float": float(v)}
    if isinstance(v, (int, float, str, bool)):
        return v
    return str(v)


def collect_constants(mod):
    """Pull every public Fraction/int/float attribute off UBPSourceCodeParticlePhysics."""
    pp = mod.UBPSourceCodeParticlePhysics()
    out = {}
    for attr in sorted(dir(pp)):
        if attr.startswith("_"):
            continue
        try:
            v = getattr(pp, attr)
        except Exception:
            continue
        if isinstance(v, Fraction):
            out[attr] = {"fraction": str(v), "float": float(v)}
        elif isinstance(v, (int,)) and not isinstance(v, bool):
            out[attr] = {"int": v}
        elif isinstance(v, float):
            out[attr] = {"float": v}
    return out


def collect_predictions(mod):
    pp = mod.UBPSourceCodeParticlePhysics()
    try:
        preds = pp.get_ultimate_predictions()
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}
    serial = {}
    for k, v in preds.items():
        if isinstance(v, dict):
            serial[k] = {kk: to_serialisable(vv) for kk, vv in v.items()}
        else:
            serial[k] = to_serialisable(v)
    return serial


def collect_engine_inventory(mod):
    """List every public class exported by the backbone module."""
    classes = sorted(
        c for c in dir(mod)
        if c[:1].isupper() and not c.startswith(chr(95))
        and isinstance(getattr(mod, c, None), type)
    )
    return classes


def diff_constants(old: dict, new: dict) -> list:
    rows = []
    all_keys = sorted(set(old) | set(new))
    for k in all_keys:
        o = old.get(k)
        n = new.get(k)
        if o is None:
            rows.append({"constant": k, "old": None, "new": n, "delta_pct": None,
                         "status": "NEW_IN_V54"})
            continue
        if n is None:
            rows.append({"constant": k, "old": o, "new": None, "delta_pct": None,
                         "status": "REMOVED_IN_V54"})
            continue
        # Compare float values
        of = o.get("float", o.get("int"))
        nf = n.get("float", n.get("int"))
        if of is None or nf is None:
            rows.append({"constant": k, "old": o, "new": n, "delta_pct": None,
                         "status": "TYPE_CHANGE"})
            continue
        if of == 0:
            delta = 0.0 if nf == 0 else float("inf")
        else:
            delta = (nf - of) / abs(of) * 100
        status = "UNCHANGED" if abs(delta) < 1e-9 else "CHANGED"
        rows.append({"constant": k, "old": of, "new": nf, "delta_pct": delta,
                     "status": status})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true",
                    help="Skip get_ultimate_predictions (faster)")
    args = ap.parse_args()

    print("[diff] Loading v5.3 (digital twin archive_v53/)...")
    archive_path = REPO_ROOT / "archive_v53" / "ubp_core_v5_3_merged.py"
    if not archive_path.exists():
        print(f"FATAL: archived v5.3 backbone not found at {archive_path}")
        sys.exit(1)
    spec_old = importlib.util.spec_from_file_location("ubp_core_v5_3_merged", archive_path)
    old_mod = importlib.util.module_from_spec(spec_old)
    spec_old.loader.exec_module(old_mod)

    print("[diff] Loading v5.4 (current working backbone)...")
    new_mod = importlib.import_module("ubp_unified_v5")

    print("[diff] Collecting constants...")
    old_consts = collect_constants(old_mod)
    new_consts = collect_constants(new_mod)

    print("[diff] Collecting predictions..." + (" (skipped)" if args.quick else ""))
    old_preds = {} if args.quick else collect_predictions(old_mod)
    new_preds = {} if args.quick else collect_predictions(new_mod)

    print("[diff] Collecting class inventories...")
    old_classes = collect_engine_inventory(old_mod)
    new_classes = collect_engine_inventory(new_mod)

    diff_rows = diff_constants(old_consts, new_consts)
    added_classes = sorted(set(new_classes) - set(old_classes))
    removed_classes = sorted(set(old_classes) - set(new_classes))

    timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    out_dir = REPO_ROOT / "docs" / "v5_4_migration"
    out_dir.mkdir(parents=True, exist_ok=True)

    report = {
        "timestamp": timestamp,
        "old_backbone": "ubp_core_v5_3_merged (digital twin archive_v53/)",
        "new_backbone": "ubp_unified_v5 (v5.4.0 reference)",
        "constants_diff": diff_rows,
        "classes_added_in_v54": added_classes,
        "classes_removed_in_v54": removed_classes,
        "old_predictions": old_preds,
        "new_predictions": new_preds,
    }

    json_path = out_dir / f"constant_diff_{timestamp}.json"
    json_path.write_text(json.dumps(report, indent=2, default=str))
    print(f"[diff] JSON  → {json_path}")

    # Markdown summary
    md = ["# UBP v5.3 → v5.4 Constant Diff Report",
          f"*Generated: {timestamp} UTC*",
          "",
          f"**Old backbone:** `ubp_core_v5_3_merged` (archive_v53/)  ",
          f"**New backbone:** `ubp_unified_v5` v5.4.0 (reference)",
          "",
          "## Constant Deltas",
          "",
          "| Constant | Old (v5.3) | New (v5.4) | Δ % | Status |",
          "|---|---|---|---|---|"]
    for r in diff_rows:
        if r["status"] in ("UNCHANGED",):
            continue   # only show changes
        o = r["old"] if r["old"] is not None else "—"
        n = r["new"] if r["new"] is not None else "—"
        d = f"{r['delta_pct']:+.6f}" if r["delta_pct"] is not None else "—"
        md.append(f"| `{r['constant']}` | {o} | {n} | {d} | {r['status']} |")

    md += ["", "## Classes Added in v5.4", ""]
    for c in added_classes:
        md.append(f"- `{c}`")
    md += ["", "## Classes Removed in v5.4", ""]
    for c in removed_classes:
        md.append(f"- `{c}`")

    md_path = out_dir / f"constant_diff_{timestamp}.md"
    md_path.write_text("\n".join(md))
    print(f"[diff] MD    → {md_path}")

    # Console summary
    print()
    print("=" * 70)
    print("CONSTANT DIFF SUMMARY")
    print("=" * 70)
    changed = [r for r in diff_rows if r["status"] == "CHANGED"]
    new = [r for r in diff_rows if r["status"] == "NEW_IN_V54"]
    removed = [r for r in diff_rows if r["status"] == "REMOVED_IN_V54"]
    print(f"  Constants:  {len(diff_rows):4d} total")
    print(f"              {len(changed):4d} CHANGED")
    print(f"              {len(new):4d} NEW_IN_V54")
    print(f"              {len(removed):4d} REMOVED_IN_V54")
    print(f"  Classes:    +{len(added_classes)} added in v5.4, -{len(removed_classes)} removed")
    if changed:
        print("\n  Changed constants (top 10 by |Δ|):")
        for r in sorted(changed, key=lambda x: abs(x["delta_pct"] or 0), reverse=True)[:10]:
            print(f"    {r['constant']:<20}  Δ = {r['delta_pct']:+.6f}%")


if __name__ == "__main__":
    main()
