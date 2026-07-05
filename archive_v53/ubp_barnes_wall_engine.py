"""
================================================================================
UBP BARNES-WALL ENGINE v1.6 (ACTIVE PROGRAM EDITION)
================================================================================
The definitive high-dimensional extension for the UBP framework.
Implements the "Moire Interference" theory where the macro-state is a 
deterministic program driven by the seed's internal syndrome.

CORE MECHANICS:
1. BASE CASE: 32-bit block (24-bit Golay Codeword + 8-bit Zero Padding).
2. THE PROGRAM: v-component derived from the 12-bit Golay Syndrome.
3. RECURSION: | u | u + v | construction (Recursive Interference).
4. DECODER: Successive Cancellation (Recursive Parity Cleaning).
5. METRICS: 256D Symmetry Tax and Macro-NRCI (Hyperbolic).

Author: E R A Craig & UBP Research Cortex v4.2.7
Date: 22 March 2026
"""

import hashlib
from fractions import Fraction
from typing import List, Tuple, Dict, Union, Any
from ubp_core_v5_3_merged import GOLAY_ENGINE, SUBSTRATE, BinaryLinearAlgebra

class BarnesWallEngine:
    def __init__(self, dimension: int = 256):
        """Initializes the Macro-Engine (Power of 2, min 32)."""
        if (dimension & (dimension - 1)) != 0 or dimension < 32:
            raise ValueError("Dimension must be a power of 2 and >= 32.")
            
        self.dimension = dimension
        self.golay = GOLAY_ENGINE
        self.Y = SUBSTRATE.get_constants(50)['Y']
        # The 256D Macro-Anchor Constant (Index 2)
        self.MACRO_ANCHOR_NRCI = Fraction(323214, 1000000) 

    def _get_syndrome_v(self, bits: List[int]) -> List[int]:
        """
        [THE PROGRAM]
        Derives the interference component (v) from the Golay Syndrome.
        This represents the 'Geometric Frustration' of the 24-bit seed.
        """
        # Calculate the 12-bit syndrome via Parity Check Matrix H
        syndrome = BinaryLinearAlgebra.matrix_vector_multiply(self.golay.H, bits[:24])
        # Project syndrome back to 24 bits to create the 'Interference Wave'
        return self.golay.encode(syndrome)

    def _fingerprint_to_bits(self, fingerprint: str) -> List[int]:
        """Converts a SHA-256 hex string into a 24-bit seed vector."""
        h_bytes = bytes.fromhex(fingerprint)
        combined = (h_bytes[0] << 4) | (h_bytes[1] >> 4)
        msg = [(combined >> i) & 1 for i in range(11, -1, -1)]
        return self.golay.encode(msg)

    def generate(self, seed: Union[str, List[int]], current_dim: int = None) -> List[int]:
        """Recursive |u | u+v| construction with Active Interference."""
        if current_dim is None:
            if isinstance(seed, str): seed = self._fingerprint_to_bits(seed)
            current_dim = self.dimension

        if current_dim <= 32:
            # Base Case: Pad 24-bit Golay to 32-bit block and scale to Leech coords
            padded = (seed + [0]*8)[:32]
            return [x * 2 for x in padded]
            
        half = current_dim // 2
        # Recursive Step 1: Unfold the first half (u)
        u = self.generate(seed, half)
        
        # Recursive Step 2: Generate the Interference Wave (v)
        # v is derived from the seed's syndrome, creating the Moire effect
        v_bits = self._get_syndrome_v(seed)
        v_padded = (v_bits + [0]*(half-24))[:half]
        v = [x * 2 for x in v_padded]
        
        # BW Construction: [ u | u + v ]
        # Addition % 4 maintains the Leech-style integer lattice (0, 2, 4)
        return u + [(a + b) % 4 for a, b in zip(u, v)]

    def snap(self, macro_point: List[int]) -> List[int]:
        """Successive Cancellation Decoder (The Lens)."""
        def clean_layer(vec):
            n = len(vec)
            if n == 32:
                v24_raw = [abs(x)//2 for x in vec[:24]]
                decoded, _, _ = self.golay.decode(v24_raw)
                return [x * 2 for x in self.golay.encode(decoded)] + [0]*8
            
            half = n // 2
            u = clean_layer(vec[:half])
            # Recover v-noise from the [u | u+v] structure
            v_noisy = [(a + b) % 4 for a, b in zip(vec[:half], vec[half:])]
            v = clean_layer(v_noisy)
            return u + [(a + b) % 4 for a, b in zip(u, v)]
            
        return clean_layer(macro_point)

    def calculate_nrci(self, macro_point: List[int]) -> Fraction:
        """Calculates Macro-Stability (NRCI) for the 256D manifold."""
        hamming = sum(1 for x in macro_point if x != 0)
        norm_sq = sum(x**2 for x in macro_point)
        macro_tax = (Fraction(hamming, 1) * self.Y) + Fraction(norm_sq, 64)
        return Fraction(10, 1) / (Fraction(10, 1) + macro_tax)

    def audit(self, identifier: str, micro_nrci: Fraction, fingerprint: str) -> Dict[str, Any]:
        """Performs a full high-dimensional audit of a KB entry."""
        macro_vec = self.generate(fingerprint)
        snapped_vec = self.snap(macro_vec)
        macro_nrci = self.calculate_nrci(snapped_vec)
        rel_coherence = macro_nrci / micro_nrci
        
        return {
            "ubp_id": identifier,
            "micro_nrci": float(micro_nrci),
            "macro_nrci": float(macro_nrci),
            "relative_coherence": float(rel_coherence),
            "clarity_status": "HIGH" if rel_coherence > 0.30 else "LOW"
        }

if __name__ == "__main__":
    print("--- UBP BARNES-WALL ENGINE v1.6 SELF-DIAGNOSTIC ---")
    engine = BarnesWallEngine(256)
    
    # 1. Test Basis Vector (Index 2) - Should have 0 syndrome (No Interference)
    basis_2 = [0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 1, 1, 1, 0, 0, 0, 1, 0]
    macro_basis = engine.generate(basis_2)
    nrci_basis = engine.calculate_nrci(macro_basis)
    print(f"Test 1 (Basis Anchor): NRCI_256 = {float(nrci_basis):.6f}")
    
    # 2. Test Noisy Vector - Should trigger the 'Program' (Interference)
    noisy_vec = list(basis_2)
    noisy_vec[0] ^= 1 # Add 1 bit of noise
    macro_noisy = engine.generate(noisy_vec)
    nrci_noisy = engine.calculate_nrci(macro_noisy)
    print(f"Test 2 (Noisy Program): NRCI_256 = {float(nrci_noisy):.6f}")
    
    # 3. Verify Interference
    if nrci_noisy != nrci_basis:
        print("✅ INTERFERENCE DETECTED: The Program is active.")
    else:
        print("❌ ERROR: No interference detected. System is static.")

    # 4. Verify Decoder
    snapped = engine.snap(macro_noisy)
    nrci_snapped = engine.calculate_nrci(snapped)
    print(f"Test 3 (Lattice Snap):  NRCI_256 = {float(nrci_snapped):.6f}")
    if nrci_snapped > nrci_noisy:
        print("✅ DECODER VERIFIED: Clarity obtained.")
    else:
        print("❌ ERROR: Decoder failed to improve stability.")
