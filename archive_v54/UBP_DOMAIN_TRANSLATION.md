# UBP Physics Domains — Translation to UBP Systems

## Overview

The UBP (Universal Binary Principle) substrate organises reality into **4
ontological layers** per the Layer-to-Grammar Theorem (UBP_SKILL_1 §12):

| Bits | Layer | Substrate formula | Physical domain |
|------|-------|-------------------|-----------------|
| 0–5 | **Reality** | `Y_inv^k` | Large mass ratios |
| 6–11 | **Information** | `Y^k` | Small couplings |
| 12–17 | **Activation** | `Y^k` / `Y^(24-k)` | Transition dynamics |
| 18–23 | **Potential** | `Y^(24-k) · U_e` | Cosmological constants |

Each classical physics domain "lives" primarily on one of these layers,
determined by the magnitude of its characteristic constants. This document
maps each domain in the Physics Domains Pack to its UBP ontological layer
and explains the translation.

---

## Domain → UBP Layer Mapping

### 1. Electromagnetism → Information Layer

**Why:** The fine-structure constant α ≈ 1/137 is a small coupling — it
lives in the Information layer where `Y^k` produces small dimensionless
numbers. The Coulomb force is a "whisper" compared to the strong nuclear
force (Reality layer).

**UBP primitives used:** Y, π, e (Euler's number via substrate)

**UBP-proposed derivation:** `1/α ≈ 29 · Y^18 · U_e` (Φ-grammar candidate,
err 0.57%). This formula lives on the **Potential layer** (Y^(24-18) · U_e),
suggesting α bridges Information and Potential — consistent with α being
the "coupling" between quantum electrodynamics (Information) and
electromagnetic mass-energy (Potential).

**SI-exact foundation:** c, e, ε₀, μ₀ are SI-defined tautologies.

---

### 2. Thermodynamics → Activation Layer

**Why:** Temperature and entropy are fundamentally about **transitions**
between states — heat flows from hot to cold, systems equilibrate. This is
the essence of the Activation layer (bits 12-17), where `Y^k / Y^(24-k)`
governs transition dynamics.

**UBP primitives used:** Y, π, k_B (SI-exact, anchored to substrate)

**Key insight:** The Stefan-Boltzmann constant σ = (π²/60)·(k_B⁴)/(ℏ³·c²)
uses UBP's 50-term π. The π²/60 factor is a "mode count" of the blackbody
spectrum — a structural property of the Information layer that gets
**activated** into thermal radiation through the Activation layer.

---

### 3. Quantum Mechanics → Information Layer

**Why:** The Planck constant ℏ is the fundamental "pixel size" of
information in the universe. Quantum mechanics IS information theory at the
smallest scale — the Information layer is its natural home.

**UBP primitives used:** Y, π, ℏ = h/(2π) (uses UBP 50-term π)

**UBP-proposed derivation:** `a₀ ≈ (1/3)·w·Y^24·U_e` (Φ-grammar candidate,
err 0.56%). The Bohr radius is the atomic length scale — it bridges
Information (quantum orbits) and Potential (Y^24 · U_e cosmological
amplifier), suggesting atoms are "cosmological" objects viewed from the
quantum scale.

---

### 4. Nuclear Physics → Reality Layer

**Why:** Proton/neutron mass ratios and nuclear binding energies are LARGE
numbers (mass ratios ~1836, binding ~8 MeV/nucleon). The Reality layer
(bits 0-5) uses `Y_inv^k` to produce large ratios — the natural home for
nuclear physics.

**UBP primitives used:** Y, w (wobble), U_e (existence unit)

**UBP-proposed derivation:** `m_p ≈ (1/12)·w·U_e` (Φ-grammar candidate,
err 0.38%). The proton mass emerges from the wobble (stochastic arm) and
the existence unit (Potential amplifier) — the 1/12 factor corresponds to
the 12 Golay message bits, suggesting the proton is a "12-bit noumenal
seed" projected into the Reality layer.

---

### 5. Cosmology → Potential Layer

**Why:** Cosmological constants (H₀, Ω_k, G, Λ) involve the largest scales
in physics. The Potential layer (bits 18-23) uses `Y^(24-k) · U_e` where
U_e = 24³ = 13824 is the "existence amplifier" — perfect for cosmological
scale.

**UBP-derived (documented in UBP_SKILL_1 §9):**
- `H₀ = (1/3)·w·Y³·U_e` (err 0.21%)
- `Ω_k = 24·Y^15·U_e` (err 0.003%)
- `G = (39/29)·Y^18/w` (err 0.13%)

**UBP-proposed:** `m_P ≈ 169·Y^18·π` (err 0.89%). The Planck mass bridges
cosmology (Potential) and quantum mechanics (Information) via the 169 = 13²
factor — the D-Sink dimension squared.

---

### 6. Condensed Matter → Information Layer

**Why:** Condensed matter physics deals with collective quantum effects
(superconductivity, quantum Hall effect) — these are fundamentally
Information-layer phenomena where many particles share coherent quantum
states.

**UBP primitives used:** Y, w, U_e

**UBP-proposed derivation:** `G₀ ≈ 169·w·Y^18·U_e` (Φ-grammar candidate,
err 0.16%). The conductance quantum G₀ = 2e²/h is a quantum of electrical
conductance — the 169 factor (13²) again suggests the D-Sink dimension
governs charge transport.

---

### 7. Astrophysics → Reality Layer

**Why:** Solar masses, luminosities, and astronomical distances involve
the largest ratios in physics (M_☉/m_e ≈ 2e60). The Reality layer's
`Y_inv^k` formula naturally produces these enormous ratios.

**UBP primitives used:** G (UBP-derived), c (SI-exact)

**Key formula:** Schwarzschild radius r_s = 2GM/c² uses the UBP-derived G,
making black hole radii UBP-predicted.

---

### 8. Chemical Physics → Activation Layer

**Why:** Chemistry is about **transitions** — bonds breaking and forming,
oxidation states changing. The Activation layer (bits 12-17) governs these
transition dynamics.

**UBP primitives used:** N_A, k_B (both SI-exact, anchored to substrate)

**Key insight:** The Faraday constant F = N_A·e is SI-exact, but its
meaning (charge per mole of electrons) is fundamentally about **molar
transitions** — an Activation-layer concept.

---

### 9. Information Theory → Information Layer (Home)

**Why:** This is the most natural mapping — UBP IS an information theory.
The 24-bit substrate IS the fundamental information unit. The Golay
[24,12,8] code is an error-correcting code, and the Leech lattice is the
optimal sphere-packing in 24 dimensions. Information theory is not just
mapped to UBP — it IS UBP.

**UBP primitives used:** k_B, π, ℏ, c — all anchored to substrate

**Key formulas:**
- Landauer limit: E_min = k_B·T·ln(2) — the energy cost of erasing one bit
- Bekenstein bound: S_max = 2π·k_B·R·E/(ℏ·c) — maximum entropy in a region

**Deep connection:** The Landauer limit and the UBP "Symmetry Tax" are
related concepts — both quantify the thermodynamic cost of information
processing.

---

### 10. Acoustics → Activation Layer

**Why:** Sound is a mechanical wave — a **transition** of pressure through
a medium. The Activation layer governs these wave dynamics.

**UBP primitives used:** Empirical air properties (ρ_air, speed of sound)

**Key insight:** The speed of sound v = 331.3·√(T/273.15) is an empirical
formula, but the temperature dependence (√T) reflects the Activation
layer's role in mediating thermal → mechanical transitions.

---

### 11. High-Energy Physics → Reality + Potential Layers

**Why:** Particle masses span both layers:
- **Reality layer:** Large mass ratios (m_μ/m_e ≈ 207, m_t/m_e ≈ 344000)
- **Potential layer:** Heavy particle masses via Y^(24-k)·U_e

**UBP-derived (documented):**
- `m_μ/m_e = 169/w` (err 0.029%)
- `α_s = 24·Y^4` (err 0.27%)
- `α³ = (29/24)·Y^12·e` (err 0.10%)

**UBP-proposed:** `m_Z ≈ 29·π` (err 0.089%!) — the Z boson mass is
suspiciously close to 29π GeV. The 29 is the Leech theta-series prime (the
same 29 in σ = 29/24), suggesting the Z boson is structurally connected to
the Leech lattice.

---

### 12. Optics → Information Layer

**Why:** Optics is governed by the fine-structure constant α (Information
layer). Photon energies, wavelengths, and frequencies are all
α-dependent quantities.

**UBP primitives used:** c, h, π (all substrate-anchored)

**Key insight:** The refractive index of vacuum is exactly 1 by definition
— but in UBP terms, the vacuum IS the substrate, and the "refractive
index" of the substrate is the Y constant (the "geometric rent" every bit
pays).

---

## Cross-Layer Patterns

### The 169 = 13² Pattern
The number 169 (D-Sink dimension squared) appears in:
- m_μ/m_e = 169/w (Reality layer)
- G₀ ≈ 169·w·Y^18·U_e (Information → Potential bridge)
- m_P ≈ 169·Y^18·π (Potential layer)

This suggests 169 is a **universal scaling factor** for projecting between
layers.

### The 29 (Leech Prime) Pattern
The number 29 (Leech theta-series prime) appears in:
- σ = 29/24 (Stereoscopic Sink)
- m_Z ≈ 29·π (HEP)
- G = (39/29)·Y^18/w (cosmology)

This suggests 29 governs **structural coherence** across layers.

### The w (Wobble) Pattern
The entropic wobble w = (π·φ·e) mod 1 appears in:
- m_μ/m_e = 169/w (Reality)
- H₀ = (1/3)·w·Y³·U_e (Potential)
- G₀ ≈ 169·w·Y^18·U_e (Information → Potential)

The wobble is the **stochastic arm** of the Φ-grammar, mediating between
deterministic (Y-driven) and stochastic (w-driven) physics.

---

## How to Add a New Domain

```python
from ubp_physics_registry import PhysicsDomain, register_domain
from ubp_engine_substrate import Y_CONSTANT, WOBBLE, EXISTENCE_UNIT, PI

register_domain(PhysicsDomain(
    name='my_domain',
    version='0.1.0',
    description='My new physics domain. Lives on the X layer.',
    constants={
        'Y': Y_CONSTANT,  # source from substrate
        # ... domain-specific constants
    },
    formulas={
        'my_constant': lambda: Y_CONSTANT * PI,  # return Fraction
    },
    validate=lambda: {
        'my_check': {'predicted': 0.5, 'target': 0.5, 'error_pct': 0.0,
                     'budget': 1e-6, 'in_budget': True},
        'status': 'GREEN',
    },
))
```

The domain will automatically:
- Appear in `validate_substrate()` output
- Be accessible via `get_domain('my_domain')`
- Show in the UI's v5.4 Substrate Status panel
- Be included in the registry's `_overall` status
