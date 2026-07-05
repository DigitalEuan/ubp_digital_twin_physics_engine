"""
Phase 3 tests — TGIC engine, BarnesWall shim, Sovereign ALU, Physics Registry.

Verifies that:
  1. ubp_tgic_engine still works under v5.4 (no regressions from Phase 1)
  2. ubp_barnes_wall_engine shim correctly re-exports v5.4 BarnesWallEngine
     AND provides the v1.6 backwards-compat aliases (audit_macro_state,
     macro_nrci) so any legacy consumer still works
  3. ubp_eml_alu_sovereign loads without the previous backslash-e
     SyntaxWarning
  4. The new ubp_physics_registry module provides a working plugin pattern:
       - register_domain / get_domain / list_domains / validate_all_domains
       - dependency resolution
       - validate_substrate() picks up registered domains automatically
  5. A sample domain can be registered and validated end-to-end

Run:  pytest tests/test_phase3_engines_and_registry.py -v
"""
from __future__ import annotations

import sys
import warnings
from fractions import Fraction
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ── TGIC engine still works under v5.4 ─────────────────────────────────────
def test_tgic_engine_loads_under_v54():
    """ubp_tgic_engine must import cleanly under the v5.4 backbone."""
    import ubp_tgic_engine as tgic
    assert tgic.CORE_AVAILABLE is True
    # Core classes must be present
    assert hasattr(tgic, 'TGICExactEngine')
    assert hasattr(tgic, 'TGICInteractionEngine')
    assert hasattr(tgic, 'TGICConstraintSystem')


def test_tgic_constraint_system_initialises():
    """TGICConstraintSystem must initialise with the Y constant."""
    import ubp_tgic_engine as tgic
    cs = tgic.TGICConstraintSystem(tgic.CONST['Y'])
    assert cs is not None
    assert cs.y_const == tgic.CONST['Y']


# ── BarnesWall shim ────────────────────────────────────────────────────────
def test_barnes_wall_shim_reexports_v54_class():
    """The shim must re-export the v5.4 BarnesWallEngine class (not a
    separate standalone class)."""
    import ubp_barnes_wall_engine as shim
    import ubp_unified_v5 as bb
    assert shim.BarnesWallEngine is bb.BarnesWallEngine


def test_barnes_wall_shim_emits_deprecation_warning():
    """Importing the shim must emit a DeprecationWarning."""
    # Force a fresh import to trigger the warning
    import importlib
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        # Remove from sys.modules so the import re-runs
        sys.modules.pop('ubp_barnes_wall_engine', None)
        importlib.import_module('ubp_barnes_wall_engine')
    dep_warnings = [w for w in caught if issubclass(w.category, DeprecationWarning)]
    assert len(dep_warnings) >= 1, f"Expected DeprecationWarning, got: {[w.category.__name__ for w in caught]}"
    assert 'deprecated' in str(dep_warnings[0].message).lower()


def test_barnes_wall_shim_backwards_compat_aliases():
    """The shim must add v1.6-compat aliases audit_macro_state and macro_nrci
    so any legacy consumer code keeps working."""
    import ubp_barnes_wall_engine as shim
    assert hasattr(shim.BarnesWallEngine, 'audit_macro_state')
    assert hasattr(shim.BarnesWallEngine, 'macro_nrci')
    # The aliases must point at the v5.4 methods
    assert shim.BarnesWallEngine.audit_macro_state is shim.BarnesWallEngine.audit
    assert shim.BarnesWallEngine.macro_nrci     is shim.BarnesWallEngine.nrci


def test_barnes_wall_shim_audit_works():
    """End-to-end: use the v1.6 alias name to call the v5.4 audit method."""
    import ubp_barnes_wall_engine as shim
    import ubp_unified_v5 as bb
    g = bb.GolayCodeEngine()
    bw = shim.BarnesWallEngine(g, 256)
    seed = [1]*8 + [0]*16
    # Both names must work and return the same data
    audit_v54 = bw.audit(seed, Fraction(1, 4))
    audit_v16 = bw.audit_macro_state(seed, Fraction(1, 4))
    assert audit_v54 == audit_v16
    # Result must have the documented fields
    for k in ('dim', 'micro_nrci', 'macro_nrci', 'noisy_nrci',
              'relative_coherence', 'clarity', 'decoder_gain',
              'seed_hw', 'vector_hw', 'vector_norm_sq', 'anchor'):
        assert k in audit_v54, f"audit result missing field: {k}"


# ── EML Sovereign ALU ─────────────────────────────────────────────────────
def test_eml_alu_sovereign_imports_without_syntax_warning():
    """Importing ubp_eml_alu_sovereign must NOT raise a SyntaxWarning about
    invalid escape sequence (the previous backslash-e in the docstring)."""
    import importlib
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        sys.modules.pop('ubp_eml_alu_sovereign', None)
        importlib.import_module('ubp_eml_alu_sovereign')
    syntax_warnings = [w for w in caught if issubclass(w.category, SyntaxWarning)]
    assert len(syntax_warnings) == 0, (
        f"SyntaxWarning still present: {[str(w.message) for w in syntax_warnings]}"
    )


def test_eml_alu_sovereign_grand_unified_loads():
    """The GrandUnifiedEmlALU class must instantiate."""
    import ubp_eml_alu_sovereign as eml
    alu = eml.GrandUnifiedEmlALU()
    assert alu is not None


# ── Physics registry ──────────────────────────────────────────────────────
def test_physics_registry_singleton():
    """get_registry() must return the same singleton every call."""
    from ubp_physics_registry import get_registry
    r1 = get_registry()
    r2 = get_registry()
    assert r1 is r2


def test_physics_registry_initially_empty():
    """The registry starts empty (no domains registered)."""
    from ubp_physics_registry import get_registry, PhysicsDomain
    r = get_registry()
    # Make sure no leftover domains from other tests
    for name in list(r.registered_names):
        r.unregister(name)
    assert r.registered_names == []
    assert r.domains == {}


def test_register_and_retrieve_domain():
    """register_domain + get_domain must round-trip a PhysicsDomain."""
    from ubp_physics_registry import (
        PhysicsDomain, register_domain, get_domain, get_registry,
    )
    r = get_registry()
    # Clean slate
    for name in list(r.registered_names):
        r.unregister(name)
    d = PhysicsDomain(
        name='test_domain',
        version='0.1.0',
        description='A test domain',
        constants={'k': Fraction(1, 2)},
    )
    register_domain(d)
    assert 'test_domain' in r.registered_names
    retrieved = get_domain('test_domain')
    assert retrieved is d
    assert retrieved.constants['k'] == Fraction(1, 2)


def test_register_duplicate_raises():
    """Registering the same name twice without replace=True must raise."""
    from ubp_physics_registry import PhysicsDomain, register_domain, get_registry
    r = get_registry()
    for name in list(r.registered_names):
        r.unregister(name)
    register_domain(PhysicsDomain(name='dup', version='0.1.0'))
    with pytest.raises(ValueError, match='already registered'):
        register_domain(PhysicsDomain(name='dup', version='0.2.0'))


def test_register_duplicate_with_replace_succeeds():
    """replace=True must allow overriding an existing domain."""
    from ubp_physics_registry import PhysicsDomain, register_domain, get_domain, get_registry
    r = get_registry()
    for name in list(r.registered_names):
        r.unregister(name)
    register_domain(PhysicsDomain(name='dup', version='0.1.0'))
    register_domain(PhysicsDomain(name='dup', version='0.2.0'), replace=True)
    assert get_domain('dup').version == '0.2.0'


def test_register_with_unmet_dependency_raises():
    """Registering a domain with unmet depends_on must raise ValueError."""
    from ubp_physics_registry import PhysicsDomain, register_domain, get_registry
    r = get_registry()
    for name in list(r.registered_names):
        r.unregister(name)
    d = PhysicsDomain(
        name='dependent',
        version='0.1.0',
        depends_on=['nonexistent'],
    )
    with pytest.raises(ValueError, match='unregistered'):
        register_domain(d)


def test_register_with_met_dependency_succeeds():
    """Registering a domain with met depends_on must succeed."""
    from ubp_physics_registry import PhysicsDomain, register_domain, get_registry
    r = get_registry()
    for name in list(r.registered_names):
        r.unregister(name)
    register_domain(PhysicsDomain(name='base', version='0.1.0'))
    register_domain(PhysicsDomain(name='dependent', version='0.1.0', depends_on=['base']))
    assert 'dependent' in r.registered_names


def test_validate_all_with_no_domains():
    """validate_all() with no domains must return GREEN."""
    from ubp_physics_registry import get_registry, validate_all_domains
    r = get_registry()
    for name in list(r.registered_names):
        r.unregister(name)
    result = validate_all_domains()
    assert result['_overall'] == 'GREEN'
    assert result['_domain_count'] == 0


def test_validate_all_with_green_domain():
    """A domain whose validate() returns GREEN must aggregate to GREEN."""
    from ubp_physics_registry import PhysicsDomain, register_domain, get_registry, validate_all_domains
    r = get_registry()
    for name in list(r.registered_names):
        r.unregister(name)
    register_domain(PhysicsDomain(
        name='green_domain',
        version='0.1.0',
        validate=lambda: {'status': 'GREEN', 'note': 'all good'},
    ))
    result = validate_all_domains()
    assert result['_overall'] == 'GREEN'
    assert result['green_domain']['status'] == 'GREEN'


def test_validate_all_with_red_domain():
    """A domain whose validate() raises must aggregate to RED."""
    from ubp_physics_registry import PhysicsDomain, register_domain, get_registry, validate_all_domains
    r = get_registry()
    for name in list(r.registered_names):
        r.unregister(name)
    def bad_validate():
        raise RuntimeError("boom")
    register_domain(PhysicsDomain(
        name='bad_domain',
        version='0.1.0',
        validate=bad_validate,
    ))
    result = validate_all_domains()
    assert result['_overall'] == 'RED'
    assert result['bad_domain']['status'] == 'RED'
    assert 'RuntimeError: boom' in result['bad_domain']['error']


def test_validate_all_with_skip_domain():
    """A domain without validate() must aggregate to YELLOW (skip)."""
    from ubp_physics_registry import PhysicsDomain, register_domain, get_registry, validate_all_domains
    r = get_registry()
    for name in list(r.registered_names):
        r.unregister(name)
    register_domain(PhysicsDomain(name='no_validate', version='0.1.0'))
    result = validate_all_domains()
    assert result['_overall'] == 'YELLOW'
    assert result['no_validate']['status'] == 'SKIP'


def test_physics_domain_formula_value():
    """PhysicsDomain.formula_value(name) must compute and return the prediction."""
    from ubp_physics_registry import PhysicsDomain
    d = PhysicsDomain(
        name='test',
        version='0.1.0',
        formulas={'double_y': lambda: Fraction(2) * Fraction(264675430405, 10**12)},
    )
    val = d.formula_value('double_y')
    assert val == Fraction(2) * Fraction(264675430405, 10**12)


def test_physics_domain_rejects_empty_name():
    """PhysicsDomain must reject an empty name."""
    from ubp_physics_registry import PhysicsDomain
    with pytest.raises(ValueError, match='non-empty'):
        PhysicsDomain(name='', version='0.1.0')


# ── Substrate integration ────────────────────────────────────────────────
def test_substrate_get_physics_registry_works():
    """ubp_engine_substrate.get_physics_registry() must return the singleton."""
    import ubp_engine_substrate as sub
    from ubp_physics_registry import get_registry
    assert sub.get_physics_registry() is get_registry()


def test_validate_substrate_includes_physics_registry_block():
    """validate_substrate() must include the physics_registry block (Phase 3)."""
    import ubp_engine_substrate as sub
    r = sub.validate_substrate()
    assert 'physics_registry' in r
    block = r['physics_registry']
    assert '_overall' in block
    assert '_domain_count' in block


def test_validate_substrate_picks_up_registered_domain():
    """Registering a domain AND calling validate_substrate must include
    that domain's validation result in the substrate report."""
    import ubp_engine_substrate as sub
    from ubp_physics_registry import PhysicsDomain, register_domain, get_registry
    # Clean slate
    r = get_registry()
    for name in list(r.registered_names):
        r.unregister(name)
    # Register a test domain with a GREEN validate
    register_domain(PhysicsDomain(
        name='substrate_integration_test',
        version='0.1.0',
        validate=lambda: {'status': 'GREEN', 'note': 'integration'},
    ))
    # Run validate_substrate
    report = sub.validate_substrate()
    assert report['overall'] == 'GREEN'
    assert 'substrate_integration_test' in report['physics_registry']
    assert report['physics_registry']['substrate_integration_test']['status'] == 'GREEN'
    # Cleanup
    r.unregister('substrate_integration_test')


# ── Sample domain (demonstrates the extension pattern) ────────────────────
def test_sample_electromagnetism_domain_registers_and_validates():
    """Demonstrate the extension pattern with a minimal EM domain.
    This is the example from ubp_physics_registry.py's docstring."""
    from fractions import Fraction
    from ubp_physics_registry import PhysicsDomain, register_domain, get_domain, get_registry
    import ubp_engine_substrate as sub

    # Clean slate
    r = get_registry()
    for name in list(r.registered_names):
        r.unregister(name)

    # Source PI from the substrate (single source of truth)
    PI = sub.PI

    # ε₀ = 1/(4π·c²·10⁻⁷) F/m — exact by SI definition (c is exact)
    # We use Fraction for exact arithmetic; c is 299792458 m/s (exact integer)
    C = Fraction(299792458)
    EM_CONSTS = {
        'epsilon_0': Fraction(1) / (4 * PI * C**2 * Fraction(1, 10**7)),
        'mu_0':      4 * PI * Fraction(1, 10**7),
        'c_exact':   C,
    }

    def coulomb_constant():
        """k_e = 1/(4πε₀) ≈ 8.9875517873681764e9 N·m²/C²"""
        return Fraction(1) / (4 * PI * EM_CONSTS['epsilon_0'])

    EM_FORMULAS = {
        'coulomb_constant': coulomb_constant,
    }

    def em_validate():
        k = float(coulomb_constant())
        target = 8.9875517873681764e9
        err = abs(k - target) / target * 100
        return {
            'coulomb_constant': {
                'predicted': k, 'target': target, 'error_pct': err,
                'budget': 0.001,
            },
            'status': 'GREEN' if err < 0.001 else 'YELLOW',
        }

    register_domain(PhysicsDomain(
        name='electromagnetism',
        version='0.1.0',
        description='Coulomb, Maxwell constants — substrate-derived via SI exact c.',
        constants=EM_CONSTS,
        formulas=EM_FORMULAS,
        validate=em_validate,
    ))

    # Retrieve and use
    em = get_domain('electromagnetism')
    assert em.name == 'electromagnetism'
    assert em.version == '0.1.0'
    k_e = em.formula_value('coulomb_constant')
    assert isinstance(k_e, Fraction)
    # Sanity: k_e should be ~8.988e9
    assert 8.0e9 < float(k_e) < 9.0e9

    # Validate
    v = em.validate()
    assert v['status'] == 'GREEN'
    assert v['coulomb_constant']['error_pct'] < 0.001

    # Cleanup
    r.unregister('electromagnetism')
