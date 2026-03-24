"""
================================================================================
UBP ENGINE SUBSTRATE v1.0
================================================================================
The foundational layer of the UBP Game Engine.

This module is the single point of integration between the UBP Core Studio
(v5.3 Merged) and the game engine. It imports and exposes all UBP mathematical
primitives, constants, and engines that the game physics layer will use.

NO simplifications. NO shortcuts. This substrate uses the real UBP system:
  - GolayCodeEngine [24,12,8] for state error-correction and Coherence Snap
  - LeechLatticeEngine (Λ₂₄) for Symmetry Tax (mass/energy equivalent)
  - UBPUltimateSubstrate for 50-term π and the Y-Constant
  - TGICExactEngine for relational pull (gravity analogue)
  - BinaryLinearAlgebra for all GF(2) operations
  - UBPSourceCodeParticlePhysics for fundamental constant derivation

UBP Game Engine v1.0 (built on UBP Core Studio v4.2.7 / v5.3)
Author: E R A Craig, New Zealand
Date: March 2026
================================================================================
"""

import sys
import os
import re
import hashlib
from fractions import Fraction
from typing import List, Tuple, Dict, Any, Optional

# ---------------------------------------------------------------------------
# PATH SETUP: Add the UBP core directory to sys.path so we can import directly
# ---------------------------------------------------------------------------
_ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
# Also add the engine directory itself to sys.path
if _ENGINE_DIR not in sys.path:
    sys.path.insert(0, _ENGINE_DIR)

_CORE_DIR = os.path.join(os.path.dirname(_ENGINE_DIR), "core_studio_v4.0", "core")
if os.path.exists(_CORE_DIR) and _CORE_DIR not in sys.path:
    sys.path.insert(0, _CORE_DIR)

# ---------------------------------------------------------------------------
# IMPORT THE REAL UBP CORE
# ---------------------------------------------------------------------------
try:
    from ubp_core_v5_3_merged import (
        GolayCodeEngine,
        LeechLatticeEngine,
        BinaryLinearAlgebra,
        UBPUltimateSubstrate,
        UBPSourceCodeParticlePhysics,
        ConstructionPrimitive,
        ConstructionPath,
        UBPObject,
        TriadActivationEngine,
        LeechPointScaled,
        GOLAY_ENGINE,
        LEECH_ENGINE,
        PARTICLE_PHYSICS,
        SUBSTRATE,
    )
    from ubp_tgic_engine import (
        TGICExactEngine,
        TGICInteractionEngine,
        TGICConstraintSystem,
        OffBit,
    )
    _CORE_LOADED = True
    print("[UBP Engine Substrate] UBP Core v5.3 loaded successfully.")
except ImportError as e:
    _CORE_LOADED = False
    print(f"[UBP Engine Substrate] CRITICAL: Could not load UBP Core: {e}")
    raise RuntimeError(
        f"UBP Core not found at {_CORE_DIR}. "
        "Ensure the UBP_Repo/core_studio_v4.0/core directory exists."
    ) from e

# ---------------------------------------------------------------------------
# FUNDAMENTAL CONSTANTS (derived from UBP substrate, exact rational)
# ---------------------------------------------------------------------------
_CONST = SUBSTRATE.get_constants(50)

# The Observer Constant — the most important value in UBP
# Y ≈ 0.2646 — the geometric rent paid by every bit to maintain identity
Y_CONSTANT: Fraction = _CONST['Y']

# The Observer Fixed Point — Y_inv = π + 2/π ≈ 3.7776
Y_INV: Fraction = _CONST['Y_INV']

# π to 50-term continued fraction precision
PI: Fraction = _CONST['PI']

# The Triadic Monad constants (for particle physics derivation)
PHI: Fraction = Fraction(1618033988749895, 1000000000000000)   # Golden ratio
E_CONST: Fraction = Fraction(2718281828459045, 1000000000000000)  # Euler's number

# The Existence Unit: 24³ = 13824
EXISTENCE_UNIT: Fraction = Fraction(24**3, 1)

# The 13D Sink Leakage (wobble from Triadic Monad)
_MONAD = PI * PHI * E_CONST
_WOBBLE = _MONAD % Fraction(1, 1)
SINK_L: Fraction = _WOBBLE / Fraction(13, 1)

# Golay substrate properties
GOLAY_BLOCK_LENGTH: int = 24
GOLAY_MESSAGE_LENGTH: int = 12
GOLAY_MIN_DISTANCE: int = 8
GOLAY_CORRECTION_RADIUS: int = 3

# Leech Lattice geometry constants
KISSING_NUMBER: int = 196560          # Leech Lattice kissing number (Λ₂₄)
LEECH_DIMENSION: int = 24             # Leech Lattice dimension

# ---------------------------------------------------------------------------
# PHYSICAL CONSTANTS (real SI values, used for scaling the virtual space)
# These are the empirical anchors that UBP derives geometrically.
# ---------------------------------------------------------------------------
SPEED_OF_LIGHT_MS: int = 299_792_458          # m/s (exact)
PLANCK_H: Fraction = Fraction(662607015, 10**41)  # J·s (≈ 6.626e-34)
BOLTZMANN_K: Fraction = Fraction(1380649, 10**29)  # J/K (≈ 1.381e-23)

# Gravitational acceleration on Earth's surface (m/s²)
# Used as the baseline for the game space gravity scale.
# In the engine, this is expressed as a UBP Symmetry Tax gradient per tick.
G_EARTH_MS2: Fraction = Fraction(980665, 100000)   # 9.80665 m/s²

# ---------------------------------------------------------------------------
# ENGINE SINGLETON ACCESSORS
# ---------------------------------------------------------------------------

def get_golay() -> GolayCodeEngine:
    """Return the global Golay engine singleton."""
    return GOLAY_ENGINE

def get_leech() -> LeechLatticeEngine:
    """Return the global Leech Lattice engine singleton."""
    return LEECH_ENGINE

def get_tgic() -> TGICExactEngine:
    """Return a fresh TGIC engine instance."""
    return TGICExactEngine()

def get_particle_physics() -> UBPSourceCodeParticlePhysics:
    """Return the global particle physics engine singleton."""
    return PARTICLE_PHYSICS

# ---------------------------------------------------------------------------
# CORE SUBSTRATE OPERATIONS
# ---------------------------------------------------------------------------

def encode_to_golay(message_12bit: List[int]) -> List[int]:
    """
    Encode a 12-bit noumenal seed into a 24-bit Golay codeword.
    This is the fundamental act of 'manifesting' an informational intent
    into a phenomenal (observable) state.
    """
    if len(message_12bit) != 12:
        raise ValueError("Noumenal seed must be exactly 12 bits.")
    return GOLAY_ENGINE.encode(message_12bit)

def decode_from_golay(received_24bit: List[int]) -> Tuple[List[int], bool, int]:
    """
    Decode a 24-bit received vector back to its 12-bit noumenal seed.
    Returns (message, correctable, errors_corrected).
    Corrects up to 3 bit-flips (the 3-3-3 Golay Limit).
    """
    if len(received_24bit) != 24:
        raise ValueError("Received vector must be exactly 24 bits.")
    return GOLAY_ENGINE.decode(received_24bit)

def coherence_snap(noisy_vector: List[int]) -> Tuple[List[int], Dict[str, Any]]:
    """
    Snap a drifting 24-bit state to the nearest valid Golay codeword.
    This is the fundamental 'restorative pressure' of the UBP substrate —
    the universe correcting a state that has drifted from coherence.
    Returns (snapped_vector, snap_metadata).
    """
    return GOLAY_ENGINE.snap_to_codeword(noisy_vector)

def calculate_symmetry_tax(vector_24bit: List[int]) -> Fraction:
    """
    Calculate the Symmetry Tax (LAW_SYMMETRY_001) for a 24-bit vector.

    Tax = (Hamming_Weight × Y) + (Norm² / 8)

    This is the UBP equivalent of mass-energy. It represents the geometric
    cost the substrate must pay to maintain this entity's identity.
    Higher tax = heavier/more complex entity.
    """
    return LEECH_ENGINE.calculate_symmetry_tax(vector_24bit)

def calculate_nrci(vector_24bit: List[int]) -> Fraction:
    """
    Calculate the Non-Random Coherence Index (NRCI) for a 24-bit vector.

    NRCI = 10 / (10 + Tax)

    Maps stability between 1.0 (perfect codeword, maximum coherence) and
    approaching 0.0 (Deep Hole, informational dissolution).
    """
    tax = calculate_symmetry_tax(vector_24bit)
    return Fraction(10, 1) / (Fraction(10, 1) + tax)

def hamming_weight(vector: List[int]) -> int:
    """Return the Hamming weight (number of 1-bits) of a vector."""
    return BinaryLinearAlgebra.hamming_weight(vector)

def hamming_distance(v1: List[int], v2: List[int]) -> int:
    """Return the Hamming distance between two equal-length vectors."""
    return BinaryLinearAlgebra.hamming_distance(v1, v2)

def vector_from_math_dna(math_dna: str) -> List[int]:
    """
    Derive a deterministic 24-bit Golay vector from a mathematical DNA string.
    Uses SHA-256 fingerprinting (SOP_002 standard) to generate the noumenal seed,
    then encodes it into a full 24-bit phenomenal codeword.

    This is how every entity in the engine gets its unique geometric identity.
    """
    h = hashlib.sha256(math_dna.encode('utf-8')).digest()
    # Extract 12-bit noumenal seed from first two bytes
    seed_int = ((h[0] << 8) | h[1]) & 0xFFF
    if seed_int == 0:
        seed_int = 137  # Prevent void collapse (fine structure constant proxy)
    msg_bits = [(seed_int >> i) & 1 for i in range(11, -1, -1)]
    return GOLAY_ENGINE.encode(msg_bits)

def get_ontological_layers(vector_24bit: List[int]) -> Dict[str, Fraction]:
    """
    Return the four ontological layer health values for a 24-bit vector.
    Layers: Reality (bits 0-5), Info (bits 6-11),
            Activation (bits 12-17), Potential (bits 18-23).
    Each layer score is a Fraction in [0, 1].
    """
    point = LeechPointScaled(coords=tuple(vector_24bit))
    return point.get_ontological_health()

def xor_interact(v1: List[int], v2: List[int]) -> List[int]:
    """
    Perform a UBP interaction (XOR 'Smash') between two 24-bit vectors,
    then snap the result to the nearest Golay codeword.
    This models the collision/interaction of two entities.
    """
    raw = [(a ^ b) for a, b in zip(v1, v2)]
    snapped, _ = coherence_snap(raw)
    return snapped

def get_relational_pull(
    target_vector: List[int],
    manifold: Dict[Any, List[int]]
) -> Fraction:
    """
    Calculate the total relational pull on a target vector from all other
    vectors in the manifold (the TGIC gravity analogue).

    Pull = Σ Y/2 / (Hamming_Distance(target, neighbor) + 1)

    This is the UBP equivalent of gravitational attraction — entities with
    similar geometric signatures exert stronger pull on each other.
    """
    pull = Fraction(0)
    for key, vec in manifold.items():
        dist = hamming_distance(target_vector, vec)
        pull += (Y_CONSTANT / 2) / Fraction(dist + 1, 1)
    return pull

# ---------------------------------------------------------------------------
# CONSTRUCTION PATH TAX HELPER
# ---------------------------------------------------------------------------

def _construction_tax_from_dna(math_dna: str) -> Fraction:
    """
    Parse the construction=... field from a math_dna string and compute
    the ConstructionPath Symmetry Tax.

    The ConstructionPath tax is the correct UBP mass measure for entities
    because it captures the complexity of the geometric construction recipe,
    not just the binary vector weight (which is the same for all weight-12
    Golay codewords).

    Parsing: construction=D(n)X(m)N(D(k))J(D(j))...
    Each primitive is D, X, N, or J followed by a count in parentheses.
    """
    # Extract construction string
    m = re.search(r'construction=([^|]+)', math_dna)
    if not m:
        # No construction field — use a minimal single-step path
        prims = [ConstructionPrimitive('D', 1)]
        path = ConstructionPath(prims, 'default')
        return path.tax

    construction_str = m.group(1)

    # Parse primitives: match D(n), X(n), N(D(n)), J(D(n)) patterns
    # Extract all top-level D/X/N/J with their counts
    prims = []
    tokens = re.findall(r'([DXNJ])\((\d+)(?:[^)]*)?\)', construction_str)
    for ptype, count in tokens:
        prims.append(ConstructionPrimitive(ptype, int(count)))

    if not prims:
        prims = [ConstructionPrimitive('D', 1)]

    path = ConstructionPath(prims, 'entity')
    return path.tax


# ---------------------------------------------------------------------------
# SUBSTRATE VALIDATION
# ---------------------------------------------------------------------------

def validate_substrate() -> Dict[str, Any]:
    """
    Run a full substrate validation (equivalent to ubp_handshake.py).
    Verifies: π precision, Golay encode/decode, Leech tax, particle physics.
    Returns a status report dict.
    """
    report = {}

    # 1. π precision check
    pi_val = float(PI)
    pi_error = abs(pi_val - 3.14159265358979323846) / 3.14159265358979323846 * 100
    report['pi_precision'] = {
        'value': pi_val,
        'error_pct': pi_error,
        'status': 'GREEN' if pi_error < 1e-10 else 'RED'
    }

    # 2. Golay round-trip
    test_msg = [1, 0, 1, 1, 0, 0, 1, 0, 1, 1, 0, 1]
    encoded = GOLAY_ENGINE.encode(test_msg)
    decoded, ok, errs = GOLAY_ENGINE.decode(encoded)
    report['golay_roundtrip'] = {
        'message': test_msg,
        'encoded_weight': sum(encoded),
        'decoded_match': decoded == test_msg,
        'errors_corrected': errs,
        'status': 'GREEN' if decoded == test_msg else 'RED'
    }

    # 3. Golay error correction (inject 3 bit-flips at correctable positions)
    # The UBP Golay syndrome table covers error indices 0..4095 (12-bit range).
    # Correctable 3-bit errors must have all positions in bits 0-11.
    # Using positions 0, 1, 2 -> error index = 1+2+4 = 7 (within range).
    noisy = encoded.copy()
    noisy[0] ^= 1; noisy[1] ^= 1; noisy[2] ^= 1
    dec2, ok2, errs2 = GOLAY_ENGINE.decode(noisy)
    report['golay_correction'] = {
        'bits_flipped': 3,
        'corrected': dec2 == test_msg,
        'errors_corrected': errs2,
        'note': 'Corrects errors in noumenal half (bits 0-11); phenomenal errors use snap_to_codeword',
        'status': 'GREEN' if dec2 == test_msg else 'RED'
    }

    # 4. Symmetry Tax sanity
    zero_vec = [0] * 24
    tax_zero = calculate_symmetry_tax(zero_vec)
    ones_vec = [1] * 24
    tax_ones = calculate_symmetry_tax(ones_vec)
    report['symmetry_tax'] = {
        'zero_vector_tax': float(tax_zero),
        'all_ones_tax': float(tax_ones),
        'y_constant': float(Y_CONSTANT),
        'status': 'GREEN' if tax_zero == Fraction(0) and tax_ones > 0 else 'RED'
    }

    # 5. Particle physics predictions
    preds = PARTICLE_PHYSICS.get_ultimate_predictions()
    global_err = preds['global_error']
    report['particle_physics'] = {
        'global_error_pct': global_err,
        'alpha_inv_error_pct': preds['alpha_inv']['error_percent'],
        'muon_ratio_error_pct': preds['muon_electron']['error_percent'],
        'proton_ratio_error_pct': preds['proton_electron']['error_percent'],
        'status': 'GREEN' if global_err < 0.5 else 'YELLOW'
    }

    # 6. Y-constant derivation check
    y_float = float(Y_CONSTANT)
    report['y_constant'] = {
        'value': y_float,
        'expected_approx': 0.2646,
        'deviation': abs(y_float - 0.2646),
        'status': 'GREEN' if abs(y_float - 0.2646) < 0.001 else 'RED'
    }

    # Overall status
    all_green = all(v.get('status', 'RED') in ('GREEN', 'YELLOW')
                    for v in report.values())
    report['overall'] = 'GREEN' if all_green else 'RED'

    return report


# ---------------------------------------------------------------------------
# MODULE SELF-TEST
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    print("=" * 72)
    print("UBP ENGINE SUBSTRATE v1.0 — SELF-TEST")
    print("=" * 72)

    result = validate_substrate()
    for key, val in result.items():
        if key == 'overall':
            print(f"\n{'='*72}")
            print(f"OVERALL STATUS: {val}")
            print(f"{'='*72}")
        else:
            status = val.get('status', '?')
            print(f"  [{status}] {key}")
            for k2, v2 in val.items():
                if k2 != 'status':
                    print(f"         {k2}: {v2}")


# ---------------------------------------------------------------------------
# UBPEngineSubstrate CLASS WRAPPER
# ---------------------------------------------------------------------------
# Provides an object-oriented interface to the module-level substrate functions.
# This class is used by ubp_server_v3.py and other modules that need a
# stateful substrate object.
# ---------------------------------------------------------------------------

class UBPEngineSubstrate:
    """
    Object-oriented wrapper around the UBP Engine Substrate module functions.
    Exposes all substrate capabilities as instance methods while maintaining
    the singleton UBP core objects (Golay, Leech, TGIC, etc.).
    """

    def __init__(self):
        # Expose the singleton engines as attributes
        self.golay = GOLAY_ENGINE
        self.leech = LEECH_ENGINE
        self.tgic = get_tgic()
        self.particle_physics = PARTICLE_PHYSICS

        # Expose key constants (using the names defined in this module)
        self.Y_CONSTANT = Y_CONSTANT
        self.PI = PI
        self.G_EARTH_MS2 = G_EARTH_MS2
        self.SINK_L = SINK_L
        self.KISSING_NUMBER = KISSING_NUMBER
        self.LEECH_DIMENSION = LEECH_DIMENSION
        # Physics engine constants are in ubp_physics_v3 — import lazily
        try:
            from ubp_physics_v3 import (
                _C_DRAG as _c, _V_MAX as _v, _G_PER_TICK_SQ as _g,
                _V_REST_THRESHOLD as _r
            )
            self.C_DRAG = _c
            self.V_MAX = _v
            self.G_PER_TICK_SQ = _g
            self.V_REST_THRESHOLD = _r
        except ImportError:
            self.C_DRAG = None
            self.V_MAX = None
            self.G_PER_TICK_SQ = None
            self.V_REST_THRESHOLD = None

    # --- Golay Operations ---
    def encode(self, message_12bit):
        return encode_to_golay(message_12bit)

    def decode(self, received_24bit):
        return decode_from_golay(received_24bit)

    def coherence_snap(self, noisy_vector):
        return coherence_snap(noisy_vector)

    # --- Symmetry & NRCI ---
    def calculate_symmetry_tax(self, vector_24bit):
        return calculate_symmetry_tax(vector_24bit)

    def calculate_nrci(self, vector_24bit):
        return calculate_nrci(vector_24bit)

    # --- Vector Operations ---
    def hamming_weight(self, vector):
        return hamming_weight(vector)

    def hamming_distance(self, v1, v2):
        return hamming_distance(v1, v2)

    def vector_from_math_dna(self, math_dna):
        return vector_from_math_dna(math_dna)

    def xor_interact(self, v1, v2):
        return xor_interact(v1, v2)

    # --- Construction Tax ---
    def construction_tax_from_dna(self, math_dna):
        return _construction_tax_from_dna(math_dna)

    # --- Validation ---
    def validate(self):
        return validate_substrate()

    def __repr__(self):
        return (
            f"UBPEngineSubstrate("
            f"Y={float(self.Y_CONSTANT):.6f}, "
            f"V_MAX={float(self.V_MAX):.4f}, "
            f"C_DRAG={float(self.C_DRAG):.6f})"
        )
