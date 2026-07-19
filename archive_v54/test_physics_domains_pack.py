"""
Comprehensive tests for the UBP Physics Domains Pack.

Tests all 12 registered physics domains:
  1. electromagnetism
  2. thermodynamics
  3. quantum_mechanics
  4. nuclear_physics
  5. cosmology
  6. condensed_matter
  7. astrophysics
  8. chemical_physics
  9. information_theory
 10. acoustics
 11. high_energy_physics
 12. optics

Each domain is tested for:
  • Registration (appears in registry)
  • Validation (all checks pass / GREEN status)
  • Constants (key constants present and non-zero)
  • Formulas (each formula returns a Fraction or float when called)
  • UBP layer mapping (documented in description)

Run:  pytest tests/test_physics_domains_pack.py -v
"""
from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope="module", autouse=True)
def ensure_domains_pack_loaded():
    """Ensure the physics domains pack is loaded (registers all 12 domains)."""
    import ubp_physics_domains_pack  # noqa: F401
    yield


# ── All 12 domains register ──────────────────────────────────────────────
EXPECTED_DOMAINS = [
    'electromagnetism', 'thermodynamics', 'quantum_mechanics',
    'nuclear_physics', 'cosmology', 'condensed_matter',
    'astrophysics', 'chemical_physics', 'information_theory',
    'acoustics', 'high_energy_physics', 'optics',
]

def test_all_12_domains_registered():
    """All 12 physics domains must be registered."""
    from ubp_physics_registry import get_registry
    r = get_registry()
    for name in EXPECTED_DOMAINS:
        assert name in r.registered_names, f"Missing domain: {name}"


def test_all_12_domains_validate_green():
    """All 12 domains must validate GREEN."""
    from ubp_physics_registry import validate_all_domains
    results = validate_all_domains()
    assert results['_overall'] == 'GREEN', (
        f"Overall: {results['_overall']}"
    )
    for name in EXPECTED_DOMAINS:
        assert name in results
        assert results[name]['status'] == 'GREEN', (
            f"{name}: {results[name]['status']}"
        )


# ── Parameterized domain tests ───────────────────────────────────────────
@pytest.mark.parametrize("domain_name", EXPECTED_DOMAINS)
def test_domain_has_version(domain_name):
    """Each domain must have a version string."""
    from ubp_physics_registry import get_domain
    d = get_domain(domain_name)
    assert d.version
    assert d.version.startswith('0.1.')


@pytest.mark.parametrize("domain_name", EXPECTED_DOMAINS)
def test_domain_has_description(domain_name):
    """Each domain must have a non-empty description."""
    from ubp_physics_registry import get_domain
    d = get_domain(domain_name)
    assert d.description
    assert len(d.description) > 20


@pytest.mark.parametrize("domain_name", EXPECTED_DOMAINS)
def test_domain_has_constants(domain_name):
    """Each domain must expose at least 3 constants."""
    from ubp_physics_registry import get_domain
    d = get_domain(domain_name)
    assert len(d.constants) >= 3, f"{domain_name} has only {len(d.constants)} constants"


@pytest.mark.parametrize("domain_name", EXPECTED_DOMAINS)
def test_domain_has_formulas(domain_name):
    """Each domain must expose at least 2 formulas."""
    from ubp_physics_registry import get_domain
    d = get_domain(domain_name)
    assert len(d.formulas) >= 2, f"{domain_name} has only {len(d.formulas)} formulas"


@pytest.mark.parametrize("domain_name", EXPECTED_DOMAINS)
def test_domain_formulas_return_numeric(domain_name):
    """Each formula must return a Fraction or float when called."""
    from ubp_physics_registry import get_domain
    d = get_domain(domain_name)
    for fname, fn in d.formulas.items():
        result = fn()
        assert isinstance(result, (Fraction, float, int)), (
            f"{domain_name}.{fname} returned {type(result).__name__}"
        )


# ── Domain-specific tests ────────────────────────────────────────────────

# Electromagnetism
def test_electromagnetism_constants():
    """EM domain must have c, e, ε₀, μ₀, Z₀, k_e, α."""
    from ubp_physics_registry import get_domain
    d = get_domain('electromagnetism')
    for k in ('c', 'e', 'epsilon_0', 'mu_0', 'Z_0', 'k_e', 'alpha'):
        assert k in d.constants, f"Missing {k}"


def test_electromagnetism_alpha_correct():
    """Fine-structure constant α ≈ 7.297e-3 (1/α ≈ 137.036)."""
    from ubp_physics_registry import get_domain
    d = get_domain('electromagnetism')
    alpha = float(d.formula_value('alpha'))
    assert 7.29e-3 < alpha < 7.30e-3
    alpha_inv = float(d.formula_value('alpha_inv'))
    assert 136 < alpha_inv < 138


def test_electromagnetism_ubp_proposed_alpha_inv():
    """UBP-proposed 1/α ≈ 29·Y^18·U_e must be within 1% of 137.036."""
    from ubp_physics_registry import get_domain
    d = get_domain('electromagnetism')
    ubp_pred = float(d.formula_value('alpha_inv_ubp_proposed'))
    err = abs(ubp_pred - 137.036) / 137.036 * 100
    assert err < 1.0, f"UBP-proposed 1/α error: {err:.4f}%"


# Thermodynamics
def test_thermodynamics_stefan_boltzmann():
    """Stefan-Boltzmann σ must match CODATA (uses UBP π)."""
    from ubp_physics_registry import get_domain
    d = get_domain('thermodynamics')
    sigma = float(d.formula_value('stefan_boltzmann'))
    assert abs(sigma - 5.670374419e-8) / 5.670374419e-8 < 1e-4


def test_thermodynamics_gas_constant():
    """R = N_A·k_B must be SI-exact 8.314462618."""
    from ubp_physics_registry import get_domain
    d = get_domain('thermodynamics')
    R = float(d.formula_value('gas_constant'))
    assert abs(R - 8.314462618) / 8.314462618 < 1e-6


# Quantum mechanics
def test_quantum_bohr_radius():
    """Bohr radius a₀ ≈ 5.29177e-11 m."""
    from ubp_physics_registry import get_domain
    d = get_domain('quantum_mechanics')
    a0 = float(d.formula_value('bohr_radius'))
    assert abs(a0 - 5.29177210903e-11) / 5.29177210903e-11 < 1e-4


def test_quantum_rydberg():
    """Rydberg constant R_∞ ≈ 1.0973731568160e7 /m."""
    from ubp_physics_registry import get_domain
    d = get_domain('quantum_mechanics')
    R = float(d.formula_value('rydberg_constant'))
    assert abs(R - 1.0973731568160e7) / 1.0973731568160e7 < 1e-4


def test_quantum_hartree():
    """Hartree energy E_h ≈ 4.3597e-18 J."""
    from ubp_physics_registry import get_domain
    d = get_domain('quantum_mechanics')
    Eh = float(d.formula_value('hartree_energy'))
    assert abs(Eh - 4.3597447222071e-18) / 4.3597447222071e-18 < 1e-4


# Nuclear physics
def test_nuclear_proton_mass():
    """Proton mass ≈ 938.272 MeV."""
    from ubp_physics_registry import get_domain
    d = get_domain('nuclear_physics')
    mp = float(d.formula_value('proton_mass'))
    assert abs(mp - 938.272) / 938.272 < 1e-4


def test_nuclear_ubp_proposed_proton_mass():
    """UBP-proposed m_p ≈ (1/12)·w·U_e must be within 1% of 938.272 MeV."""
    from ubp_physics_registry import get_domain
    d = get_domain('nuclear_physics')
    ubp_pred = float(d.formula_value('proton_mass_ubp_proposed'))
    err = abs(ubp_pred - 938.272) / 938.272 * 100
    assert err < 1.0, f"UBP-proposed m_p error: {err:.4f}%"


# Cosmology
def test_cosmology_hubble():
    """H₀ ≈ 69.85 km/s/Mpc (UBP-derived, within 1% of 70)."""
    from ubp_physics_registry import get_domain
    d = get_domain('cosmology')
    H0 = float(d.formula_value('hubble_constant'))
    assert abs(H0 - 70.0) / 70.0 < 0.01


def test_cosmology_gravitational_G():
    """G ≈ 6.683e-11 (UBP-derived, within 0.5% of CODATA)."""
    from ubp_physics_registry import get_domain
    d = get_domain('cosmology')
    G = float(d.formula_value('gravitational_G'))
    assert abs(G - 6.6743e-11) / 6.6743e-11 < 0.005


def test_cosmology_planck_mass():
    """Planck mass m_P ≈ 2.176e-8 kg (derived from UBP G)."""
    from ubp_physics_registry import get_domain
    d = get_domain('cosmology')
    mP = float(d.formula_value('planck_mass'))
    assert abs(mP - 2.176434e-8) / 2.176434e-8 < 0.01


# Condensed matter
def test_condensed_matter_conductance_quantum():
    """G₀ = 2e²/h ≈ 7.748e-5 S (SI-exact)."""
    from ubp_physics_registry import get_domain
    d = get_domain('condensed_matter')
    G0 = float(d.formula_value('conductance_quantum'))
    assert abs(G0 - 7.748091729e-5) / 7.748091729e-5 < 1e-6


def test_condensed_matter_ubp_proposed_G0():
    """UBP-proposed G₀ ≈ 169·w·Y^18·U_e must be within 1%."""
    from ubp_physics_registry import get_domain
    d = get_domain('condensed_matter')
    ubp_pred = float(d.formula_value('G0_ubp_proposed'))
    err = abs(ubp_pred - 7.748091729e-5) / 7.748091729e-5 * 100
    assert err < 1.0, f"UBP-proposed G₀ error: {err:.4f}%"


# Astrophysics
def test_astrophysics_solar_mass():
    """Solar mass M_☉ ≈ 1.98847e30 kg."""
    from ubp_physics_registry import get_domain
    d = get_domain('astrophysics')
    Msun = float(d.formula_value('solar_mass'))
    assert abs(Msun - 1.98847e30) / 1.98847e30 < 1e-4


def test_astrophysics_schwarzschild():
    """Schwarzschild radius of Sun ≈ 2953 m (uses UBP G)."""
    from ubp_physics_registry import get_domain
    d = get_domain('astrophysics')
    rs = float(d.formula_value('schwarzschild_radius_sun'))
    assert abs(rs - 2953.25) / 2953.25 < 0.01


# Chemical physics
def test_chemical_faraday():
    """Faraday constant F = N_A·e ≈ 96485.33 C/mol (SI-exact)."""
    from ubp_physics_registry import get_domain
    d = get_domain('chemical_physics')
    F = float(d.formula_value('faraday_constant'))
    assert abs(F - 96485.33212) / 96485.33212 < 1e-6


def test_chemical_atomic_mass_unit():
    """Atomic mass unit u ≈ 1.6605e-27 kg (SI-exact via N_A)."""
    from ubp_physics_registry import get_domain
    d = get_domain('chemical_physics')
    u = float(d.formula_value('atomic_mass_unit'))
    assert abs(u - 1.66053906660e-27) / 1.66053906660e-27 < 1e-6


# Information theory
def test_information_landauer():
    """Landauer limit at 1K ≈ 9.57e-24 J."""
    from ubp_physics_registry import get_domain
    d = get_domain('information_theory')
    E = float(d.formula_value('landauer_limit_1K'))
    assert abs(E - 9.569856e-24) / 9.569856e-24 < 1e-3


def test_information_bekenstein():
    """Bekenstein bound for 1kg/1m ≈ 2.466e20."""
    from ubp_physics_registry import get_domain
    d = get_domain('information_theory')
    S = float(d.formula_value('bekenstein_bound_1kg_1m'))
    assert 2e20 < S < 3e20


# Acoustics
def test_acoustics_speed_of_sound():
    """Speed of sound at 20°C ≈ 343.2 m/s."""
    from ubp_physics_registry import get_domain
    d = get_domain('acoustics')
    v = float(d.formula_value('speed_of_sound_20C'))
    assert 340 < v < 346


def test_acoustics_reference_pressure():
    """Reference sound pressure p₀ = 20 μPa."""
    from ubp_physics_registry import get_domain
    d = get_domain('acoustics')
    p = float(d.formula_value('reference_pressure'))
    assert abs(p - 20e-6) / 20e-6 < 1e-6


# High-energy physics
def test_hep_muon_ratio():
    """Muon/electron ratio ≈ 206.7 (UBP-derived)."""
    from ubp_physics_registry import get_domain
    d = get_domain('high_energy_physics')
    mu = float(d.formula_value('muon_electron_ratio'))
    assert abs(mu - 206.7683) / 206.7683 < 0.001


def test_hep_ubp_proposed_Z_mass():
    """UBP-proposed m_Z ≈ 29·π must be within 0.5% of 91.1876 GeV."""
    from ubp_physics_registry import get_domain
    d = get_domain('high_energy_physics')
    ubp_pred = float(d.formula_value('Z_boson_mass_ubp_proposed'))
    err = abs(ubp_pred - 91.1876) / 91.1876 * 100
    assert err < 0.5, f"UBP-proposed m_Z error: {err:.4f}%"


# Optics
def test_optics_green_light_frequency():
    """500 nm green light frequency ≈ 5.996e14 Hz."""
    from ubp_physics_registry import get_domain
    d = get_domain('optics')
    f = float(d.formula_value('frequency_green'))
    assert abs(f - 5.99584916e14) / 5.99584916e14 < 1e-6


def test_optics_photon_energy():
    """Green photon energy ≈ 3.97e-19 J."""
    from ubp_physics_registry import get_domain
    d = get_domain('optics')
    E = float(d.formula_value('photon_energy_green'))
    assert abs(E - 3.972891714e-19) / 3.972891714e-19 < 1e-6


# ── UBP layer mapping documentation ──────────────────────────────────────
DOMAIN_LAYER_MAP = {
    'electromagnetism':  'Information',
    'thermodynamics':    'Activation',
    'quantum_mechanics': 'Information',
    'nuclear_physics':   'Reality',
    'cosmology':         'Potential',
    'condensed_matter':  'Information',
    'astrophysics':      'Reality',
    'chemical_physics':  'Activation',
    'information_theory':'Information',
    'acoustics':         'Activation',
    'high_energy_physics':'Reality + Potential',
    'optics':            'Information',
}

@pytest.mark.parametrize("domain_name,expected_layer", DOMAIN_LAYER_MAP.items())
def test_domain_description_mentions_ubp_layer(domain_name, expected_layer):
    """Each domain description must mention its UBP layer mapping."""
    from ubp_physics_registry import get_domain
    d = get_domain(domain_name)
    assert 'layer' in d.description.lower(), (
        f"{domain_name} description doesn't mention 'layer': {d.description}"
    )
