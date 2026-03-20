"""
================================================================================
UBP PHYSICS ENGINE v3.2
================================================================================
V3.2 Fixes:
  1. CONTINUOUS COLLISION DETECTION — collision checks always run regardless of
     whether integer cell movement occurred. V3.1 only checked collisions when
     move_x/y/z != 0, causing slow-moving objects to pass through each other.
     Fix: always test the new position (including fractional movement) against
     all other entities.

  2. OVERLAP RESOLUTION — if an entity is already overlapping another at the
     start of a tick (e.g., spawned inside another), it is pushed out along
     the minimum penetration axis before the tick begins.

  3. KINETIC-TO-THERMAL CONVERSION — on collision, the kinetic energy lost
     (ΔKE = 0.5 × m × (v_before² - v_after²)) is converted to heat:
     ΔT_ubp = ΔKE × BOLTZMANN_THERMAL_FACTOR / heat_capacity
     This makes high-velocity impacts raise the temperature of the entity.

  4. LEVER ARM PHYSICS — LEVER_ARM entities are no longer skipped. They
     participate in full physics (gravity, collision, support detection).
================================================================================
"""

from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal, getcontext
from fractions import Fraction
from typing import Dict, List, Optional, Tuple, Any

getcontext().prec = 50

from ubp_entity_v3 import (
    UBPEntityV3, EntityType, Position, Velocity, AngularVelocity,
    Orientation, AABB, D, D0, D1, D_HALF, to_decimal
)
from ubp_engine_substrate import (
    Y_CONSTANT, Y_INV, SINK_L, G_EARTH_MS2,
    hamming_distance, calculate_nrci, calculate_symmetry_tax,
    BOLTZMANN_K,
)
from ubp_materials import AmbientEnvironment

# ---------------------------------------------------------------------------
# PHYSICS CONSTANTS
# ---------------------------------------------------------------------------

_Y = to_decimal(Y_CONSTANT)
_Y_INV = to_decimal(Y_INV)
_SINK_L = to_decimal(SINK_L)
_G_EARTH = to_decimal(G_EARTH_MS2)

_G_PER_TICK_SQ: Decimal = _G_EARTH / D('3600') * _Y
_C_DRAG: Decimal = _Y * _Y
_V_MAX: Decimal = D('1') / _Y
_V_REST_THRESHOLD: Decimal = _SINK_L / D('100')
_EPSILON: Decimal = D('1E-9')

# Thermal conversion factor: fraction of lost KE that becomes heat
# Derived from LAW_ONTOLOGICAL_FRICTION_001: The Shaving (Y²) is the
# dissipation fraction. We use Y² as the thermal conversion efficiency.
_THERMAL_CONVERSION = _C_DRAG  # = Y² ≈ 0.07005


@dataclass
class PhysicsResultV3:
    entity_id: int
    delta_position: Tuple[Decimal, Decimal, Decimal]
    new_velocity: Velocity
    new_angular_velocity: AngularVelocity
    new_orientation: Orientation
    forces_applied: Dict[str, Decimal]
    collisions: List[int]
    is_resting: bool
    thermal_delta: Decimal


class UBPPhysicsEngineV3:
    """
    V3.2 UBP deterministic physics engine.
    Continuous collision detection, overlap resolution, kinetic-to-thermal.
    """

    def __init__(self, ambient: Optional[AmbientEnvironment] = None):
        self.ambient = ambient or AmbientEnvironment()
        self._rho_air: Decimal = to_decimal(self.ambient.air_density_ubp)
        self._T_ambient: Decimal = to_decimal(self.ambient.temperature_ubp)

    def update_ambient(self, ambient: AmbientEnvironment) -> None:
        self.ambient = ambient
        self._rho_air = to_decimal(ambient.air_density_ubp)
        self._T_ambient = to_decimal(ambient.temperature_ubp)

    def compute_gravity(self, entity: UBPEntityV3) -> Decimal:
        return -_G_PER_TICK_SQ

    def compute_air_resistance(self, entity: UBPEntityV3) -> Velocity:
        T_STP = D('3.2329')
        if self._T_ambient > D0:
            rho_corrected = self._rho_air * T_STP / self._T_ambient
        else:
            rho_corrected = self._rho_air
        drag_coeff = _C_DRAG * rho_corrected / entity.inertia
        vx, vy, vz = entity.velocity.vx, entity.velocity.vy, entity.velocity.vz
        ax = -drag_coeff * vx * abs(vx)
        ay = -drag_coeff * vy * abs(vy)
        az = -drag_coeff * vz * abs(vz)
        return Velocity(ax, ay, az)

    def compute_friction(self, entity: UBPEntityV3, surface: UBPEntityV3) -> Velocity:
        dH = hamming_distance(entity.golay_vector, surface.golay_vector)
        mu = D1 - D(str(dH)) / D('24')
        mu = max(D0, min(D1, mu))
        friction_mag = mu * _G_PER_TICK_SQ / entity.inertia
        ax = D0
        az = D0
        if abs(entity.velocity.vx) > _V_REST_THRESHOLD:
            ax = -friction_mag * (D1 if entity.velocity.vx > D0 else D('-1'))
        if abs(entity.velocity.vz) > _V_REST_THRESHOLD:
            az = -friction_mag * (D1 if entity.velocity.vz > D0 else D('-1'))
        return Velocity(ax, D0, az)

    def detect_collision(
        self, entity: UBPEntityV3, test_position: Position,
        all_entities: List[UBPEntityV3],
    ) -> Optional[UBPEntityV3]:
        """Test if entity at test_position overlaps any other entity."""
        w, h, d = entity.size
        test_aabb = AABB(
            test_position.x, test_position.y, test_position.z,
            test_position.x + w, test_position.y + h, test_position.z + d,
        )
        for other in all_entities:
            if other.entity_id == entity.entity_id:
                continue
            if other.entity_type == EntityType.FLUID_EMITTER:
                continue
            if other.material.phase_stp == 1 and not other.is_static:
                continue
            if test_aabb.overlaps(other.aabb()):
                return other
        return None

    def detect_support(
        self, entity: UBPEntityV3, all_entities: List[UBPEntityV3],
    ) -> Optional[UBPEntityV3]:
        test_pos = Position(
            entity.position.x,
            entity.position.y - D('0.001'),
            entity.position.z,
        )
        return self.detect_collision(entity, test_pos, all_entities)

    def _resolve_overlap(
        self, entity: UBPEntityV3, all_entities: List[UBPEntityV3]
    ) -> None:
        """
        Push entity out of any overlapping entities along the minimum
        penetration axis. This handles cases where entities were spawned
        overlapping or were pushed into each other by external forces.
        """
        for other in all_entities:
            if other.entity_id == entity.entity_id:
                continue
            if other.entity_type == EntityType.FLUID_EMITTER:
                continue
            if other.material.phase_stp == 1 and not other.is_static:
                continue
            bb_a = entity.aabb()
            bb_b = other.aabb()
            if not bb_a.overlaps(bb_b):
                continue
            # Compute penetration depths on each axis
            pen_x_left  = float(bb_a.max_x) - float(bb_b.min_x)
            pen_x_right = float(bb_b.max_x) - float(bb_a.min_x)
            pen_y_down  = float(bb_a.max_y) - float(bb_b.min_y)
            pen_y_up    = float(bb_b.max_y) - float(bb_a.min_y)
            pen_z_front = float(bb_a.max_z) - float(bb_b.min_z)
            pen_z_back  = float(bb_b.max_z) - float(bb_a.min_z)

            min_pen = min(pen_x_left, pen_x_right, pen_y_down, pen_y_up,
                          pen_z_front, pen_z_back)

            if min_pen == pen_y_down:
                entity.position.y = bb_b.min_y - entity.size[1] - D('0.001')
                if entity.velocity.vy > D0:
                    entity.velocity.vy = D0
            elif min_pen == pen_y_up:
                entity.position.y = bb_b.max_y + D('0.001')
                if entity.velocity.vy < D0:
                    entity.velocity.vy = D0
            elif min_pen == pen_x_left:
                entity.position.x = bb_b.min_x - entity.size[0] - D('0.001')
                if entity.velocity.vx > D0:
                    entity.velocity.vx = D0
            elif min_pen == pen_x_right:
                entity.position.x = bb_b.max_x + D('0.001')
                if entity.velocity.vx < D0:
                    entity.velocity.vx = D0
            elif min_pen == pen_z_front:
                entity.position.z = bb_b.min_z - entity.size[2] - D('0.001')
                if entity.velocity.vz > D0:
                    entity.velocity.vz = D0
            else:
                entity.position.z = bb_b.max_z + D('0.001')
                if entity.velocity.vz < D0:
                    entity.velocity.vz = D0

    def resolve_collision(
        self, entity_a: UBPEntityV3, entity_b: UBPEntityV3, axis: str = 'y',
    ) -> Tuple[Velocity, Velocity]:
        """
        Resolve collision using UBP XOR Smash.
        Restitution = NRCI(a.vector XOR b.vector)
        """
        xor_vec = [a ^ b for a, b in zip(entity_a.golay_vector, entity_b.golay_vector)]
        restitution = to_decimal(calculate_nrci(xor_vec))
        m_a = entity_a.inertia
        m_b = entity_b.inertia if not entity_b.is_static else D('1E20')
        inv_m_a = D1 / m_a
        inv_m_b = D1 / m_b

        if axis == 'y':
            rel_v = entity_a.velocity.vy - entity_b.velocity.vy
            j = -(D1 + restitution) * rel_v / (inv_m_a + inv_m_b)
            new_va = Velocity(entity_a.velocity.vx, entity_a.velocity.vy + j * inv_m_a, entity_a.velocity.vz)
            new_vb = Velocity(entity_b.velocity.vx, entity_b.velocity.vy - j * inv_m_b if not entity_b.is_static else entity_b.velocity.vy, entity_b.velocity.vz)
        elif axis == 'x':
            rel_v = entity_a.velocity.vx - entity_b.velocity.vx
            j = -(D1 + restitution) * rel_v / (inv_m_a + inv_m_b)
            new_va = Velocity(entity_a.velocity.vx + j * inv_m_a, entity_a.velocity.vy, entity_a.velocity.vz)
            new_vb = Velocity(entity_b.velocity.vx - j * inv_m_b if not entity_b.is_static else entity_b.velocity.vx, entity_b.velocity.vy, entity_b.velocity.vz)
        else:  # z
            rel_v = entity_a.velocity.vz - entity_b.velocity.vz
            j = -(D1 + restitution) * rel_v / (inv_m_a + inv_m_b)
            new_va = Velocity(entity_a.velocity.vx, entity_a.velocity.vy, entity_a.velocity.vz + j * inv_m_a)
            new_vb = Velocity(entity_b.velocity.vx, entity_b.velocity.vy, entity_b.velocity.vz - j * inv_m_b if not entity_b.is_static else entity_b.velocity.vz)

        return new_va, new_vb

    def _kinetic_to_thermal(
        self, entity: UBPEntityV3,
        v_before: Velocity, v_after: Velocity,
    ) -> Decimal:
        """
        Convert kinetic energy lost in collision to thermal energy.

        ΔKE = 0.5 × m × (|v_before|² - |v_after|²)
        ΔT_ubp = ΔKE × Y² / heat_capacity
        (Y² = The Shaving = thermal conversion efficiency)

        This implements the physical reality that inelastic collisions
        generate heat — a block smashed at high velocity into the floor
        will show a measurable temperature increase.
        """
        ke_before = (v_before.vx**2 + v_before.vy**2 + v_before.vz**2) * entity.mass / D('2')
        ke_after  = (v_after.vx**2  + v_after.vy**2  + v_after.vz**2)  * entity.mass / D('2')
        delta_ke = ke_before - ke_after
        if delta_ke <= D0:
            return D0
        if entity.thermal.heat_capacity <= D0:
            return D0
        delta_T = delta_ke * _THERMAL_CONVERSION / entity.thermal.heat_capacity
        return delta_T

    def apply_impulse(
        self, entity: UBPEntityV3,
        force_x: Decimal = D0, force_y: Decimal = D0, force_z: Decimal = D0,
    ) -> None:
        entity.velocity.vx += force_x / entity.inertia
        entity.velocity.vy += force_y / entity.inertia
        entity.velocity.vz += force_z / entity.inertia
        entity.is_resting = False
        entity.is_sleeping = False

    def _cap_velocity(self, v: Velocity) -> Velocity:
        def cap(val: Decimal) -> Decimal:
            if val > _V_MAX: return _V_MAX
            if val < -_V_MAX: return -_V_MAX
            return val
        return Velocity(cap(v.vx), cap(v.vy), cap(v.vz))

    def apply_angular_damping(self, entity: UBPEntityV3) -> None:
        damp = D1 - _C_DRAG
        entity.angular_velocity.wx *= damp
        entity.angular_velocity.wy *= damp
        entity.angular_velocity.wz *= damp
        if entity.angular_velocity.magnitude() < _V_REST_THRESHOLD:
            entity.angular_velocity = AngularVelocity()

    def integrate_orientation(self, entity: UBPEntityV3) -> None:
        wx = entity.angular_velocity.wx
        wy = entity.angular_velocity.wy
        wz = entity.angular_velocity.wz
        if wx == D0 and wy == D0 and wz == D0:
            return
        q = entity.orientation
        dw = D_HALF * (-q.x*wx - q.y*wy - q.z*wz)
        dx = D_HALF * ( q.w*wx + q.y*wz - q.z*wy)
        dy = D_HALF * ( q.w*wy - q.x*wz + q.z*wx)
        dz = D_HALF * ( q.w*wz + q.x*wy - q.y*wx)
        entity.orientation = Orientation(q.w+dw, q.x+dx, q.y+dy, q.z+dz).normalise()

    def step(
        self, entity: UBPEntityV3,
        all_entities: List[UBPEntityV3],
        tick: int = 0,
    ) -> PhysicsResultV3:
        """
        V3.2 physics step with continuous collision detection.

        Key change from V3.1: collision checks are ALWAYS performed against
        the new position (including fractional sub-cell movement), not only
        when integer cell movement occurs.
        """
        forces: Dict[str, Decimal] = {}
        collisions: List[int] = []
        thermal_delta = D0

        if entity.is_static:
            return PhysicsResultV3(
                entity_id=entity.entity_id,
                delta_position=(D0, D0, D0),
                new_velocity=entity.velocity,
                new_angular_velocity=entity.angular_velocity,
                new_orientation=entity.orientation,
                forces_applied={},
                collisions=[],
                is_resting=True,
                thermal_delta=D0,
            )

        # ---- OVERLAP RESOLUTION (pre-step) ----
        self._resolve_overlap(entity, all_entities)

        # ---- 1. GRAVITY ----
        g_acc = self.compute_gravity(entity)
        entity.velocity.vy += g_acc
        forces['gravity'] = g_acc

        # ---- 2. AIR RESISTANCE ----
        drag = self.compute_air_resistance(entity)
        entity.velocity.vx += drag.vx
        entity.velocity.vy += drag.vy
        entity.velocity.vz += drag.vz
        forces['drag_x'] = drag.vx
        forces['drag_y'] = drag.vy
        forces['drag_z'] = drag.vz

        # ---- 3. FRICTION (if resting) ----
        if entity.is_resting:
            support = self.detect_support(entity, all_entities)
            if support is not None:
                friction = self.compute_friction(entity, support)
                entity.velocity.vx += friction.vx
                entity.velocity.vz += friction.vz
                forces['friction_x'] = friction.vx
                forces['friction_z'] = friction.vz
            else:
                entity.is_resting = False

        # ---- 4. CAP VELOCITY ----
        entity.velocity = self._cap_velocity(entity.velocity)

        # ---- 5. COMPUTE NEW POSITION (continuous — no integer extraction) ----
        # V3.2 FIX: Use full continuous position movement, not integer steps.
        # This ensures collision detection works for slow-moving objects.
        new_x = entity.position.x + entity.velocity.vx
        new_y = entity.position.y + entity.velocity.vy
        new_z = entity.position.z + entity.velocity.vz

        # ---- 6. Y-AXIS COLLISION (always check) ----
        pre_collision_vy = entity.velocity.vy
        collider_y = self.detect_collision(
            entity, Position(entity.position.x, new_y, entity.position.z),
            all_entities
        )
        if collider_y is not None:
            collisions.append(collider_y.entity_id)
            v_before = Velocity(entity.velocity.vx, entity.velocity.vy, entity.velocity.vz)
            vel_a, vel_b = self.resolve_collision(entity, collider_y, axis='y')
            entity.velocity = vel_a
            if not collider_y.is_static:
                collider_y.velocity = vel_b
                collider_y.is_resting = False
                collider_y.is_sleeping = False
            # Kinetic-to-thermal conversion
            thermal_delta += self._kinetic_to_thermal(entity, v_before, entity.velocity)
            # Position correction
            if pre_collision_vy < D0:
                new_y = collider_y.aabb().max_y
            else:
                new_y = collider_y.aabb().min_y - entity.size[1]
            if abs(entity.velocity.vy) < _V_REST_THRESHOLD:
                entity.velocity.vy = D0
                entity.is_resting = True

        # ---- 7. X-AXIS COLLISION (always check) ----
        collider_x = self.detect_collision(
            entity, Position(new_x, new_y, entity.position.z),
            all_entities
        )
        if collider_x is not None:
            collisions.append(collider_x.entity_id)
            v_before = Velocity(entity.velocity.vx, entity.velocity.vy, entity.velocity.vz)
            pre_vx = entity.velocity.vx
            vel_a, vel_b = self.resolve_collision(entity, collider_x, axis='x')
            entity.velocity = vel_a
            if not collider_x.is_static:
                collider_x.velocity = vel_b
                collider_x.is_resting = False
                collider_x.is_sleeping = False
            thermal_delta += self._kinetic_to_thermal(entity, v_before, entity.velocity)
            if pre_vx > D0:
                new_x = collider_x.aabb().min_x - entity.size[0]
            else:
                new_x = collider_x.aabb().max_x
            if abs(entity.velocity.vx) < _V_REST_THRESHOLD:
                entity.velocity.vx = D0

        # ---- 8. Z-AXIS COLLISION (always check) ----
        collider_z = self.detect_collision(
            entity, Position(new_x, new_y, new_z),
            all_entities
        )
        if collider_z is not None:
            collisions.append(collider_z.entity_id)
            v_before = Velocity(entity.velocity.vx, entity.velocity.vy, entity.velocity.vz)
            pre_vz = entity.velocity.vz
            vel_a, vel_b = self.resolve_collision(entity, collider_z, axis='z')
            entity.velocity = vel_a
            if not collider_z.is_static:
                collider_z.velocity = vel_b
                collider_z.is_resting = False
                collider_z.is_sleeping = False
            thermal_delta += self._kinetic_to_thermal(entity, v_before, entity.velocity)
            if pre_vz > D0:
                new_z = collider_z.aabb().min_z - entity.size[2]
            else:
                new_z = collider_z.aabb().max_z
            if abs(entity.velocity.vz) < _V_REST_THRESHOLD:
                entity.velocity.vz = D0

        # ---- 9. SPACE BOUNDARY ----
        if new_y < D0:
            v_before = Velocity(entity.velocity.vx, entity.velocity.vy, entity.velocity.vz)
            new_y = D0
            entity.velocity.vy = D0
            entity.is_resting = True
            thermal_delta += self._kinetic_to_thermal(entity, v_before, entity.velocity)

        # ---- 10. UPDATE POSITION ----
        old_pos = entity.position
        entity.position = Position(new_x, new_y, new_z)
        delta = (new_x - old_pos.x, new_y - old_pos.y, new_z - old_pos.z)

        # ---- 11. SUPPORT CHECK ----
        if not entity.is_resting:
            support = self.detect_support(entity, all_entities)
            if support is not None and entity.velocity.vy >= D0:
                entity.is_resting = True
                entity.velocity.vy = D0
                entity.position = Position(
                    entity.position.x,
                    support.aabb().max_y,
                    entity.position.z,
                )

        # ---- 12. APPLY THERMAL DELTA ----
        entity.thermal.temperature_ubp += thermal_delta

        # ---- 13. COHERENCE SNAP ----
        entity.apply_coherence_snap()

        # ---- 14. THERMAL EXCHANGE WITH AMBIENT ----
        old_T = entity.thermal.temperature_ubp
        entity.apply_thermal_exchange(self.ambient)
        thermal_delta += entity.thermal.temperature_ubp - old_T

        # ---- 15. ANGULAR DYNAMICS ----
        self.apply_angular_damping(entity)
        self.integrate_orientation(entity)

        return PhysicsResultV3(
            entity_id=entity.entity_id,
            delta_position=delta,
            new_velocity=entity.velocity,
            new_angular_velocity=entity.angular_velocity,
            new_orientation=entity.orientation,
            forces_applied=forces,
            collisions=collisions,
            is_resting=entity.is_resting,
            thermal_delta=thermal_delta,
        )
