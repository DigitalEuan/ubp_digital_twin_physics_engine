"""
================================================================================
UBP DOMAIN SPAWNS — Slice 3 of the domains-in-3D integration
================================================================================
A domain-native spawn registry for the 12 physics-pack domains.

This module does NOT try to solve the full live-force problem yet; that lands in
later slices (pairwise Newtonian gravity, Coulomb coupling, field solvers,
decays, wavefront propagation). What it does do is critically important:

  1. Every spawnable physics object is declared ONCE here.
  2. Every preset reads its real-world values from the physics registry.
  3. Every spawned entity carries domain metadata, provenance, and the exact
     real-world quantities later slices will use for real forces / fields.
  4. No preset needs to be reimplemented later — future slices only CONSUME
     the metadata emitted here.

In other words: Slice 3 establishes the durable ABI between
    physics-domain formulas  →  spawn presets  →  entity metadata  →  later couplers/overlays.

Output contract
---------------
`build_spawn_spec(domain, preset, params, world_physics)` returns a plain dict with:

    {
      'label': 'Photon_500nm',
      'material_name': 'silicon',
      'size': (0.6, 0.6, 0.6),             # workspace visual size (cells)
      'temperature_K': 293.15,
      'render_shape': 'sphere',            # frontend render hint
      'display_colour': '#22c55e',
      'domain_tag': 'optics',
      'domain_role': 'photon',
      'domain_params': {                   # real-world metadata for future slices
          'wavelength_m': 5e-7,
          'frequency_hz': 5.995e14,
          'energy_J': 3.97e-19,
          ...
      },
      'formula_source': 'E = h*c/lambda',
      'research_candidate': False,
      'workspace_scaling_note': 'visual-only scale; real quantities stored in domain_params',
    }

Why some visual sizes are explicit numbers
------------------------------------------
Visual sizes in workspace cells (0.6, 1.0, 2.0, ...) ARE NOT physical constants.
They are UI scaling hints so subatomic and cosmic objects can coexist in the same
20×20×20 workspace without numerical nonsense. The actual real-world quantities are
always preserved verbatim inside `domain_params`.

Author: UBP Digital Twin Project · Slice 3 (July 2026)
================================================================================
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import Any, Dict, List, Optional

from ubp_engine_substrate import get_physics_registry, SPEED_OF_LIGHT_MS, PLANCK_H
from ubp_world_physics import WorldPhysicsState


# ── Helpers ──────────────────────────────────────────────────────────────────
def _domain(name: str):
    return get_physics_registry().get_domain(name)


def _const(domain_name: str, const_name: str) -> float:
    d = _domain(domain_name)
    if const_name not in d.constants:
        raise KeyError(f"{domain_name}.{const_name} missing. Available: {list(d.constants.keys())}")
    return float(d.constants[const_name])


def _formula(domain_name: str, formula_name: str) -> float:
    d = _domain(domain_name)
    if formula_name not in d.formulas:
        raise KeyError(f"{domain_name}.{formula_name} missing. Available: {list(d.formulas.keys())}")
    return float(d.formulas[formula_name]())


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _nm_to_m(nm: float) -> float:
    return nm * 1e-9


def _workspace_visual_size(real_length_m: Optional[float],
                           *,
                           floor: float = 0.35,
                           ceil: float = 4.0,
                           reference_m: Optional[float] = None) -> float:
    """Map a real-world length to a stable workspace cell size.

    This is a VIEW transform, not physics. We never lose the original length — it
    is preserved in `domain_params`. When `reference_m` is provided, size scales
    by log-ratio to keep orderings visible without collapsing to zero.
    """
    if real_length_m is None or real_length_m <= 0:
        return 1.0
    if reference_m is None or reference_m <= 0:
        return 1.0
    import math
    ratio = abs(real_length_m / reference_m)
    if ratio <= 0:
        return 1.0
    # log10 ratio compressed into a bounded visual size.
    size = 1.0 + 0.35 * math.log10(ratio)
    return _clamp(size, floor, ceil)


def _wavelength_to_colour_hex(wavelength_nm: float) -> str:
    """Approximate visible-light colour for 380–780 nm.

    This is a UI mapping, not a physics constant.
    """
    wl = wavelength_nm
    if wl < 420: return '#7c3aed'   # violet
    if wl < 470: return '#2563eb'   # blue
    if wl < 500: return '#06b6d4'   # cyan
    if wl < 570: return '#22c55e'   # green
    if wl < 590: return '#eab308'   # yellow
    if wl < 620: return '#f97316'   # orange
    return '#ef4444'                # red


def _mass_mev_to_kg(m_mev: float) -> float:
    # E = m c^2, 1 eV = e joules. Uses exact c and exact e through the registry.
    e_charge = _const('electromagnetism', 'e')
    c = float(SPEED_OF_LIGHT_MS)
    return m_mev * 1e6 * e_charge / (c * c)


# ── Catalog declaration ──────────────────────────────────────────────────────
# This is the frontend-facing preset schema. It intentionally contains no real
# physical numbers (other than default user-input examples like 500 nm or 440 Hz).
# Real values are resolved dynamically via domain constants when spawned.
DOMAIN_SPAWN_CATALOG: Dict[str, Dict[str, Any]] = {
    'electromagnetism': {
        'label': 'Electromagnetism',
        'colour': '#38bdf8',
        'presets': {
            'negative_charge': {
                'label': 'Negative charge',
                'description': 'Electron-like charge carrier (real e, m_e metadata).',
                'params': {},
            },
            'positive_charge': {
                'label': 'Positive charge',
                'description': 'Proton-like charge carrier (real +e, m_p metadata).',
                'params': {},
            },
            'dipole_probe': {
                'label': 'Dipole probe',
                'description': 'Neutral probe carrying dipole-length metadata for future field visualisation.',
                'params': {'dipole_length_m': {'type': 'number', 'default': 1e-9, 'label': 'Dipole length (m)'}},
            },
        },
    },
    'thermodynamics': {
        'label': 'Thermodynamics',
        'colour': '#f59e0b',
        'presets': {
            'thermal_probe_hot': {
                'label': 'Thermal probe (hot)',
                'description': 'A hot test body. Existing thermal engine already cools it through time.',
                'params': {'temperature_K': {'type': 'number', 'default': 500.0, 'label': 'Temperature (K)'}},
            },
            'thermal_probe_cold': {
                'label': 'Thermal probe (cold)',
                'description': 'A cold test body for heat-gradient visualisation.',
                'params': {'temperature_K': {'type': 'number', 'default': 200.0, 'label': 'Temperature (K)'}},
            },
        },
    },
    'quantum_mechanics': {
        'label': 'Quantum mechanics',
        'colour': '#a78bfa',
        'presets': {
            'bohr_atom': {
                'label': 'Bohr atom',
                'description': 'Hydrogenic atom carrying a₀, λ_C, E_h metadata.',
                'params': {'n': {'type': 'number', 'default': 1, 'label': 'Principal n'}},
            },
        },
    },
    'nuclear_physics': {
        'label': 'Nuclear physics',
        'colour': '#fb7185',
        'presets': {
            'proton': {
                'label': 'Proton',
                'description': 'Proton mass from nuclear domain, charge from EM domain.',
                'params': {},
            },
            'neutron': {
                'label': 'Neutron',
                'description': 'Neutral nucleon carrying m_n and μ_N metadata.',
                'params': {},
            },
        },
    },
    'cosmology': {
        'label': 'Cosmology',
        'colour': '#8b5cf6',
        'presets': {
            'planck_seed': {
                'label': 'Planck seed',
                'description': 'Carries Planck mass / length / time metadata from cosmology domain.',
                'params': {},
            },
            'hubble_marker': {
                'label': 'Hubble marker',
                'description': 'Test body carrying H₀ metadata for future Hubble-flow slice.',
                'params': {},
            },
        },
    },
    'condensed_matter': {
        'label': 'Condensed matter',
        'colour': '#22d3ee',
        'presets': {
            'superconductor_lump': {
                'label': 'Superconductor lump',
                'description': 'Carries G₀, R_K, K_J, Φ₀ metadata for later transport overlays.',
                'params': {},
            },
        },
    },
    'astrophysics': {
        'label': 'Astrophysics',
        'colour': '#f97316',
        'presets': {
            'sun_mass': {
                'label': 'Solar mass marker',
                'description': 'M☉ + Schwarzschild radius metadata.',
                'params': {},
            },
            'earth_mass': {
                'label': 'Earth mass marker',
                'description': 'Earth-scale mass marker derived from M☉ body-ratio.',
                'params': {},
            },
            'black_hole': {
                'label': 'Black-hole seed',
                'description': 'Carries Schwarzschild radius metadata for in-world overlay.',
                'params': {'solar_masses': {'type': 'number', 'default': 1.0, 'label': 'Solar masses'}},
            },
        },
    },
    'chemical_physics': {
        'label': 'Chemical physics',
        'colour': '#84cc16',
        'presets': {
            'mole_sample': {
                'label': 'Mole sample',
                'description': 'Carries molar volume STP, Loschmidt number, Faraday constant.',
                'params': {'moles': {'type': 'number', 'default': 1.0, 'label': 'Amount (mol)'}},
            },
        },
    },
    'information_theory': {
        'label': 'Information theory',
        'colour': '#14b8a6',
        'presets': {
            'golay_codeword': {
                'label': 'Golay codeword body',
                'description': 'Object tagged as a 24-bit substrate / information carrier.',
                'params': {},
            },
            'bekenstein_boundary': {
                'label': 'Bekenstein boundary',
                'description': 'Carries Bekenstein bound metadata for entropy overlays.',
                'params': {'radius_m': {'type': 'number', 'default': 1.0, 'label': 'Radius (m)'}},
            },
        },
    },
    'acoustics': {
        'label': 'Acoustics',
        'colour': '#fbbf24',
        'presets': {
            'sound_emitter': {
                'label': 'Sound emitter',
                'description': 'Carries frequency, v_sound, Z_air for future expanding-wave slice.',
                'params': {'frequency_hz': {'type': 'number', 'default': 440.0, 'label': 'Frequency (Hz)'}},
            },
        },
    },
    'high_energy_physics': {
        'label': 'High-energy physics',
        'colour': '#ec4899',
        'presets': {
            'z_boson': {
                'label': 'Z boson',
                'description': 'm_Z empirical + UBP-proposed 29π research-candidate metadata.',
                'params': {},
                'research_candidate': True,
            },
        },
    },
    'optics': {
        'label': 'Optics',
        'colour': '#22c55e',
        'presets': {
            'photon': {
                'label': 'Photon',
                'description': 'Photon with wavelength/frequency/energy metadata.',
                'params': {'wavelength_nm': {'type': 'number', 'default': 500.0, 'label': 'Wavelength (nm)'}},
            },
            'laser_beam': {
                'label': 'Laser packet',
                'description': 'Photon packet tagged as coherent optical source.',
                'params': {'wavelength_nm': {'type': 'number', 'default': 650.0, 'label': 'Wavelength (nm)'}},
            },
        },
    },
}


def get_domain_spawn_catalog() -> Dict[str, Any]:
    """Return the frontend-facing spawn catalog."""
    return {
        'domain_count': len(DOMAIN_SPAWN_CATALOG),
        'domains': DOMAIN_SPAWN_CATALOG,
    }


# ── Preset builders ──────────────────────────────────────────────────────────
def build_spawn_spec(domain: str,
                     preset: str,
                     params: Optional[Dict[str, Any]],
                     world: WorldPhysicsState) -> Dict[str, Any]:
    params = params or {}

    # Optics -----------------------------------------------------------------
    if domain == 'optics' and preset in ('photon', 'laser_beam'):
        wavelength_nm = float(params.get('wavelength_nm', 500.0))
        wavelength_m = _nm_to_m(wavelength_nm)
        c = float(SPEED_OF_LIGHT_MS)
        h = float(PLANCK_H)
        frequency_hz = c / wavelength_m
        energy_J = h * frequency_hz
        return {
            'label': f"{'Laser' if preset == 'laser_beam' else 'Photon'}_{wavelength_nm:.0f}nm",
            'material_name': 'silicon',
            'size': (0.55, 0.55, 0.55),
            'temperature_K': world.ambient_temperature_K,
            'render_shape': 'sphere',
            'display_colour': _wavelength_to_colour_hex(wavelength_nm),
            'domain_tag': 'optics',
            'domain_role': 'coherent_packet' if preset == 'laser_beam' else 'photon',
            'domain_params': {
                'wavelength_nm': wavelength_nm,
                'wavelength_m': wavelength_m,
                'frequency_hz': frequency_hz,
                'energy_J': energy_J,
                'n_vacuum': _const('optics', 'n_vacuum'),
                'impedance_free_space': _const('optics', 'Z_0'),
                'real_speed_ms': c,
                'coherent': preset == 'laser_beam',
            },
            'formula_source': 'f = c/lambda ; E = h*f',
            'research_candidate': False,
            'workspace_scaling_note': 'Visual packet only; real wavelength/frequency/energy preserved in metadata.',
        }

    # Electromagnetism -------------------------------------------------------
    if domain == 'electromagnetism' and preset in ('negative_charge', 'positive_charge', 'dipole_probe'):
        e = _const('electromagnetism', 'e')
        k_e = _const('electromagnetism', 'k_e')
        alpha = _const('electromagnetism', 'alpha')
        if preset == 'negative_charge':
            return {
                'label': 'NegativeCharge',
                'material_name': 'copper',
                'size': (0.65, 0.65, 0.65),
                'temperature_K': world.ambient_temperature_K,
                'render_shape': 'sphere',
                'display_colour': '#2563eb',
                'domain_tag': 'electromagnetism',
                'domain_role': 'negative_charge',
                'domain_params': {
                    'charge_C': -e,
                    'real_mass_kg': _const('quantum_mechanics', 'm_e'),
                    'coulomb_constant': k_e,
                    'alpha': alpha,
                    'interaction_scale_m_per_cell': _const('quantum_mechanics', 'a0'),
                    'pairwise_em_enabled': True,
                    'pairwise_gravity_enabled': True,
                },
                'formula_source': 'q = -e ; k_e = 1/(4*pi*epsilon_0)',
                'research_candidate': False,
                'workspace_scaling_note': 'Visual carrier uses material mass; real charge/mass stored for future Coulomb slice.',
            }
        if preset == 'positive_charge':
            return {
                'label': 'PositiveCharge',
                'material_name': 'gold',
                'size': (0.72, 0.72, 0.72),
                'temperature_K': world.ambient_temperature_K,
                'render_shape': 'sphere',
                'display_colour': '#ef4444',
                'domain_tag': 'electromagnetism',
                'domain_role': 'positive_charge',
                'domain_params': {
                    'charge_C': e,
                    'real_mass_kg': _mass_mev_to_kg(_const('nuclear_physics', 'm_proton_MeV')),
                    'coulomb_constant': k_e,
                    'alpha': alpha,
                    'interaction_scale_m_per_cell': _const('quantum_mechanics', 'a0'),
                    'pairwise_em_enabled': True,
                    'pairwise_gravity_enabled': True,
                },
                'formula_source': 'q = +e ; m_p from nuclear_physics',
                'research_candidate': False,
                'workspace_scaling_note': 'Visual carrier uses material mass; real charge/mass stored for future Coulomb slice.',
            }
        dipole_length_m = float(params.get('dipole_length_m', 1e-9))
        return {
            'label': 'DipoleProbe',
            'material_name': 'steel',
            'size': (1.10, 0.35, 0.35),
            'temperature_K': world.ambient_temperature_K,
            'render_shape': 'box',
            'display_colour': '#38bdf8',
            'domain_tag': 'electromagnetism',
            'domain_role': 'dipole_probe',
            'domain_params': {
                'dipole_length_m': dipole_length_m,
                'coulomb_constant': k_e,
                'alpha': alpha,
                'interaction_scale_m_per_cell': dipole_length_m,
                'pairwise_em_enabled': False,
                'pairwise_gravity_enabled': False,
            },
            'formula_source': 'Tagged probe for future E-field / dipole visualisation',
            'research_candidate': False,
            'workspace_scaling_note': 'Dipole length preserved in metadata for future field-line slice.',
        }

    # Thermodynamics ---------------------------------------------------------
    if domain == 'thermodynamics' and preset in ('thermal_probe_hot', 'thermal_probe_cold'):
        T = float(params.get('temperature_K', 500.0 if preset.endswith('hot') else 200.0))
        return {
            'label': f"ThermalProbe_{T:.0f}K",
            'material_name': 'iron',
            'size': (0.90, 0.90, 0.90),
            'temperature_K': T,
            'render_shape': 'sphere',
            'display_colour': '#f97316' if T >= world.ambient_temperature_K else '#38bdf8',
            'domain_tag': 'thermodynamics',
            'domain_role': 'thermal_probe',
            'domain_params': {
                'temperature_K': T,
                'ambient_temperature_K': world.ambient_temperature_K,
                'k_B': _const('thermodynamics', 'k_B'),
                'R': _const('thermodynamics', 'R'),
                'sigma': _const('thermodynamics', 'sigma'),
            },
            'formula_source': 'Thermal probe; exchange handled by existing entity thermal engine',
            'research_candidate': False,
            'workspace_scaling_note': 'This preset already evolves through time via existing thermal exchange.',
        }

    # Quantum mechanics ------------------------------------------------------
    if domain == 'quantum_mechanics' and preset == 'bohr_atom':
        n = max(1, int(params.get('n', 1)))
        a0 = _const('quantum_mechanics', 'a0')
        lambda_c = _const('quantum_mechanics', 'lambda_C')
        hartree = _const('quantum_mechanics', 'E_hartree')
        m_e = _const('quantum_mechanics', 'm_e')
        radius_m = a0 * n * n
        visual_size = _workspace_visual_size(radius_m, reference_m=a0)
        return {
            'label': f"BohrAtom_n{n}",
            'material_name': 'silicon',
            'size': (visual_size, visual_size, visual_size),
            'temperature_K': world.ambient_temperature_K,
            'render_shape': 'sphere',
            'display_colour': '#a78bfa',
            'domain_tag': 'quantum_mechanics',
            'domain_role': 'bohr_atom',
            'domain_params': {
                'principal_n': n,
                'bohr_radius_m': a0,
                'orbital_radius_m': radius_m,
                'compton_wavelength_m': lambda_c,
                'hartree_energy_J': hartree,
                'electron_mass_kg': m_e,
                'interaction_scale_m_per_cell': radius_m,
                'pairwise_em_enabled': False,
                'pairwise_gravity_enabled': False,
            },
            'formula_source': 'r_n = a0*n^2',
            'research_candidate': False,
            'workspace_scaling_note': 'Workspace radius is visual; exact a0 and r_n preserved for overlays.',
        }

    # Nuclear physics --------------------------------------------------------
    if domain == 'nuclear_physics' and preset in ('proton', 'neutron'):
        if preset == 'proton':
            m_mev = _const('nuclear_physics', 'm_proton_MeV')
            return {
                'label': 'Proton',
                'material_name': 'gold',
                'size': (0.62, 0.62, 0.62),
                'temperature_K': world.ambient_temperature_K,
                'render_shape': 'sphere',
                'display_colour': '#f97316',
                'domain_tag': 'nuclear_physics',
                'domain_role': 'proton',
                'domain_params': {
                    'mass_MeV': m_mev,
                    'real_mass_kg': _mass_mev_to_kg(m_mev),
                    'charge_C': _const('electromagnetism', 'e'),
                    'mu_N': _const('nuclear_physics', 'mu_N'),
                    'interaction_scale_m_per_cell': _const('quantum_mechanics', 'lambda_C'),
                    'pairwise_em_enabled': True,
                    'pairwise_gravity_enabled': True,
                },
                'formula_source': 'm_p empirical, charge from electromagnetism.e',
                'research_candidate': False,
                'workspace_scaling_note': 'Real proton mass preserved for future nuclear / EM couplers.',
            }
        m_mev = _const('nuclear_physics', 'm_neutron_MeV')
        return {
            'label': 'Neutron',
            'material_name': 'steel',
            'size': (0.62, 0.62, 0.62),
            'temperature_K': world.ambient_temperature_K,
            'render_shape': 'sphere',
            'display_colour': '#94a3b8',
            'domain_tag': 'nuclear_physics',
            'domain_role': 'neutron',
            'domain_params': {
                'mass_MeV': m_mev,
                'real_mass_kg': _mass_mev_to_kg(m_mev),
                'charge_C': 0.0,
                'mu_N': _const('nuclear_physics', 'mu_N'),
                'interaction_scale_m_per_cell': _const('quantum_mechanics', 'lambda_C'),
                'pairwise_em_enabled': False,
                'pairwise_gravity_enabled': True,
            },
            'formula_source': 'm_n empirical',
            'research_candidate': False,
            'workspace_scaling_note': 'Real neutron mass preserved for future couplers.',
        }

    # Cosmology --------------------------------------------------------------
    if domain == 'cosmology' and preset in ('planck_seed', 'hubble_marker'):
        if preset == 'planck_seed':
            return {
                'label': 'PlanckSeed',
                'material_name': 'carbon',
                'size': (0.45, 0.45, 0.45),
                'temperature_K': world.ambient_temperature_K,
                'render_shape': 'sphere',
                'display_colour': '#8b5cf6',
                'domain_tag': 'cosmology',
                'domain_role': 'planck_seed',
                'domain_params': {
                    'planck_mass_kg': _const('cosmology', 'm_P'),
                    'planck_length_m': _const('cosmology', 'l_P'),
                    'planck_time_s': _const('cosmology', 't_P'),
                    'planck_temperature_K': _const('cosmology', 'T_P'),
                    'newton_G': world.newton_G,
                    'hubble_h0_km_s_mpc': world.hubble_h0_km_s_mpc,
                },
                'formula_source': 'Planck units via UBP-derived G',
                'research_candidate': True,
                'workspace_scaling_note': 'Planck-scale quantities are too small to render directly; visual seed carries exact metadata.',
            }
        return {
            'label': 'HubbleMarker',
            'material_name': 'aluminium',
            'size': (0.75, 0.75, 0.75),
            'temperature_K': world.ambient_temperature_K,
            'render_shape': 'sphere',
            'display_colour': '#c084fc',
            'domain_tag': 'cosmology',
            'domain_role': 'hubble_marker',
            'domain_params': {
                'H0_km_s_mpc': world.hubble_h0_km_s_mpc,
                'omega_k': _const('cosmology', 'Omega_k'),
                'newton_G': world.newton_G,
            },
            'formula_source': 'H0 = (1/3)wY^3U_e',
            'research_candidate': False,
            'workspace_scaling_note': 'Future Hubble-flow slice reads H0 from this metadata.',
        }

    # Condensed matter -------------------------------------------------------
    if domain == 'condensed_matter' and preset == 'superconductor_lump':
        return {
            'label': 'SuperconductorLump',
            'material_name': 'aluminium',
            'size': (1.20, 0.70, 0.70),
            'temperature_K': 4.2,
            'render_shape': 'box',
            'display_colour': '#22d3ee',
            'domain_tag': 'condensed_matter',
            'domain_role': 'superconductor_lump',
            'domain_params': {
                'G0': _const('condensed_matter', 'G_0'),
                'R_K': _const('condensed_matter', 'R_K'),
                'K_J': _const('condensed_matter', 'K_J'),
                'phi_0': _const('condensed_matter', 'Phi_0'),
                'mu_B': _const('condensed_matter', 'mu_B'),
            },
            'formula_source': 'Condensed-matter exact constants from domain registry',
            'research_candidate': True,
            'workspace_scaling_note': 'Transport quantities preserved for later lattice / Hall overlays.',
        }

    # Astrophysics -----------------------------------------------------------
    if domain == 'astrophysics' and preset in ('sun_mass', 'earth_mass', 'black_hole'):
        M_sun = _const('astrophysics', 'M_sun')
        r_s_sun = _const('astrophysics', 'r_schwarzschild_sun')
        AU = _const('astrophysics', 'AU')
        if preset == 'sun_mass':
            visual = _clamp(r_s_sun * world.cosmology_scale * 2e6, 0.9, 2.2)
            return {
                'label': 'SunMassMarker',
                'material_name': 'gold',
                'size': (visual, visual, visual),
                'temperature_K': 5778.0,
                'render_shape': 'sphere',
                'display_colour': '#fbbf24',
                'domain_tag': 'astrophysics',
                'domain_role': 'sun_mass',
                'domain_params': {
                    'real_mass_kg': M_sun,
                    'schwarzschild_radius_m': r_s_sun,
                    'luminosity_W': _const('astrophysics', 'L_sun'),
                    'AU_m': AU,
                    'workspace_scale': world.cosmology_scale,
                    'interaction_scale_m_per_cell': 1.0 / world.cosmology_scale,
                    'pairwise_em_enabled': False,
                    'pairwise_gravity_enabled': True,
                },
                'formula_source': 'M_sun empirical; r_s = 2GM/c^2 using UBP-derived G',
                'research_candidate': False,
                'workspace_scaling_note': 'Visual size tied to scaled Schwarzschild radius; real mass preserved verbatim.',
            }
        if preset == 'earth_mass':
            earth_mass_kg = M_sun / 332946.0
            earth_radius_m = AU * (6371000.0 / 149597870700.0)
            visual = _clamp(earth_radius_m * world.cosmology_scale * 1000, 0.7, 1.2)
            return {
                'label': 'EarthMassMarker',
                'material_name': 'silicon',
                'size': (visual, visual, visual),
                'temperature_K': 288.0,
                'render_shape': 'sphere',
                'display_colour': '#3b82f6',
                'domain_tag': 'astrophysics',
                'domain_role': 'earth_mass',
                'domain_params': {
                    'real_mass_kg': earth_mass_kg,
                    'real_radius_m': earth_radius_m,
                    'workspace_scale': world.cosmology_scale,
                    'interaction_scale_m_per_cell': 1.0 / world.cosmology_scale,
                    'pairwise_em_enabled': False,
                    'pairwise_gravity_enabled': True,
                },
                'formula_source': 'Earth mass/radius expressed as dimensionless ratio against astrophysics.M_sun/AU',
                'research_candidate': False,
                'workspace_scaling_note': 'Real Earth-scale quantities preserved for future Newtonian coupling.',
            }
        solar_masses = float(params.get('solar_masses', 1.0))
        real_mass_kg = solar_masses * M_sun
        r_s = solar_masses * r_s_sun
        visual = _clamp(r_s * world.cosmology_scale * 2e6, 0.8, 2.5)
        return {
            'label': f"BlackHole_{solar_masses:g}Msun",
            'material_name': 'carbon',
            'size': (visual, visual, visual),
            'temperature_K': world.ambient_temperature_K,
            'render_shape': 'sphere',
            'display_colour': '#111827',
            'domain_tag': 'astrophysics',
            'domain_role': 'black_hole',
            'domain_params': {
                'solar_masses': solar_masses,
                'real_mass_kg': real_mass_kg,
                'schwarzschild_radius_m': r_s,
                'workspace_scale': world.cosmology_scale,
                'interaction_scale_m_per_cell': 1.0 / world.cosmology_scale,
                'pairwise_em_enabled': False,
                'pairwise_gravity_enabled': True,
            },
            'formula_source': 'r_s = 2GM/c^2',
            'research_candidate': False,
            'workspace_scaling_note': 'Visual sphere marks event-horizon scale only; later overlays will draw r_s shell.',
        }

    # Chemical physics -------------------------------------------------------
    if domain == 'chemical_physics' and preset == 'mole_sample':
        moles = float(params.get('moles', 1.0))
        V_m = _const('chemical_physics', 'V_molar_STP')
        return {
            'label': f"MoleSample_{moles:g}mol",
            'material_name': 'air',
            'size': (_clamp(0.7 + 0.15 * moles, 0.7, 2.5),) * 3,
            'temperature_K': 273.15,
            'render_shape': 'sphere',
            'display_colour': '#84cc16',
            'domain_tag': 'chemical_physics',
            'domain_role': 'mole_sample',
            'domain_params': {
                'moles': moles,
                'molar_volume_stp_m3_per_mol': V_m,
                'sample_volume_m3': moles * V_m,
                'loschmidt_number_m3': _const('chemical_physics', 'n_Loschmidt'),
                'faraday_constant': _const('chemical_physics', 'F'),
            },
            'formula_source': 'V = n * V_m(STP)',
            'research_candidate': False,
            'workspace_scaling_note': 'Sample volume is real; workspace volume is a symbolic proxy.',
        }

    # Information theory -----------------------------------------------------
    if domain == 'information_theory' and preset in ('golay_codeword', 'bekenstein_boundary'):
        if preset == 'golay_codeword':
            return {
                'label': 'GolayCodewordBody',
                'material_name': 'silicon',
                'size': (1.00, 1.00, 1.00),
                'temperature_K': world.ambient_temperature_K,
                'render_shape': 'box',
                'display_colour': '#14b8a6',
                'domain_tag': 'information_theory',
                'domain_role': 'golay_codeword',
                'domain_params': {
                    'substrate_bits': 24,
                    'golay_message_bits': 12,
                    'golay_codewords': 4096,
                    'landauer_1K_J': _const('information_theory', 'landauer_1K'),
                },
                'formula_source': '24-bit substrate / Golay code metadata',
                'research_candidate': False,
                'workspace_scaling_note': 'Later overlays will render the 24-bit codeword above the entity.',
            }
        radius_m = float(params.get('radius_m', 1.0))
        return {
            'label': f"BekensteinBoundary_{radius_m:g}m",
            'material_name': 'steel',
            'size': (_clamp(0.8 + 0.2 * radius_m, 0.8, 2.6),) * 3,
            'temperature_K': world.ambient_temperature_K,
            'render_shape': 'sphere',
            'display_colour': '#0f766e',
            'domain_tag': 'information_theory',
            'domain_role': 'bekenstein_boundary',
            'domain_params': {
                'radius_m': radius_m,
                'bekenstein_bound_reference': _const('information_theory', 'bekenstein_1kg_1m'),
                'landauer_1K_J': _const('information_theory', 'landauer_1K'),
            },
            'formula_source': 'Tagged entropy boundary object',
            'research_candidate': False,
            'workspace_scaling_note': 'Future overlays can turn this into an entropy shell or information bound indicator.',
        }

    # Acoustics --------------------------------------------------------------
    if domain == 'acoustics' and preset == 'sound_emitter':
        f_hz = float(params.get('frequency_hz', 440.0))
        return {
            'label': f"SoundEmitter_{f_hz:.0f}Hz",
            'material_name': 'copper',
            'size': (0.90, 0.90, 0.90),
            'temperature_K': world.ambient_temperature_K,
            'render_shape': 'sphere',
            'display_colour': '#f59e0b',
            'domain_tag': 'acoustics',
            'domain_role': 'sound_emitter',
            'domain_params': {
                'frequency_hz': f_hz,
                'speed_of_sound_ms': world.speed_of_sound_ms,
                'reference_pressure_pa': _const('acoustics', 'p_ref'),
                'acoustic_impedance_air': _const('acoustics', 'Z_air'),
                'pain_threshold_pa': _const('acoustics', 'pain_threshold'),
            },
            'formula_source': 'Emitter tagged with acoustics-domain air properties',
            'research_candidate': False,
            'workspace_scaling_note': 'Later slices will emit pressure rings at v_sound using this metadata.',
        }

    # High-energy physics ----------------------------------------------------
    if domain == 'high_energy_physics' and preset == 'z_boson':
        m_z = _const('high_energy_physics', 'm_Z')
        m_z_ubp = _const('high_energy_physics', 'm_Z_ubp_proposed')
        return {
            'label': 'ZBoson',
            'material_name': 'gold',
            'size': (0.58, 0.58, 0.58),
            'temperature_K': world.ambient_temperature_K,
            'render_shape': 'sphere',
            'display_colour': '#ec4899',
            'domain_tag': 'high_energy_physics',
            'domain_role': 'z_boson',
            'domain_params': {
                'mass_GeV': m_z,
                'mass_GeV_ubp_proposed': m_z_ubp,
                'muon_ratio': _const('high_energy_physics', 'muon_ratio'),
                'alpha_s': _const('high_energy_physics', 'alpha_s'),
                'real_mass_kg': _mass_mev_to_kg(m_z * 1000.0),
                'interaction_scale_m_per_cell': _const('quantum_mechanics', 'lambda_C'),
                'pairwise_em_enabled': False,
                'pairwise_gravity_enabled': True,
            },
            'formula_source': 'm_Z empirical with UBP research candidate 29*pi',
            'research_candidate': True,
            'workspace_scaling_note': 'Real HEP mass preserved; later decay/effect slices will consume it.',
        }

    # Default optics formula names already covered above. --------------------

    raise KeyError(f"Unknown domain/preset combination: {domain}/{preset}")


__all__ = [
    'DOMAIN_SPAWN_CATALOG',
    'get_domain_spawn_catalog',
    'build_spawn_spec',
]
