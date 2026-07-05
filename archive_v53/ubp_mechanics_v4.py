"""
ubp_mechanics_v4.py — UBP Deterministic Mechanics Layer v4.0
=============================================================
Implements the four foundational UBP mechanics described in the README
and the UBP Knowledge Base:

  1. PHI-ORBIT TICK  (LAW_PHI_ORBIT_1953)
     One "game tick" = 1-bit circular shift + XOR with the Phi-primitive
     vector.  This replaces the float `dt` with a closed, deterministic
     1,953-step orbit through the Golay manifold.

  2. SYNTHESIS COLLISION EVENT  (6-Step Flow)
     When two entities occupy the same Leech Lattice neighbourhood
     (Hamming distance ≤ 8), their vectors are added in Z₂⁴ (XOR), the
     result is snapped to the nearest Golay codeword, and the Hamming
     gap determines "Impact Damage" to NRCI.

  3. NRCI HEALTH & 13D SINK  (LAW_13D_SINK_001, LAW_TOPOLOGICAL_BUFFER_001)
     Every entity carries a live NRCI score.  Each interaction costs a
     Symmetry Tax (Y ≈ 0.2647).  When NRCI drops below the Topological
     Buffer threshold (0.42 noise floor), the entity undergoes Entropic
     Dissolution — it "falls into the Deep Hole" and is flagged for
     removal by the physics engine.

  4. LEECH LATTICE SPATIAL ADDRESSING  (LAW_KISSING_EXPANSION_001)
     Entity positions are mapped to valid Leech Lattice addresses via
     BinaryLinearAlgebra.fold24_to3().  The 24-bit identity vector is
     folded into three 8-bit octets that define the entity's lattice
     cell.  Movement is expressed as a transition between adjacent cells.

  5. HYBRID STEREOSCOPY SIGMA  (LAW_HYBRID_STEREOSCOPY_002)
     The 29/24 Sigma ratio is exposed as a constant for use in particle
     mass calculations.

Author : UBP Digital Twin Physics Engine Project
Version: 4.0
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Import UBP core engines (singletons already initialised in core module)
# ---------------------------------------------------------------------------
from ubp_core_v5_3_merged import (
    GOLAY_ENGINE,
    LEECH_ENGINE,
    BinaryLinearAlgebra,
    UBPUltimateSubstrate,
)

# ---------------------------------------------------------------------------
# UBP CONSTANTS  (all Fraction — float-free)
# ---------------------------------------------------------------------------
_CONSTS = UBPUltimateSubstrate.get_v6_constants()  # v6.3.1: canonical constants incl. SINK_L
Y: Fraction = _CONSTS['Y']               # Ontological constant ≈ 0.26468
PI: Fraction = _CONSTS['PI']             # π (50-term series)
Y_INV: Fraction = _CONSTS['Y_INV']       # 1/Y ≈ 3.7783

# Sink leakage L = WOBBLE/13 = (PI*PHI*E mod 1) / 13  (LAW_13D_SINK_001 v6.3.1)
# Canonical derivation from get_v6_constants(); WOBBLE ≈ 0.8176, L ≈ 0.0629
SINK_L: Fraction = _CONSTS['SINK_L']

# Kissing number of the Leech Lattice
KISSING: int = 196_560

# Topological Buffer thresholds  (LAW_TOPOLOGICAL_BUFFER_001 + UBP-Py v2.1)
# NRCI_REFLEX_THRESHOLD = 6/10 = 0.60  — canonical UBP reflex prune line
#   (from ubppy.py: vm.reflex(threshold=Fraction(6, 10)))
# NRCI_NOISE_FLOOR = Y/Y_INV = Y² ≈ 0.0700 above dissolution
#   (Y² = The Shaving; entities within one Shaving of the floor are STRESSED)
# NRCI_DISSOLUTION_THRESHOLD = 2/5 = 0.40
#   (Golay minimum: 2 correctable errors out of 5 parity checks)
# NRCI_COHERENT_THRESHOLD = 11/12 ≈ 0.9167
#   (LAW_COMP_010: 11-bit friction at the Horizon; 11/12 = max stable ratio)
NCRI_REFLEX_THRESHOLD: float = 0.60     # Canonical UBP reflex prune line (Fraction(6,10))
NRCI_NOISE_FLOOR: float = 0.42          # Below this → dissolution imminent (0.40 + Y²)
NRCI_DISSOLUTION_THRESHOLD: float = 0.40 # Hard cull threshold (2/5 Golay minimum)
NRCI_AVG_TARGET: float = 0.60           # Healthy average = reflex threshold
NRCI_COHERENT_THRESHOLD: float = 11.0 / 12.0  # ≈11/12 ≈ 0.9167 (LAW_COMP_010 Horizon)

# Phi-Orbit vector  (LAW_PHI_ORBIT_1953 — from KB atlas)
PHI_VEC: List[int] = [
    1, 1, 0, 1, 1, 1, 1, 0,
    1, 1, 1, 1, 1, 0, 1, 0,
    1, 0, 0, 0, 1, 1, 0, 1,
]
PHI_ORBIT_PERIOD: int = 1_953           # Closed orbit length

# Hybrid Stereoscopy Sigma  (LAW_HYBRID_STEREOSCOPY_002)
SIGMA: Fraction = Fraction(29, 24)      # Baryonic Base / Spatial Core ratio

# Symmetry Tax scaling for NRCI (from UBPObject.get_nrci formula)
NRCI_TAX_SCALE: Fraction = Fraction(1, 10)

# Leech neighbourhood distance for collision detection
LEECH_COLLISION_RADIUS: int = 8         # Hamming distance ≤ 8 → collision zone

# Gap thresholds for Synthesis Event damage
GAP_DAMAGE_THRESHOLD: int = 3           # Gap > 3 → NRCI damage
GAP_DISSOLUTION_THRESHOLD: int = 7      # Gap > 7 → dissolution


# ===========================================================================
# 1.  PHI-ORBIT TICK ENGINE  (LAW_PHI_ORBIT_1953)
# ===========================================================================

class PhiOrbitEngine:
    """
    Implements the Phi-Orbit Tick as a deterministic geometric torque.

    One tick = one 1-bit circular shift of the entity's 24-bit vector,
    followed by an XOR with the Phi-primitive vector, then a Golay
    lattice snap.  This guarantees:
      - Exact reversibility after 1,953 ticks
      - No floating-point accumulation
      - NRCI drift that reflects the entity's "metabolic cost"
    """

    def __init__(self) -> None:
        self._golay = GOLAY_ENGINE
        self._leech = LEECH_ENGINE

    # ------------------------------------------------------------------
    def tick_vector(self, vector: List[int]) -> Tuple[List[int], float]:
        """
        Apply one Phi-Orbit tick to a 24-bit Golay vector.

        Returns:
            (new_vector, new_nrci_score)
        """
        # Step 1: 1-bit circular shift (right)
        shifted: List[int] = vector[-1:] + vector[:-1]

        # Step 2: XOR with Phi-primitive vector
        xored: List[int] = [a ^ b for a, b in zip(shifted, PHI_VEC)]

        # Step 3: Lattice snap — decode then re-encode to nearest codeword
        decoded, _success, _gap = self._golay.decode(xored)
        snapped: List[int] = self._golay.encode(decoded)

        # Step 4: Recompute NRCI
        nrci = self._compute_nrci(snapped)

        return snapped, nrci

    # ------------------------------------------------------------------
    def compute_nrci(self, vector: List[int]) -> float:
        """Public helper: compute NRCI score for any 24-bit vector."""
        return self._compute_nrci(vector)

    # ------------------------------------------------------------------
    def _compute_nrci(self, vector: List[int]) -> float:
        """
        NRCI = 10 / (10 + tax * (1 - L))

        v6.3.1 UPDATE: The Sink Leakage L is applied as a tax rebate.
        The 13D Sink 'absorbs' a fraction L of the tax on every tick,
        reflecting the substrate's ongoing garbage collection.
        Formula: NRCI = 10 / (10 + tax * (1 - L))
        """
        tax: Fraction = self._leech.calculate_symmetry_tax(vector)
        # Apply Sink Leakage rebate: effective_tax = tax * (1 - L)
        effective_tax: Fraction = tax * (Fraction(1, 1) - SINK_L)
        nrci: Fraction = Fraction(10, 1) / (Fraction(10, 1) + effective_tax)
        return float(nrci)

    # ------------------------------------------------------------------
    @staticmethod
    def fold_to_lattice_cell(vector: List[int]) -> Tuple[int, int, int]:
        """
        Map a 24-bit vector to a 3D Leech Lattice cell address.
        Uses BinaryLinearAlgebra.fold24_to3() — sums bits in three 8-bit
        octets to give (x, y, z) in range [0, 8].
        """
        folded = BinaryLinearAlgebra.fold24_to3(vector)
        return (folded[0], folded[1], folded[2])

    # ------------------------------------------------------------------
    @staticmethod
    def lattice_distance(v1: List[int], v2: List[int]) -> int:
        """Hamming distance between two 24-bit vectors."""
        return BinaryLinearAlgebra.hamming_distance(v1, v2)


# ===========================================================================
# 2.  SYNTHESIS COLLISION EVENT  (6-Step Flow)
# ===========================================================================

@dataclass
class SynthesisResult:
    """Result of a Synthesis Collision Event."""
    impact_gap: int                     # Hamming gap after snap
    nrci_damage_a: float                # NRCI reduction for entity A
    nrci_damage_b: float                # NRCI reduction for entity B
    combined_vector: List[int]          # Snapped impact vector
    dissolution_a: bool                 # Entity A should be dissolved
    dissolution_b: bool                 # Entity B should be dissolved
    event_type: str                     # 'ELASTIC', 'DAMAGE', 'DISSOLUTION'


class SynthesisCollisionEngine:
    """
    Implements the 6-Step Synthesis Collision Event (The Flow).

    When two entities enter the Leech Lattice collision zone
    (Hamming distance ≤ 8), their vectors are:
      1. Added in Z₂⁴ (XOR) — The Flow
      2. Decoded by the Golay engine
      3. Snapped to the nearest codeword — Lattice Snap
      4. Gap measured — Impact Damage
      5. NRCI reduced proportionally
      6. Dissolution checked against LAW_TOPOLOGICAL_BUFFER_001
    """

    def __init__(self) -> None:
        self._golay = GOLAY_ENGINE
        self._leech = LEECH_ENGINE
        self._phi = PhiOrbitEngine()

    # ------------------------------------------------------------------
    def synthesise(
        self,
        vector_a: List[int],
        vector_b: List[int],
        nrci_a: float,
        nrci_b: float,
    ) -> SynthesisResult:
        """
        Perform the full 6-step Synthesis Event between two entities.

        Args:
            vector_a: 24-bit Golay vector of entity A
            vector_b: 24-bit Golay vector of entity B
            nrci_a:   Current NRCI score of entity A
            nrci_b:   Current NRCI score of entity B

        Returns:
            SynthesisResult with all outcomes
        """
        # Step 1: The Flow — Additive Superposition (v6.3.1)
        # Convert {0,1} -> {-1,+1}, sum, then collapse back.
        # Replaces XOR 'Smash' which was a Z₂ simplification.
        # sum>0 -> 0 (Phenomenal), sum<0 -> 1 (Noumenal), sum=0 -> 0 (Void)
        b_a = [-1 if x == 0 else 1 for x in vector_a]
        b_b = [-1 if x == 0 else 1 for x in vector_b]
        raw_sum = [b_a[i] + b_b[i] for i in range(24)]
        combined_raw: List[int] = [0 if s >= 0 else 1 for s in raw_sum]

        # Step 2 & 3: Decode + Lattice Snap
        decoded, _success, gap = self._golay.decode(combined_raw)
        snapped: List[int] = self._golay.encode(decoded)

        # Step 4: Measure Impact Damage via Gap Score
        # Gap 0-3: elastic (no damage)
        # Gap 4-7: damage proportional to gap
        # Gap 8+:  dissolution
        damage_a = 0.0
        damage_b = 0.0
        dissolution_a = False
        dissolution_b = False
        event_type = 'ELASTIC'

        if gap > GAP_DAMAGE_THRESHOLD:
            # Damage = gap * Y (Symmetry Tax per gap unit)
            raw_damage = float(gap) * float(Y)
            # Scale by relative NRCI — weaker entity takes more damage
            total_nrci = nrci_a + nrci_b if (nrci_a + nrci_b) > 0 else 1.0
            damage_a = raw_damage * (nrci_b / total_nrci)
            damage_b = raw_damage * (nrci_a / total_nrci)
            event_type = 'DAMAGE'

        if gap > GAP_DISSOLUTION_THRESHOLD:
            # Check if either entity falls below dissolution threshold
            if (nrci_a - damage_a) < NRCI_DISSOLUTION_THRESHOLD:
                dissolution_a = True
            if (nrci_b - damage_b) < NRCI_DISSOLUTION_THRESHOLD:
                dissolution_b = True
            if dissolution_a or dissolution_b:
                event_type = 'DISSOLUTION'

        return SynthesisResult(
            impact_gap=gap,
            nrci_damage_a=damage_a,
            nrci_damage_b=damage_b,
            combined_vector=snapped,
            dissolution_a=dissolution_a,
            dissolution_b=dissolution_b,
            event_type=event_type,
        )

    # ------------------------------------------------------------------
    def in_collision_zone(
        self, vector_a: List[int], vector_b: List[int]
    ) -> bool:
        """
        Check if two entities are in the Leech Lattice collision zone
        (Hamming distance ≤ LEECH_COLLISION_RADIUS).
        """
        d = BinaryLinearAlgebra.hamming_distance(vector_a, vector_b)
        return d <= LEECH_COLLISION_RADIUS


# ===========================================================================
# 3.  NRCI HEALTH SYSTEM & 13D SINK  (LAW_13D_SINK_001)
# ===========================================================================

@dataclass
class NCRIState:
    """Live NRCI health state for a simulation entity."""
    vector: List[int]
    nrci: float
    symmetry_tax: float
    tick_phase: int = 0                 # Position in 1,953-step Phi orbit
    dissolution_pending: bool = False
    total_ticks: int = 0
    collision_count: int = 0
    total_damage_received: float = 0.0

    # Metabolic rendering hints (for frontend)
    @property
    def opacity(self) -> float:
        """Opacity 0.2–1.0 based on NRCI (metabolic rendering)."""
        if self.nrci >= NRCI_COHERENT_THRESHOLD:
            return 1.0
        elif self.nrci >= NRCI_AVG_TARGET:
            return 0.7 + 0.3 * (self.nrci - NRCI_AVG_TARGET) / (NRCI_COHERENT_THRESHOLD - NRCI_AVG_TARGET)
        elif self.nrci >= NRCI_NOISE_FLOOR:
            return 0.4 + 0.3 * (self.nrci - NRCI_NOISE_FLOOR) / (NRCI_AVG_TARGET - NRCI_NOISE_FLOOR)
        else:
            return max(0.2, self.nrci / NRCI_NOISE_FLOOR * 0.4)

    @property
    def health_status(self) -> str:
        """Human-readable health status."""
        if self.dissolution_pending:
            return 'DISSOLVING'
        elif self.nrci >= NRCI_COHERENT_THRESHOLD:
            return 'COHERENT'
        elif self.nrci >= NRCI_AVG_TARGET:
            return 'STABLE'
        elif self.nrci >= NRCI_NOISE_FLOOR:
            return 'STRESSED'
        else:
            return 'CRITICAL'

    @property
    def tilt_degrees(self) -> float:
        """
        Tilt angle — deviation from the North (0°) alignment.
        High NRCI = near 0° (pointing North, coherent).
        Low NRCI = high tilt (chaotic).
        """
        return (1.0 - self.nrci) * 90.0

    def to_dict(self) -> Dict:
        return {
            'nrci': round(self.nrci, 6),
            'symmetry_tax': round(self.symmetry_tax, 6),
            'tick_phase': self.tick_phase,
            'health_status': self.health_status,
            'opacity': round(self.opacity, 3),
            'tilt_degrees': round(self.tilt_degrees, 2),
            'dissolution_pending': self.dissolution_pending,
            'total_ticks': self.total_ticks,
            'collision_count': self.collision_count,
            'total_damage_received': round(self.total_damage_received, 6),
            'vector': self.vector,
        }


class SinkEngine:
    """
    Implements the 13D Sink garbage collection (LAW_13D_SINK_001).

    Every tick, entities pay a Symmetry Tax proportional to Y.
    When NRCI drops below the Topological Buffer noise floor (0.42),
    the entity begins leaking bits into the 13th dimension.
    At NRCI < 0.40, the entity is dissolved (vector → VOID).
    """

    VOID_VECTOR: List[int] = [0] * 24   # The Deep Hole

    def __init__(self) -> None:
        self._leech = LEECH_ENGINE
        self._phi = PhiOrbitEngine()

    # ------------------------------------------------------------------
    def apply_tick(self, state: NCRIState) -> NCRIState:
        """
        Apply one tick of Phi-Orbit + Symmetry Tax to an NRCI state.
        Returns the updated state (mutates in place and returns self).
        """
        # Apply Phi-Orbit tick to vector
        new_vector, new_nrci = self._phi.tick_vector(state.vector)

        # Recompute symmetry tax
        tax = float(self._leech.calculate_symmetry_tax(new_vector))

        # Update state
        state.vector = new_vector
        state.nrci = new_nrci
        state.symmetry_tax = tax
        state.tick_phase = (state.tick_phase + 1) % PHI_ORBIT_PERIOD
        state.total_ticks += 1

        # Check dissolution
        if state.nrci < NRCI_DISSOLUTION_THRESHOLD:
            state.dissolution_pending = True

        return state

    # ------------------------------------------------------------------
    def apply_damage(self, state: NCRIState, damage: float) -> NCRIState:
        """
        Apply collision damage to an NRCI state.
        Damage reduces NRCI directly; if below threshold, flag dissolution.
        """
        state.nrci = max(0.0, state.nrci - damage)
        state.total_damage_received += damage
        state.collision_count += 1

        if state.nrci < NRCI_DISSOLUTION_THRESHOLD:
            state.dissolution_pending = True

        return state

    # ------------------------------------------------------------------
    def is_dissolved(self, state: NCRIState) -> bool:
        """Check if entity has fallen into the Deep Hole."""
        return state.dissolution_pending and state.nrci < NRCI_DISSOLUTION_THRESHOLD

    # ------------------------------------------------------------------
    @staticmethod
    def make_state(vector: List[int]) -> NCRIState:
        """
        Create an NCRIState from a 24-bit vector.

        v6.3.1 UPDATE: NRCI uses Sink Leakage rebate:
            NRCI = 10 / (10 + tax * (1 - L))
        """
        base_tax = LEECH_ENGINE.calculate_symmetry_tax(vector)
        effective_tax = base_tax * (Fraction(1, 1) - SINK_L)
        nrci_frac = Fraction(10, 1) / (Fraction(10, 1) + effective_tax)
        return NCRIState(
            vector=list(vector),
            nrci=float(nrci_frac),
            symmetry_tax=float(base_tax),
        )


# ===========================================================================
# 4.  LEECH LATTICE SPATIAL ADDRESSING  (LAW_KISSING_EXPANSION_001)
# ===========================================================================

@dataclass
class LeechAddress:
    """
    A Leech Lattice spatial address for a simulation entity.

    v6.3.1 UPDATE: fold24_to3 now returns 3 bits (0 or 1) via recursive XOR,
    not 3 octet-sums in [0,8]. The address is therefore a 3-bit polarity
    vector representing the entity's fundamental spatial orientation.

    The 8 possible addresses (000 to 111) correspond to the 8 octants of
    the Leech Lattice's 3D projection. This is the correct UBP spatial
    addressing scheme: entities in the same octant are geometrically aligned.

    Physical position is still tracked by the physics engine (Decimal coords).
    The Leech address is the topological address, not the metric position.
    """
    cell_x: int   # 0 or 1 (polarity of X axis after fold)
    cell_y: int   # 0 or 1 (polarity of Y axis after fold)
    cell_z: int   # 0 or 1 (polarity of Z axis after fold)
    cell_size: float = 1.0   # Physical metres per lattice cell (for rendering)

    @property
    def octant(self) -> int:
        """Octant index 0-7 from the 3-bit address."""
        return (self.cell_x << 2) | (self.cell_y << 1) | self.cell_z

    @property
    def physical_x(self) -> float:
        return self.cell_x * self.cell_size

    @property
    def physical_y(self) -> float:
        return self.cell_y * self.cell_size

    @property
    def physical_z(self) -> float:
        return self.cell_z * self.cell_size

    def to_dict(self) -> Dict:
        return {
            'cell': (self.cell_x, self.cell_y, self.cell_z),
            'octant': self.octant,
            'physical': (
                round(self.physical_x, 4),
                round(self.physical_y, 4),
                round(self.physical_z, 4),
            ),
        }

    @staticmethod
    def from_vector(vector: List[int], cell_size: float = 1.0) -> 'LeechAddress':
        """Derive a Leech Lattice topological address from a 24-bit vector."""
        folded = BinaryLinearAlgebra.fold24_to3(vector)
        return LeechAddress(
            cell_x=folded[0],
            cell_y=folded[1],
            cell_z=folded[2],
            cell_size=cell_size,
        )

    def hamming_distance_to(self, other: 'LeechAddress') -> int:
        """
        Hamming distance between two 3-bit Leech addresses (0, 1, 2, or 3).
        v6.3.1: Changed from Manhattan to Hamming since cells are now bits.
        """
        return (self.cell_x ^ other.cell_x) + \
               (self.cell_y ^ other.cell_y) + \
               (self.cell_z ^ other.cell_z)


class LeechAddressingEngine:
    """
    Maps simulation entities to valid Leech Lattice addresses and
    tracks adjacency for collision zone detection.
    """

    def __init__(self, cell_size: float = 1.0) -> None:
        self.cell_size = cell_size
        self._phi = PhiOrbitEngine()

    # ------------------------------------------------------------------
    def get_address(self, vector: List[int]) -> LeechAddress:
        """Get the Leech Lattice address for a 24-bit vector."""
        return LeechAddress.from_vector(vector, self.cell_size)

    # ------------------------------------------------------------------
    def are_adjacent(
        self, vector_a: List[int], vector_b: List[int], radius: int = 1
    ) -> bool:
        """
        Check if two entities are in adjacent Leech Lattice cells
        (Manhattan distance ≤ radius).
        """
        addr_a = self.get_address(vector_a)
        addr_b = self.get_address(vector_b)
        return addr_a.hamming_distance_to(addr_b) <= radius

    # ------------------------------------------------------------------
    def get_kissing_neighbours(
        self, vector: List[int]
    ) -> List[Tuple[int, int, int]]:
        """
        Return the 26 adjacent lattice cells (3D Moore neighbourhood)
        for the given vector's address.
        """
        addr = self.get_address(vector)
        neighbours = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    if dx == 0 and dy == 0 and dz == 0:
                        continue
                    neighbours.append((
                        addr.cell_x + dx,
                        addr.cell_y + dy,
                        addr.cell_z + dz,
                    ))
        return neighbours


# ===========================================================================
# 5.  UBP MECHANICS COORDINATOR  (top-level interface for physics engine)
# ===========================================================================

class UBPMechanicsV4:
    """
    Top-level coordinator for all UBP v4.0 deterministic mechanics.

    This is the single object imported by ubp_entity_v3.py and
    ubp_physics_v3.py to access all UBP mechanics without duplicating
    engine instances.

    Usage:
        from ubp_mechanics_v4 import UBP_MECHANICS

        # Per-tick update for an entity
        new_vec, new_nrci = UBP_MECHANICS.tick(entity.golay_vector)

        # Collision between two entities
        result = UBP_MECHANICS.collide(vec_a, vec_b, nrci_a, nrci_b)

        # Get Leech address for rendering
        addr = UBP_MECHANICS.get_address(entity.golay_vector)
    """

    def __init__(self) -> None:
        self.phi_orbit = PhiOrbitEngine()
        self.synthesis = SynthesisCollisionEngine()
        self.sink = SinkEngine()
        self.addressing = LeechAddressingEngine()

        # Expose key constants
        self.Y = Y
        self.PI = PI
        self.Y_INV = Y_INV
        self.SINK_L = SINK_L
        self.KISSING = KISSING
        self.SIGMA = SIGMA
        self.PHI_VEC = PHI_VEC
        self.PHI_ORBIT_PERIOD = PHI_ORBIT_PERIOD
        self.NRCI_NOISE_FLOOR = NRCI_NOISE_FLOOR
        self.NRCI_DISSOLUTION_THRESHOLD = NRCI_DISSOLUTION_THRESHOLD

    # ------------------------------------------------------------------
    # Phi-Orbit Tick
    # ------------------------------------------------------------------
    def tick(self, vector: List[int]) -> Tuple[List[int], float]:
        """Apply one Phi-Orbit tick. Returns (new_vector, new_nrci)."""
        return self.phi_orbit.tick_vector(vector)

    def compute_nrci(self, vector: List[int]) -> float:
        """Compute NRCI for a 24-bit vector."""
        return self.phi_orbit.compute_nrci(vector)

    def fold_to_cell(self, vector: List[int]) -> Tuple[int, int, int]:
        """Fold a 24-bit vector to a 3D lattice cell (x, y, z)."""
        return PhiOrbitEngine.fold_to_lattice_cell(vector)

    # ------------------------------------------------------------------
    # Synthesis Collision
    # ------------------------------------------------------------------
    def collide(
        self,
        vector_a: List[int],
        vector_b: List[int],
        nrci_a: float,
        nrci_b: float,
    ) -> SynthesisResult:
        """Perform a Synthesis Collision Event between two entities."""
        return self.synthesis.synthesise(vector_a, vector_b, nrci_a, nrci_b)

    def in_collision_zone(
        self, vector_a: List[int], vector_b: List[int]
    ) -> bool:
        """Check if two vectors are in the Leech collision zone."""
        return self.synthesis.in_collision_zone(vector_a, vector_b)

    # ------------------------------------------------------------------
    # NRCI State Management
    # ------------------------------------------------------------------
    def make_nrci_state(self, vector: List[int]) -> NCRIState:
        """Create an NCRIState from a 24-bit vector."""
        return SinkEngine.make_state(vector)

    def apply_sink_tick(self, state: NCRIState) -> NCRIState:
        """Apply one 13D Sink tick to an NRCI state."""
        return self.sink.apply_tick(state)

    def apply_damage(self, state: NCRIState, damage: float) -> NCRIState:
        """Apply collision damage to an NRCI state."""
        return self.sink.apply_damage(state, damage)

    def is_dissolved(self, state: NCRIState) -> bool:
        """Check if an entity should be dissolved."""
        return self.sink.is_dissolved(state)

    # ------------------------------------------------------------------
    # Leech Lattice Addressing
    # ------------------------------------------------------------------
    def get_address(self, vector: List[int]) -> LeechAddress:
        """Get the Leech Lattice address for a 24-bit vector."""
        return self.addressing.get_address(vector)

    def are_adjacent(
        self, vector_a: List[int], vector_b: List[int]
    ) -> bool:
        """Check if two entities are in adjacent lattice cells."""
        return self.addressing.are_adjacent(vector_a, vector_b)

    # ------------------------------------------------------------------
    # Hybrid Stereoscopy
    # ------------------------------------------------------------------
    def sigma_mass(self, base_mass: float) -> float:
        """
        Apply the Hybrid Stereoscopy Sigma correction to a mass value.
        Sigma = 29/24 — the Baryonic Base / Spatial Core ratio.
        """
        return base_mass * float(self.SIGMA)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    def vector_fingerprint(self, vector: List[int]) -> str:
        """SHA-256 fingerprint of a 24-bit vector."""
        data = ''.join(str(b) for b in vector).encode()
        return hashlib.sha256(data).hexdigest()[:16]

    def full_entity_report(
        self,
        label: str,
        vector: List[int],
        nrci: float,
        position: Tuple[float, float, float],
    ) -> Dict:
        """
        Generate a full UBP mechanics report for an entity.
        Used by the frontend data panel and the server /state endpoint.
        """
        addr = self.get_address(vector)
        tax = float(LEECH_ENGINE.calculate_symmetry_tax(vector))
        cell = self.fold_to_cell(vector)
        return {
            'label': label,
            'vector': vector,
            'fingerprint': self.vector_fingerprint(vector),
            'nrci': round(nrci, 6),
            'symmetry_tax': round(tax, 6),
            'health_status': (
                'COHERENT' if nrci >= NRCI_COHERENT_THRESHOLD else
                'STABLE' if nrci >= NRCI_AVG_TARGET else
                'STRESSED' if nrci >= NRCI_NOISE_FLOOR else
                'CRITICAL'
            ),
            'opacity': max(0.2, min(1.0, nrci)),
            'tilt_degrees': round((1.0 - nrci) * 90.0, 2),
            'leech_address': addr.to_dict(),
            'lattice_cell': cell,
            'physical_position': position,
            'sigma_correction': round(float(SIGMA), 6),
        }


# ---------------------------------------------------------------------------
# MODULE-LEVEL SINGLETON  (import this in other modules)
# ---------------------------------------------------------------------------
UBP_MECHANICS = UBPMechanicsV4()


# ---------------------------------------------------------------------------
# MODULE SELF-TEST
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    import json

    print("=" * 72)
    print("UBP MECHANICS v4.0 — SELF-TEST")
    print("=" * 72)

    # --- Test 1: Phi-Orbit Tick ---
    print("\n[1] PHI-ORBIT TICK (LAW_PHI_ORBIT_1953)")
    player_vec = [0,0,1,0,0,1,1,1,0,0,1,0,1,0,1,0,1,0,1,1,1,1,0,0]
    wall_vec   = [1,1,0,1,1,0,1,0,1,1,1,0,1,1,1,1,1,1,0,1,0,0,0,1]

    history = []
    pv, wv = list(player_vec), list(wall_vec)
    for i in range(5):
        pv, pnrci = UBP_MECHANICS.tick(pv)
        wv, wnrci = UBP_MECHANICS.tick(wv)
        history.append({'Player': round(pnrci, 16), 'Wall': round(wnrci, 16)})
        print(f"  Tick {i+1}: Player NRCI={pnrci:.10f}  Wall NRCI={wnrci:.10f}")

    expected = [
        {'Player': 0.6813796908424689, 'Wall': 0.6813796908424689},
        {'Player': 0.6813796908424689, 'Wall': 0.6159605143398686},
        {'Player': 0.6813796908424689, 'Wall': 0.7623459965437248},
        {'Player': 0.7623459965437248, 'Wall': 0.7623459965437248},
        {'Player': 0.6813796908424689, 'Wall': 0.6159605143398686},
    ]
    match = all(
        abs(history[i]['Player'] - expected[i]['Player']) < 1e-10 and
        abs(history[i]['Wall'] - expected[i]['Wall']) < 1e-10
        for i in range(5)
    )
    print(f"  README engine_test.json match: {'PASS' if match else 'FAIL'}")

    # --- Test 2: Synthesis Collision ---
    print("\n[2] SYNTHESIS COLLISION EVENT (6-Step Flow)")
    result = UBP_MECHANICS.collide(player_vec, wall_vec, 0.68, 0.68)
    print(f"  Impact Gap: {result.impact_gap}")
    print(f"  Event Type: {result.event_type}")
    print(f"  NRCI Damage A: {result.nrci_damage_a:.6f}")
    print(f"  NRCI Damage B: {result.nrci_damage_b:.6f}")
    print(f"  Dissolution A: {result.dissolution_a}  B: {result.dissolution_b}")

    # --- Test 3: NRCI State & 13D Sink ---
    print("\n[3] NRCI STATE & 13D SINK (LAW_13D_SINK_001)")
    state = UBP_MECHANICS.make_nrci_state(player_vec)
    print(f"  Initial NRCI: {state.nrci:.6f}  Status: {state.health_status}")
    for _ in range(10):
        state = UBP_MECHANICS.apply_sink_tick(state)
    print(f"  After 10 ticks: NRCI={state.nrci:.6f}  Phase={state.tick_phase}")
    # Apply heavy damage to test dissolution
    state_damaged = UBP_MECHANICS.make_nrci_state(player_vec)
    state_damaged = UBP_MECHANICS.apply_damage(state_damaged, 0.5)
    print(f"  After 0.5 damage: NRCI={state_damaged.nrci:.6f}  Dissolving={state_damaged.dissolution_pending}")

    # --- Test 4: Leech Lattice Addressing ---
    print("\n[4] LEECH LATTICE SPATIAL ADDRESSING")
    addr = UBP_MECHANICS.get_address(player_vec)
    print(f"  Player lattice cell: {addr.to_dict()}")
    cell = UBP_MECHANICS.fold_to_cell(player_vec)
    print(f"  fold24_to3 cell: {cell}")
    adjacent = UBP_MECHANICS.are_adjacent(player_vec, wall_vec)
    print(f"  Player/Wall adjacent: {adjacent}")

    # --- Test 5: Full Entity Report ---
    print("\n[5] FULL ENTITY REPORT")
    report = UBP_MECHANICS.full_entity_report(
        'TestBlock', player_vec, 0.68, (3.0, 1.0, 5.0)
    )
    print(f"  {json.dumps(report, indent=4)}")

    # --- Test 6: Sigma Mass Correction ---
    print("\n[6] HYBRID STEREOSCOPY SIGMA (LAW_HYBRID_STEREOSCOPY_002)")
    base = 938.272  # Proton mass MeV/c²
    corrected = UBP_MECHANICS.sigma_mass(base)
    print(f"  Sigma = {float(SIGMA):.6f} (29/24)")
    print(f"  Proton base mass: {base} MeV/c²")
    print(f"  Sigma-corrected:  {corrected:.4f} MeV/c²")

    print("\n" + "=" * 72)
    print("ALL TESTS COMPLETE")
    print("=" * 72)
