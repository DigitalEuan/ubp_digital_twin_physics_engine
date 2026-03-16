"""
================================================================================
UBP PHYSICS ENGINE v3.0
================================================================================
The deterministic physics engine for the UBP Digital Twin.

All constants are derived from UBP laws — no empirical tuning.

Key upgrades from V2:
  1. Equivalence Principle gravity (uniform for all masses — V2 bug fixed)
  2. Thermal effects on drag (air density is temperature-dependent)
  3. Ambient environment integration (temperature, air density, pressure)
  4. Topological Torque moment of inertia for angular dynamics
  5. Material-specific friction (Hamming distance between entity and surface vectors)
  6. Phase-aware collision (gas entities don't collide with solid entities)

Physics constants (all UBP-derived):
  g_tick²  = G_EARTH × Y / 3600     (gravity per tick at 60 tps)
  C_DRAG   = Y²                      (LAW_ONTOLOGICAL_FRICTION_001, The Shaving)
  V_MAX    = 1/Y                     (substrate speed limit)
  μ        = 1 − dH(a,b)/24         (LAW_INTERACTION_RATIONAL)
  e        = NRCI(a XOR b)           (collision restitution, LAW_COMP_001)
  V_REST   = SINK_L / 100            (rest threshold from 13D Sink leakage)
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

# Gravity per tick² (Equivalence Principle: uniform for all masses)
# g_tick² = G_EARTH × Y / 60² = 9.80665 × 0.2647 / 3600 ≈ 0.000721
_G_PER_TICK_SQ: Decimal = _G_EARTH / D('3600') * _Y

# Drag coefficient = Y² (The Shaving — LAW_ONTOLOGICAL_FRICTION_001)
_C_DRAG: Decimal = _Y * _Y

# Speed limit = 1/Y ≈ 3.778 cells/tick
_V_MAX: Decimal = D('1') / _Y

# Rest threshold = SINK_L / 100 (13D Sink leakage)
_V_REST_THRESHOLD: Decimal = _SINK_L / D('100')

# Minimum separation to avoid overlap (1 Planck unit)
_EPSILON: Decimal = D('1E-9')

# ---------------------------------------------------------------------------
# PHYSICS RESULT
# ---------------------------------------------------------------------------

@dataclass
class PhysicsResultV3:
    """Result of a single physics step for one entity."""
    entity_id: int
    delta_position: Tuple[Decimal, Decimal, Decimal]
    new_velocity: Velocity
    new_angular_velocity: AngularVelocity
    new_orientation: Orientation
    forces_applied: Dict[str, Decimal]
    collisions: List[int]  # entity_ids of colliders
    is_resting: bool
    thermal_delta: Decimal  # Change in temperature_ubp this tick


# ---------------------------------------------------------------------------
# PHYSICS ENGINE V3
# ---------------------------------------------------------------------------

class UBPPhysicsEngineV3:
    """
    The V3 UBP deterministic physics engine.

    Operates on UBPEntityV3 objects. Called once per tick by UBPSpaceV3.
    """

    def __init__(self, ambient: Optional[AmbientEnvironment] = None):
        self.ambient = ambient or AmbientEnvironment()
        # Air density in UBP units (temperature-dependent)
        self._rho_air: Decimal = to_decimal(self.ambient.air_density_ubp)
        self._T_ambient: Decimal = to_decimal(self.ambient.temperature_ubp)

    def update_ambient(self, ambient: AmbientEnvironment) -> None:
        """Update the ambient environment (e.g., temperature change)."""
        self.ambient = ambient
        self._rho_air = to_decimal(ambient.air_density_ubp)
        self._T_ambient = to_decimal(ambient.temperature_ubp)

    # -----------------------------------------------------------------------
    # GRAVITY
    # -----------------------------------------------------------------------

    def compute_gravity(self, entity: UBPEntityV3) -> Decimal:
        """
        Compute gravitational acceleration (Equivalence Principle).
        All masses fall at the same rate: a = -g_tick²
        Only drag and friction are mass-dependent.
        Returns: vy acceleration (negative = downward)
        """
        return -_G_PER_TICK_SQ

    # -----------------------------------------------------------------------
    # AIR RESISTANCE
    # -----------------------------------------------------------------------

    def compute_air_resistance(self, entity: UBPEntityV3) -> Velocity:
        """
        Compute air resistance (drag) on an entity.

        F_drag = C_DRAG × ρ_air × v² / inertia
        where C_DRAG = Y² (The Shaving), ρ_air is temperature-dependent.

        Temperature effect: ρ_air ∝ 1/T (ideal gas law)
        ρ_air_T = ρ_air_STP × T_STP / T_current
        """
        # Temperature-corrected air density
        T_STP = D('3.2329')  # 293.15 K in UBP units
        if self._T_ambient > D0:
            rho_corrected = self._rho_air * T_STP / self._T_ambient
        else:
            rho_corrected = self._rho_air

        drag_coeff = _C_DRAG * rho_corrected / entity.inertia

        # Quadratic drag (opposing velocity direction)
        vx, vy, vz = entity.velocity.vx, entity.velocity.vy, entity.velocity.vz
        ax = -drag_coeff * vx * abs(vx)
        ay = -drag_coeff * vy * abs(vy)
        az = -drag_coeff * vz * abs(vz)

        return Velocity(ax, ay, az)

    # -----------------------------------------------------------------------
    # FRICTION
    # -----------------------------------------------------------------------

    def compute_friction(
        self, entity: UBPEntityV3, surface: UBPEntityV3
    ) -> Velocity:
        """
        Compute kinetic friction between entity and surface.

        μ = 1 - dH(entity_vector, surface_vector) / 24
        (LAW_INTERACTION_RATIONAL: F = 1 / (1 + k × d²))

        F_friction = μ × g_tick² × sign(v) / inertia
        (opposes horizontal motion)
        """
        dH = hamming_distance(entity.golay_vector, surface.golay_vector)
        mu = D1 - D(str(dH)) / D('24')
        mu = max(D0, min(D1, mu))

        friction_mag = mu * _G_PER_TICK_SQ / entity.inertia

        # Apply opposing horizontal velocity
        ax = D0
        az = D0
        if abs(entity.velocity.vx) > _V_REST_THRESHOLD:
            ax = -friction_mag * (D1 if entity.velocity.vx > D0 else D('-1'))
        if abs(entity.velocity.vz) > _V_REST_THRESHOLD:
            az = -friction_mag * (D1 if entity.velocity.vz > D0 else D('-1'))

        return Velocity(ax, D0, az)

    # -----------------------------------------------------------------------
    # COLLISION DETECTION
    # -----------------------------------------------------------------------

    def detect_collision(
        self,
        entity: UBPEntityV3,
        test_position: Position,
        all_entities: List[UBPEntityV3],
    ) -> Optional[UBPEntityV3]:
        """
        Test if entity at test_position overlaps any other entity.
        Returns the first collider found (or None).
        Fluid particles are excluded from solid collision detection.
        """
        w, h, d = entity.size
        test_aabb = AABB(
            test_position.x, test_position.y, test_position.z,
            test_position.x + w, test_position.y + h, test_position.z + d,
        )
        for other in all_entities:
            if other.entity_id == entity.entity_id:
                continue
            # Fluid particles do not participate in solid collision
            if other.entity_type == EntityType.FLUID_EMITTER:
                continue
            # Gas-phase entities don't block solid entities
            if other.material.phase_stp == 1 and not other.is_static:
                continue
            if test_aabb.overlaps(other.aabb()):
                return other
        return None

    def detect_support(
        self,
        entity: UBPEntityV3,
        all_entities: List[UBPEntityV3],
    ) -> Optional[UBPEntityV3]:
        """
        Test if entity is supported from below (resting on something).
        Tests a position 0.001 units below the current position.
        """
        test_pos = Position(
            entity.position.x,
            entity.position.y - D('0.001'),
            entity.position.z,
        )
        return self.detect_collision(entity, test_pos, all_entities)

    # -----------------------------------------------------------------------
    # COLLISION RESPONSE
    # -----------------------------------------------------------------------

    def resolve_collision(
        self,
        entity_a: UBPEntityV3,
        entity_b: UBPEntityV3,
    ) -> Tuple[Velocity, Velocity]:
        """
        Resolve a collision between two entities using UBP XOR Smash.

        Restitution coefficient = NRCI(a.vector XOR b.vector)
        (LAW_COMP_001 + LAW_ENG_SWITCH_001: Tax(A^B) = Tax(C), Efficiency = 11/12)

        Impulse-based collision response (1D along collision axis).
        """
        xor_vec = [a ^ b for a, b in zip(entity_a.golay_vector, entity_b.golay_vector)]
        restitution = to_decimal(calculate_nrci(xor_vec))

        # Relative velocity along y-axis (primary collision axis)
        rel_vy = entity_a.velocity.vy - entity_b.velocity.vy

        # Impulse magnitude
        m_a = entity_a.inertia
        m_b = entity_b.inertia if not entity_b.is_static else D('1E20')

        j = -(D1 + restitution) * rel_vy / (D1/m_a + D1/m_b)

        # Apply impulse
        new_vy_a = entity_a.velocity.vy + j / m_a
        new_vy_b = entity_b.velocity.vy - j / m_b if not entity_b.is_static else entity_b.velocity.vy

        return (
            Velocity(entity_a.velocity.vx, new_vy_a, entity_a.velocity.vz),
            Velocity(entity_b.velocity.vx, new_vy_b, entity_b.velocity.vz),
        )

    def apply_impulse(
        self,
        entity: UBPEntityV3,
        force_x: Decimal = D0,
        force_y: Decimal = D0,
        force_z: Decimal = D0,
    ) -> None:
        """
        Apply an external impulse force to an entity.
        Δv = F / inertia
        """
        entity.velocity.vx += force_x / entity.inertia
        entity.velocity.vy += force_y / entity.inertia
        entity.velocity.vz += force_z / entity.inertia
        entity.is_resting = False
        entity.is_sleeping = False

    # -----------------------------------------------------------------------
    # VELOCITY CAP
    # -----------------------------------------------------------------------

    def _cap_velocity(self, v: Velocity) -> Velocity:
        """Enforce the substrate speed limit V_MAX = 1/Y."""
        def cap(val: Decimal) -> Decimal:
            if val > _V_MAX:
                return _V_MAX
            if val < -_V_MAX:
                return -_V_MAX
            return val
        return Velocity(cap(v.vx), cap(v.vy), cap(v.vz))

    # -----------------------------------------------------------------------
    # ANGULAR DYNAMICS
    # -----------------------------------------------------------------------

    def apply_angular_damping(self, entity: UBPEntityV3) -> None:
        """
        Apply angular damping (Hamming Damping from LAW_ONTOLOGICAL_FRICTION_001).
        ω_new = ω × (1 - Y²) = ω × (1 - C_DRAG)
        """
        damp = D1 - _C_DRAG
        entity.angular_velocity.wx *= damp
        entity.angular_velocity.wy *= damp
        entity.angular_velocity.wz *= damp

        # Stop rotation if below rest threshold
        if entity.angular_velocity.magnitude() < _V_REST_THRESHOLD:
            entity.angular_velocity = AngularVelocity()

    def integrate_orientation(self, entity: UBPEntityV3) -> None:
        """
        Integrate angular velocity into orientation (quaternion integration).
        q_new = q + 0.5 × q × ω_quat × dt
        """
        wx = entity.angular_velocity.wx
        wy = entity.angular_velocity.wy
        wz = entity.angular_velocity.wz

        if wx == D0 and wy == D0 and wz == D0:
            return

        q = entity.orientation
        # Quaternion derivative: dq/dt = 0.5 * q * [0, wx, wy, wz]
        dw = D_HALF * (-q.x*wx - q.y*wy - q.z*wz)
        dx = D_HALF * ( q.w*wx + q.y*wz - q.z*wy)
        dy = D_HALF * ( q.w*wy - q.x*wz + q.z*wx)
        dz = D_HALF * ( q.w*wz + q.x*wy - q.y*wx)

        entity.orientation = Orientation(
            q.w + dw, q.x + dx, q.y + dy, q.z + dz
        ).normalise()

    # -----------------------------------------------------------------------
    # MAIN STEP
    # -----------------------------------------------------------------------

    def step(
        self,
        entity: UBPEntityV3,
        all_entities: List[UBPEntityV3],
        tick: int = 0,
    ) -> PhysicsResultV3:
        """
        Advance entity physics by one tick.

        Pipeline:
          1. Skip if static or sleeping
          2. Apply gravity (Equivalence Principle — uniform)
          3. Apply air resistance (temperature-corrected)
          4. Apply friction (if resting on surface)
          5. Cap velocity at V_MAX
          6. Compute new position (sub-cell accumulator)
          7. Detect and resolve Y-axis collision
          8. Detect and resolve X/Z-axis collision
          9. Enforce space boundaries
         10. Detect support (rest condition)
         11. Apply coherence snap (every N ticks)
         12. Apply thermal exchange
         13. Integrate angular velocity
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

        # ---- 5. SUB-CELL ACCUMULATOR ----
        entity._sub_x += entity.velocity.vx
        entity._sub_y += entity.velocity.vy
        entity._sub_z += entity.velocity.vz

        # Extract integer cell movement
        move_x = int(entity._sub_x)
        move_y = int(entity._sub_y)
        move_z = int(entity._sub_z)

        entity._sub_x -= D(str(move_x))
        entity._sub_y -= D(str(move_y))
        entity._sub_z -= D(str(move_z))

        # Compute new position
        new_x = entity.position.x + D(str(move_x)) + entity._sub_x
        new_y = entity.position.y + D(str(move_y)) + entity._sub_y
        new_z = entity.position.z + D(str(move_z)) + entity._sub_z

        # Reset sub-cell after applying
        entity._sub_x = D0
        entity._sub_y = D0
        entity._sub_z = D0

        new_pos = Position(new_x, new_y, new_z)

        # ---- 6. Y-AXIS COLLISION ----
        pre_collision_vy = entity.velocity.vy
        if new_y != entity.position.y:
            collider_y = self.detect_collision(
                entity, Position(entity.position.x, new_y, entity.position.z),
                all_entities
            )
            if collider_y is not None:
                collisions.append(collider_y.entity_id)
                # Resolve collision
                vel_a, vel_b = self.resolve_collision(entity, collider_y)
                entity.velocity = vel_a

                # Place entity on top of or below collider based on pre-collision direction
                if pre_collision_vy < D0:
                    # Falling down — place on top of collider
                    new_y = collider_y.aabb().max_y
                else:
                    # Moving up — place below collider
                    new_y = collider_y.aabb().min_y - entity.size[1]

                # Check rest condition
                if abs(entity.velocity.vy) < _V_REST_THRESHOLD:
                    entity.velocity.vy = D0
                    entity.is_resting = True

        # ---- 7. X-AXIS COLLISION ----
        if new_x != entity.position.x:
            collider_x = self.detect_collision(
                entity, Position(new_x, new_y, entity.position.z),
                all_entities
            )
            if collider_x is not None:
                collisions.append(collider_x.entity_id)
                pre_vx = entity.velocity.vx
                xor_vec = [a ^ b for a, b in zip(entity.golay_vector, collider_x.golay_vector)]
                restitution = to_decimal(calculate_nrci(xor_vec))
                entity.velocity.vx = -entity.velocity.vx * restitution
                if pre_vx > D0:
                    new_x = collider_x.aabb().min_x - entity.size[0]
                else:
                    new_x = collider_x.aabb().max_x
                if abs(entity.velocity.vx) < _V_REST_THRESHOLD:
                    entity.velocity.vx = D0

        # ---- 8. Z-AXIS COLLISION ----
        if new_z != entity.position.z:
            collider_z = self.detect_collision(
                entity, Position(new_x, new_y, new_z),
                all_entities
            )
            if collider_z is not None:
                collisions.append(collider_z.entity_id)
                pre_vz = entity.velocity.vz
                xor_vec = [a ^ b for a, b in zip(entity.golay_vector, collider_z.golay_vector)]
                restitution = to_decimal(calculate_nrci(xor_vec))
                entity.velocity.vz = -entity.velocity.vz * restitution
                if pre_vz > D0:
                    new_z = collider_z.aabb().min_z - entity.size[2]
                else:
                    new_z = collider_z.aabb().max_z
                if abs(entity.velocity.vz) < _V_REST_THRESHOLD:
                    entity.velocity.vz = D0

        # ---- 9. SPACE BOUNDARY ----
        if new_y < D0:
            new_y = D0
            entity.velocity.vy = D0
            entity.is_resting = True

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

        # ---- 12. COHERENCE SNAP ----
        entity.apply_coherence_snap()

        # ---- 13. THERMAL EXCHANGE ----
        old_T = entity.thermal.temperature_ubp
        entity.apply_thermal_exchange(self.ambient)
        thermal_delta = entity.thermal.temperature_ubp - old_T

        # ---- 14. ANGULAR DYNAMICS ----
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
