"""
================================================================================
UBP MATERIALS v3.0 — Composite Material System
================================================================================
Every material in V3 is built from real UBP KB element entries (ELEM_*).
A block of Iron is N × ELEM_Fe_026. A block of water is 2H + O per molecule.

The macroscopic properties (mass, inertia, thermal capacity, heat transfer,
friction coefficient) are integrated from the atomic vectors in the KB.

Crystal structure determines thermal connectivity:
  FCC (Crystal=2): connectivity = 12  (Cu, Al, Au, Ni)
  BCC (Crystal=3): connectivity = 8   (Fe, Na, W)
  Hexagonal (Crystal=1): connectivity = 6  (H, C, N, O)
  Monoclinic/Other: connectivity = 4

Laws applied:
  LAW_TOPO_EFFICIENCY_001: Metabolic_Cost ~ 1 / Connectivity
  LAW_TOPO_EFFICIENCY_002: Cost(FCC) ~ 0.76 * Cost(Cubic)
  LAW_VOLUMETRIC_REBATE_001: Rebate = 1 - (Compactness / 13)
  LAW_TOPOLOGICAL_TORQUE_001: I = mass*(w²+h²+d²)/12 * (1+NRCI) * Rebate
================================================================================
"""

import json
import os
from fractions import Fraction
from typing import Dict, List, Optional, Tuple, Any
from decimal import Decimal

# ---------------------------------------------------------------------------
# KB LOADER
# ---------------------------------------------------------------------------

_KB_PATH = os.path.join(os.path.dirname(__file__), '..', 'upload', 'ubp_system_kb.json')
_KB_FALLBACK = os.path.join(os.path.dirname(__file__), 'ubp_system_kb.json')

def _load_kb() -> Dict[str, Any]:
    """Load the UBP system KB JSON."""
    for path in [_KB_PATH, _KB_FALLBACK]:
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            # Index by ubp_id
            return {v['ubp_id']: v for v in raw.values() if 'ubp_id' in v}
    raise FileNotFoundError(
        "ubp_system_kb.json not found. Place it in UBP_Repo/upload/ or ubp_game_engine_v3/."
    )

_KB: Dict[str, Any] = _load_kb()

# ---------------------------------------------------------------------------
# CRYSTAL CONNECTIVITY MAP (from KB Crystal field)
# Crystal=1 Hexagonal, Crystal=2 FCC/Cubic, Crystal=3 BCC, Crystal=4+ Other
# ---------------------------------------------------------------------------
_CRYSTAL_CONNECTIVITY: Dict[int, int] = {
    1: 6,   # Hexagonal (H, C, N, O)
    2: 12,  # FCC/Cubic (Cu, Al, Au, Ni, Si)
    3: 8,   # BCC (Fe, Na, W, Mo)
    4: 4,   # Monoclinic/Other
    5: 4,
    6: 4,
}

# ---------------------------------------------------------------------------
# ELEMENT DATA CLASS
# ---------------------------------------------------------------------------

class UBPElement:
    """
    A single UBP element entry from the KB.
    Wraps the atlas, math, and lexicon fields.
    """

    def __init__(self, ubp_id: str):
        if ubp_id not in _KB:
            raise KeyError(f"Element '{ubp_id}' not found in UBP KB.")
        entry = _KB[ubp_id]
        self.ubp_id = ubp_id
        self.lexicon = entry['lexicon']
        self.tags = entry['tags']
        self.fingerprint = entry['fingerprint']

        # Atlas (geometric identity)
        atlas = entry['atlas']
        self.vector: List[int] = atlas['vector']
        self.nrci_score: float = atlas['nrci_score']
        self.nrci: Fraction = Fraction(str(atlas['nrci']))
        self.tax: Fraction = Fraction(str(atlas['tax']))
        self.hamming_weight: int = atlas['weight']
        self.tilt: float = atlas.get('tilt', 0.0)

        # Math (physical properties parsed from pipe-separated string)
        self._math_raw = entry['math']
        self._props = self._parse_math(self._math_raw)

        # Derived properties
        self.atomic_number: int = int(self._props.get('Z', 0))
        self.atomic_mass: Fraction = self._parse_fraction(self._props.get('M', '1'))
        self.density: Fraction = self._parse_fraction(self._props.get('Rho', '1'))
        self.melting_point_K: Fraction = self._parse_fraction(self._props.get('MP', '300'))
        self.boiling_point_K: Fraction = self._parse_fraction(self._props.get('BP', '400'))
        self.ionisation_energy: Fraction = self._parse_fraction(self._props.get('Ion', '0'))
        self.electronegativity: Fraction = self._parse_fraction(self._props.get('EN', '0'))
        self.valence_electrons: int = int(self._props.get('Valence_e', 1))
        self.phase_stp: int = int(self._props.get('Phase_STP', 3))  # 1=gas, 2=liquid, 3=solid
        self.crystal_type: int = int(self._props.get('Crystal', 1))
        self.oxidation_state: int = int(self._props.get('Oxidation', 0))

        # Crystal connectivity (from LAW_TOPO_EFFICIENCY_001)
        self.connectivity: int = _CRYSTAL_CONNECTIVITY.get(self.crystal_type, 4)

        # Thermal capacity (LAW_TOPO_EFFICIENCY_001: C ~ connectivity / 24)
        # Scaled by Y (coherence ratio) to convert to UBP units
        from ubp_engine_substrate import Y_CONSTANT
        self.thermal_capacity: Fraction = Y_CONSTANT * Fraction(self.connectivity, 24)

        # Heat transfer coefficient (The Shaving applied to thermal flow)
        self.heat_transfer: Fraction = Y_CONSTANT * Y_CONSTANT * Fraction(self.connectivity, 24)

    def _parse_math(self, math_str: str) -> Dict[str, str]:
        """Parse 'Key=Value|Key=Value' format."""
        props = {}
        for part in math_str.split('|'):
            if '=' in part:
                k, v = part.split('=', 1)
                props[k.strip()] = v.strip()
        return props

    def _parse_fraction(self, val_str: str) -> Fraction:
        """Parse a string that may be an integer, decimal, or fraction."""
        try:
            if '/' in val_str:
                return Fraction(val_str)
            else:
                return Fraction(val_str)
        except (ValueError, ZeroDivisionError):
            return Fraction(0)

    def __repr__(self) -> str:
        return (f"UBPElement({self.ubp_id}, Z={self.atomic_number}, "
                f"NRCI={self.nrci_score:.4f}, crystal={self.crystal_type})")


# ---------------------------------------------------------------------------
# MATERIAL RECIPE — defines what a macroscopic material is made of
# ---------------------------------------------------------------------------

class MaterialRecipe:
    """
    A recipe for a macroscopic material, defined as a mixture of UBP elements.
    Each entry is (element_ubp_id, count_per_formula_unit).

    Examples:
      Iron block: [('ELEM_Fe_026', 1)]
      Water molecule: [('ELEM_H_001', 2), ('ELEM_O_008', 1)]
      Steel (approx): [('ELEM_Fe_026', 19), ('ELEM_C_006', 1)]
      Aluminium: [('ELEM_Al_013', 1)]
      Copper: [('ELEM_Cu_029', 1)]
    """

    # Pre-defined material recipes
    PRESETS: Dict[str, List[Tuple[str, int]]] = {
        'iron':      [('ELEM_Fe_026', 1)],
        'copper':    [('ELEM_Cu_029', 1)],
        'aluminium': [('ELEM_Al_013', 1)],
        'gold':      [('ELEM_Au_079', 1)],
        'carbon':    [('ELEM_C_006', 1)],
        'silicon':   [('ELEM_Si_014', 1)],
        'water':     [('ELEM_H_001', 2), ('ELEM_O_008', 1)],
        'air':       [('ELEM_N_007', 4), ('ELEM_O_008', 1)],
        'steel':     [('ELEM_Fe_026', 19), ('ELEM_C_006', 1)],
        'sodium':    [('ELEM_Na_011', 1)],
        # Generic simulation blocks (fallback to Iron)
        'standard':  [('ELEM_Fe_026', 1)],
        'heavy':     [('ELEM_Au_079', 1)],
        'light':     [('ELEM_Al_013', 1)],
    }

    # Compound phase overrides: elements may be gaseous but the compound is liquid/solid
    # H2O: H and O are both gas at STP, but water is liquid (phase=2) at STP
    # This is the emergent phase from molecular bonding — a UBP compound property
    PHASE_OVERRIDES: Dict[str, int] = {
        'water': 2,   # liquid
        'air':   1,   # gas (correct as-is)
    }

    def __init__(self, name: str, composition: Optional[List[Tuple[str, int]]] = None):
        self.name = name
        if composition is not None:
            self.composition = composition
        elif name in self.PRESETS:
            self.composition = self.PRESETS[name]
        else:
            # Default to iron
            self.composition = self.PRESETS['iron']

        # Load elements
        self.elements: List[Tuple[UBPElement, int]] = []
        for elem_id, count in self.composition:
            elem = UBPElement(elem_id)
            self.elements.append((elem, count))

        # Compute aggregate properties
        self._compute_aggregate()

    def _compute_aggregate(self) -> None:
        """Compute macroscopic properties from the atomic composition."""
        total_count = sum(c for _, c in self.elements)

        # Aggregate vector: Additive Superposition + Phenomenal Collapse (v6.3.1)
        # LAW_SYNTHESIS_SUPERPOSITION_001: Replace XOR 'Smash' with The Flow.
        # Each element contributes count copies in bipolar {-1, +1} space.
        # The sum is then collapsed: sum > 0 -> 0 (void), sum < 0 -> 1 (presence),
        # sum == 0 -> 0 (Void/Deep Hole — equal pressures resolve to absence).
        # Finally, Golay Coherence Snap is applied to ensure the result is a
        # valid codeword (the substrate self-corrects the composite identity).
        bipolar_sum = [0] * 24
        for elem, count in self.elements:
            for _ in range(count):
                for i in range(24):
                    bipolar_sum[i] += (-1 if elem.vector[i] == 0 else 1)
        # Phenomenal Collapse: sum > 0 -> 0 (void), sum < 0 -> 1 (presence)
        collapsed = [0 if s >= 0 else 1 for s in bipolar_sum]
        # Golay Coherence Snap: ensure valid codeword
        try:
            from ubp_engine_substrate import coherence_snap
            snapped, _ = coherence_snap(collapsed)
            self.aggregate_vector: List[int] = snapped
        except Exception:
            self.aggregate_vector: List[int] = collapsed

        # Aggregate NRCI: weighted average
        total_nrci = sum(Fraction(str(elem.nrci_score)) * count
                        for elem, count in self.elements)
        self.aggregate_nrci: Fraction = total_nrci / Fraction(total_count, 1)

        # Aggregate Symmetry Tax: sum of all element taxes
        self.aggregate_tax: Fraction = sum(
            elem.tax * count for elem, count in self.elements
        )

        # Aggregate atomic mass: sum of all element masses
        self.aggregate_mass: Fraction = sum(
            elem.atomic_mass * count for elem, count in self.elements
        )

        # Aggregate density: weighted average
        self.aggregate_density: Fraction = sum(
            elem.density * count for elem, count in self.elements
        ) / Fraction(total_count, 1)

        # Aggregate thermal capacity (LAW_TOPO_EFFICIENCY_001)
        self.aggregate_thermal_capacity: Fraction = sum(
            elem.thermal_capacity * count for elem, count in self.elements
        ) / Fraction(total_count, 1)

        # Aggregate heat transfer coefficient
        self.aggregate_heat_transfer: Fraction = sum(
            elem.heat_transfer * count for elem, count in self.elements
        ) / Fraction(total_count, 1)

        # Aggregate melting point: weighted average
        self.aggregate_melting_point: Fraction = sum(
            elem.melting_point_K * count for elem, count in self.elements
        ) / Fraction(total_count, 1)

        # Aggregate connectivity: weighted average
        self.aggregate_connectivity: Fraction = Fraction(
            sum(elem.connectivity * count for elem, count in self.elements),
            total_count
        )

        # Phase at STP: majority vote, with compound override for molecular materials
        # (H2O elements are gaseous but water compound is liquid at STP)
        phases = [elem.phase_stp for elem, count in self.elements for _ in range(count)]
        majority_phase = max(set(phases), key=phases.count)
        self.phase_stp: int = MaterialRecipe.PHASE_OVERRIDES.get(self.name, majority_phase)

    def __repr__(self) -> str:
        return (f"MaterialRecipe({self.name}, "
                f"NRCI={float(self.aggregate_nrci):.4f}, "
                f"mass={float(self.aggregate_mass):.4f})")


# ---------------------------------------------------------------------------
# AMBIENT ENVIRONMENT
# ---------------------------------------------------------------------------

class AmbientEnvironment:
    """
    The ambient environment of the simulation space.

    All values are derived from UBP laws and real physical constants:
    - Temperature: 293.15 K (20°C) scaled by Y/24
    - Air density: 1.225 kg/m³ scaled by Y
    - Air composition: 80% N₂ + 20% O₂ (approximated as 4N + 1O)
    - Atmospheric pressure: 101325 Pa scaled by Y²
    - Humidity: 0 (dry air, default)

    The ambient environment affects:
    - Air drag (density-dependent)
    - Thermal exchange (temperature gradient)
    - Fluid evaporation (temperature vs boiling point)
    """

    def __init__(
        self,
        temperature_K: float = 293.15,
        humidity: float = 0.0,
        gravity_ms2: float = 9.80665,
    ):
        from ubp_engine_substrate import Y_CONSTANT, G_EARTH_MS2, BOLTZMANN_K

        self.temperature_K: Fraction = Fraction(str(round(temperature_K, 4)))
        self.humidity: Fraction = Fraction(str(round(humidity, 4)))
        self.gravity_ms2: Fraction = G_EARTH_MS2

        # Air material
        self.air_material = MaterialRecipe('air')

        # Ambient temperature in UBP units: T_ubp = T_K * Y / 24
        self.temperature_ubp: Fraction = self.temperature_K * Y_CONSTANT / Fraction(24, 1)

        # Air density in UBP units: rho_air = 1.225 * Y
        self.air_density_ubp: Fraction = Fraction(1225, 1000) * Y_CONSTANT

        # Atmospheric pressure in UBP units: P_atm = 101325 * Y^2
        self.pressure_ubp: Fraction = Fraction(101325, 1) * Y_CONSTANT * Y_CONSTANT

        # Boltzmann constant (for thermal exchange)
        self.boltzmann: Fraction = BOLTZMANN_K

    @property
    def temperature_celsius(self) -> float:
        return float(self.temperature_K) - 273.15

    def thermal_exchange_rate(self, entity_material: MaterialRecipe) -> Fraction:
        """
        Compute the thermal exchange rate between an entity and the ambient air.
        Rate = k_heat_entity * k_heat_air / (k_heat_entity + k_heat_air)
        (Parallel thermal resistance)
        """
        k_entity = entity_material.aggregate_heat_transfer
        k_air = self.air_material.aggregate_heat_transfer
        if k_entity + k_air == 0:
            return Fraction(0)
        return k_entity * k_air / (k_entity + k_air)

    def __repr__(self) -> str:
        return (f"AmbientEnvironment(T={float(self.temperature_K):.1f}K, "
                f"T_ubp={float(self.temperature_ubp):.4f}, "
                f"rho_air={float(self.air_density_ubp):.4f})")


# ---------------------------------------------------------------------------
# MATERIAL REGISTRY (singleton)
# ---------------------------------------------------------------------------

class MaterialRegistry:
    """
    Global registry of all loaded materials.
    Caches MaterialRecipe objects to avoid repeated KB lookups.
    """

    _instance: Optional['MaterialRegistry'] = None
    _cache: Dict[str, MaterialRecipe] = {}

    @classmethod
    def get(cls, name: str) -> MaterialRecipe:
        """Get or create a MaterialRecipe by name."""
        if name not in cls._cache:
            cls._cache[name] = MaterialRecipe(name)
        return cls._cache[name]

    @classmethod
    def register(cls, name: str, composition: List[Tuple[str, int]]) -> MaterialRecipe:
        """Register a custom material recipe."""
        recipe = MaterialRecipe(name, composition)
        cls._cache[name] = recipe
        return recipe

    @classmethod
    def list_presets(cls) -> List[str]:
        """List all preset material names."""
        return list(MaterialRecipe.PRESETS.keys())


# ---------------------------------------------------------------------------
# ELEMENT LOOKUP HELPERS
# ---------------------------------------------------------------------------

def get_element(ubp_id: str) -> UBPElement:
    """Get a UBP element by its KB ID."""
    return UBPElement(ubp_id)

def list_elements() -> List[str]:
    """List all element IDs in the KB."""
    return [k for k in _KB if k.startswith('ELEM_')]

def list_laws() -> List[str]:
    """List all law IDs in the KB."""
    return [k for k in _KB if k.startswith('LAW_')]

def get_law(law_id: str) -> Optional[Dict[str, Any]]:
    """Get a law entry from the KB."""
    return _KB.get(law_id)
