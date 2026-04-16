# Universal Binary Principle Physics Engine

A deterministic, UBP-native physics simulation engine with full 3D Three.js rendering, composite material system, thermal properties, UBP-derived fluid SPH constants, and Topological Torque rigid body mechanics.

This is a full Game Engine development project, not using standard game engine design but my UBP theory to be the "rules of the game. I think that if the UBP can model reality accurately then surely it should actually make a physics virtual space - lets see.

**UNDER CONSTRUCTION**
* 30 March 2026 (Updated to Engine v5.0 / UBP v6.3.1 Theory)
* 16 April 2026 (Updated to Engine v5.1 / UBP v6.3.2 Theory)
* E R A Craig, New Zealand

UBP: [https://github.com/DigitalEuan/UBP_Repo/tree/main/core_studio_v4.0]

## All constants from UBP geometric laws:

| Constant | V2 Formula | V3 Formula | Law |
|---|---|---|---|
| Pressure stiffness | `Y³ × 0.001` | `SINK_L × 24 / KISSING` | LAW_INFORMATIONAL_SATURATION_001 |
| Viscosity | `(1-NRCI) × Y × 10` | `Y / 96` | LAW_ONTOLOGICAL_FRICTION_001 |
| Surface tension | `Y × 5` | `Y² / KISSING` | LAW_COMP_001 |
| Smoothing radius | `0.5` | `1 / (Y × 24)` | Golay code dimension |

## 16.04.26: Updated to Engine v5.1 (UBP v6.3.2 Alignment)
* **Current status:** Fully audited and aligned with UBP Core v6.3.2 (Sovereign ALU v9.2). All mechanics are UBP-native with 64/64 validation tests passing.
* **New in v5.1:**
  * **Sovereign ALU v9.2 (`ubp_eml_alu_sovereign.py`):** The full sovereign ALU is now bundled with the engine and accessible via `get_sovereign_alu()` in the substrate.
  * **Gray Code UMS (LAW_GRAY_CODE_UMS):** Entity state (velocity/NRCI/temperature) is now encoded as a 24-bit Golay codeword via Gray Code Unified Measurement System, ensuring Hamming distance 1 between adjacent states (minimal ontological drift).
  * **Pantograph Tax (LAW_PANTOGRAPH_THERMODYNAMICS_001):** Large lever bodies now experience an additional macroscopic symmetry tax via affine kinematic projection: `k = 1 + WOBBLE`, `V_macro = k³ × V_noum`, `T_adj = T_base × (1 - C_macro/13)`.
  * **Observer Dynamics (LAW_OBSERVER_DYNAMICS_001):** Each entity now tracks `is_manifested` (NRCI ≥ Conscious Threshold 0.70), `soc_energy` (Self-Organising Complexity energy), `ter_score` (Total Experienced Result), and `dqi` (Design Quality Index).
  * **Wall of Reality (LAW_TOTAL_EXPERIENCED_RESULT_001):** The space simulation loop now checks each entity's SOC frequency against `F_MAX_HZ = 1 THz`. Entities exceeding the Wall of Reality are dissolved.
  * **Stereoscopic Sink (LAW_STEREOSCOPIC_SINK_001):** `SINK_L_STEREO = SINK_L × SINK_SIGMA` is now defined in the substrate for binocular/stereoscopic observer contexts.
  * **Poynting Z-Component (LAW_POYNTING_VECTOR_001):** Fluid pressure forces now include an orthogonal Z-component modulated by the particle's NRCI, modelling the Poynting vector's energy transport orthogonality.
  * **Position Type Safety:** `Position` dataclass now enforces `Decimal` arithmetic via `__post_init__` coercion, eliminating `float + Decimal` crashes in AABB calculations.

## 30.03.26: Updated to Engine v5.0 (UBP v6.3.1 Alignment)
* **Current status:** The engine has been fully audited and aligned with UBP Core v6.3.1. All simplified mechanics and floating-point placeholders have been replaced with canonical UBP mathematical structures.
* **Key Upgrades:**
  * **Additive Superposition (The Flow):** Replaced XOR with true additive superposition for material aggregation and collision synthesis.
  * **Recursive XOR Folding (LAW_GEO_FOLD_001):** Replaced standard summation folding with the canonical 24-to-3 recursive fold.
  * **Volumetric Rebate:** Fully integrated into the `calculate_symmetry_tax` engine.
  * **13D Sink Leakage:** `SINK_L` is now correctly derived from the Triadic Monad Wobble (`(π × φ × e) mod 1 / 13`).
  * **TGIC Manifold Pressure:** 9-neighbor overheating penalty is now actively computed and applied in the main physics loop.
  * **Lever Mechanics:** Lever torque now directly utilizes UBP Symmetry Tax as rotational resistance.
  * **Fluid Dynamics:** SPH viscosity is now dynamically modulated by the particle's live NRCI score, and `math.pi` has been replaced with the UBP 50-term exact `PI`.

## Topological Torque Moment of Inertia

```
I = m × L² / 12 × (1 + NRCI) × Volumetric_Rebate
```

## Composite Material System

Every entity is an aggregate of N × `ELEM_XXX_YYY` particles from the UBP KB:

```python
iron_block = EntityFactoryV3.make_block('IronBlock', 'iron', position)
# → 1000 × ELEM_Fe_026 particles
# → aggregate Golay vector (Additive Superposition of all particle vectors)
# → aggregate NRCI, mass, thermal properties
```

Available materials: `iron`, `copper`, `aluminium`, `steel`, `water`, `air`

Where:
- `(1 + NRCI)` is the Topological Torque correction (LAW_TOPOLOGICAL_TORQUE_001)
- `Volumetric_Rebate` = `1 - compactness/13` (13D Sink geometry)
- `compactness = V^(2/3) / S` (volume-to-surface ratio)

## Thermal Properties

Every entity has a `ThermalState`:

| Property | Formula | Law |
|---|---|---|
| `temperature_ubp` | `T_K × Y / 24` | LAW_THERMAL_001 |
| `heat_capacity` | `Σ(particle_capacity) / N` | LAW_TOPO_EFFICIENCY_001 |
| `heat_transfer` | `Σ(particle_transfer) / N` | The Shaving |

Temperature in Kelvin: `T_K = T_ubp × 24 / Y`

## Ambient Environment

```python
ambient = AmbientEnvironment(temperature_K=293.15)
# → air_density_ubp = Y × ρ_air_SI / 1000
# → atmospheric_pressure_ubp = P_atm × Y² / 1000
# → drag_coefficient = Y² × (T_K / 293.15)^0.5
```

## UBP Physics Constants

| Constant | Value | Derivation |
|---|---|---|
| Y (Ontological Constant) | 0.26468 | UBP core (50-term π series) |
| C_DRAG (air drag) | Y² = 0.07005 | LAW_ONTOLOGICAL_FRICTION_001 |
| V_MAX (speed limit) | 1/Y = 3.778 | Substrate speed limit |
| G_TICK (gravity/tick²) | G_earth × Y / 3600 | Equivalence Principle |
| REST_THRESHOLD | SINK_L / 100 | 13D Sink leakage |
| SPH_STIFFNESS | SINK_L × 24 / KISSING | LAW_INFORMATIONAL_SATURATION_001 |
| SPH_VISCOSITY | Y / 96 | LAW_ONTOLOGICAL_FRICTION_001 |
| SPH_SURFACE_TENSION | Y² / KISSING | LAW_COMP_001 |
| BOLTZMANN_K (UBP) | Y × k_B_SI | Thermal bridge |


## New v5.1 Observer Dynamics Constants

| Constant | Value | Derivation | Law |
|---|---|---|---|
| `CONSCIOUS_THRESHOLD` | 0.70 | Fraction(7,10) — Conscious perception boundary | LAW_OBSERVER_DYNAMICS_001 |
| `SINK_L_STEREO` | SINK_L × SINK_SIGMA ≈ 0.0760 | Stereoscopic binocular rebate | LAW_STEREOSCOPIC_SINK_001 |
| `F_MAX_HZ` | 1 × 10¹² Hz (1 THz) | Wall of Reality frequency ceiling | LAW_TOTAL_EXPERIENCED_RESULT_001 |
| `DQI_THRESHOLD` | 0.70 | Well-formed entity minimum | LAW_VTE_QUANTIZATION_001 |

## New v5.1 Entity State Fields

Every entity now carries the following Observer Dynamics fields, updated each tick:

| Field | Type | Description |
|---|---|---|
| `is_manifested` | `bool` | `True` if NRCI ≥ 0.70 (MANIFESTED), `False` if SUBLIMINAL |
| `soc_energy` | `float` | Self-Organising Complexity energy (SOC = Σ toggle × Y × NRCI) |
| `ter_score` | `float` | Total Experienced Result (weighted harmonic of bit-pattern quality metrics) |
| `dqi` | `float` | Design Quality Index (0–1, weighted harmonic of NRCI, utility, template accuracy) |
| `ums_vector` | `List[int]` | 24-bit Gray Code UMS encoded state (velocity/NRCI/temp as Golay codeword) |

The APP that drives the UBP scripts is made with Google AI Stidio
<div align="center">
<img width="200" height="auto" alt="GHBanner" src="https://github.com/user-attachments/assets/0aa67016-6eaf-458a-adb2-6e31a0763ed6" />
</div>

# Run and deploy your AI Studio app

This contains everything you need to run your app locally.

View your app in AI Studio: https://ai.studio/apps/406ddb09-11fc-4f15-974d-e40047dd23cc

## Run Locally

**Prerequisites:**  Node.js


1. Install dependencies:
   `npm install`
2. Set the `GEMINI_API_KEY` in [.env.local](.env.local) to your Gemini API key
3. Run the app:
   `npm run dev`
