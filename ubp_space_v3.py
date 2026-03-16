"""
================================================================================
UBP SPACE v3.0 — The Digital Twin World
================================================================================
The world container for the V3 UBP Digital Twin simulation.

Manages:
  - All solid entities (blocks, floor, walls, lever arms)
  - All fluid bodies (SPH water pools)
  - The ambient environment (temperature, air density, pressure)
  - The physics engine (gravity, drag, friction, collision)
  - The rigid body engine (lever constraints, torque)
  - The simulation tick loop
  - State serialisation for Three.js rendering
================================================================================
"""

from __future__ import annotations
import json
import time
from decimal import Decimal, getcontext
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 50

from ubp_entity_v3 import (
    UBPEntityV3, EntityFactoryV3, EntityType, Position, Velocity,
    D, D0, D1, to_decimal
)
from ubp_physics_v3 import UBPPhysicsEngineV3, _G_PER_TICK_SQ
from ubp_rigid_body_v3 import UBPRigidBodyEngineV3, PivotConstraintV3
from ubp_fluid_v3 import FluidBodyV3
from ubp_materials import AmbientEnvironment, MaterialRegistry
from ubp_engine_substrate import Y_CONSTANT, SINK_L

_Y = to_decimal(Y_CONSTANT)
_SINK_L = to_decimal(SINK_L)


class UBPSpaceV3:
    """
    The V3 UBP Digital Twin simulation space.

    A 3D world with UBP-deterministic physics, composite materials,
    thermal properties, lever mechanics, and SPH fluid simulation.
    """

    def __init__(
        self,
        width: float = 20.0,
        height: float = 20.0,
        depth: float = 20.0,
        temperature_K: float = 293.15,
        include_floor: bool = True,
    ):
        self.width = width
        self.height = height
        self.depth = depth

        # Ambient environment
        self.ambient = AmbientEnvironment(temperature_K=temperature_K)

        # Entity registry
        self._entities: Dict[int, UBPEntityV3] = {}
        self._entity_list: List[UBPEntityV3] = []  # Ordered list for physics

        # Fluid bodies
        self._fluid_bodies: List[FluidBodyV3] = []

        # Physics engine
        self.physics = UBPPhysicsEngineV3(ambient=self.ambient)

        # Rigid body engine
        self.rigid_body = UBPRigidBodyEngineV3()

        # Simulation state
        self.tick: int = 0
        self.time_seconds: float = 0.0
        self.ticks_per_second: int = 60

        # Space bounds for fluid
        self._space_bounds = (0.0, width, 1.0, height, 0.0, depth)

        # Create floor
        if include_floor:
            floor = EntityFactoryV3.make_floor(
                label='Floor',
                width=width,
                depth=depth,
                position=Position(D0, D0, D0),
            )
            self.add_entity(floor)

        # Performance tracking
        self._tick_times: List[float] = []

    # -----------------------------------------------------------------------
    # ENTITY MANAGEMENT
    # -----------------------------------------------------------------------

    def add_entity(self, entity: UBPEntityV3) -> UBPEntityV3:
        """Add an entity to the space."""
        self._entities[entity.entity_id] = entity
        self._entity_list.append(entity)
        return entity

    def remove_entity(self, entity_id: int) -> None:
        """Remove an entity from the space."""
        if entity_id in self._entities:
            entity = self._entities.pop(entity_id)
            self._entity_list.remove(entity)

    def get_entity(self, entity_id: int) -> Optional[UBPEntityV3]:
        """Get an entity by ID."""
        return self._entities.get(entity_id)

    def get_entity_by_label(self, label: str) -> Optional[UBPEntityV3]:
        """Get an entity by label."""
        for e in self._entity_list:
            if e.label == label:
                return e
        return None

    def add_fluid(self, fluid: FluidBodyV3) -> FluidBodyV3:
        """Add a fluid body to the space."""
        self._fluid_bodies.append(fluid)
        return fluid

    def add_lever(
        self,
        lever_entity: UBPEntityV3,
        pivot_x: float,
        pivot_y: float,
        pivot_z: float,
    ) -> PivotConstraintV3:
        """Add a lever entity with a pivot constraint."""
        self.add_entity(lever_entity)
        constraint = self.rigid_body.add_lever(lever_entity, pivot_x, pivot_y, pivot_z)
        return constraint

    # -----------------------------------------------------------------------
    # FORCE APPLICATION
    # -----------------------------------------------------------------------

    def push_entity(
        self,
        entity_id: int,
        force_x: float = 0.0,
        force_y: float = 0.0,
        force_z: float = 0.0,
    ) -> bool:
        """Apply a push force to an entity."""
        entity = self.get_entity(entity_id)
        if entity is None or entity.is_static:
            return False
        self.physics.apply_impulse(
            entity,
            D(str(force_x)), D(str(force_y)), D(str(force_z))
        )
        return True

    def pull_entity(
        self,
        entity_id: int,
        force_x: float = 0.0,
        force_y: float = 0.0,
        force_z: float = 0.0,
    ) -> bool:
        """Apply a pull force to an entity (negative push)."""
        return self.push_entity(entity_id, -force_x, -force_y, -force_z)

    def set_ambient_temperature(self, temperature_K: float) -> None:
        """Change the ambient temperature of the space."""
        self.ambient = AmbientEnvironment(temperature_K=temperature_K)
        self.physics.update_ambient(self.ambient)

    # -----------------------------------------------------------------------
    # SIMULATION STEP
    # -----------------------------------------------------------------------

    def step(self) -> Dict[str, Any]:
        """
        Advance the simulation by one tick.

        Returns a summary of the tick for debugging and rendering.
        """
        t_start = time.perf_counter()

        # ---- RIGID BODY STEP (before physics so lever position is updated) ----
        torque_results = self.rigid_body.step(
            self._entity_list, _G_PER_TICK_SQ
        )

        # ---- PHYSICS STEP (all non-static entities) ----
        physics_results = []
        for entity in self._entity_list:
            if entity.is_static:
                continue
            # Skip lever arms (managed by rigid body engine)
            if entity.entity_type == EntityType.LEVER_ARM:
                continue
            result = self.physics.step(entity, self._entity_list, self.tick)
            physics_results.append(result)

        # ---- FLUID STEP ----
        solid_entities = [e for e in self._entity_list if e.is_static or e.is_resting]
        for fluid in self._fluid_bodies:
            fluid.step(
                solid_entities=solid_entities,
                space_bounds=self._space_bounds,
                ambient_temperature_ubp=float(self.ambient.temperature_ubp),
            )

        # ---- ADVANCE TICK ----
        self.tick += 1
        self.time_seconds = self.tick / self.ticks_per_second

        t_end = time.perf_counter()
        self._tick_times.append(t_end - t_start)

        return {
            'tick': self.tick,
            'time_s': self.time_seconds,
            'physics_results': len(physics_results),
            'torque_results': len(torque_results),
            'fluid_particles': sum(f.particle_count() for f in self._fluid_bodies),
            'tick_ms': (t_end - t_start) * 1000,
        }

    def run_ticks(self, n: int) -> None:
        """Run n ticks of the simulation."""
        for _ in range(n):
            self.step()

    def run_until_stable(self, max_ticks: int = 5000) -> int:
        """
        Run until all solid entities are at rest, or max_ticks is reached.
        Returns the number of ticks taken.
        """
        for i in range(max_ticks):
            self.step()
            if self._all_solid_at_rest():
                return i + 1
        return max_ticks

    def _all_solid_at_rest(self) -> bool:
        """Check if all non-static solid entities are at rest."""
        for entity in self._entity_list:
            if entity.is_static:
                continue
            if entity.entity_type in (EntityType.LEVER_ARM, EntityType.FLUID_EMITTER):
                continue
            if not entity.is_resting:
                return False
        return True

    # -----------------------------------------------------------------------
    # STATE SERIALISATION
    # -----------------------------------------------------------------------

    def get_state(self) -> Dict[str, Any]:
        """Return the full simulation state as a dictionary."""
        return {
            'tick': self.tick,
            'time_s': self.time_seconds,
            'ambient': {
                'temperature_K': float(self.ambient.temperature_K),
                'temperature_ubp': float(self.ambient.temperature_ubp),
                'air_density_ubp': float(self.ambient.air_density_ubp),
                'pressure_ubp': float(self.ambient.pressure_ubp),
            },
            'entities': [e.to_dict() for e in self._entity_list],
            'fluid_bodies': [
                {
                    'material': f.material_name,
                    'particle_count': f.particle_count(),
                    'particles': f.get_state(),
                }
                for f in self._fluid_bodies
            ],
            'lever_constraints': self.rigid_body.get_state(),
        }

    def get_threejs_state(self) -> Dict[str, Any]:
        """
        Return the simulation state formatted for Three.js rendering.

        This is the primary output for the Three.js frontend.
        """
        entities = [e.to_threejs_state() for e in self._entity_list]

        fluid_particles = []
        for fluid in self._fluid_bodies:
            fluid_particles.extend(fluid.get_threejs_state())

        lever_states = []
        for c in self.rigid_body.constraints:
            import math
            lever_states.append({
                'lever_id': c.lever.entity_id,
                'angle_deg': float(c.angle) * 180.0 / math.pi,
                'pivot': c.pivot_world.to_dict(),
                'angular_velocity': float(c.angular_velocity),
                'topological_cost': float(c.topological_cost()),
            })

        return {
            'tick': self.tick,
            'time_s': round(self.time_seconds, 4),
            'ambient': {
                'temperature_K': round(float(self.ambient.temperature_K), 2),
                'temperature_ubp': round(float(self.ambient.temperature_ubp), 6),
            },
            'entities': entities,
            'fluid_particles': fluid_particles,
            'lever_constraints': lever_states,
            'stats': {
                'entity_count': len(self._entity_list),
                'fluid_particle_count': len(fluid_particles),
                'avg_tick_ms': round(
                    sum(self._tick_times[-60:]) / max(len(self._tick_times[-60:]), 1) * 1000, 2
                ),
            },
        }

    def get_threejs_state_json(self) -> str:
        """Return the Three.js state as a JSON string."""
        return json.dumps(self.get_threejs_state())

    def get_entity_info(self, entity_id: int) -> Optional[Dict[str, Any]]:
        """Return detailed UBP info for a specific entity."""
        entity = self.get_entity(entity_id)
        if entity is None:
            return None
        return entity.to_dict()

    def summary(self) -> str:
        """Return a human-readable summary of the simulation state."""
        lines = [
            f"UBP Space V3 — Tick {self.tick} ({self.time_seconds:.3f}s)",
            f"  Ambient: {float(self.ambient.temperature_K):.1f}K, "
            f"ρ_air={float(self.ambient.air_density_ubp):.4f}",
            f"  Entities: {len(self._entity_list)}",
        ]
        for e in self._entity_list:
            if e.is_static:
                continue
            lines.append(
                f"    [{e.label}] mat={e.material.name} "
                f"pos=({float(e.position.x):.3f},{float(e.position.y):.3f},{float(e.position.z):.3f}) "
                f"v=({float(e.velocity.vx):.5f},{float(e.velocity.vy):.5f},{float(e.velocity.vz):.5f}) "
                f"rest={e.is_resting} T={float(e.thermal.temperature_ubp):.4f}ubp"
            )
        for fluid in self._fluid_bodies:
            lines.append(
                f"  Fluid [{fluid.material_name}]: {fluid.particle_count()} particles, "
                f"avg_y={fluid.average_y():.3f}"
            )
        for c in self.rigid_body.constraints:
            import math
            lines.append(
                f"  Lever [{c.lever.label}]: angle={float(c.angle)*180/math.pi:.2f}° "
                f"ω={float(c.angular_velocity):.5f} rad/tick"
            )
        return '\n'.join(lines)
