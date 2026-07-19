"""
Phase 4 tests — ubp_physics_v3 and ubp_mechanics_v4* under v5.4 alignment.

Verifies that:
  1. ubp_mechanics_v4 imports constants from ubp_engine_substrate (single
     source of truth) — no longer bypasses to UBPUltimateSubstrate.
  2. SIGMA in mechanics matches PARTICLE_PHYSICS.sigma exactly.
  3. Mechanics v4 has access to v5.4 shear and physics-prediction constants.
  4. Mechanics v4 registers itself as the "core_mechanics" domain.
  5. ubp_physics_v3 imports the v5.4 physics-prediction constants.
  6. ubp_physics_v3 registers itself as the "core_physics" domain.
  7. Both domains validate GREEN through the registry.
  8. validate_substrate() now picks up both new domains automatically.
  9. The existing 64-test run_validation.py suite still passes (no regressions).

NOTE ON TEST ISOLATION
----------------------
Some Phase 3 tests deliberately clear the registry (test_physics_registry_initially_empty,
test_register_and_retrieve_domain, etc.). This can leave the registry empty
even though ubp_mechanics_v4 / ubp_physics_v3 were imported earlier in the
session (their registration side-effects only fire on first import).

The `ensure_domains_registered` fixture below re-runs the registration by
directly invoking the registration logic, so Phase 4 tests are robust to
registry state pollution from Phase 3 tests.

Run:  pytest tests/test_phase4_physics_and_mechanics.py -v
"""
from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ── Cross-test fixture: ensure both core domains are registered ──────────
@pytest.fixture
def ensure_domains_registered():
    """Ensure core_mechanics and core_physics are both registered.

    Phase 3 tests may have cleared the registry; this fixture re-runs the
    registration side-effects (idempotent — uses replace=True semantics
    via the registry's replace parameter).
    """
    from ubp_physics_registry import get_registry

    # Force-import the modules. They register themselves on import. If they
    # were already imported, the side-effect has already run; if the
    # registry was cleared since, we re-register manually.
    import ubp_mechanics_v4  # noqa: F401
    import ubp_physics_v3    # noqa: F401

    r = get_registry()
    # If the domains are missing (because Phase 3 cleared them), re-register
    # by reloading the modules.
    if 'core_mechanics' not in r.registered_names or 'core_physics' not in r.registered_names:
        import importlib
        # Reload to re-fire the registration side-effects
        importlib.reload(ubp_mechanics_v4)
        importlib.reload(ubp_physics_v3)
    return r


# ── Mechanics v4: v5.4 substrate imports ──────────────────────────────────
def test_mechanics_v4_imports_clean():
    """ubp_mechanics_v4 must import without errors under v5.4."""
    import ubp_mechanics_v4 as m
    assert m is not None


def test_mechanics_v4_sigma_matches_substrate():
    """SIGMA in mechanics must equal PARTICLE_PHYSICS.sigma (single source
    of truth). v1.0 redefined it locally as Fraction(29, 24)."""
    import ubp_mechanics_v4 as m
    import ubp_engine_substrate as sub
    assert m.SIGMA == sub.SINK_SIGMA
    assert m.SIGMA == sub.PARTICLE_PHYSICS.sigma
    assert m.SIGMA == Fraction(29, 24)


def test_mechanics_v4_constants_match_substrate():
    """Y, PI, Y_INV, SINK_L, KISSING in mechanics must match substrate."""
    import ubp_mechanics_v4 as m
    import ubp_engine_substrate as sub
    assert m.Y == sub.Y_CONSTANT
    assert m.PI == sub.PI
    assert m.Y_INV == sub.Y_INV
    assert m.SINK_L == sub.SINK_L
    assert m.KISSING == sub.KISSING_NUMBER
    assert m.KISSING == 196560


def test_mechanics_v4_has_v54_shear_constants():
    """Mechanics v4 must expose v5.4 shear constants for use in collision
    and synthesis strength calculations."""
    import ubp_mechanics_v4 as m
    assert hasattr(m, 'SHEAR_1')
    assert hasattr(m, 'SHEAR_2')
    assert isinstance(m.SHEAR_1, Fraction)
    assert isinstance(m.SHEAR_2, Fraction)
    # Documented approximate values (UBP_SKILL_1 §7)
    assert abs(float(m.SHEAR_1) - 1.04992) < 1e-4
    assert abs(float(m.SHEAR_2) - 1.05324) < 1e-4


def test_mechanics_v4_has_v54_physics_predictions():
    """Mechanics v4 must expose v5.4 physics-prediction constants."""
    import ubp_mechanics_v4 as m
    assert hasattr(m, 'MUON_ELECTRON_RATIO')
    assert hasattr(m, 'GRAVITATIONAL_G')
    # Documented values
    assert abs(float(m.MUON_ELECTRON_RATIO) - 206.7075) < 0.01
    assert abs(float(m.GRAVITATIONAL_G) - 6.683e-11) < 1e-13


def test_mechanics_v4_singleton_loads():
    """UBP_MECHANICS singleton must be instantiated."""
    import ubp_mechanics_v4 as m
    assert m.UBP_MECHANICS is not None


def test_mechanics_v4_thresholds_canonical():
    """NRCI thresholds must match UBP canonical values."""
    import ubp_mechanics_v4 as m
    assert m.NRCI_DISSOLUTION_THRESHOLD == 0.40
    assert m.NRCI_NOISE_FLOOR == 0.42
    assert m.NCRI_REFLEX_THRESHOLD == 0.60
    assert m.NRCI_AVG_TARGET == 0.60
    assert m.NRCI_COHERENT_THRESHOLD == 11.0 / 12.0
    # Phi-Orbit period canonical
    assert m.PHI_ORBIT_PERIOD == 1953
    # Phi-Orbit vector is 24 bits
    assert len(m.PHI_VEC) == 24
    assert all(b in (0, 1) for b in m.PHI_VEC)


# ── Mechanics v4: registers as "core_mechanics" domain ───────────────────
def test_mechanics_v4_registers_core_mechanics_domain(ensure_domains_registered):
    """Importing ubp_mechanics_v4 must register a 'core_mechanics' domain
    in the physics registry."""
    r = ensure_domains_registered
    assert 'core_mechanics' in r.registered_names


def test_core_mechanics_domain_validates_green(ensure_domains_registered):
    """The core_mechanics domain's validate() must return GREEN."""
    from ubp_physics_registry import get_domain
    d = get_domain('core_mechanics')
    v = d.validate()
    assert v['status'] == 'GREEN'
    assert v['singleton_loaded'] is True
    assert v['sigma_matches_substrate'] is True
    assert v['thresholds_in_range'] is True
    assert v['phi_orbit_period_canonical'] is True
    assert v['kissing_number_canonical'] is True


def test_core_mechanics_domain_exposes_constants(ensure_domains_registered):
    """The core_mechanics domain must expose its constants through the registry."""
    from ubp_physics_registry import get_domain
    d = get_domain('core_mechanics')
    for k in ('Y', 'PI', 'Y_INV', 'SINK_L', 'SIGMA', 'SHEAR_1', 'SHEAR_2'):
        assert k in d.constants, f"core_mechanics missing constant: {k}"


# ── Mechanics v4.1 macro-soul patch ───────────────────────────────────────
def test_macro_soul_imports_clean():
    """ubp_mechanics_v4_1_macro_soul must import without errors."""
    import ubp_mechanics_v4_1_macro_soul as ms
    assert ms is not None
    assert hasattr(ms, 'NCRIState')
    assert hasattr(ms, 'patch_phi_orbit_tick')
    assert hasattr(ms, 'patch_apply_damage')
    assert hasattr(ms, 'patch_dissolution_check')


def test_macro_soul_ncristate_has_macro_fields():
    """NCRIState from macro_soul must carry the v4.1 macro fields."""
    import ubp_mechanics_v4_1_macro_soul as ms
    state = ms.NCRIState(vector=[1]*8 + [0]*16, nrci=0.7, symmetry_tax=2.0)
    assert hasattr(state, 'macro_nrci')
    assert hasattr(state, 'macro_basin')
    assert hasattr(state, 'macro_tax')
    assert hasattr(state, 'shadow_drift')


# ── Physics v3: v5.4 imports ─────────────────────────────────────────────
def test_physics_v3_imports_clean():
    """ubp_physics_v3 must import without errors under v5.4."""
    import ubp_physics_v3 as p
    assert p is not None


def test_physics_v3_has_v54_constants():
    """ubp_physics_v3 must expose v5.4 shear and physics-prediction constants."""
    import ubp_physics_v3 as p
    for attr in ('SHEAR_1', 'SHEAR_2', 'MUON_ELECTRON_RATIO',
                 'STRONG_COUPLING_ALPHA_S', 'ALPHA_CUBED',
                 'HUBBLE_H0', 'OMEGA_K_BASE', 'GRAVITATIONAL_G'):
        assert hasattr(p, attr), f"ubp_physics_v3 missing v5.4 constant: {attr}"


def test_physics_v3_constants_match_substrate():
    """v5.4 constants in physics_v3 must match the substrate (single source)."""
    import ubp_physics_v3 as p
    import ubp_engine_substrate as sub
    assert p.SHEAR_1 == sub.SHEAR_1
    assert p.SHEAR_2 == sub.SHEAR_2
    assert p.MUON_ELECTRON_RATIO == sub.MUON_ELECTRON_RATIO
    assert p.GRAVITATIONAL_G == sub.GRAVITATIONAL_G


def test_physics_v3_internal_constants_unchanged():
    """The internal _Y, _SINK_L, _G_PER_TICK_SQ, _C_DRAG, _V_MAX,
    _V_REST_THRESHOLD constants must still be derived correctly from the
    substrate values (Decimal-converted, no precision loss).

    NOTE: We use 1e-15 tolerance because comparing Decimal→float vs
    Fraction→float introduces ~1e-17 round-off. The point of this test
    is to catch gross drift, not bit-exact equality across numeric types.
    """
    import ubp_physics_v3 as p
    import ubp_engine_substrate as sub
    # _Y must equal Decimal(Y_CONSTANT)
    assert abs(float(p._Y) - float(sub.Y_CONSTANT)) < 1e-15
    # _SINK_L must equal Decimal(SINK_L)
    assert abs(float(p._SINK_L) - float(sub.SINK_L)) < 1e-15
    # _C_DRAG = Y²
    assert abs(float(p._C_DRAG) - float(sub.Y_CONSTANT) ** 2) < 1e-15
    # _V_MAX = 1/Y
    assert abs(float(p._V_MAX) - 1.0 / float(sub.Y_CONSTANT)) < 1e-15


# ── Physics v3: registers as "core_physics" domain ───────────────────────
def test_physics_v3_registers_core_physics_domain(ensure_domains_registered):
    """Importing ubp_physics_v3 must register a 'core_physics' domain."""
    r = ensure_domains_registered
    assert 'core_physics' in r.registered_names


def test_core_physics_domain_validates_green(ensure_domains_registered):
    """The core_physics domain's validate() must return GREEN — all 6 v5.4
    canonical formulas within their documented error budgets."""
    from ubp_physics_registry import get_domain
    d = get_domain('core_physics')
    v = d.validate()
    assert v['status'] == 'GREEN', f"core_physics validate failed: {v}"
    # All 6 canonical formulas must be in budget
    for name in ('muon_electron_ratio', 'strong_coupling_alpha_s',
                 'alpha_cubed', 'hubble_H0', 'omega_k_base',
                 'gravitational_G'):
        assert name in v
        entry = v[name]
        assert entry['in_budget'] is True, (
            f"{name}: err={entry['error_pct']:.4f}% exceeds budget {entry['budget']}%"
        )


def test_core_physics_domain_exposes_formulas(ensure_domains_registered):
    """The core_physics domain must expose its formulas through the registry."""
    from ubp_physics_registry import get_domain
    d = get_domain('core_physics')
    for name in ('muon_electron_ratio', 'strong_coupling_alpha_s',
                 'alpha_cubed', 'hubble_H0', 'omega_k_base',
                 'gravitational_G'):
        assert name in d.formulas, f"core_physics missing formula: {name}"
        # Each formula must return a Fraction when called
        result = d.formula_value(name)
        assert isinstance(result, Fraction), (
            f"{name} formula returned {type(result).__name__}, expected Fraction"
        )


# ── Substrate integration: validate_substrate picks up both domains ───────
def test_validate_substrate_picks_up_both_domains(ensure_domains_registered):
    """validate_substrate() must now include both core_mechanics and
    core_physics in its physics_registry block."""
    import ubp_engine_substrate as sub
    r = sub.validate_substrate()
    assert r['overall'] == 'GREEN'
    assert 'physics_registry' in r
    reg = r['physics_registry']
    assert reg['_overall'] == 'GREEN'
    assert reg['_domain_count'] >= 2
    assert 'core_mechanics' in reg
    assert reg['core_mechanics']['status'] == 'GREEN'
    assert 'core_physics' in reg
    assert reg['core_physics']['status'] == 'GREEN'


# ── No regressions in existing validation suite ───────────────────────────
def test_run_validation_suite_still_passes():
    """The 64-test run_validation.py suite must still pass — no regressions
    from the v5.4 alignment changes in Phase 4."""
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
