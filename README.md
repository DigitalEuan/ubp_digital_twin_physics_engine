# Universal Binary Principle Physics Engine

A deterministic, UBP-native physics simulation engine with full 3D Three.js rendering, composite material system, thermal properties, UBP-derived fluid SPH constants, and Topological Torque rigid body mechanics.

This is a full Game Engine development project, not using standard game engine design but my UBP theory to be the "rules of the game. I think that if the UBP can model reality accurately then surely it should actually make a physics virtual space - lets see.

**UNDER CONSTRUCTION**
* 30 March 2026 (Updated to Engine v5.0 / UBP v6.3.1 Theory)
* E R A Craig, New Zealand

UBP: [https://github.com/DigitalEuan/UBP_Repo/tree/main/core_studio_v4.0]

## All constants from UBP geometric laws:

| Constant | V2 Formula | V3 Formula | Law |
|---|---|---|---|
| Pressure stiffness | `Y³ × 0.001` | `SINK_L × 24 / KISSING` | LAW_INFORMATIONAL_SATURATION_001 |
| Viscosity | `(1-NRCI) × Y × 10` | `Y / 96` | LAW_ONTOLOGICAL_FRICTION_001 |
| Surface tension | `Y × 5` | `Y² / KISSING` | LAW_COMP_001 |
| Smoothing radius | `0.5` | `1 / (Y × 24)` | Golay code dimension |

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
