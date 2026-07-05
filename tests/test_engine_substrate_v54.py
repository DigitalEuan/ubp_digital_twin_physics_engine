"""
UBP Engine Substrate v2.0 (v5.4 aligned) — public API tests.

Verifies that every v5.4 enhancement documented in ubp_engine_substrate.py
is reachable through the substrate's public surface and produces the
documented values. These tests are the regression contract for Phase 2.

Run:  pytest tests/test_engine_substrate_v54.py -v
"""
from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path

import pytest

# Make sure the repo root is on the path (conftest already does this, but be defensive)
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ── Module-level import & smoke ────────────────────────────────────────────
def test_substrate_imports():
    """The substrate module must import without errors."""
    import ubp_engine_substrate as sub
    assert sub._CORE_LOADED is True


# ── v5.4-sourced constants ──────────────────────────────────────────────────
def test_constants_now_match_particle_physics():
    """Y, PI, PHI, E_CONST, MONAD, WOBBLE, SINK_L, SINK_L_STEREO, SINK_SIGMA,
    EXISTENCE_UNIT must now match PARTICLE_PHYSICS first-class attributes
    (single source of truth) — no longer re-derived from truncated Fractions."""
    import ubp_engine_substrate as sub
    pp = sub.PARTICLE_PHYSICS
    assert sub.Y_CONSTANT      == sub._CONST['Y']
    assert sub.PI              == sub._CONST['PI']
    assert sub.PHI             == pp.phi
    assert sub.E_CONST         == pp.e_const
    assert sub.MONAD           == pp.monad
    assert sub.WOBBLE          == pp.wobble
    assert sub.SINK_L          == pp.L
    assert sub.SINK_L_STEREO   == pp.L_s
    assert sub.SINK_SIGMA      == pp.sigma
    assert sub.EXISTENCE_UNIT  == pp.U_e


def test_phi_e_sourced_from_particle_physics():
    """PHI and E_CONST must now be sourced from PARTICLE_PHYSICS (single
    source of truth) instead of being manually re-defined as Fractions in
    this module.

    NOTE: We previously assumed v5.4 used higher-precision φ/e. Live
    verification shows v5.4's pp.phi and pp.e_const reduce to the SAME
    rational as the v1.0 truncations (Fraction(1618033988749895, 10**15)
    for φ etc.). The improvement here is therefore about SINGLE SOURCE OF
    TRUTH — every dependent module now imports PARTICLE_PHYSICS.phi
    instead of re-defining its own φ — NOT about extra precision.
    """
    import ubp_engine_substrate as sub
    pp = sub.PARTICLE_PHYSICS
    # The key invariant: substrate re-exports the backbone's value, not a
    # manually-redefined one. If the backbone ever upgrades φ/e precision,
    # every downstream module benefits automatically.
    assert sub.PHI == pp.phi
    assert sub.E_CONST == pp.e_const
    # And the value must be a Fraction (float-free mandate)
    assert isinstance(sub.PHI, Fraction)
    assert isinstance(sub.E_CONST, Fraction)
    # Sanity: still recognizes as φ ≈ 1.618...
    assert abs(float(sub.PHI) - 1.618033988749895) < 1e-14
    assert abs(float(sub.E_CONST) - 2.718281828459045) < 1e-14


def test_L_eq_w_over_13():
    """L = w/13 must hold exactly (UBP_SKILL_1 §3)."""
    import ubp_engine_substrate as sub
    assert sub.SINK_L == sub.WOBBLE / Fraction(13, 1)


def test_L_s_eq_L_times_sigma():
    """L_s = L × σ (UBP_SKILL_1 §3)."""
    import ubp_engine_substrate as sub
    assert sub.SINK_L_STEREO == sub.SINK_L * sub.SINK_SIGMA


def test_sigma_is_29_over_24():
    """σ = 29/24 exactly (UBP_SKILL_1 §3)."""
    import ubp_engine_substrate as sub
    assert sub.SINK_SIGMA == Fraction(29, 24)


def test_U_e_is_24_cubed():
    """U_e = 24³ = 13824."""
    import ubp_engine_substrate as sub
    assert int(sub.EXISTENCE_UNIT) == 24 ** 3


# ── v5.4 physics predictions ────────────────────────────────────────────────
def test_shear_constants():
    """Shear_1 and Shear_2 must match UBP_SKILL_1 §7 documented values."""
    import ubp_engine_substrate as sub
    LY = sub.SINK_L * sub.Y_CONSTANT
    expected_shear_1 = 1 + 3 * float(LY)
    expected_shear_2 = 1 + 3 * float(LY) + 12 * float(LY) ** 2
    assert abs(float(sub.SHEAR_1) - expected_shear_1) < 1e-12
    assert abs(float(sub.SHEAR_2) - expected_shear_2) < 1e-12
    # Documented approximate values
    assert abs(float(sub.SHEAR_1) - 1.04992) < 1e-4
    assert abs(float(sub.SHEAR_2) - 1.05324) < 1e-4


def test_muon_electron_ratio():
    """m_μ/m_e = 169/w (UBP_SKILL_1 §9 row 1)."""
    import ubp_engine_substrate as sub
    expected = Fraction(169) / sub.WOBBLE
    assert sub.MUON_ELECTRON_RATIO == expected
    err = abs(float(sub.MUON_ELECTRON_RATIO) - 206.7683) / 206.7683 * 100
    assert err < 0.10  # < 0.1% per UBP_SKILL


def test_strong_coupling_alpha_s():
    """α_s = 24·Y⁴ (UBP_SKILL_1 §9 row 2)."""
    import ubp_engine_substrate as sub
    expected = Fraction(24) * sub.Y_CONSTANT ** 4
    assert sub.STRONG_COUPLING_ALPHA_S == expected
    err = abs(float(sub.STRONG_COUPLING_ALPHA_S) - 0.1181) / 0.1181 * 100
    assert err < 0.50


def test_alpha_cubed():
    """α³ = (29/24)·Y¹²·e (UBP_SKILL_1 §9 row 7)."""
    import ubp_engine_substrate as sub
    expected = Fraction(29, 24) * sub.Y_CONSTANT ** 12 * sub.E_CONST
    assert sub.ALPHA_CUBED == expected
    target = float(Fraction(1000, 137036) ** 3)
    err = abs(float(sub.ALPHA_CUBED) - target) / target * 100
    assert err < 0.50


def test_hubble_H0():
    """H₀ = (1/3)·w·Y³·U_e (UBP_SKILL_1 §9 row 8)."""
    import ubp_engine_substrate as sub
    expected = Fraction(1, 3) * sub.WOBBLE * sub.Y_CONSTANT ** 3 * sub.EXISTENCE_UNIT
    assert sub.HUBBLE_H0 == expected
    err = abs(float(sub.HUBBLE_H0) - 70.0) / 70.0 * 100
    assert err < 1.00


def test_omega_k_base():
    """Ω_k base = 24·Y¹⁵·U_e (UBP_SKILL_1 §9 row 4)."""
    import ubp_engine_substrate as sub
    expected = Fraction(24) * sub.Y_CONSTANT ** 15 * sub.EXISTENCE_UNIT
    assert sub.OMEGA_K_BASE == expected
    err = abs(float(sub.OMEGA_K_BASE) - 7.27e-4) / 7.27e-4 * 100
    assert err < 1.00


def test_gravitational_G():
    """G = (39/29)·Y¹⁸/w (UBP_SKILL_1 §9 row G)."""
    import ubp_engine_substrate as sub
    expected = Fraction(39, 29) * sub.Y_CONSTANT ** 18 / sub.WOBBLE
    assert sub.GRAVITATIONAL_G == expected
    err = abs(float(sub.GRAVITATIONAL_G) - 6.6743e-11) / 6.6743e-11 * 100
    assert err < 0.50


# ── v5.4 engine accessors ──────────────────────────────────────────────────
def test_get_monster():
    """get_monster() returns the MonsterGroup singleton."""
    import ubp_engine_substrate as sub
    m = sub.get_monster()
    assert m is sub.MONSTER_ENGINE
    # MOONSHINE module map must be exposed (Monster ∩ modular forms)
    assert hasattr(m, 'MOONSHINE')


def test_get_barnes_wall():
    """get_barnes_wall(dimension) returns a BarnesWallEngine of that dim."""
    import ubp_engine_substrate as sub
    bw = sub.get_barnes_wall(256)
    assert bw is not None
    assert getattr(bw, 'dimension', None) == 256
    # Reject invalid dimensions
    with pytest.raises(ValueError):
        sub.get_barnes_wall(100)


def test_get_triad():
    """get_triad() returns a fresh TriadActivationEngine (no args needed in v5.4)."""
    import ubp_engine_substrate as sub
    t1 = sub.get_triad()
    t2 = sub.get_triad()
    assert t1 is not None and t2 is not None
    # Fresh instances — not the same object
    assert t1 is not t2


def test_get_noise_alu_default_sv():
    """get_noise_alu() defaults to SV (substrate-verified) mode."""
    import ubp_engine_substrate as sub
    alu = sub.get_noise_alu()
    assert alu is not None
    assert hasattr(alu, 'add')


def test_get_noise_alu_sm_mode():
    """get_noise_alu('SM') accepts the substrate-mediated mode."""
    import ubp_engine_substrate as sub
    alu = sub.get_noise_alu('SM')
    assert alu is not None
    assert hasattr(alu, 'add')


def test_get_noise_alu_invalid_mode():
    """Invalid ALU mode must raise ValueError."""
    import ubp_engine_substrate as sub
    with pytest.raises(ValueError):
        sub.get_noise_alu('XX')


def test_get_physics_alu():
    """get_physics_alu() returns a PhysicsALU (subclass of NoiseALU)."""
    import ubp_engine_substrate as sub
    import ubp_unified_v5 as bb
    palu = sub.get_physics_alu()
    assert isinstance(palu, bb.PhysicsALU)
    assert isinstance(palu, bb.NoiseALU)  # inheritance check


def test_get_linear_algebra_alu():
    """get_linear_algebra_alu() returns a LinearAlgebraALU."""
    import ubp_engine_substrate as sub
    lalu = sub.get_linear_algebra_alu()
    assert lalu is not None
    assert hasattr(lalu, 'add')


# ── validate_substrate v5.4 enhancements ───────────────────────────────────
def test_validate_substrate_returns_green():
    """validate_substrate() must return overall GREEN status."""
    import ubp_engine_substrate as sub
    r = sub.validate_substrate()
    assert r['overall'] == 'GREEN', f"validate_substrate overall = {r['overall']}"


def test_validate_substrate_has_v54_predictions():
    """validate_substrate must include the v54_physics_predictions block."""
    import ubp_engine_substrate as sub
    r = sub.validate_substrate()
    assert 'v54_physics_predictions' in r
    block = r['v54_physics_predictions']
    assert block['status'] == 'GREEN'
    # Each formula must have predicted/target/error_pct/budget
    for k in ('muon_electron_ratio', 'strong_coupling_alpha_s', 'alpha_cubed',
              'hubble_H0', 'omega_k_base', 'gravitational_G'):
        assert k in block, f"missing v5.4 prediction: {k}"
        entry = block[k]
        for field in ('predicted', 'target', 'error_pct', 'budget'):
            assert field in entry, f"{k} missing field {field}"
        assert entry['error_pct'] < entry['budget'], (
            f"{k}: error {entry['error_pct']:.4f}% exceeds budget {entry['budget']}%"
        )


def test_validate_substrate_has_triad_engines_block():
    """validate_substrate must include the triad_engines block (v5.4 NEW)."""
    import ubp_engine_substrate as sub
    r = sub.validate_substrate()
    assert 'triad_engines' in r
    block = r['triad_engines']
    assert block['status'] in ('GREEN', 'YELLOW')
    assert block.get('monster_loaded') is True
    assert block.get('barnes_wall_dim_256') is True
    assert block.get('triad_instantiable') is True


def test_validate_substrate_has_sovereign_alu_block():
    """validate_substrate must include the sovereign_alu block (v5.4 NEW)."""
    import ubp_engine_substrate as sub
    r = sub.validate_substrate()
    assert 'sovereign_alu' in r
    block = r['sovereign_alu']
    assert block['status'] in ('GREEN', 'YELLOW')
    assert block.get('noise_alu_loaded') is True
    assert block.get('physics_alu_loaded') is True
    assert block.get('linear_algebra_alu_loaded') is True


# ── UBPEngineSubstrate class wrapper ────────────────────────────────────────
def test_UBPEngineSubstrate_exposes_v54_attrs():
    """UBPEngineSubstrate instance must expose every v5.4 NEW attribute."""
    import ubp_engine_substrate as sub
    s = sub.UBPEngineSubstrate()
    # Triad engines
    assert s.monster is sub.MONSTER_ENGINE
    assert s.barnes_wall is sub.BW_ENGINE
    assert s.triad is not None
    # v5.4 constants
    for attr in ('SHEAR_1', 'SHEAR_2', 'MUON_ELECTRON_RATIO',
                 'STRONG_COUPLING_ALPHA_S', 'ALPHA_CUBED', 'HUBBLE_H0',
                 'OMEGA_K_BASE', 'GRAVITATIONAL_G', 'W_BOSON_BASE',
                 'PHI', 'E_CONST', 'MONAD', 'WOBBLE', 'SINK_SIGMA',
                 'EXISTENCE_UNIT', 'Y_INV'):
        assert hasattr(s, attr), f"UBPEngineSubstrate missing attribute: {attr}"


def test_UBPEngineSubstrate_has_v54_accessor_methods():
    """UBPEngineSubstrate must expose v5.4 NEW accessor methods."""
    import ubp_engine_substrate as sub
    s = sub.UBPEngineSubstrate()
    for m in ('get_monster', 'get_barnes_wall', 'get_triad',
              'get_noise_alu', 'get_physics_alu', 'get_linear_algebra_alu'):
        assert hasattr(s, m) and callable(getattr(s, m)), f"missing method: {m}"
    # Round-trip through the accessors
    assert s.get_monster() is sub.MONSTER_ENGINE
    assert s.get_barnes_wall(256) is not None
    assert s.get_triad() is not None
    assert s.get_noise_alu() is not None
    assert s.get_physics_alu() is not None
    assert s.get_linear_algebra_alu() is not None
