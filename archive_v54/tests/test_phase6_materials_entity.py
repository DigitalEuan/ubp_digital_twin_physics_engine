"""
Phase 6 tests — ubp_materials.py and ubp_entity_v3.py under v5.4 alignment.

Verifies that:
  1. ubp_entity_v3:
     • Imports cleanly with KISSING_NUMBER from substrate (was hardcoded)
     • Physics constants (_G_PER_TICK_SQ, _V_MAX, _C_DRAG, _V_REST_THRESHOLD)
       match their canonical UBP formulas
     • Shear constants present and in range
     • Observer Dynamics canonical values (CONSCIOUS_THRESHOLD=7/10, F_MAX_HZ=1THz)
     • Registers as the "core_entity" domain
     • core_entity validates GREEN (all 14 checks)
  2. ubp_materials:
     • Imports cleanly with module-level substrate imports (no more inline)
     • KB loaded with elements and laws
     • Crystal connectivity map covers all documented types
     • MaterialRegistry returns valid recipes for presets
     • Registers as the "core_materials" domain
     • core_materials validates GREEN (all 7 checks)
  3. The full registry now has 7 domains: core_mechanics, core_physics,
     core_fluid, core_rigid_body, core_space, core_materials, core_entity.
  4. validate_substrate() picks up all 7 domains.
  5. run_validation.py 64/64 still passes (no regressions).

Run:  pytest tests/test_phase6_materials_entity.py -v
"""
from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ── Cross-test fixture: ensure all 7 core domains are registered ──────────
@pytest.fixture
def ensure_all_7_domains_registered():
    """Ensure all 7 core domains are registered."""
    from ubp_physics_registry import get_registry

    import ubp_mechanics_v4   # noqa: F401
    import ubp_physics_v3     # noqa: F401
    import ubp_fluid_v3       # noqa: F401
    import ubp_rigid_body_v3  # noqa: F401
    import ubp_space_v3       # noqa: F401
    import ubp_materials      # noqa: F401
    import ubp_entity_v3      # noqa: F401

    r = get_registry()
    required = {'core_mechanics', 'core_physics', 'core_fluid',
                'core_rigid_body', 'core_space', 'core_materials', 'core_entity'}
    if not required.issubset(set(r.registered_names)):
        import importlib
        for name, mod in [
            ('core_mechanics', ubp_mechanics_v4),
            ('core_physics', ubp_physics_v3),
            ('core_fluid', ubp_fluid_v3),
            ('core_rigid_body', ubp_rigid_body_v3),
            ('core_space', ubp_space_v3),
            ('core_materials', ubp_materials),
            ('core_entity', ubp_entity_v3),
        ]:
            if name not in r.registered_names:
                importlib.reload(mod)
    return r


# ── Entity v3 ─────────────────────────────────────────────────────────────
def test_entity_v3_imports_clean():
    """ubp_entity_v3 must import without errors under v5.4."""
    import ubp_entity_v3 as e
    assert e is not None


def test_entity_v3_kissing_sourced_from_substrate():
    """_KISSING in entity must be sourced from substrate (was hardcoded)."""
    import ubp_entity_v3 as e
    import ubp_engine_substrate as sub
    assert int(e._KISSING) == sub.KISSING_NUMBER
    assert int(e._KISSING) == 196560


def test_entity_v3_constants_match_canonical_formulas():
    """All entity physics constants must match their canonical UBP formulas:
      • _G_PER_TICK_SQ = G_EARTH / 3600 * Y
      • _V_MAX = 1 / Y
      • _C_DRAG = Y² (The Shaving)
      • _V_REST_THRESHOLD = SINK_L / 100
    """
    import ubp_entity_v3 as e
    from decimal import Decimal as D
    # _G_PER_TICK_SQ = G_EARTH / 3600 * Y
    expected_g = e._G_EARTH / D('3600') * e._Y
    assert abs(float(e._G_PER_TICK_SQ) - float(expected_g)) < 1e-30
    # _V_MAX = 1 / Y
    expected_vmax = D('1') / e._Y
    assert abs(float(e._V_MAX) - float(expected_vmax)) < 1e-30
    # _C_DRAG = Y²
    expected_cdrag = e._Y * e._Y
    assert abs(float(e._C_DRAG) - float(expected_cdrag)) < 1e-30
    # _V_REST_THRESHOLD = SINK_L / 100
    expected_vrest = e._SINK_L / D('100')
    assert abs(float(e._V_REST_THRESHOLD) - float(expected_vrest)) < 1e-30


def test_entity_v3_constants_positive():
    """All entity physics constants must be positive."""
    import ubp_entity_v3 as e
    assert float(e._G_PER_TICK_SQ) > 0
    assert float(e._V_MAX) > 0
    assert float(e._C_DRAG) > 0
    assert float(e._V_REST_THRESHOLD) > 0


def test_entity_v3_has_v54_shear_constants():
    """ubp_entity_v3 must expose v5.4 shear constants."""
    import ubp_entity_v3 as e
    assert hasattr(e, 'SHEAR_1')
    assert hasattr(e, 'SHEAR_2')
    assert 1.04 < float(e.SHEAR_1) < 1.06
    assert 1.04 < float(e.SHEAR_2) < 1.07


def test_entity_v3_observer_dynamics_canonical():
    """CONSCIOUS_THRESHOLD must be 7/10, F_MAX_HZ must be 1 THz."""
    import ubp_entity_v3 as e
    assert e.CONSCIOUS_THRESHOLD == Fraction(7, 10)
    assert e.F_MAX_HZ == 10**12


def test_entity_v3_registers_core_entity_domain(ensure_all_7_domains_registered):
    """Importing ubp_entity_v3 must register a 'core_entity' domain."""
    r = ensure_all_7_domains_registered
    assert 'core_entity' in r.registered_names


def test_core_entity_domain_validates_green(ensure_all_7_domains_registered):
    """The core_entity domain's validate() must return GREEN — all 14 checks."""
    from ubp_physics_registry import get_domain
    d = get_domain('core_entity')
    v = d.validate()
    assert v['status'] == 'GREEN', f"core_entity validate failed: {v}"
    # All 14 checks must pass
    for k in ('kissing_matches_substrate',
              'g_per_tick_sq_formula', 'v_max_formula',
              'c_drag_formula', 'v_rest_threshold_formula',
              'g_per_tick_sq_positive', 'v_max_positive',
              'c_drag_positive', 'v_rest_threshold_positive',
              'shear_1_in_range', 'shear_2_in_range',
              'conscious_threshold_canonical', 'f_max_hz_canonical'):
        assert v.get(k) is True, f"core_entity check {k} failed: {v.get(k)}"


def test_core_entity_domain_exposes_formulas(ensure_all_7_domains_registered):
    """The core_entity domain must expose its formulas through the registry."""
    from ubp_physics_registry import get_domain
    d = get_domain('core_entity')
    for name in ('speed_limit', 'drag_coefficient', 'rest_threshold',
                 'conscious_threshold', 'wall_of_reality_hz'):
        assert name in d.formulas, f"core_entity missing formula: {name}"
        result = d.formula_value(name)
        assert isinstance(result, Fraction), (
            f"{name} formula returned {type(result).__name__}, expected Fraction"
        )


# ── Materials ─────────────────────────────────────────────────────────────
def test_materials_imports_clean():
    """ubp_materials must import without errors under v5.4."""
    import ubp_materials as m
    assert m is not None


def test_materials_no_inline_substrate_imports():
    """v5.4: all ubp_engine_substrate imports must be at module level
    (no more inline `from ubp_engine_substrate import X` inside methods)."""
    src = open(REPO_ROOT / 'ubp_materials.py').read()
    # Find all `from ubp_engine_substrate import` occurrences
    import re
    matches = re.findall(r'^\s*from ubp_engine_substrate import', src, re.MULTILINE)
    # Should be exactly 1 (the module-level import at line 43)
    assert len(matches) == 1, (
        f"Expected 1 module-level ubp_engine_substrate import, found {len(matches)}"
    )


def test_materials_kb_loaded():
    """The UBP system KB must load with element and law entries."""
    import ubp_materials as m
    assert len(m._KB) > 0
    assert any(k.startswith('ELEM_') for k in m._KB)
    assert any(k.startswith('LAW_') for k in m._KB)


def test_materials_crystal_connectivity_complete():
    """Crystal connectivity map must cover all documented crystal types (1-4)."""
    import ubp_materials as m
    for ct in (1, 2, 3, 4):
        assert ct in m._CRYSTAL_CONNECTIVITY
    # Documented connectivities
    assert m._CRYSTAL_CONNECTIVITY[1] == 6   # Hexagonal
    assert m._CRYSTAL_CONNECTIVITY[2] == 12  # FCC/Cubic
    assert m._CRYSTAL_CONNECTIVITY[3] == 8   # BCC
    assert m._CRYSTAL_CONNECTIVITY[4] == 4   # Monoclinic/Other


def test_materials_registry_returns_presets():
    """MaterialRegistry.get() must return valid recipes for all presets."""
    import ubp_materials as m
    for name in ('iron', 'copper', 'aluminium', 'water', 'air', 'steel'):
        recipe = m.MaterialRegistry.get(name)
        assert recipe is not None
        assert recipe.name == name


def test_materials_ambient_environment_loads():
    """AmbientEnvironment must instantiate with default 293.15 K."""
    import ubp_materials as m
    env = m.AmbientEnvironment()
    assert env is not None
    assert float(env.temperature_K) == 293.15
    # T_ubp = T_K * Y / 24
    import ubp_engine_substrate as sub
    expected_t_ubp = Fraction('293.15') * sub.Y_CONSTANT / Fraction(24)
    assert env.temperature_ubp == expected_t_ubp


def test_materials_has_v54_shear_constants():
    """ubp_materials must expose v5.4 shear constants."""
    import ubp_materials as m
    assert hasattr(m, 'SHEAR_1')
    assert hasattr(m, 'SHEAR_2')
    assert 1.04 < float(m.SHEAR_1) < 1.06
    assert 1.04 < float(m.SHEAR_2) < 1.07


def test_materials_registers_core_materials_domain(ensure_all_7_domains_registered):
    """Importing ubp_materials must register a 'core_materials' domain."""
    r = ensure_all_7_domains_registered
    assert 'core_materials' in r.registered_names


def test_core_materials_domain_validates_green(ensure_all_7_domains_registered):
    """The core_materials domain's validate() must return GREEN — all 7 checks."""
    from ubp_physics_registry import get_domain
    d = get_domain('core_materials')
    v = d.validate()
    assert v['status'] == 'GREEN', f"core_materials validate failed: {v}"
    for k in ('kb_loaded', 'kb_has_elements', 'kb_has_laws',
              'crystal_map_complete', 'material_registry_works',
              'shear_1_in_range', 'shear_2_in_range'):
        assert v.get(k) is True, f"core_materials check {k} failed: {v.get(k)}"


def test_core_materials_domain_exposes_formulas(ensure_all_7_domains_registered):
    """The core_materials domain must expose its formulas through the registry."""
    from ubp_physics_registry import get_domain
    d = get_domain('core_materials')
    for name in ('thermal_capacity_fcc_representative',
                 'heat_transfer_fcc_representative'):
        assert name in d.formulas, f"core_materials missing formula: {name}"
        result = d.formula_value(name)
        assert isinstance(result, Fraction), (
            f"{name} formula returned {type(result).__name__}, expected Fraction"
        )


# ── Full registry: all 7 domains ─────────────────────────────────────────
def test_registry_has_7_core_domains(ensure_all_7_domains_registered):
    """The registry must now have all 7 core domains registered."""
    r = ensure_all_7_domains_registered
    expected = {'core_mechanics', 'core_physics', 'core_fluid',
                'core_rigid_body', 'core_space',
                'core_materials', 'core_entity'}
    actual = set(r.registered_names)
    missing = expected - actual
    assert not missing, f"Missing domains: {missing}"


def test_all_7_domains_validate_green(ensure_all_7_domains_registered):
    """All 7 core domains must validate GREEN through the registry."""
    from ubp_physics_registry import validate_all_domains
    results = validate_all_domains()
    assert results['_overall'] == 'GREEN', (
        f"Overall registry validation failed: {results['_overall']}"
    )
    assert results['_domain_count'] >= 7
    for name in ('core_mechanics', 'core_physics', 'core_fluid',
                 'core_rigid_body', 'core_space',
                 'core_materials', 'core_entity'):
        assert name in results
        assert results[name]['status'] == 'GREEN', (
            f"{name} status = {results[name]['status']}"
        )


# ── Substrate integration ────────────────────────────────────────────────
def test_validate_substrate_picks_up_all_7_domains(ensure_all_7_domains_registered):
    """validate_substrate() must now include all 7 domains in its
    physics_registry block, all GREEN."""
    import ubp_engine_substrate as sub
    r = sub.validate_substrate()
    assert r['overall'] == 'GREEN'
    assert 'physics_registry' in r
    reg = r['physics_registry']
    assert reg['_overall'] == 'GREEN'
    assert reg['_domain_count'] >= 7
    for name in ('core_mechanics', 'core_physics', 'core_fluid',
                 'core_rigid_body', 'core_space',
                 'core_materials', 'core_entity'):
        assert name in reg
        assert reg[name]['status'] == 'GREEN'


# ── No regressions in existing validation suite ──────────────────────────
def test_run_validation_suite_still_passes():
    """The 64-test run_validation.py suite must still pass — no regressions
    from the v5.4 alignment changes in Phase 6."""
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
