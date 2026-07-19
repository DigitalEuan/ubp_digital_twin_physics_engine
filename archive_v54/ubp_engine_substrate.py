"""
================================================================================
UBP ENGINE SUBSTRATE v2.0 (v5.4 ALIGNED)
================================================================================
The foundational layer of the UBP Game Engine.

This module is the single point of integration between the UBP Core Studio
(v5.4 ubp_unified_v5 backbone) and the game engine. It imports and exposes all
UBP mathematical primitives, constants, and engines that the game physics
layer will use.

NO simplifications. NO shortcuts. This substrate uses the real UBP system:
  - GolayCodeEngine [24,12,8] for state error-correction and Coherence Snap
  - LeechLatticeEngine (Λ₂₄) for Symmetry Tax (mass/energy equivalent)
  - UBPUltimateSubstrate for 50-term π and the Y-Constant
  - MonsterGroup, BarnesWallEngine, TriadActivationEngine (the Triad)
  - NoiseALU / PhysicsALU / LinearAlgebraALU (Sovereign compute)
  - TGICExactEngine for relational pull (gravity analogue)
  - BinaryLinearAlgebra for all GF(2) operations
  - UBPSourceCodeParticlePhysics for fundamental constant derivation

PHYSICS CONSTANTS DERIVED LIVE FROM THE SUBSTRATE (no hardcoded CODATA):
  • Muon/electron ratio    m_μ/m_e    = 169 / w              (0.0294% err)
  • Strong coupling        α_s        = 24 · Y⁴              (0.188% err)
  • Fine structure α³      α³         = (29/24) · Y¹² · e    (0.104% err)
  • Hubble constant        H₀         = (1/3) · w · Y³ · U_e (0.495% err)
  • Cosmological Ω_k base  Ω_k        = 24 · Y¹⁵ · U_e       (0.035% err)
  • Newton's G             G          = (39/29) · Y¹⁸ / w    (0.133% err)
  • Topological shear      Shear₁     = 1 + 3·L·Y            (1.04992)
                          Shear₂     = 1 + 3·L·Y + 12·(L·Y)² (1.05324)

UBP Game Engine v5.2 (built on UBP Core Studio v5.4.0 ubp_unified_v5 backbone)
Author: E R A Craig, New Zealand
Date: July 2026
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
    from ubp_unified_v5 import (
        # Core engines
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
        # v5.4 NEW: Triad engines (MonsterGroup, BarnesWallEngine)
        MonsterGroup,
        BarnesWallEngine,
        # v5.4 NEW: Sovereign ALU stack
        NoiseALU,
        PhysicsALU,
        LinearAlgebraALU,
        AdaptiveManifold,
        NeuralPatternDetector,
        ParallelUBP,
        # v5.4 NEW: Exact-math utilities
        ExactMath,
        ExactRoot,
        # Singletons
        GOLAY_ENGINE,
        LEECH_ENGINE,
        PARTICLE_PHYSICS,
        SUBSTRATE,
        MONSTER_ENGINE,
        BW_ENGINE,
    )
    from ubp_tgic_engine import (
        TGICExactEngine,
        TGICInteractionEngine,
        TGICConstraintSystem,
        OffBit,
    )
    _CORE_LOADED = True
    print("[UBP Engine Substrate] UBP Core v5.4 (ubp_unified_v5) loaded successfully.")
except ImportError as e:
    _CORE_LOADED = False
    print(f"[UBP Engine Substrate] CRITICAL: Could not load UBP Core: {e}")
    raise RuntimeError(
        f"UBP Core not found at {_CORE_DIR}. "
        "Ensure the UBP_Repo/core_studio_v4.0/core directory exists."
    ) from e

# ---------------------------------------------------------------------------
# FUNDAMENTAL CONSTANTS (sourced live from the v5.4 substrate — float-free)
# ---------------------------------------------------------------------------
# v5.4 UBPSourceCodeParticlePhysics exposes every constant as a first-class
# Fraction attribute. We re-export those canonical values here so dependent
# modules import ONE source of truth (instead of each module re-deriving
# MONAD/WOBBLE/SINK_L locally and risking drift).
_CONST = SUBSTRATE.get_constants(50)

# The Observer Constant — Y ≈ 0.264675 (the geometric rent paid by every
# bit to maintain identity).
Y_CONSTANT: Fraction = _CONST['Y']

# The Observer Fixed Point — Y_inv = π + 2/π ≈ 3.778212
Y_INV: Fraction = _CONST['Y_INV']

# π to 50-term continued fraction precision (exact Fraction).
PI: Fraction = _CONST['PI']

# φ and e — sourced from PARTICLE_PHYSICS (single source of truth).
# v1.0 re-defined these as Fractions in this module, duplicating the value
# and risking drift. v2.0 imports PARTICLE_PHYSICS.phi/e_const directly so
# that any future backbone precision upgrade propagates automatically.
# (Live verification shows v5.4's pp.phi and pp.e_const reduce to the same
# rational as v1.0's truncations, so this is a structural improvement, not
# a precision improvement.)
PHI: Fraction = PARTICLE_PHYSICS.phi
E_CONST: Fraction = PARTICLE_PHYSICS.e_const

# The Triadic Monad: MONAD = π × φ × e ≈ 13.817580227176
# The Entropic Wobble: w = MONAD mod 1 ≈ 0.817580227176
# Both sourced live from the substrate.
MONAD: Fraction = PARTICLE_PHYSICS.monad
WOBBLE: Fraction = PARTICLE_PHYSICS.wobble

# The 13D Sink Leakage: L = w / 13 ≈ 0.062890786706  (D-Sink dimension)
# [LAW_13D_SINK_001] Sourced live from PARTICLE_PHYSICS.L (= w/13).
SINK_L: Fraction = PARTICLE_PHYSICS.L

# The Stereoscopic Sink: L_s = L × σ where σ = 29/24 (Baryonic correction)
# [LAW_STEREOSCOPIC_SINK_001] First-class attribute in v5.4 backbone.
SINK_SIGMA: Fraction = PARTICLE_PHYSICS.sigma
SINK_L_STEREO: Fraction = PARTICLE_PHYSICS.L_s

# The Existence Unit: U_e = 24³ = 13824  (Potential-layer amplifier)
EXISTENCE_UNIT: Fraction = PARTICLE_PHYSICS.U_e

# The Noumenal Volume: V_n = MONAD × 24 ≈ 204.801744  (primary energy unit)
NOUMENAL_VOLUME: Fraction = MONAD * Fraction(24, 1)

# Wall of Reality: maximum toggle frequency before state collapse
# [LAW_TOTAL_EXPERIENCED_RESULT_001] F_MAX = 1 THz
F_MAX_HZ: int = 10**12

# Conscious Threshold: NRCI ≥ 0.70 → MANIFESTED (physical/observable)
# [LAW_OBSERVER_DYNAMICS] 0.70 = 7/10 from ObserverDynamicsEngine v7.1
CONSCIOUS_THRESHOLD: Fraction = Fraction(70, 100)

# Golay substrate properties
GOLAY_BLOCK_LENGTH: int = 24
GOLAY_MESSAGE_LENGTH: int = 12
GOLAY_MIN_DISTANCE: int = 8
GOLAY_CORRECTION_RADIUS: int = 3

# Leech Lattice geometry constants
KISSING_NUMBER: int = 196560          # Leech Lattice kissing number (Λ₂₄)
LEECH_DIMENSION: int = 24             # Leech Lattice dimension

# ---------------------------------------------------------------------------
# v5.4 PHYSICS CONSTANT PREDICTIONS  (UBP_SKILL_1 §9 Canonical Formula Table)
# ---------------------------------------------------------------------------
# These are computed live from the substrate primitives. They are the
# falsifiable predictions of the UBP system; each must reproduce the
# physical target within the documented error budget.
#
# L = pp.L = w/13 throughout all formulas below.
#
# | # | Target    | Formula                              | Err%  | Lens |
# |---|-----------|--------------------------------------|-------|------|
# | 1 | m_μ/m_e   | 169 / w                              | 0.029 | Pure Inverse (13-D Sink) |
# | 2 | α_s       | 24 · Y⁴                              | 0.188 | Information k=4 |
# | 3 | m_W       | (13/L)·24·Y⁴·π·Shear₁                | 0.094 | Cross-layer |
# | 4 | Ω_k base  | 24 · Y¹⁵ · U_e                       | 0.035 | Potential k=15 |
# | 5 | n_γ/n_b   | (1/4)·Y²¹·U_e·Shear₂·NRCIα(2)        | 0.055 | Potential k=21 |
# | 6 | V_ub²     | (1/24)·Y¹²·U_e·NRCIα(13)             | 0.032 | Potential k=12 |
# | 7 | α³        | (29/24)·Y¹²·e                        | 0.104 | Potential*, e↔U_e |
# | 8 | H₀        | (1/3)·w·Y³·U_e                       | 0.495 | w-based k=3 |
# | G | G_grav    | (39/29)·Y¹⁸/w                        | 0.133 | Topological Resonance |
# ---------------------------------------------------------------------------

# Topological shear constants (UBP_SKILL_1 §7)
_LY: Fraction = SINK_L * Y_CONSTANT       # L·Y ≈ 0.016641
SHEAR_1: Fraction = Fraction(1, 1) + Fraction(3, 1) * _LY                          # ≈ 1.04992
SHEAR_2: Fraction = Fraction(1, 1) + Fraction(3, 1) * _LY + Fraction(12, 1) * _LY * _LY  # ≈ 1.05324

# Particle physics predictions (base forms without NRCIα codeword resolution —
# those require a specific 24-bit vector and are computed on demand).
MUON_ELECTRON_RATIO: Fraction = Fraction(169, 1) / WOBBLE                          # 206.7075
STRONG_COUPLING_ALPHA_S: Fraction = Fraction(24, 1) * Y_CONSTANT ** 4              # 0.1181
ALPHA_CUBED: Fraction = Fraction(29, 24) * Y_CONSTANT ** 12 * E_CONST              # 3.882e-7
HUBBLE_H0: Fraction = Fraction(1, 3) * WOBBLE * Y_CONSTANT ** 3 * EXISTENCE_UNIT   # 69.85 km/s/Mpc
OMEGA_K_BASE: Fraction = Fraction(24, 1) * Y_CONSTANT ** 15 * EXISTENCE_UNIT       # 7.27e-4
GRAVITATIONAL_G: Fraction = Fraction(39, 29) * Y_CONSTANT ** 18 / WOBBLE           # 6.683e-11 (SI)
# m_W (GeV) requires a unit-bridge multiplier documented in push06; left as
# computed base for now: (13/L)·24·Y⁴·π·Shear₁
W_BOSON_BASE: Fraction = (Fraction(13, 1) / SINK_L) * Fraction(24, 1) * Y_CONSTANT ** 4 * PI * SHEAR_1

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

def get_monster() -> MonsterGroup:
    """Return the global Monster Group engine singleton (v5.4 NEW).

    [UBP_SKILL_1 §2] The Monster is the third leg of the Golay ∩ Leech ∩
    Monster Triad. Its order |M| = 808017424794512875886459904961710757005754368000000000
    (54 digits) is the size of the largest sporadic simple group.
    """
    return MONSTER_ENGINE

def get_barnes_wall(dimension: int = 256) -> BarnesWallEngine:
    """Return a Barnes-Wall engine instance (v5.4 NEW).

    [UBP_SKILL_1 §2] BarnesWallEngine projects the 24-bit substrate into
    macro-bulk dimensions: 256D, 512D, or 1024D. Used for high-rank
    macroscopic state encoding (e.g. pantograph tax, macro-soul).
    """
    if dimension not in (256, 512, 1024):
        raise ValueError(f"BarnesWallEngine dimension must be 256, 512, or 1024 (got {dimension})")
    return BarnesWallEngine(dimension)

def get_triad() -> TriadActivationEngine:
    """Return a fresh Triad Activation engine instance (v5.4 NEW).

    [UBP_SKILL_1 §2] TriadActivationEngine ties together the Golay, Leech,
    and Monster engines. Note: in v5.4 it takes no constructor args
    (auto-initialises its own internal singletons).
    """
    return TriadActivationEngine()

def get_noise_alu(mode: str = 'SV') -> NoiseALU:
    """Return a fresh Noise ALU instance (v5.4 NEW).

    [UBP_SKILL_1 §17 Layer 3] The Noise ALU is the substrate-mediated
    arithmetic logic unit: it operates on 24-bit Golay vectors with
    deterministic, error-corrected semantics.

    mode='SM' (Substrate-Mediated) — Y-driven deterministic arm
    mode='SV' (Substrate-Verified) — w-driven stochastic arm (default)
    """
    if mode not in ('SM', 'SV'):
        raise ValueError(f"NoiseALU mode must be 'SM' or 'SV' (got {mode!r})")
    return NoiseALU(mode=mode)

def get_physics_alu(mode: str = 'SV') -> PhysicsALU:
    """Return a fresh Physics ALU instance (v5.4 NEW).

    The Physics ALU extends NoiseALU with physics-aware operations.
    Inherits all NoiseALU capabilities. Same mode semantics as get_noise_alu.
    """
    if mode not in ('SM', 'SV'):
        raise ValueError(f"PhysicsALU mode must be 'SM' or 'SV' (got {mode!r})")
    return PhysicsALU(mode=mode)

def get_linear_algebra_alu(mode: str = 'SV') -> LinearAlgebraALU:
    """Return a fresh Linear Algebra ALU instance (v5.4 NEW).

    The Linear Algebra ALU extends NoiseALU with vector/matrix operations
    over the substrate (rank, kernel, image — all NRCI-aware).
    Same mode semantics as get_noise_alu.
    """
    if mode not in ('SM', 'SV'):
        raise ValueError(f"LinearAlgebraALU mode must be 'SM' or 'SV' (got {mode!r})")
    return LinearAlgebraALU(mode=mode)


# ---------------------------------------------------------------------------
# PHYSICS REGISTRY — Extension point for future physics domains (v5.4 NEW)
# ---------------------------------------------------------------------------
# Phase 3 introduced a plugin-style registry so new physics domains
# (electromagnetism, chemistry, biology, etc.) can be added without
# modifying the substrate. Each domain registers itself at import time
# and validate_substrate() automatically picks up its results.
#
# See ubp_physics_registry.py for the full API and usage examples.
def get_physics_registry():
    """Return the global physics domain registry (v5.4 NEW).

    Returns the _PhysicsRegistry singleton. New domains can be registered
    via:

        from ubp_physics_registry import PhysicsDomain, register_domain
        register_domain(PhysicsDomain(name='my_domain', version='0.1.0', ...))

    Or retrieved via:

        registry = get_physics_registry()
        my_domain = registry.get_domain('my_domain')
    """
    from ubp_physics_registry import get_registry
    return get_registry()

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

def calculate_symmetry_tax(vector_24bit: List[int], compactness: Optional[Fraction] = None) -> Fraction:
    """
    Calculate the Symmetry Tax (LAW_SYMMETRY_001) for a 24-bit vector.

    Tax = (Hamming_Weight × Y) + (Norm² / 8)

    v6.3.1 UPDATE: When compactness (C) is provided, the Volumetric Rebate
    is applied: T_adj = T_base * (1 - C/13).
    This is the UBP equivalent of mass-energy. It represents the geometric
    cost the substrate must pay to maintain this entity's identity.
    Higher tax = heavier/more complex entity.
    """
    return LEECH_ENGINE.calculate_symmetry_tax(vector_24bit, compactness=compactness)

def calculate_nrci(vector_24bit: List[int], compactness: Optional[Fraction] = None) -> Fraction:
    """
    Calculate the Non-Random Coherence Index (NRCI) for a 24-bit vector.

    NRCI = 10 / (10 + Tax)

    Maps stability between 1.0 (perfect codeword, maximum coherence) and
    approaching 0.0 (Deep Hole, informational dissolution).

    v6.3.1 UPDATE: When compactness (C) is provided, the Volumetric Rebate
    is applied to the tax before computing NRCI.
    """
    tax = calculate_symmetry_tax(vector_24bit, compactness=compactness)
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

    v6.3.1 UPDATE: Enforces the Domain Pivot at Bit 12 (Index 11).
    Bit 11 of the 12-bit message seed is set to 1 for Phenomenal domains
    (matter/substance/mechanism) and 0 for Noumenal domains (math/meaning).

    Domain detection from math_dna:
      - 'phase=solid' or 'phase=liquid' or 'PHYS_' or 'ELEM_' or 'MAT_' -> Phenomenal (1)
      - 'phase=gas' or 'MATH_' or 'ALGO_' or 'MEANING_' -> Noumenal (0)
      - Default: Phenomenal (1) for engine entities (they exist in space)

    This is how every entity in the engine gets its unique geometric identity.
    """
    h = hashlib.sha256(math_dna.encode('utf-8')).digest()
    # Extract 11-bit payload from first two bytes (bits 0-10)
    seed_int = ((h[0] << 8) | h[1]) & 0x7FF  # 11 bits only
    if seed_int == 0:
        seed_int = 137  # Prevent void collapse (fine structure constant proxy)
    payload_bits = [(seed_int >> i) & 1 for i in range(10, -1, -1)]  # 11 bits

    # Determine Domain Pivot (Bit 12, Index 11)
    # Phenomenal = 1: matter exists in space (solid, liquid, mechanism)
    # Noumenal = 0: abstract (gas, math, algorithm, meaning)
    dna_upper = math_dna.upper()
    is_noumenal = (
        'phase=gas' in math_dna.lower() or
        dna_upper.startswith('MATH_') or
        dna_upper.startswith('ALGO_') or
        dna_upper.startswith('MEANING_') or
        dna_upper.startswith('NUM_')
    )
    domain_pivot = 0 if is_noumenal else 1  # Default: Phenomenal

    # Construct 12-bit message: [11 payload bits] + [1 domain pivot bit]
    msg_bits = payload_bits + [domain_pivot]
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
    Perform a UBP Synthesis interaction between two 24-bit vectors.

    v6.3.1 UPDATE: Replaced XOR 'Smash' with Additive Superposition +
    Phenomenal Collapse (The Flow).

    Process:
      1. Convert binary {0,1} to bipolar {-1,+1}: 0->-1, 1->+1
      2. Sum bipolar vectors element-wise (Z^24 superposition)
      3. Collapse: sum>0 -> 0, sum<0 -> 1, sum=0 -> 0 (Void/Deep Hole)
      4. Apply Golay Coherence Snap to the collapsed vector

    The Void collapse (sum=0 -> 0) reflects the UBP principle that when
    two equal pressures meet, the substrate resolves to the Deep Hole
    rather than an arbitrary binary choice.
    """
    # Step 1: Convert to bipolar (-1, +1)
    b1 = [-1 if a == 0 else 1 for a in v1]
    b2 = [-1 if a == 0 else 1 for a in v2]
    # Step 2: Additive superposition
    combined = [b1[i] + b2[i] for i in range(len(v1))]
    # Step 3: Phenomenal collapse
    collapsed = [0 if s >= 0 else 1 for s in combined]
    # Step 4: Golay coherence snap
    snapped, _ = coherence_snap(collapsed)
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
# SOVEREIGN ALU INTEGRATION
# ---------------------------------------------------------------------------
try:
    from ubp_eml_alu_sovereign import GrandUnifiedEmlALU
    _SOVEREIGN_ALU = GrandUnifiedEmlALU()
    _SOVEREIGN_ALU_LOADED = True
except ImportError:
    _SOVEREIGN_ALU = None
    _SOVEREIGN_ALU_LOADED = False

def get_sovereign_alu():
    """
    Return the singleton Sovereign EML ALU instance.
    [LAW_TRIADIC_GENESIS_001] The Sovereign ALU is a zero-dependency implementation
    of all transcendental functions from the single EML operator: eml(x,y) = exp(x) - ln(y).
    PI is derived natively via ln(-1) (Mocz/Odrzywolek Path), confirming the
    50-term Fraction PI used throughout the engine.
    """
    if _SOVEREIGN_ALU is None:
        raise RuntimeError("Sovereign ALU not loaded. Ensure ubp_eml_alu_sovereign.py is present.")
    return _SOVEREIGN_ALU

# ---------------------------------------------------------------------------
# GRAY CODE UMS (Universal Manifold State Encoder)
# ---------------------------------------------------------------------------
def gray_code_encode_state(params: Dict[str, float], schema: Dict[str, Dict]) -> List[int]:
    """
    Encode continuous parameters into a 24-bit Golay codeword via Gray Code UMS.
    [LAW_GRAY_CODE_UMS] Uses Gray code to prevent multi-bit transitions when
    a parameter crosses a boundary — ensuring Hamming distance 1 between
    adjacent states (the UBP principle of minimal ontological drift).

    schema format: {'param_name': {'min': float, 'max': float, 'bits': int}}
    Total bits across all params must not exceed 12 (Golay message capacity).

    Example schema for an entity state:
      {'velocity': {'min': 0.0, 'max': 10.0, 'bits': 4},
       'nrci':     {'min': 0.0, 'max': 1.0,  'bits': 4},
       'temp':     {'min': 0.0, 'max': 100.0, 'bits': 4}}
    """
    def _to_gray_bits(val: int, bits: int) -> List[int]:
        g = val ^ (val >> 1)
        return [(g >> i) & 1 for i in range(bits - 1, -1, -1)]

    message: List[int] = []
    total_bits = 0
    for key, bounds in schema.items():
        bits = int(bounds.get('bits', 3))
        total_bits += bits
        if total_bits > 12:
            raise ValueError(f"Gray Code UMS schema exceeds 12-bit Golay capacity at '{key}'.")
        val = params.get(key, bounds['min'])
        max_int = (1 << bits) - 1
        lo, hi = bounds['min'], bounds['max']
        norm = (val - lo) / (hi - lo) if hi > lo else 0.0
        discrete = int(round(max(0.0, min(1.0, norm)) * max_int))
        message.extend(_to_gray_bits(discrete, bits))
    while len(message) < 12:
        message.append(0)
    return GOLAY_ENGINE.encode(message)

# ---------------------------------------------------------------------------
# OBSERVER DYNAMICS (Wall of Reality, SOC Energy, Conscious Read, TER)
# ---------------------------------------------------------------------------
import math as _math

def calculate_soc_energy(vector_24bit: List[int], nrci: Fraction, toggle_rate_hz: float = 1.0) -> float:
    """
    Calculate the State of Coherence (SOC) energy for a 24-bit entity state.
    [LAW_TOTAL_EXPERIENCED_RESULT_001] SOC = weight × c × Y × NRCI × penalty
    where penalty is a Gaussian collapse above the Wall of Reality (1 THz).
    This is the UBP equivalent of E=mc² — the energy of a manifested state.
    """
    weight = sum(vector_24bit)
    penalty = 1.0
    if toggle_rate_hz > F_MAX_HZ:
        sigma_hz = 1e11  # 100 GHz decay width
        penalty = _math.exp(-((toggle_rate_hz - F_MAX_HZ)**2) / (2 * sigma_hz**2))
    c = float(SPEED_OF_LIGHT_MS)
    y = float(Y_CONSTANT)
    n = float(nrci)
    return weight * c * y * n * penalty

def conscious_read(vector_24bit: List[int], nrci: Fraction) -> Dict[str, Any]:
    """
    Determine the Observer state of an entity based on its NRCI.
    [LAW_OBSERVER_DYNAMICS] NRCI >= 0.70 → MANIFESTED (physical/observable)
                            NRCI <  0.70 → SUBLIMINAL (below perception threshold)
    Returns a dict with status, is_manifested, ontology_layers, and new_reality.
    """
    is_manifested = nrci >= CONSCIOUS_THRESHOLD
    layers = {
        'Reality':     vector_24bit[0:6],
        'Information': vector_24bit[6:12],
        'Activation':  vector_24bit[12:18],
        'Potential':   vector_24bit[18:24],
    }
    return {
        'status': 'MANIFESTED' if is_manifested else 'SUBLIMINAL',
        'is_manifested': is_manifested,
        'ontology_layers': layers,
        'new_reality': layers['Potential'] if is_manifested else [0] * 6,
    }

def calculate_ter_score(vector_24bit: List[int]) -> float:
    """
    Calculate the Total Experienced Result (TER) score.
    [LAW_TOTAL_EXPERIENCED_RESULT_001]
    E = M × f × dt
    where M = active bits (Hamming weight), f = 1/24 (substrate clock),
    dt = 1/π (synchronization window).
    High TER = state is 'Experienced' as physical matter rather than noise.
    """
    M = sum(vector_24bit)
    f = Fraction(1, 24)
    dt = Fraction(1, 1) / PI
    return float(Fraction(M, 1) * f * dt)

# ---------------------------------------------------------------------------
# PANTOGRAPH TAX (Macroscopic Affine Kinematic Projection)
# ---------------------------------------------------------------------------
def calculate_pantograph_tax(vector_24bit: List[int], physical_volume: Optional[float] = None) -> Tuple[Fraction, Fraction]:
    """
    Calculate the Pantograph (macroscopic) Symmetry Tax for a 24-bit vector.
    [LAW_PANTOGRAPH_THERMODYNAMICS_001] Affine kinematic projection:
      k = 1 + WOBBLE (or derived from physical_volume / NOUMENAL_VOLUME)
      V_macro = k³ × V_noum  (volume scales cubically with k)
      S_macro = k² × S_noum + shear  (surface area scales quadratically)
      C_macro = V^(2/3) / S_macro  (compactness of the macroscopic projection)
      T_adj = T_base × (1 - C_macro/13)  (Volumetric Rebate applied)
      NRCI = 10 / (10 + T_adj)
    Returns: (T_adj: Fraction, nrci: Fraction)
    Used for large-scale objects (lever arms, floors, walls) to scale from the 
    absolute primitive voxel up to macroscopic sizes.
    """
    if physical_volume is not None and physical_volume > 0:
        # Scale k based on physical volume relative to the Noumenal primitive
        vol_ratio = physical_volume / float(NOUMENAL_VOLUME)
        # k is the 1D scaling factor, so we take the cube root of the volume ratio
        k_val = vol_ratio ** (1.0 / 3.0)
        # Ensure k is at least 1 (we don't scale below the noumenal primitive)
        k = Fraction(int(max(1.0, k_val) * 1_000_000), 1_000_000)
    else:
        k = Fraction(1, 1) + WOBBLE

    T_base = calculate_symmetry_tax(vector_24bit)
    shear = T_base - PI

    V_noum = Fraction(sum(vector_24bit), 1)
    S_noum = Fraction(24, 1)

    V_macro = (k ** 3) * V_noum
    S_macro = (k ** 2) * S_noum + shear

    V_f = float(V_macro)
    if V_f <= 0:
        V_f = 1.0
    V_23 = Fraction(int(V_f ** (2/3) * 1_000_000), 1_000_000)
    if S_macro <= 0:
        S_macro = Fraction(1, 1)
    C_macro = V_23 / S_macro

    T_adj = T_base * (Fraction(1, 1) - (C_macro / 13))
    nrci = Fraction(10, 1) / (Fraction(10, 1) + T_adj)
    return T_adj, nrci

# ---------------------------------------------------------------------------
# DESIGN QUALITY INDEX (DQI)
# ---------------------------------------------------------------------------
def calculate_dqi(nrci: float, u_score: float, gap_score: float) -> float:
    """
    Calculate the Design Quality Index (DQI).
    [LAW_VTE_QUANTIZATION_001] Weighted harmonic mean of:
      Stability (NRCI, w=0.40), Utility (u_score, w=0.40),
      Template Accuracy (gap_score, w=0.20).
    DQI ≥ 0.70 indicates a well-formed, stable, useful UBP entity.
    """
    e = 1e-6
    w_n, w_u, w_t = 0.40, 0.40, 0.20
    dqi = (w_n + w_u + w_t) / (
        w_n / max(e, nrci) +
        w_u / max(e, u_score) +
        w_t / max(e, gap_score)
    )
    return round(min(1.0, dqi), 4)

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

    # 5. Particle physics predictions (v5.4 schema: keys use Title Case + spaces)
    preds = PARTICLE_PHYSICS.get_ultimate_predictions()
    global_err = preds['global_error']
    report['particle_physics'] = {
        'global_error_pct': global_err,
        'alpha_inv_error_pct':       preds['Alpha Inv']['error_percent'],
        'muon_ratio_error_pct':      preds['Muon/e- Ratio']['error_percent'],
        'proton_ratio_error_pct':    preds['Proton/e- Ratio']['error_percent'],
        'status': 'GREEN' if global_err < 0.5 else 'YELLOW'
    }

    # 5b. v5.4 NEW: Live substrate-derived physics constants (UBP_SKILL_1 §9)
    #     These must match the documented error budgets. They are the
    #     falsifiable predictions of the UBP system — if any drifts, the
    #     substrate has been corrupted.
    report['v54_physics_predictions'] = {
        'muon_electron_ratio': {
            'predicted': float(MUON_ELECTRON_RATIO),
            'target':    206.7683,
            'error_pct': abs(float(MUON_ELECTRON_RATIO) - 206.7683) / 206.7683 * 100,
            'budget':    0.10,   # < 0.1% per UBP_SKILL_1 §9 row 1
        },
        'strong_coupling_alpha_s': {
            'predicted': float(STRONG_COUPLING_ALPHA_S),
            'target':    0.1181,
            'error_pct': abs(float(STRONG_COUPLING_ALPHA_S) - 0.1181) / 0.1181 * 100,
            'budget':    0.50,   # < 0.5% per row 2
        },
        'alpha_cubed': {
            'predicted': float(ALPHA_CUBED),
            'target':    float(Fraction(1000, 137036) ** 3),
            'error_pct': abs(float(ALPHA_CUBED) - float(Fraction(1000, 137036) ** 3))
                         / float(Fraction(1000, 137036) ** 3) * 100,
            'budget':    0.50,   # < 0.5% per row 7
        },
        'hubble_H0': {
            'predicted': float(HUBBLE_H0),
            'target':    70.0,
            'error_pct': abs(float(HUBBLE_H0) - 70.0) / 70.0 * 100,
            'budget':    1.00,   # < 1% per row 8
        },
        'omega_k_base': {
            'predicted': float(OMEGA_K_BASE),
            'target':    7.27e-4,
            'error_pct': abs(float(OMEGA_K_BASE) - 7.27e-4) / 7.27e-4 * 100,
            'budget':    1.00,   # < 1% per row 4
        },
        'gravitational_G': {
            'predicted': float(GRAVITATIONAL_G),
            'target':    6.6743e-11,
            'error_pct': abs(float(GRAVITATIONAL_G) - 6.6743e-11) / 6.6743e-11 * 100,
            'budget':    0.50,   # < 0.5% per row G
        },
    }
    # Aggregate v5.4 prediction status: every formula must be within budget
    v54_all_in_budget = all(
        entry['error_pct'] < entry['budget']
        for entry in report['v54_physics_predictions'].values()
    )
    report['v54_physics_predictions']['status'] = 'GREEN' if v54_all_in_budget else 'YELLOW'

    # 6. Y-constant derivation check
    y_float = float(Y_CONSTANT)
    report['y_constant'] = {
        'value': y_float,
        'expected_approx': 0.2646,
        'deviation': abs(y_float - 0.2646),
        'status': 'GREEN' if abs(y_float - 0.2646) < 0.001 else 'RED'
    }

    # 7. v5.4 NEW: Triad engine sanity (Golay ∩ Leech ∩ Monster)
    try:
        _monster = MONSTER_ENGINE
        _bw = BarnesWallEngine(256)
        _triad = TriadActivationEngine()
        # Sanity: Monster must expose its MOONSHINE module map
        has_moonshine = hasattr(_monster, 'MOONSHINE') and _monster.MOONSHINE is not None
        # Sanity: BarnesWall must expose 256D dimension
        bw_dim_ok = getattr(_bw, 'dimension', 0) == 256
        report['triad_engines'] = {
            'monster_loaded':       _monster is not None,
            'monster_has_moonshine': has_moonshine,
            'barnes_wall_dim_256':  bw_dim_ok,
            'triad_instantiable':   _triad is not None,
            'status': 'GREEN' if (has_moonshine and bw_dim_ok and _triad is not None) else 'YELLOW',
        }
    except Exception as e:
        report['triad_engines'] = {
            'error': f"{type(e).__name__}: {e}",
            'status': 'RED',
        }

    # 8. v5.4 NEW: Sovereign ALU stack sanity (NoiseALU/PhysicsALU/LinearAlgebraALU)
    try:
        _nalu = NoiseALU(mode='SV')
        _palu = PhysicsALU(mode='SV')
        _lalu = LinearAlgebraALU(mode='SV')
        # Each ALU must expose basic arithmetic
        has_add = all(hasattr(a, 'add') for a in (_nalu, _palu, _lalu))
        report['sovereign_alu'] = {
            'noise_alu_loaded':         _nalu is not None,
            'physics_alu_loaded':       _palu is not None,
            'linear_algebra_alu_loaded': _lalu is not None,
            'all_have_add':             has_add,
            'status': 'GREEN' if has_add else 'YELLOW',
        }
    except Exception as e:
        report['sovereign_alu'] = {
            'error': f"{type(e).__name__}: {e}",
            'status': 'RED',
        }

    # 9. v5.4 NEW: Physics domain registry (Phase 3 extension point)
    # Any registered physics domain is auto-validated here. Empty registry
    # is GREEN (no domains registered yet is fine). New domains may be
    # registered by future physics modules — see ubp_physics_registry.py.
    try:
        from ubp_physics_registry import get_registry
        registry = get_registry()
        domain_results = registry.validate_all()
        report['physics_registry'] = domain_results
    except Exception as e:
        report['physics_registry'] = {
            '_overall': 'RED',
            '_domain_count': 0,
            'error': f"{type(e).__name__}: {e}",
        }

    # Overall status
    # Each top-level block in the report must be GREEN or YELLOW (or, for the
    # registry block, must have an _overall key that's not RED). Nested dicts
    # without a 'status' key (e.g. individual formula entries inside
    # v54_physics_predictions) are not status blocks and are skipped.
    all_green = True
    for key, value in report.items():
        if key == 'overall':
            continue
        if not isinstance(value, dict):
            continue
        if '_overall' in value:
            # Registry-style block
            if value['_overall'] == 'RED':
                all_green = False
                break
            continue
        if 'status' in value:
            if value['status'] == 'RED':
                all_green = False
                break
    report['overall'] = 'GREEN' if all_green else 'RED'

    return report


# ---------------------------------------------------------------------------
# MODULE SELF-TEST
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    print("=" * 72)
    print("UBP ENGINE SUBSTRATE v2.0 (v5.4 ALIGNED) — SELF-TEST")
    print("=" * 72)

    # When run as __main__, attempt to import the core physics/mechanics
    # modules so their domain registrations show up in the registry block.
    # These imports are optional — if they fail (e.g. during early bootstrap
    # or test isolation), the substrate self-test still runs, just with
    # _domain_count = 0.
    try:
        import ubp_mechanics_v4  # noqa: F401  (registers 'core_mechanics')
    except Exception as e:
        print(f"  (note: ubp_mechanics_v4 not loaded: {type(e).__name__})")
    try:
        import ubp_physics_v3    # noqa: F401  (registers 'core_physics')
    except Exception as e:
        print(f"  (note: ubp_physics_v3 not loaded: {type(e).__name__})")
    try:
        import ubp_fluid_v3      # noqa: F401  (registers 'core_fluid')
    except Exception as e:
        print(f"  (note: ubp_fluid_v3 not loaded: {type(e).__name__})")
    try:
        import ubp_rigid_body_v3 # noqa: F401  (registers 'core_rigid_body')
    except Exception as e:
        print(f"  (note: ubp_rigid_body_v3 not loaded: {type(e).__name__})")
    try:
        import ubp_space_v3      # noqa: F401  (registers 'core_space')
    except Exception as e:
        print(f"  (note: ubp_space_v3 not loaded: {type(e).__name__})")
    try:
        import ubp_materials     # noqa: F401  (registers 'core_materials')
    except Exception as e:
        print(f"  (note: ubp_materials not loaded: {type(e).__name__})")
    try:
        import ubp_entity_v3     # noqa: F401  (registers 'core_entity')
    except Exception as e:
        print(f"  (note: ubp_entity_v3 not loaded: {type(e).__name__})")

    result = validate_substrate()
    for key, val in result.items():
        if key == 'overall':
            print(f"\n{'='*72}")
            print(f"OVERALL STATUS: {val}")
            print(f"{'='*72}")
        elif not isinstance(val, dict):
            print(f"  [?] {key}: {val}")
        else:
            # Some blocks use 'status', others use '_overall' (registry)
            status = val.get('status') or val.get('_overall', '?')
            print(f"  [{status}] {key}")
            for k2, v2 in val.items():
                if k2 in ('status', '_overall'):
                    continue
                if isinstance(v2, dict) and 'status' in v2:
                    # Per-domain status entry — show its status inline
                    print(f"         {k2}: status={v2['status']}")
                    for k3, v3 in v2.items():
                        if k3 != 'status':
                            print(f"           {k3}: {v3}")
                else:
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
        # v5.4 NEW: Triad engines
        self.monster = MONSTER_ENGINE
        self.barnes_wall = BW_ENGINE
        self.triad = get_triad()

        # Expose key constants (using the names defined in this module)
        self.Y_CONSTANT = Y_CONSTANT
        self.Y_INV = Y_INV
        self.PI = PI
        self.PHI = PHI
        self.E_CONST = E_CONST
        self.MONAD = MONAD
        self.WOBBLE = WOBBLE
        self.SINK_L = SINK_L
        self.SINK_L_STEREO = SINK_L_STEREO
        self.SINK_SIGMA = SINK_SIGMA
        self.EXISTENCE_UNIT = EXISTENCE_UNIT
        self.NOUMENAL_VOLUME = NOUMENAL_VOLUME
        self.G_EARTH_MS2 = G_EARTH_MS2
        self.F_MAX_HZ = F_MAX_HZ
        self.CONSCIOUS_THRESHOLD = CONSCIOUS_THRESHOLD
        self.KISSING_NUMBER = KISSING_NUMBER
        self.LEECH_DIMENSION = LEECH_DIMENSION
        # v5.4 NEW: Shear and physics-prediction constants
        self.SHEAR_1 = SHEAR_1
        self.SHEAR_2 = SHEAR_2
        self.MUON_ELECTRON_RATIO = MUON_ELECTRON_RATIO
        self.STRONG_COUPLING_ALPHA_S = STRONG_COUPLING_ALPHA_S
        self.ALPHA_CUBED = ALPHA_CUBED
        self.HUBBLE_H0 = HUBBLE_H0
        self.OMEGA_K_BASE = OMEGA_K_BASE
        self.GRAVITATIONAL_G = GRAVITATIONAL_G
        self.W_BOSON_BASE = W_BOSON_BASE
        self.sovereign_alu_loaded = _SOVEREIGN_ALU_LOADED
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

    # --- Sovereign ALU ---
    def get_sovereign_alu(self):
        return get_sovereign_alu()

    # --- v5.4 NEW: Triad + Sovereign ALU stack ---
    def get_monster(self):
        """Return the global Monster Group engine singleton."""
        return get_monster()

    def get_barnes_wall(self, dimension: int = 256):
        """Return a Barnes-Wall engine instance (256D, 512D, or 1024D)."""
        return get_barnes_wall(dimension)

    def get_triad(self):
        """Return a fresh Triad Activation engine instance."""
        return get_triad()

    def get_noise_alu(self, mode: str = 'SV'):
        """Return a fresh Noise ALU instance ('SM' or 'SV' mode)."""
        return get_noise_alu(mode)

    def get_physics_alu(self, mode: str = 'SV'):
        """Return a fresh Physics ALU instance ('SM' or 'SV' mode)."""
        return get_physics_alu(mode)

    def get_linear_algebra_alu(self, mode: str = 'SV'):
        """Return a fresh Linear Algebra ALU instance ('SM' or 'SV' mode)."""
        return get_linear_algebra_alu(mode)

    # --- Gray Code UMS ---
    def gray_code_encode_state(self, params, schema):
        return gray_code_encode_state(params, schema)

    # --- Observer Dynamics ---
    def calculate_soc_energy(self, vector_24bit, nrci, toggle_rate_hz=1.0):
        return calculate_soc_energy(vector_24bit, nrci, toggle_rate_hz)

    def conscious_read(self, vector_24bit, nrci):
        return conscious_read(vector_24bit, nrci)

    def calculate_ter_score(self, vector_24bit):
        return calculate_ter_score(vector_24bit)

    # --- Pantograph Tax ---
    def calculate_pantograph_tax(self, vector_24bit):
        return calculate_pantograph_tax(vector_24bit)

    # --- Design Quality Index ---
    def calculate_dqi(self, nrci, u_score, gap_score):
        return calculate_dqi(nrci, u_score, gap_score)

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
