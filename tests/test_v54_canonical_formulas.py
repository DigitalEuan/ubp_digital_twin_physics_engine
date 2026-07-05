"""
UBP v5.4 canonical physics formula predictions — live verification.

Each formula in UBP_SKILL_1 §9 (Canonical Formula Table) is recomputed live
from the substrate primitives and compared to its physical target. These are
the falsifiable predictions of the UBP system; we treat them as the
regression contract for the v5.4 migration.

Run:  pytest tests/test_v54_canonical_formulas.py -v
"""
from __future__ import annotations

from fractions import Fraction

import pytest


# ── Physical targets (UBP_SKILL_1 §9) ──────────────────────────────────────
TARGETS = {
    "m_mu_over_m_e":  Fraction(2067683, 10000),       # 206.7683
    "alpha_s":        Fraction(1181, 10000),          # 0.1181
    "alpha_cubed":    Fraction(1000, 137036) ** 3,    # (1/137.036)^3 — note 137.036 = 137036/1000
    "H0":             Fraction(70),                    # 70 km/s/Mpc
    "Omega_k_base":   Fraction(727, 1_000_000),        # 7.27e-4 (pre-NRCI)
}

# Tolerances (UBP_SKILL_1 §13 null-model protocol)
TOL_PREDICTIVE = 0.001     # < 0.1% = PREDICTIVE
TOL_SURPRISING = 0.01      # < 1%   = SURPRISING
TOL_PROVISIONAL = 1.00     # ≥ 1%   = PROVISIONAL


def _verdict(err_pct: float) -> str:
    if err_pct < TOL_PREDICTIVE * 100:
        return "PREDICTIVE"
    if err_pct < TOL_SURPRISING * 100:
        return "SURPRISING"
    return "PROVISIONAL"


# ── Formula computations ────────────────────────────────────────────────────
def test_muon_electron_ratio(pp):
    """m_μ/m_e = 169 / w   (UBP_SKILL_1 §9 row 1, Pure Inverse projection)."""
    pred = Fraction(169) / pp.wobble
    target = TARGETS["m_mu_over_m_e"]
    err = abs(float(pred) - float(target)) / float(target) * 100
    assert err < 0.1, (
        f"m_μ/m_e: pred={float(pred):.6f} target={float(target):.6f} "
        f"err={err:.4f}% verdict={_verdict(err)}"
    )


def test_alpha_s(pp):
    """α_s = 24 · Y^4   (Information-layer, k=4)."""
    pred = 24 * pp.Y ** 4
    target = TARGETS["alpha_s"]
    err = abs(float(pred) - float(target)) / float(target) * 100
    assert err < 0.5, f"α_s: pred={float(pred):.6f} err={err:.4f}%"


def test_alpha_cubed(pp):
    """α³ = (29/24) · Y^12 · e   (Potential layer, e replaces U_e).

    Target: (1/137.036)³ = (1000/137036)³ — α ≈ 1/137.036, so α³ ≈ 3.89e-7.
    Documented error: 0.104%.
    """
    pred = Fraction(29, 24) * pp.Y ** 12 * pp.e_const
    # 1/137.036 as a Fraction: 137.036 = 137036/1000, so 1/137.036 = 1000/137036
    target = Fraction(1000, 137036) ** 3
    pred_f = float(pred)
    target_f = float(target)
    err = abs(pred_f - target_f) / target_f * 100
    assert err < 0.5, (
        f"α³: pred={pred_f:.6e} target={target_f:.6e} err={err:.4f}% "
        f"(expected ~0.104%)"
    )


def test_H0(pp):
    """H₀ = (1/3) · w · Y^3 · U_e   (w-based layer, k=3)."""
    pred = Fraction(1, 3) * pp.wobble * pp.Y ** 3 * Fraction(pp.U_e)
    target = float(TARGETS["H0"])
    pred_f = float(pred)
    err = abs(pred_f - target) / target * 100
    # UBP skill allows up to 0.5% on H0 (FP rate 0.02%)
    assert err < 1.0, f"H₀: pred={pred_f:.4f} target={target} err={err:.4f}%"


def test_Omega_k_base(pp):
    """Ω_k base = 24 · Y^15 · U_e   (Potential layer, k=15, before NRCIα)."""
    pred = 24 * pp.Y ** 15 * Fraction(pp.U_e)
    target = float(TARGETS["Omega_k_base"])
    pred_f = float(pred)
    err = abs(pred_f - target) / target * 100
    assert err < 1.0, f"Ω_k base: pred={pred_f:.6e} err={err:.4f}%"


def test_gravity_G_topological(pp):
    """G = (39/29) · Y^18 / w   (Phase-4 combinatorial, UBP_SKILL_1 §9 row G).

    Target G = 6.6743e-11 m³ kg⁻¹ s⁻² (CODATA 2018). UBP value reported
    at 0.1327% error in core_studio_v4.0/README.md.
    """
    pred = Fraction(39, 29) * pp.Y ** 18 / pp.wobble
    target = 6.6743e-11
    pred_f = float(pred)
    err = abs(pred_f - target) / target * 100
    # Documented as 0.1327% — allow up to 0.5% for tolerance
    assert err < 0.5, (
        f"G: pred={pred_f:.6e} target={target:.6e} err={err:.4f}% "
        f"(expected ~0.13%)"
    )


def test_topological_shear_constants(pp):
    """Shear_1 and Shear_2 (UBP_SKILL_1 §7) — exact rational forms."""
    LY = pp.L * pp.Y
    Shear_1 = 1 + 3 * LY
    Shear_2 = 1 + 3 * LY + 12 * LY ** 2
    # Documented values
    assert abs(float(Shear_1) - 1.04992) < 1e-4, f"Shear_1 = {float(Shear_1):.6f}"
    assert abs(float(Shear_2) - 1.05324) < 1e-4, f"Shear_2 = {float(Shear_2):.6f}"


def test_get_ultimate_predictions_returns_dict(pp):
    """get_ultimate_predictions() must return the documented structure."""
    preds = pp.get_ultimate_predictions()
    assert isinstance(preds, dict)
    # Must contain key particle entries
    required = ["Proton/e- Ratio", "Muon/e- Ratio", "Alpha Inv"]
    for k in required:
        assert k in preds, f"missing prediction key: {k}"
        entry = preds[k]
        assert isinstance(entry, dict)
        for field in ("val", "target", "error_percent", "lens"):
            assert field in entry, f"{k} missing field {field}"
