"""
Phase 5 tests — ubp_fluid_v3, ubp_rigid_body_v3, ubp_space_v3 under v5.4 alignment.

Verifies that:
  1. ubp_fluid_v3:
     • Imports cleanly with KISSING_NUMBER from substrate (was hardcoded)
     • SPH constants (smoothing radius, pressure stiffness, viscosity,
       surface tension) match their canonical UBP formulas
     • Registers as the "core_fluid" domain
     • core_fluid validates GREEN (all 10 formula checks)
  2. ubp_rigid_body_v3:
     • Imports cleanly with KISSING_NUMBER from substrate
     • C_DRAG = Y² (The Shaving), V_REST = SINK_L/100
     • Registers as the "core_rigid_body" domain
     • core_rigid_body validates GREEN (all 7 checks)
  3. ubp_space_v3:
     • Imports cleanly with v5.4 shear + physics-prediction constants
     • F_MAX_HZ is the canonical 1 THz Wall of Reality
     • Registers as the "core_space" domain
     • core_space validates GREEN (all 7 checks)
  4. The full registry now has 5 domains: core_mechanics, core_physics,
     core_fluid, core_rigid_body, core_space — all GREEN.
  5. validate_substrate() picks up all 5 domains.
  6. run_validation.py 64/64 still passes (no regressions).

Run:  pytest tests/test_phase5_fluid_rigid_space.py -v
"""
from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ── Cross-test fixture: ensure all 5 core domains are registered ──────────
@pytest.fixture
def ensure_all_domains_registered():
    """Ensure all 5 core domains are registered (core_mechanics, core_physics,
    core_fluid, core_rigid_body, core_space).

    Phase 3/4 tests may have cleared the registry; this fixture re-imports
    (or reloads) the modules to re-fire registration side-effects.
    """
    from ubp_physics_registry import get_registry

    import ubp_mechanics_v4   # noqa: F401
    import ubp_physics_v3     # noqa: F401
    import ubp_fluid_v3       # noqa: F401
    import ubp_rigid_body_v3  # noqa: F401
    import ubp_space_v3       # noqa: F401

    r = get_registry()
    required = {'core_mechanics', 'core_physics', 'core_fluid',
                'core_rigid_body', 'core_space'}
    if not required.issubset(set(r.registered_names)):
        import importlib
        # Reload to re-fire the registration side-effects
        if 'core_mechanics' not in r.registered_names:
            importlib.reload(ubp_mechanics_v4)
        if 'core_physics' not in r.registered_names:
            importlib.reload(ubp_physics_v3)
        if 'core_fluid' not in r.registered_names:
            importlib.reload(ubp_fluid_v3)
        if 'core_rigid_body' not in r.registered_names:
            importlib.reload(ubp_rigid_body_v3)
        if 'core_space' not in r.registered_names:
            importlib.reload(ubp_space_v3)
    return r


# ── Fluid v3 ──────────────────────────────────────────────────────────────
def test_fluid_v3_imports_clean():
    """ubp_fluid_v3 must import without errors under v5.4."""
    import ubp_fluid_v3 as f
    assert f is not None


def test_fluid_v3_kissing_sourced_from_substrate():
    """_KISSING in fluid must be sourced from substrate (KISSING_NUMBER),
    not hardcoded as D('196560') locally."""
    import ubp_fluid_v3 as f
    import ubp_engine_substrate as sub
    assert int(f._KISSING) == sub.KISSING_NUMBER
    assert int(f._KISSING) == 196560


def test_fluid_v3_sph_constants_match_canonical_formulas():
    """All SPH constants must match their canonical UBP formulas:
      • SMOOTHING_RADIUS = Y_INV / 8
      • PRESSURE_STIFFNESS = SINK_L × 24 / KISSING
      • VISCOSITY = Y / 96
      • SURFACE_TENSION = Y² / KISSING
    """
    import ubp_fluid_v3 as f
    from decimal import Decimal as D
    # Smoothing radius = Y_INV / 8
    expected_sr = f._Y_INV / D('8')
    assert abs(float(f.SMOOTHING_RADIUS) - float(expected_sr)) < 1e-30
    # Pressure stiffness = SINK_L × 24 / KISSING
    expected_ps = f._SINK_L * D('24') / f._KISSING
    assert abs(float(f.PRESSURE_STIFFNESS) - float(expected_ps)) < 1e-30
    # Viscosity = Y / 96
    expected_v = f._Y / D('96')
    assert abs(float(f.VISCOSITY) - float(expected_v)) < 1e-30
    # Surface tension = Y² / KISSING
    expected_st = f._Y * f._Y / f._KISSING
    assert abs(float(f.SURFACE_TENSION) - float(expected_st)) < 1e-30


def test_fluid_v3_constants_positive():
    """All SPH constants must be positive."""
    import ubp_fluid_v3 as f
    assert float(f.SMOOTHING_RADIUS) > 0
    assert float(f.PRESSURE_STIFFNESS) > 0
    assert float(f.VISCOSITY) > 0
    assert float(f.SURFACE_TENSION) > 0
    assert float(f.REST_DENSITY) > 0


def test_fluid_v3_registers_core_fluid_domain(ensure_all_domains_registered):
    """Importing ubp_fluid_v3 must register a 'core_fluid' domain."""
    r = ensure_all_domains_registered
    assert 'core_fluid' in r.registered_names


def test_core_fluid_domain_validates_green(ensure_all_domains_registered):
    """The core_fluid domain's validate() must return GREEN — all 10 checks."""
    from ubp_physics_registry import get_domain
    d = get_domain('core_fluid')
    v = d.validate()
    assert v['status'] == 'GREEN', f"core_fluid validate failed: {v}"
    # All 10 checks must pass
    for k in ('kissing_matches_substrate', 'smoothing_radius_positive',
              'pressure_stiffness_positive', 'viscosity_positive',
              'surface_tension_positive', 'rest_density_positive',
              'smoothing_radius_formula', 'pressure_stiffness_formula',
              'viscosity_formula', 'surface_tension_formula'):
        assert v.get(k) is True, f"core_fluid check {k} failed"


def test_core_fluid_domain_exposes_formulas(ensure_all_domains_registered):
    """The core_fluid domain must expose its SPH formulas through the registry."""
    from ubp_physics_registry import get_domain
    d = get_domain('core_fluid')
    for name in ('smoothing_radius', 'pressure_stiffness',
                 'viscosity', 'surface_tension'):
        assert name in d.formulas, f"core_fluid missing formula: {name}"
        # Each formula must return a Fraction when called
        result = d.formula_value(name)
        assert isinstance(result, Fraction), (
            f"{name} formula returned {type(result).__name__}, expected Fraction"
        )


# ── Rigid body v3 ─────────────────────────────────────────────────────────
def test_rigid_body_v3_imports_clean():
    """ubp_rigid_body_v3 must import without errors under v5.4."""
    import ubp_rigid_body_v3 as rb
    assert rb is not None


def test_rigid_body_v3_kissing_sourced_from_substrate():
    """_KISSING in rigid_body must be sourced from substrate."""
    import ubp_rigid_body_v3 as rb
    import ubp_engine_substrate as sub
    assert int(rb._KISSING) == sub.KISSING_NUMBER


def test_rigid_body_v3_constants_match_canonical_formulas():
    """C_DRAG = Y² (The Shaving), V_REST = SINK_L/100."""
    import ubp_rigid_body_v3 as rb
    from decimal import Decimal as D
    expected_c_drag = rb._Y * rb._Y
    expected_v_rest = rb._SINK_L / D('100')
    assert abs(float(rb._C_DRAG) - float(expected_c_drag)) < 1e-30
    assert abs(float(rb._V_REST) - float(expected_v_rest)) < 1e-30


def test_rigid_body_v3_registers_core_rigid_body_domain(ensure_all_domains_registered):
    """Importing ubp_rigid_body_v3 must register a 'core_rigid_body' domain."""
    r = ensure_all_domains_registered
    assert 'core_rigid_body' in r.registered_names


def test_core_rigid_body_domain_validates_green(ensure_all_domains_registered):
    """The core_rigid_body domain's validate() must return GREEN — all 7 checks."""
    from ubp_physics_registry import get_domain
    d = get_domain('core_rigid_body')
    v = d.validate()
    assert v['status'] == 'GREEN', f"core_rigid_body validate failed: {v}"
    for k in ('kissing_matches_substrate', 'c_drag_formula', 'v_rest_formula',
              'c_drag_positive', 'v_rest_positive',
              'shear_1_in_range', 'shear_2_in_range'):
        assert v.get(k) is True, f"core_rigid_body check {k} failed"


def test_core_rigid_body_domain_exposes_formulas(ensure_all_domains_registered):
    """The core_rigid_body domain must expose its formulas through the registry."""
    from ubp_physics_registry import get_domain
    d = get_domain('core_rigid_body')
    for name in ('angular_damping_coefficient', 'rest_threshold'):
        assert name in d.formulas, f"core_rigid_body missing formula: {name}"
        result = d.formula_value(name)
        assert isinstance(result, Fraction)


# ── Space v3 ──────────────────────────────────────────────────────────────
def test_space_v3_imports_clean():
    """ubp_space_v3 must import without errors under v5.4."""
    import ubp_space_v3 as s
    assert s is not None


def test_space_v3_has_v54_constants():
    """ubp_space_v3 must expose v5.4 shear + physics-prediction constants."""
    import ubp_space_v3 as s
    for attr in ('SHEAR_1', 'SHEAR_2', 'GRAVITATIONAL_G', 'MUON_ELECTRON_RATIO'):
        assert hasattr(s, attr), f"ubp_space_v3 missing v5.4 constant: {attr}"


def test_space_v3_f_max_hz_canonical():
    """F_MAX_HZ must be the canonical 1 THz Wall of Reality."""
    import ubp_space_v3 as s
    assert s.F_MAX_HZ == 10**12


def test_space_v3_registers_core_space_domain(ensure_all_domains_registered):
    """Importing ubp_space_v3 must register a 'core_space' domain."""
    r = ensure_all_domains_registered
    assert 'core_space' in r.registered_names


def test_core_space_domain_validates_green(ensure_all_domains_registered):
    """The core_space domain's validate() must return GREEN — all 7 checks."""
    from ubp_physics_registry import get_domain
    d = get_domain('core_space')
    v = d.validate()
    assert v['status'] == 'GREEN', f"core_space validate failed: {v}"
    for k in ('f_max_hz_canonical', 'y_matches_substrate',
              'sink_l_matches_substrate', 'shear_1_in_range',
              'shear_2_in_range', 'gravitational_g_in_range',
              'muon_ratio_in_range'):
        assert v.get(k) is True, f"core_space check {k} failed"


def test_core_space_domain_exposes_wall_of_reality_formula(ensure_all_domains_registered):
    """The core_space domain must expose the wall_of_reality_hz formula."""
    from ubp_physics_registry import get_domain
    d = get_domain('core_space')
    assert 'wall_of_reality_hz' in d.formulas
    result = d.formula_value('wall_of_reality_hz')
    assert result == Fraction(10**12)


# ── Full registry: all 5 domains ──────────────────────────────────────────
def test_registry_has_5_core_domains(ensure_all_domains_registered):
    """The registry must now have all 5 core domains registered."""
    r = ensure_all_domains_registered
    expected = {'core_mechanics', 'core_physics', 'core_fluid',
                'core_rigid_body', 'core_space'}
    actual = set(r.registered_names)
    missing = expected - actual
    assert not missing, f"Missing domains: {missing}"


def test_all_5_domains_validate_green(ensure_all_domains_registered):
    """All 5 core domains must validate GREEN through the registry."""
    from ubp_physics_registry import validate_all_domains
    results = validate_all_domains()
    assert results['_overall'] == 'GREEN', (
        f"Overall registry validation failed: {results['_overall']}"
    )
    assert results['_domain_count'] >= 5
    for name in ('core_mechanics', 'core_physics', 'core_fluid',
                 'core_rigid_body', 'core_space'):
        assert name in results
        assert results[name]['status'] == 'GREEN', (
            f"{name} status = {results[name]['status']}"
        )


# ── Substrate integration ────────────────────────────────────────────────
def test_validate_substrate_picks_up_all_5_domains(ensure_all_domains_registered):
    """validate_substrate() must now include all 5 domains in its
    physics_registry block, all GREEN."""
    import ubp_engine_substrate as sub
    r = sub.validate_substrate()
    assert r['overall'] == 'GREEN'
    assert 'physics_registry' in r
    reg = r['physics_registry']
    assert reg['_overall'] == 'GREEN'
    assert reg['_domain_count'] >= 5
    for name in ('core_mechanics', 'core_physics', 'core_fluid',
                 'core_rigid_body', 'core_space'):
        assert name in reg
        assert reg[name]['status'] == 'GREEN'


# ── No regressions in existing validation suite ──────────────────────────
def test_run_validation_suite_still_passes():
    """The 64-test run_validation.py suite must still pass — no regressions
    from the v5.4 alignment changes in Phase 5."""
    import subprocess
    result = subprocess.run(
        ['python3', 'run_validation.py'],
        capture_output=True, text=True, timeout=120,
        cwd=str(REPO_ROOT),
    )
    assert result.returncode == 0, (
        f"run_validation.py exited with code {result.returncode}\n"
        f"stdout (last 500 chars): {result.stdout[-500:]}\n"
        f"stderr (last 500 chars): {result.stderr[-500:]}"
    )
    assert '64/64 passed' in result.stdout
    assert 'ALL TESTS PASS' in result.stdout
