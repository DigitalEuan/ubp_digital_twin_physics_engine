"""
UBP TGIC ENGINE v6.2 (Relational Master Edition)
================================================
The definitive TGIC implementation. 
Integrates all 9 internal interactions + Cross-Node Relational Gravity.

STANDARDS:
- Internal Harmony: 9 Pairwise Interactions (X, Y, Z blocks)
- External Harmony: Relational Pull (Hamming-weighted attraction)
- Hardware: Leech Tax + Coherence Pressure (d > 3 penalty)

Author: E R A Craig & UBP Research Cortex v4.2.7
Date: 03 March 2026
"""
import json
import hashlib
from fractions import Fraction
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Any

try:
    from ubp_core_v5_3_merged import GOLAY_ENGINE, LEECH_ENGINE, BinaryLinearAlgebra, SUBSTRATE
    CORE_AVAILABLE = True
    CONST = SUBSTRATE.get_constants(50)
except ImportError:
    CORE_AVAILABLE = False
    CONST = {'Y': Fraction(2646, 10000), 'Y_INV': Fraction(10000, 2646)}

class TGICConstraintSystem:
    """
    [THE GENESIS LOGIC]
    Enforces the fundamental 3-6-9 UBP laws on 24-bit manifolds.
    """
    def __init__(self, y_const):
        self.y_const = y_const

    def check_3_axis_orthogonality(self, v: List[int]) -> Fraction:
        """[THE 3] Ideal: Hamming Distance of 4 between 8-bit blocks."""
        x, y, z = v[0:8], v[8:16], v[16:24]
        d_xy = abs(4 - sum(1 for i in range(8) if x[i] != y[i]))
        d_xz = abs(4 - sum(1 for i in range(8) if x[i] != z[i]))
        d_yz = abs(4 - sum(1 for i in range(8) if y[i] != z[i]))
        total_deviation = Fraction(d_xy + d_xz + d_yz, 1)
        return Fraction(1, 1) / (Fraction(1, 1) + total_deviation * self.y_const)

    def check_6_face_coherence(self, v: List[int], engine) -> Fraction:
        """[THE 6] Measures the stability of the 6 interaction faces."""
        v_xy = engine.rune_resonance_xy(v)
        v_xz = engine.rune_entangle_xz(v)
        v_yz = engine.rune_expand_yz(v)
        tax_sum = LEECH_ENGINE.calculate_symmetry_tax(v_xy) + \
                  LEECH_ENGINE.calculate_symmetry_tax(v_xz) + \
                  LEECH_ENGINE.calculate_symmetry_tax(v_yz)
        return Fraction(10, 1) / (Fraction(10, 1) + (tax_sum / 3))

    def check_9_neighbor_limit(self, target_v: List[int], manifold_vectors: List[List[int]]) -> Fraction:
        """[THE 9] Prevents 'Overheating' if neighbors > 9."""
        neighbors = sum(1 for v in manifold_vectors if BinaryLinearAlgebra.hamming_distance(target_v, v) <= 8)
        return Fraction(max(0, neighbors - 9), 1) * self.y_const

@dataclass(frozen=True)
class OffBit:
    v: Tuple[int, ...]
    phi: int
    def with_updates(self, new_v=None, delta_phi=0):
        return OffBit(v=tuple(new_v) if new_v is not None else self.v, phi=(self.phi + delta_phi) % 256)

class TGICInteractionEngine:
    """
    UBP TGIC Interaction Engine v6.3 (RuneCube Integrated)
    ----------------------------------------------------
    Governs internal bit-flows and axis-aware face operations.
    """
    def __init__(self):
        self.y_const = CONST['Y']
        self.interaction_weight = Fraction(5, 1)
        self.constraints = TGICConstraintSystem(self.y_const)
 

    def calculate_total_stability(self, v: List[int], manifold_vectors: List[List[int]] = None) -> Fraction:
        """The Master 3-6-9 Audit."""
        ortho = self.constraints.check_3_axis_orthogonality(v)
        faces = self.constraints.check_6_face_coherence(v, self)
        
        # Base Leech Stability
        tax = LEECH_ENGINE.calculate_symmetry_tax(v)
        base_nrci = Fraction(10, 1) / (Fraction(10, 1) + tax)
        
        # Neighborhood Pressure
        pressure = self.constraints.check_9_neighbor_limit(v, manifold_vectors) if manifold_vectors else Fraction(0)
            
        return (ortho + faces + base_nrci) / 3 - pressure


    # --- 1. LEGACY POINT INTERACTIONS ---
    def resonance_op(self, b_i, b_j):
        return Fraction(0) if b_i == b_j else self.y_const / 20

    def entanglement_op(self, b_i, b_j):
        return Fraction(-1, 200) if b_i == 1 and b_j == 1 else Fraction(0)

    def superposition_op(self, b_i, b_j):
        states = [Fraction(b_i), Fraction(b_j), Fraction((b_i + b_j) % 2)]
        return sum(s * Fraction(1, 3) for s in states)

    def mixed_op(self, x, y, z, mode):
        if mode == 'xyz': return Fraction(min(x, y)) * Fraction(z)
        if mode == 'yzx': return Fraction(abs(y - z)) * Fraction(x)
        if mode == 'zxy': return Fraction(max(z, x)) * Fraction(y)
        return Fraction(0)

    # --- 2. HARDENED RUNECUBE FACE OPERATIONS ---
    def rune_resonance_xy(self, v: List[int]) -> List[int]:
        """AND logic: X and Y axes converge."""
        x, y, z = v[0:8], v[8:16], v[16:24]
        new_x = [a & b for a, b in zip(x, y)]
        return self._snap(new_x + new_x + z)

    def rune_entangle_xz(self, v: List[int]) -> List[int]:
        """XOR logic: X and Z axes differentiate."""
        x, y, z = v[0:8], v[8:16], v[16:24]
        new_z = [a ^ b for a, b in zip(x, z)]
        return self._snap(x + y + new_z)

    def rune_expand_yz(self, v: List[int]) -> List[int]:
        """OR logic: Y and Z axes unify."""
        x, y, z = v[0:8], v[8:16], v[16:24]
        new_y = [a | b for a, b in zip(y, z)]
        return self._snap(x + new_y + z)

    def _snap(self, v: List[int]) -> List[int]:
        """Internal Lattice Snap to maintain immortality."""
        if not CORE_AVAILABLE: return v
        decoded, _, _ = GOLAY_ENGINE.decode(v)
        return GOLAY_ENGINE.encode(decoded)

    def calculate_internal_cost(self, v):
        """Sum of all 9 interactions within a single 24-bit vector."""
        total = Fraction(0)
        for i in range(8):
            x, y, z = v[i], v[i+8], v[i+16]
            total += self.resonance_op(x, y)
            total += self.resonance_op(y, x)
            total += self.entanglement_op(x, z)
            total += self.entanglement_op(z, x)
            total += self.superposition_op(y, z)
            total += self.superposition_op(z, y)
            total += self.mixed_op(x, y, z, 'xyz')
            total += self.mixed_op(y, z, x, 'yzx')
            total += self.mixed_op(z, x, y, 'zxy')
        return total * self.interaction_weight

class TGICExactEngine:
    def __init__(self):
        self.interactions = TGICInteractionEngine()
        self.golay = GOLAY_ENGINE if CORE_AVAILABLE else None
        self.leech = LEECH_ENGINE if CORE_AVAILABLE else None
        self.y_const = CONST['Y']

    def get_relational_pull(self, coord_target, v_target, S):
        pull = Fraction(0)
        for coord, off in S.items():
            if coord == coord_target: continue
            dist = BinaryLinearAlgebra.hamming_distance(list(v_target), list(off.v))
            pull += Fraction(1, (dist + 1))
        return pull * (self.y_const / 2)

    def get_node_energy(self, coord, v, S):
        # 1. Internal Interaction Cost (Point-to-Point)
        i_cost = self.interactions.calculate_internal_cost(v)
        
        # 2. NEW: 3-6-9 Structural Stability (The Genesis Factor)
        # We treat low stability as high energy (instability)
        manifold_vecs = [list(off.v) for off in S.values()]
        stability_score = self.interactions.calculate_total_stability(v, manifold_vecs)
        structural_energy = (Fraction(1, 1) - stability_score) * 10 
        
        # 3. Relational Pull (External Gravity)
        pull = self.get_relational_pull(coord, v, S)
        
        # Total Energy = Internal + Structural - External Pull
        return i_cost + structural_energy - pull


    def step(self, S):
        if not S: return S, {"status": "empty"}
        state_repr = str(sorted(S.items(), key=lambda x: x[0]))
        digest = hashlib.sha256(state_repr.encode()).digest()
        coord = list(S.keys())[digest[0] % len(S)]
        off_old = S[coord]
        flip_idx = digest[1] % 24
        new_v = list(off_old.v)
        new_v[flip_idx] ^= 1
        energy_old = self.get_node_energy(coord, list(off_old.v), S)
        energy_new = self.get_node_energy(coord, new_v, S)
        if energy_new < (energy_old + self.y_const / 4):
            S_new = S.copy()
            S_new[coord] = off_old.with_updates(new_v=new_v)
            dist = 0
            if self.golay: _, _, dist = self.golay.decode(new_v)
            return S_new, {"status": "accepted", "delta": float(energy_new - energy_old), "dist": dist}
        return S, {"status": "rejected"}

    def get_total_energy(self, S):
        return sum(self.get_node_energy(c, list(off.v), S) for c, off in S.items())
