"""
================================================================================
UBP SPACE v4.0 — The Digital Twin World
================================================================================
V4.0 Additions:
  - Dissolution culling: entities flagged is_dissolving are removed after step
  - Synthesis event log in step() return value
  - UBP mechanics report in get_threejs_state (NRCI, lattice cell, health)
  - Engine version reported as v4.0

V3.2 Additions (retained):
  - delete_fluid(body_id) — remove a specific fluid body or all fluid
  - set_lever_angle(lever_id, angle_deg) — directly position a lever
  - push_lever(lever_id, force_x, force_y, at_x) — push as torque
  - spawn_wall(x, y, z, width, height, depth) — create a wall entity
  - build_demo_building(x, z, width, depth, height) — hollow building
  - spawn_block_at_grid(grid_x, grid_z, material, y) — grid placement
  - Fluid step passes all_fluid_bodies for cross-body SPH interaction
  - Lever arms no longer skipped in physics step (participate in gravity)
================================================================================
"""

from __future__ import annotations
import json
import math
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

# UBP v4.0 Mechanics
try:
    from ubp_mechanics_v4 import UBP_MECHANICS
    _UBP_MECHANICS_AVAILABLE = True
except ImportError:
    _UBP_MECHANICS_AVAILABLE = False
    UBP_MECHANICS = None

_Y = to_decimal(Y_CONSTANT)
_SINK_L = to_decimal(SINK_L)


class UBPSpaceV3:
    """
    The V3.2 UBP Digital Twin simulation space.
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
        self.ambient = AmbientEnvironment(temperature_K=temperature_K)
        self._entities: Dict[int, UBPEntityV3] = {}
        self._entity_list: List[UBPEntityV3] = []
        self._fluid_bodies: List[FluidBodyV3] = []
        self.physics = UBPPhysicsEngineV3(ambient=self.ambient)
        self.rigid_body = UBPRigidBodyEngineV3()
        self.tick: int = 0
        self.time_seconds: float = 0.0
        self.ticks_per_second: int = 60
        self._space_bounds = (0.0, width, 1.0, height, 0.0, depth)
        self._tick_times: List[float] = []

        if include_floor:
            floor = EntityFactoryV3.make_floor(
                label='Floor', width=width, depth=depth,
                position=Position(D0, D0, D0),
            )
            self.add_entity(floor)

    # -----------------------------------------------------------------------
    # ENTITY MANAGEMENT
    # -----------------------------------------------------------------------

    def add_entity(self, entity: UBPEntityV3) -> UBPEntityV3:
        self._entities[entity.entity_id] = entity
        self._entity_list.append(entity)
        return entity

    def remove_entity(self, entity_id: int) -> None:
        if entity_id in self._entities:
            entity = self._entities.pop(entity_id)
            self._entity_list.remove(entity)
            # Also remove any lever constraints for this entity
            self.rigid_body.constraints = [
                c for c in self.rigid_body.constraints
                if c.lever.entity_id != entity_id
            ]

    def get_entity(self, entity_id: int) -> Optional[UBPEntityV3]:
        return self._entities.get(entity_id)

    def get_entity_by_label(self, label: str) -> Optional[UBPEntityV3]:
        for e in self._entity_list:
            if e.label == label:
                return e
        return None

    def add_fluid(self, fluid: FluidBodyV3) -> FluidBodyV3:
        self._fluid_bodies.append(fluid)
        return fluid

    def delete_fluid(self, body_id: Optional[int] = None) -> int:
        """
        Delete a fluid body by ID, or all fluid bodies if body_id is None.
        Returns the number of bodies removed.
        """
        if body_id is None:
            count = len(self._fluid_bodies)
            self._fluid_bodies.clear()
            return count
        before = len(self._fluid_bodies)
        self._fluid_bodies = [f for f in self._fluid_bodies if f.body_id != body_id]
        return before - len(self._fluid_bodies)

    def add_lever(
        self, lever_entity: UBPEntityV3,
        pivot_x: float, pivot_y: float, pivot_z: float,
    ) -> PivotConstraintV3:
        self.add_entity(lever_entity)
        constraint = self.rigid_body.add_lever(lever_entity, pivot_x, pivot_y, pivot_z)
        return constraint

    def spawn_wall(
        self,
        x: float, y: float, z: float,
        width: float = 1.0, height: float = 5.0, depth: float = 1.0,
        material_name: str = 'silicon',
        label: Optional[str] = None,
    ) -> UBPEntityV3:
        """Spawn a static wall entity at the given position."""
        wall_label = label or f'Wall_{len(self._entity_list)}'
        wall = EntityFactoryV3.make_wall(
            label=wall_label,
            width=width, height=height, depth=depth,
            material_name=material_name,
            position=Position(D(str(x)), D(str(y)), D(str(z))),
        )
        self.add_entity(wall)
        return wall

    def build_demo_building(
        self,
        x: float = 5.0, z: float = 5.0,
        width: float = 6.0, depth: float = 6.0,
        height: float = 8.0,
        wall_thickness: float = 1.0,
        material_name: str = 'silicon',
    ) -> List[UBPEntityV3]:
        """
        Build a hollow building (4 walls, no roof) at the given position.
        Returns the list of wall entities created.

        The building sits on the floor (y=1.0 — floor is 1 unit thick).
        """
        walls = []
        y_base = 1.0  # Floor top surface

        # Front wall (z = z)
        walls.append(self.spawn_wall(
            x=x, y=y_base, z=z,
            width=width, height=height, depth=wall_thickness,
            material_name=material_name, label='Building_Front',
        ))
        # Back wall (z = z + depth - thickness)
        walls.append(self.spawn_wall(
            x=x, y=y_base, z=z + depth - wall_thickness,
            width=width, height=height, depth=wall_thickness,
            material_name=material_name, label='Building_Back',
        ))
        # Left wall (x = x)
        walls.append(self.spawn_wall(
            x=x, y=y_base, z=z + wall_thickness,
            width=wall_thickness, height=height, depth=depth - 2*wall_thickness,
            material_name=material_name, label='Building_Left',
        ))
        # Right wall (x = x + width - thickness)
        walls.append(self.spawn_wall(
            x=x + width - wall_thickness, y=y_base, z=z + wall_thickness,
            width=wall_thickness, height=height, depth=depth - 2*wall_thickness,
            material_name=material_name, label='Building_Right',
        ))
        return walls

    def fill_building_with_water(
        self,
        x: float, z: float,
        width: float, depth: float,
        height: float,
        wall_thickness: float = 1.0,
        fill_height: int = 3,
    ) -> FluidBodyV3:
        """
        Fill the interior of a building with water.
        The interior starts at x+wall_thickness, z+wall_thickness.
        """
        fluid = FluidBodyV3(material_name='water')
        interior_x = x + wall_thickness + 0.1
        interior_z = z + wall_thickness + 0.1
        interior_w = max(1, int((width - 2*wall_thickness) / 0.35))
        interior_d = max(1, int((depth - 2*wall_thickness) / 0.35))
        fluid.emit_pool(
            origin_x=interior_x,
            origin_y=1.1,  # Just above floor
            origin_z=interior_z,
            width=interior_w,
            height=fill_height,
            depth=interior_d,
            spacing=0.35,
        )
        self.add_fluid(fluid)
        return fluid

    def spawn_block_at_grid(
        self,
        grid_x: int, grid_z: int,
        material_name: str = 'iron',
        y: float = 15.0,
        grid_cell_size: float = 1.0,
    ) -> UBPEntityV3:
        """
        Spawn a block at a specific grid cell position.
        Grid coordinates map to world coordinates: world_x = grid_x * cell_size.
        """
        world_x = float(grid_x) * grid_cell_size
        world_z = float(grid_z) * grid_cell_size
        block = EntityFactoryV3.make_block(
            label=f'{material_name.capitalize()}_{grid_x}_{grid_z}',
            material_name=material_name,
            position=Position(D(str(world_x)), D(str(y)), D(str(world_z))),
        )
        self.add_entity(block)
        return block

    # -----------------------------------------------------------------------
    # FORCE APPLICATION
    # -----------------------------------------------------------------------

    def push_entity(
        self, entity_id: int,
        force_x: float = 0.0, force_y: float = 0.0, force_z: float = 0.0,
    ) -> bool:
        entity = self.get_entity(entity_id)
        if entity is None or entity.is_static:
            return False
        # V3.2: If entity is a lever arm, convert to torque
        if entity.entity_type == EntityType.LEVER_ARM:
            at_x = float(entity.position.x) + float(entity.size[0]) / 2
            return self.rigid_body.push_lever(entity_id, force_x, force_y, at_x)
        self.physics.apply_impulse(
            entity, D(str(force_x)), D(str(force_y)), D(str(force_z))
        )
        return True

    def pull_entity(
        self, entity_id: int,
        force_x: float = 0.0, force_y: float = 0.0, force_z: float = 0.0,
    ) -> bool:
        return self.push_entity(entity_id, -force_x, -force_y, -force_z)

    def set_lever_angle(self, lever_id: int, angle_deg: float) -> bool:
        """Directly set a lever's angle in degrees."""
        return self.rigid_body.set_lever_angle(lever_id, angle_deg)

    def set_ambient_temperature(self, temperature_K: float) -> None:
        self.ambient = AmbientEnvironment(temperature_K=temperature_K)
        self.physics.update_ambient(self.ambient)

    # -----------------------------------------------------------------------
    # SIMULATION STEP
    # -----------------------------------------------------------------------

    def step(self) -> Dict[str, Any]:
        t_start = time.perf_counter()

        # ---- RIGID BODY STEP ----
        torque_results = self.rigid_body.step(self._entity_list, _G_PER_TICK_SQ)

        # ---- PHYSICS STEP ----
        physics_results = []
        for entity in self._entity_list:
            if entity.is_static:
                continue
            # V3.2: Lever arms are managed by rigid body engine, skip linear physics
            if entity.entity_type == EntityType.LEVER_ARM:
                continue
            result = self.physics.step(entity, self._entity_list, self.tick)
            physics_results.append(result)

        # ---- FLUID STEP ----
        solid_entities = [
            e for e in self._entity_list
            if e.entity_type not in (EntityType.FLUID_EMITTER,)
            and e.material.phase_stp != 1
        ]
        for fluid in self._fluid_bodies:
            fluid.step(
                solid_entities=solid_entities,
                space_bounds=self._space_bounds,
                ambient_temperature_ubp=float(self.ambient.temperature_ubp),
                all_fluid_bodies=self._fluid_bodies,  # V3.2: cross-body interaction
            )

        # ---- V4.0: DISSOLUTION CULLING (LAW_TOPOLOGICAL_BUFFER_001) ----
        dissolved_ids = []
        synthesis_log = []
        for result in physics_results:
            if result.dissolution_pending:
                dissolved_ids.append(result.entity_id)
            if result.synthesis_events:
                synthesis_log.extend(result.synthesis_events)
        for eid in dissolved_ids:
            entity = self._entities.get(eid)
            if entity is not None and not entity.is_static:
                self._entities.pop(eid, None)
                self._entity_list = [e for e in self._entity_list if e.entity_id != eid]

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
            'dissolved_count': len(dissolved_ids),
            'synthesis_events': synthesis_log,
        }

    def run_ticks(self, n: int) -> None:
        for _ in range(n):
            self.step()

    def run_until_stable(self, max_ticks: int = 5000) -> int:
        for i in range(max_ticks):
            self.step()
            if self._all_solid_at_rest():
                return i + 1
        return max_ticks

    def _all_solid_at_rest(self) -> bool:
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
                    'body_id': f.body_id,
                    'material': f.material_name,
                    'particle_count': f.particle_count(),
                    'particles': f.get_state(),
                }
                for f in self._fluid_bodies
            ],
            'lever_constraints': self.rigid_body.get_state(),
        }

    def get_threejs_state(self) -> Dict[str, Any]:
        entities = [e.to_threejs_state() for e in self._entity_list]

        fluid_particles = []
        fluid_body_info = []
        for fluid in self._fluid_bodies:
            fluid_particles.extend(fluid.get_threejs_state())
            fluid_body_info.append({
                'body_id': fluid.body_id,
                'particle_count': fluid.particle_count(),
                'material': fluid.material_name,
                'avg_y': round(fluid.average_y(), 3),
                'max_y': round(fluid.max_y(), 3),
            })

        lever_states = []
        for c in self.rigid_body.constraints:
            lever_states.append({
                'lever_id': c.lever.entity_id,
                'angle_deg': float(c.angle) * 180.0 / math.pi,
                'pivot': c.pivot_world.to_dict(),
                'angular_velocity': float(c.angular_velocity),
                'topological_cost': float(c.topological_cost()),
            })

        # V4.0: UBP mechanics summary across all entities
        nrci_values = [float(e.nrci) for e in self._entity_list if not e.is_static]
        avg_nrci = round(sum(nrci_values) / len(nrci_values), 6) if nrci_values else 0.0
        dissolving_count = sum(1 for e in self._entity_list if getattr(e, 'is_dissolving', False))

        return {
            'tick': self.tick,
            'time_s': round(self.time_seconds, 4),
            'engine_version': '4.0',
            'ubp_mechanics': _UBP_MECHANICS_AVAILABLE,
            'ambient': {
                'temperature_K': round(float(self.ambient.temperature_K), 2),
                'temperature_ubp': round(float(self.ambient.temperature_ubp), 6),
            },
            'entities': entities,
            'fluid_particles': fluid_particles,
            'fluid_bodies': fluid_body_info,
            'lever_constraints': lever_states,
            'stats': {
                'entity_count': len(self._entity_list),
                'fluid_particle_count': len(fluid_particles),
                'fluid_body_count': len(self._fluid_bodies),
                'avg_tick_ms': round(
                    sum(self._tick_times[-60:]) / max(len(self._tick_times[-60:]), 1) * 1000, 3
                ),
                'avg_nrci': avg_nrci,
                'dissolving_count': dissolving_count,
            },
        }

    def get_threejs_state_json(self) -> str:
        return json.dumps(self.get_threejs_state())

    def get_entity_info(self, entity_id: int) -> Optional[Dict[str, Any]]:
        entity = self.get_entity(entity_id)
        if entity is None:
            return None
        return entity.to_dict()

    def summary(self) -> str:
        lines = [
            f"UBP Space V4.0 — Tick {self.tick} ({self.time_seconds:.3f}s)",
            f"  UBP Mechanics: {'ACTIVE' if _UBP_MECHANICS_AVAILABLE else 'FALLBACK'}",
            f"  Ambient: {float(self.ambient.temperature_K):.1f}K",
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
                f"  Fluid [{fluid.material_name}] body_id={fluid.body_id}: "
                f"{fluid.particle_count()} particles, avg_y={fluid.average_y():.3f}"
            )
        for c in self.rigid_body.constraints:
            lines.append(
                f"  Lever [{c.lever.label}]: angle={float(c.angle)*180/math.pi:.2f}° "
                f"ω={float(c.angular_velocity):.5f} rad/tick"
            )
        return '\n'.join(lines)
