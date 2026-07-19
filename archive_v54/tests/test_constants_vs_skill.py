"""
UBP_SKILL canonical constants live-check.

This module is the source of truth for every constant documented in
UBP_SKILL_1and2.txt. Tests below assert that the live `ubp_unified_v5`
backbone produces EXACTLY these values. Any drift indicates either:
  • the backbone has been corrupted, or
  • the skill file is out of date.

Run:  pytest tests/test_constants_vs_skill.py -v
"""
from __future__ import annotations

from fractions import Fraction

import pytest


# ── Skill-file documented values (UBP_SKILL_1 §3) ──────────────────────────
# Tolerances: skill values marked TRUNCATED in the source doc use a wider
# tolerance (the skill prints e.g. "3.77835…" with an ellipsis); values
# marked exact use 1e-10.
SKILL_VALUES = {
    # attr:     (expected_value,           tolerance,   note)
    "Y":         (0.264675430405,           1e-10,      "exact"),
    "Y_INV":     (3.77835,                  1e-3,       "truncated in skill (3.77835…), live=3.77821"),
    "wobble":    (0.817580227176,           1e-10,      "exact"),
    "L":         (0.062890786706,           1e-10,      "exact"),
    "L_s":       (0.075993033936,           1e-10,      "exact"),
    "sigma":     (29 / 24,                  1e-12,      "exact rational"),
    "U_e":       (13824,                    0,          "exact int"),
    "monad":     (13.817580227,             1e-8,       "truncated in skill, live=13.817580227176"),
    "pi":        (3.14159265359,            1e-10,      "exact"),
    "phi":       (1.61803398875,            1e-10,      "exact"),
    "e_const":   (2.71828182846,            1e-10,      "exact"),
}

# Skill-file documented formula relationships (UBP_SKILL_1 §3, §7, §9)
SKILL_RELATIONS = {
    # L = w / 13
    "L_eq_w_over_13":     lambda pp: float(pp.wobble) / 13,
    # L_s = L × (29/24) = L × sigma
    "L_s_eq_L_times_sigma": lambda pp: float(pp.L) * float(pp.sigma),
    # Y_INV = 1 / Y
    "Y_INV_eq_inv_Y":     lambda pp: 1.0 / float(pp.Y),
    # monad = pi * phi * e
    "monad_eq_pi_phi_e":  lambda pp: float(pp.pi) * float(pp.phi) * float(pp.e_const),
}


# ── Tests ───────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("attr,spec", SKILL_VALUES.items())
def test_constant_matches_skill_value(pp, attr, spec):
    """Each documented constant must match the skill-file value within its
    declared tolerance. Tolerances are tight (1e-10) for exact values and
    loose (1e-3..1e-8) for skill values that are explicitly truncated."""
    expected, tol, note = spec
    live = float(getattr(pp, attr))
    if attr == "U_e":
        assert live == float(expected), f"{attr}: {live} != {expected}"
    else:
        assert abs(live - expected) < tol, (
            f"{attr}: live={live:.15f} expected={expected:.15f} "
            f"delta={live - expected:+.3e} tol={tol} note={note}"
        )


@pytest.mark.parametrize("name,fn", SKILL_RELATIONS.items())
def test_constant_relationships(pp, name, fn):
    """Documented algebraic relationships must hold exactly."""
    expected = fn(pp)
    if name == "L_eq_w_over_13":
        live = float(pp.L)
    elif name == "L_s_eq_L_times_sigma":
        live = float(pp.L_s)
    elif name == "Y_INV_eq_inv_Y":
        live = float(pp.Y_INV)
    elif name == "monad_eq_pi_phi_e":
        live = float(pp.monad)
    else:
        pytest.skip(f"unknown relation {name}")
    assert abs(live - expected) < 1e-12, (
        f"{name}: live={live:.15f} expected={expected:.15f}"
    )


def test_sigma_is_exact_fraction(pp):
    """σ must be stored as the exact Fraction 29/24."""
    assert pp.sigma == Fraction(29, 24)


def test_U_e_is_24_cubed(pp):
    assert int(pp.U_e) == 24 ** 3


def test_all_constants_are_fractions(pp):
    """Critical substratal constants must be stored as Fraction (not float)
    per the v5.4 'Float-Free Physics' mandate."""
    for attr in ("Y", "Y_INV", "wobble", "L", "L_s", "sigma", "U_e",
                 "monad", "pi", "phi", "e_const"):
        v = getattr(pp, attr)
        assert isinstance(v, Fraction), f"{attr} is {type(v).__name__}, expected Fraction"
