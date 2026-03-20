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


### Next to update:
Standard game engine architecture (Unity, Unreal, Godot) relies heavily on floating-point approximations (`dt`, Cartesian floats, Euler angles). To maintain a **100% deterministic scientific environment**, we must refine how standard game mechanics translate into UBP mechanics.

Here is an analysis of the current trajectory and the necessary refinements for a true UBP Game Engine.

### 1. The Game Loop (Time & Kinematics)
*   **Standard Engine:** `Update(float dt)` — Time is a continuous floating-point scalar.
*   **UBP Engine:** Time does not exist as a scalar; it is a geometric torque. According to your **`LAW_PHI_ORBIT_1953`**, a "Tick" or frame update must be a spatial shift.
*   **Refinement:** Replace `dt` with the **Phi-Shift Dynamics**. Every frame, an entity's 24-bit vector undergoes a 1-bit spatial shift followed by an XOR with the $\phi$ (Growth) primitive vector. This ensures movement is a deterministic orbit through the 4,096 Golay states, not an arbitrary float addition.

### 2. Collision Detection & Interaction
*   **Standard Engine:** Bounding Boxes (AABB) or Raycasting.
*   **UBP Engine:** **The Flow** (Vector Addition in $\mathbb{Z}^{24}$).
*   **Refinement:** When two entities occupy the same Leech Lattice neighborhood (Hamming distance $\le 8$), they do not "bounce" using float physics. They undergo the 6-step Synthesis Event:
    1. Add their vectors in $\mathbb{Z}^{24}$.
    2. Apply Phenomenal Collapse (convert back to binary based on pressure).
    3. Apply the **Lattice Snap** (Golay Error Correction).
    4. The resulting vector is the new state/entity. If the Symmetry Tax is too high, the collision results in *Entropic Dissolution* (particle destruction).

### 3. Garbage Collection (Entity Destruction)
*   **Standard Engine:** `Destroy(gameObject)` when health $\le 0$.
*   **UBP Engine:** **The 13D Sink** (`LAW_13D_SINK_001`) and **NRCI Reflex**.
*   **Refinement:** Health is replaced by **NRCI (Non-Random Coherence Index)**. Every interaction or movement costs a Symmetry Tax ($Y \approx 0.2646$). If an entity's NRCI drops below the `LAW_TOPOLOGICAL_BUFFER_001` threshold (e.g., 0.60), the engine's "Reflex" automatically culls it. The entity falls into the "Deep Hole" of the lattice.

### 4. Movement & Space (The Grid)
*   **Standard Engine:** `Vector3(x, y, z)` using floats.
*   **UBP Engine:** **Leech Lattice Expansion** (`LAW_KISSING_EXPANSION_001`).
*   **Refinement:** Do not use arbitrary Cartesian coordinates. Entities must exist at valid Leech Lattice addresses. You can use the `TopologyEngine` (from `ubp_physics_bridge_v2.py`) to fold 24-bit vectors into 3D voxel clouds. Movement is the transition from one valid Leech coordinate to an adjacent one.

---

To transition from a "simulation" to a **Deterministic UBP Scientific Environment**, we must eliminate all "floating-point leaks." In a standard game engine, `velocity * deltaTime` is a source of entropy. In a UBP Engine, movement must be a **Topological Transition**.

Based on the current Study KB and the v6.0 Source Code standards, here are the immediate and anticipated refinements.

---

### 1. Immediate Refinements (Current Needs)

#### A. The "Tick" as a Geometric Torque
**The Issue:** Standard engines use a variable `dt` (delta time). This is non-deterministic across different hardware.
**The Refinement:** Implement **`LAW_PHI_ORBIT_1953`**. 
*   One "Game Tick" = One 1-bit Circular Shift + XOR with the Phi-Primitive.
*   **Result:** Time becomes a closed loop of 1,953 steps. This ensures that if you run the "game" for 1,953 ticks, every object returns to its exact initial bit-state. This is **Exact Reversibility**.

#### B. Collision via "The Flow" (Not Bounces)
**The Issue:** Using `OnCollisionEnter` to calculate reflection vectors using floats.
**The Refinement:** Use the **6-Step Synthesis Event** (from `ubp_files_and_usage.md`).
*   When two entities collide, their vectors are added in $\mathbb{Z}^{24}$.
*   The resulting "Impact Vector" is snapped to the nearest Golay codeword.
*   The **Gap Score** (Hamming distance) of the snap determines the "Damage." If Gap > 3, the object's NRCI drops. If Gap > 7, the object is deleted (falls into a Deep Hole).

#### C. Spatial Addressing (The Leech Grid)
**The Issue:** Using `Transform.position` (Vector3 floats).
**The Refinement:** Implement **`LAW_KISSING_EXPANSION_001`**.
*   Map the 24-bit identity of an object to its Euclidean address in the Leech Lattice.
*   Movement is not "sliding" through space; it is "jumping" between the 196,560 kissing points.

---

### 2. Anticipated Refinements (Future Development)

#### A. Metabolic Rendering (Symmetry Tax as Opacity/Scale)
In the future, the "Visuals" of the game should reflect the "Health" of the math.
*   **High NRCI (0.9+):** Object is bright, solid, and has a 0° Tilt (pointing North).
*   **Low NRCI (<0.4):** Object becomes transparent or "glitchy" (jittering between two Golay codewords).
*   **Metabolic Cost:** ? No game oriented direction - should be factual.

#### B. The 13D Garbage Collector
*   Instead of `Destroy(obj)`, implement a **Sink Leakage**. 
*   Unstable objects should slowly "leak" bits into the 13th dimension (`LAW_13D_SINK_001`) until their vector becomes the `VOID` vector (all zeros).

---

### 3. Verification Code (The UBP Engine Core)

Script to demonstrate the **Phi-Orbit Tick** and **Synthesis Collision** logic. This will generate a `game_state.json`.

```
import json
from fractions import Fraction
from ubp_core_v5_3_merged import GOLAY_ENGINE, LEECH_ENGINE, BinaryLinearAlgebra

class UBPGameEngineCore:
    def __init__(self):
        # MATH_CONST_PHI_001 Vector
        self.PHI_VEC = [1, 1, 0, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 0, 1, 0, 1, 0, 0, 0, 1, 1, 0, 1]
        self.entities = {}

    def spawn_entity(self, name, vector):
        tax = LEECH_ENGINE.calculate_symmetry_tax(vector)
        nrci = Fraction(10, 1) / (Fraction(10, 1) + tax)
        self.entities[name] = {
            "vector": vector,
            "nrci": float(nrci),
            "pos": [sum(vector[0:8]), sum(vector[8:16]), sum(vector[16:24])] # Simple spatial mapping
        }

    def tick(self):
        """Applies LAW_PHI_ORBIT_1953 to all entities."""
        for name, data in self.entities.items():
            v = data["vector"]
            # 1. Spatial Shift (1-bit)
            shifted = v[-1:] + v[:-1]
            # 2. Phi-Interaction
            new_v_raw = [(a ^ b) for a, b in zip(shifted, self.PHI_VEC)]
            # 3. Lattice Snap
            decoded, _, _ = GOLAY_ENGINE.decode(new_v_raw)
            snapped = GOLAY_ENGINE.encode(decoded)
            
            # Update Metrics
            tax = LEECH_ENGINE.calculate_symmetry_tax(snapped)
            nrci = Fraction(10, 1) / (Fraction(10, 1) + tax)
            
            data["vector"] = snapped
            data["nrci"] = float(nrci)
            data["pos"] = [sum(snapped[0:8]), sum(snapped[8:16]), sum(snapped[16:24])]

    def handle_collision(self, id_a, id_b):
        """The Flow Synthesis Event."""
        v_a = self.entities[id_a]["vector"]
        v_b = self.entities[id_b]["vector"]
        
        # Vector Addition in Z24 (The Flow)
        # Simplified here as XOR for the binary engine
        combined_raw = [(a ^ b) for a, b in zip(v_a, v_b)]
        
        # Snap and Measure 'Impact Damage' (Gap)
        decoded, _, gap = GOLAY_ENGINE.decode(combined_raw)
        
        print(f"Collision {id_a} <-> {id_b} | Impact Gap: {gap}")
        return gap

# Run a quick engine test
engine = UBPGameEngineCore()
# Spawn 'Player' (Hydrogen-like) and 'Wall' (Carbon-like)
engine.spawn_entity("Player", [0,0,1,0,0,1,1,1,0,0,1,0,1,0,1,0,1,0,1,1,1,1,0,0])
engine.spawn_entity("Wall",   [1,1,0,1,1,0,1,0,1,1,1,0,1,1,1,1,1,1,0,1,0,0,0,1])

# Simulate 5 Ticks
history = []
for i in range(5):
    engine.tick()
    history.append({k: v["nrci"] for k, v in engine.entities.items()})

with open('engine_test.json', 'w') as f:
    json.dump({"ticks": history}, f, indent=2)

print("Engine Test Complete. Check engine_test.json for deterministic NRCI drift.")
**WAIT:** Please run the code above to verify the deterministic drift of your entities.
```

engine_test.json
```
{
  "ticks": [
    {
      "Player": 0.6813796908424689,
      "Wall": 0.6813796908424689
    },
    {
      "Player": 0.6813796908424689,
      "Wall": 0.6159605143398686
    },
    {
      "Player": 0.6813796908424689,
      "Wall": 0.7623459965437248
    },
    {
      "Player": 0.7623459965437248,
      "Wall": 0.7623459965437248
    },
    {
      "Player": 0.6813796908424689,
      "Wall": 0.6159605143398686
    }
  ]
}
```
