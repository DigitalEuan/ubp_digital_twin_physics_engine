# Universal Binary Principle Physics Engine

A deterministic, UBP-native physics simulation engine with full 3D Three.js rendering, composite material system, thermal properties, UBP-derived fluid SPH constants, and Topological Torque rigid body mechanics.

**UNDER CONSTRUCTION**
* 16 March 2026
* E R A Craig, New Zealand

UBP: [https://github.com/DigitalEuan/UBP_Repo/tree/main/core_studio_v4.0]

## All constants from UBP geometric laws:

| Constant | V2 Formula | V3 Formula | Law |
|---|---|---|---|
| Pressure stiffness | `Y³ × 0.001` | `SINK_L × 24 / KISSING` | LAW_INFORMATIONAL_SATURATION_001 |
| Viscosity | `(1-NRCI) × Y × 10` | `Y / 96` | LAW_ONTOLOGICAL_FRICTION_001 |
| Surface tension | `Y × 5` | `Y² / KISSING` | LAW_COMP_001 |
| Smoothing radius | `0.5` | `1 / (Y × 24)` | Golay code dimension |

## Topological Torque Moment of Inertia

```
I = m × L² / 12 × (1 + NRCI) × Volumetric_Rebate
```

## Composite Material System

Every entity is an aggregate of N × `ELEM_XXX_YYY` particles from the UBP KB:

```python
iron_block = EntityFactoryV3.make_block('IronBlock', 'iron', position)
# → 1000 × ELEM_Fe_026 particles
# → aggregate Golay vector (XOR of all particle vectors)
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


### update 20 March 2026
# UBP Digital Twin Physics Engine — Project Whiteboard
## Version: v3.2 | Status: COMPLETE | Commit: ba73304

---

## TASK COMPLETION SUMMARY

All 7 issues from the specification have been resolved and committed to GitHub.

---

## VERIFIED FIXES

### Issue (a) — Objects do not interact / water passes through objects
**Root cause:** V3.1 collision detection only triggered when integer cell movement occurred
(`if new_y != entity.position.y`), so slow-moving objects never collided.
**Fix:** V3.2 physics engine always checks collision against the full continuous new position.
Added `_resolve_overlap()` pre-step to separate already-overlapping objects.
Added fluid cohesion force (particles attracted to body centre of mass) + solid-body
repulsion (particles pushed away from entity AABBs). Water now sticks together and
cannot pass through blocks or walls.

### Issue (b) — Lever can be pushed sideways in steps, not usable
**Root cause:** Angular damping was 0.15 (too high), and there was no way to set a
specific angle or apply torque at a point.
**Fix:** Reduced damping to 0.04. Added `set_angle(lever_id, angle_deg)` for direct
positioning. Added `push_lever(lever_id, fx, fy, at_x)` to apply force at a specific
point on the arm, converting to torque about the pivot. Frontend has Set Angle + Push
Lever controls.

### Issue (c) — Temperature doesn't change on high-force impact
**Root cause:** No kinetic-to-thermal conversion existed anywhere in the codebase.
**Fix:** Added `_kinetic_to_thermal()` in physics engine. On every collision, the
lost kinetic energy (½·m·Δv²) is converted to temperature rise via heat_capacity.
Tested: extreme impulse → +119 K peak spike, then cools back to ambient via thermal
exchange. The live frontend readout shows the spike in real time.

### Issue (d) — Water cannot be selected and deleted
**Fix:** Added `delete_fluid(body_id)` to space, server, and frontend. The Fluid Bodies
panel shows each body with its particle count and a Delete button. "Delete All Fluid"
button also added.

### Issue (e) — Block placement via grid selection
**Fix:** Added `spawn_block_at_grid(grid_x, grid_z, material, y, cell_size)` to space,
server, and frontend. The Grid Placement panel lets you enter grid coordinates and
material, then click "Place on Grid".

### Task 3 — Displacement demo
**Implementation:** `run_displacement_demo()` builds a hollow 6×6×8 silicon building,
fills it with a 5-layer water body, then spawns a heavy iron block above the centre.
The block falls in, displacing water particles upward and outward over the walls.
Frontend "Run Displacement Demo" button triggers this in one click.

---

## FILES MODIFIED

| File | Changes |
|------|---------|
| `ubp_physics_v3.py` | Continuous collision detection, overlap resolution, kinetic-to-thermal |
| `ubp_fluid_v3.py` | body_id, cohesion, surface tension, cross-body + solid repulsion |
| `ubp_rigid_body_v3.py` | set_angle, push_lever, reduced damping |
| `ubp_space_v3.py` | delete_fluid, set_lever_angle, spawn_wall, build_demo_building, fill_building_with_water, spawn_block_at_grid |
| `ubp_server_v3.py` | All new commands (WS + REST), run_displacement_demo |
| `src/App.tsx` | Grid Placement, Building Tools, Fluid Bodies, Lever Controls panels |
| `server.ts` | Dev server proxies /api and /ws to FastAPI :8000 |

---

## TEST RESULTS

| # | Test | Result |
|---|------|--------|
| 1 | Block-on-block collision (no tunnelling) | PASS — b1 y=1.00, b2 y=2.00 (stacked) |
| 2 | Thermal on impact | PASS — peak T=412.55 K (+119.40 K) |
| 3 | Fluid cohesion | PASS — 48 particles, avg_y=1.70 |
| 4 | Fluid deletion | PASS — deleted=1, remaining=0 |
| 5 | Grid placement | PASS — Gold_7_3 at (7.0, 15.0, 3.0) |
| 6 | Lever set_angle | PASS — angle=25.0° |
| 7 | Displacement demo | PASS — walls, fluid, projectile all created |
| 8 | Push lever torque | PASS |
| 9 | Delete entity | PASS |
