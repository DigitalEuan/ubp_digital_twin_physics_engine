"""
================================================================================
UBP RIGID BODY SYSTEM v3.2 — Topological Torque
================================================================================
V3.2 Fixes:
  1. REDUCED ANGULAR DAMPING — from (1 - Y²) ≈ 0.9300 per tick to
     (1 - Y²/10) ≈ 0.9930 per tick. The original damping killed angular
     velocity in ~14 ticks, making the lever snap back instantly. The new
     value gives ~143 ticks of free rotation — a physically realistic lever.

  2. SET_ANGLE METHOD — allows direct angle setting for lever positioning.
     The user can place the lever at any angle before loading it.

  3. PUSH-TO-TORQUE — when an impulse is applied to a lever arm entity,
     it is converted to torque on the pivot constraint rather than linear
     velocity. This makes push buttons actually rotate the lever.

  4. LEVER ENTITY POSITION TRACKING — the lever arm's world position is
     correctly updated each tick based on the pivot angle, so entities
     placed on the lever rest on its actual rotated surface.

  5. ENTITY-ON-LEVER uses rotated AABB — accounts for the lever's current
     angle when checking if a block is resting on it.
================================================================================
"""

from __future__ import annotations
import math
from dataclasses import dataclass
from decimal import Decimal, getcontext
from fractions import Fraction
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 50

from ubp_entity_v3 import (
    UBPEntityV3, EntityType, Position, Velocity, AngularVelocity,
    Orientation, AABB, D, D0, D1, to_decimal
)
from ubp_engine_substrate import (
    Y_CONSTANT, SINK_L, calculate_nrci, hamming_distance,
)

_Y = to_decimal(Y_CONSTANT)
_SINK_L = to_decimal(SINK_L)
_C_DRAG = _Y * _Y
# V3.2: Reduced damping — Y²/10 instead of Y² so lever rotates freely
_ANGULAR_DAMPING = _C_DRAG / D('10')
_V_REST = _SINK_L / D('100')
_KISSING = D('196560')


@dataclass
class TorqueResult:
    entity_id: int
    torque_x: Decimal
    torque_y: Decimal
    torque_z: Decimal
    angular_acceleration_x: Decimal
    angular_acceleration_y: Decimal
    angular_acceleration_z: Decimal
    topological_cost: Decimal

    def to_dict(self) -> Dict[str, float]:
        return {
            'torque_x': float(self.torque_x),
            'torque_y': float(self.torque_y),
            'torque_z': float(self.torque_z),
            'alpha_x': float(self.angular_acceleration_x),
            'alpha_y': float(self.angular_acceleration_y),
            'alpha_z': float(self.angular_acceleration_z),
            'topological_cost': float(self.topological_cost),
        }


@dataclass
class PivotConstraintV3:
    """
    A pivot constraint connecting a lever arm to a fixed fulcrum point.

    V3.2: Reduced angular damping, set_angle(), push-to-torque conversion.
    """
    lever: UBPEntityV3
    pivot_world: Position
    pivot_local_x: Decimal

    angle: Decimal = D0
    angular_velocity: Decimal = D0

    max_angle: Decimal = D('1.5708')
    min_angle: Decimal = D('-1.5708')

    def moment_of_inertia(self) -> Decimal:
        L = self.lever.size[0]
        mass = self.lever.mass
        nrci = to_decimal(self.lever.nrci)
        I_classical = mass * L * L / D('12')
        I_topo = I_classical * (D1 + nrci)
        w, h, d = self.lever.size
        volume = w * h * d
        surface = D('2') * (w*h + h*d + w*d)
        if surface > D0:
            compactness = (volume ** D('0.6667')) / surface
            rebate = D1 - compactness / D('13')
            rebate = max(D('0.5'), min(D1, rebate))
        else:
            rebate = D1
        return I_topo * rebate

    def topological_cost(self) -> Decimal:
        from ubp_engine_substrate import calculate_symmetry_tax, coherence_snap
        current_tax = to_decimal(calculate_symmetry_tax(self.lever.golay_vector))
        snapped_vec, _ = coherence_snap(self.lever.golay_vector)
        snapped_tax = to_decimal(calculate_symmetry_tax(snapped_vec))
        return abs(current_tax - snapped_tax)

    def apply_torque(self, torque: Decimal) -> None:
        I = self.moment_of_inertia()
        if I <= D0:
            return
        alpha = torque / I
        self.angular_velocity += alpha
        L = self.lever.size[0]
        omega_max = (D('1') / _Y) / max(L, D1)
        if self.angular_velocity > omega_max:
            self.angular_velocity = omega_max
        elif self.angular_velocity < -omega_max:
            self.angular_velocity = -omega_max

    def apply_push_impulse(self, force_x: float, force_y: float, at_x: float) -> None:
        """
        Convert a linear push impulse into torque on the lever.
        Torque = F × r, where r is the distance from pivot to force application point.
        This is called when the user pushes a lever arm entity.
        """
        r = D(str(at_x)) - self.pivot_world.x
        # Vertical force creates torque: τ = F_y × r
        torque = D(str(force_y)) * r
        # Horizontal force also creates torque at the lever tip: τ = F_x × lever_height
        torque += D(str(force_x)) * self.lever.size[1]
        self.apply_torque(torque)

    def set_angle(self, angle_deg: float) -> None:
        """
        Directly set the lever angle in degrees.
        Clamps to [min_angle, max_angle].
        """
        angle_rad = D(str(math.radians(angle_deg)))
        self.angle = max(self.min_angle, min(self.max_angle, angle_rad))
        self.angular_velocity = D0
        self._update_lever_transform()

    def _update_lever_transform(self) -> None:
        """Update lever arm position and orientation from current angle."""
        half_angle = self.angle / D('2')
        cos_half = Decimal(str(math.cos(float(half_angle))))
        sin_half = Decimal(str(math.sin(float(half_angle))))
        self.lever.orientation = Orientation(w=cos_half, x=D0, y=D0, z=sin_half)

        cos_a = Decimal(str(math.cos(float(self.angle))))
        sin_a = Decimal(str(math.sin(float(self.angle))))
        self.lever.position = Position(
            self.pivot_world.x - self.pivot_local_x * cos_a,
            self.pivot_world.y - self.pivot_local_x * sin_a,
            self.lever.position.z,
        )

    def step(self) -> None:
        """
        Advance the pivot constraint by one tick.
        V3.2: Uses reduced angular damping (_ANGULAR_DAMPING = Y²/10).
        """
        # V3.2: Reduced damping — lever rotates freely
        self.angular_velocity *= (D1 - _ANGULAR_DAMPING)

        if abs(self.angular_velocity) < _V_REST:
            self.angular_velocity = D0

        self.angle += self.angular_velocity

        if self.angle > self.max_angle:
            self.angle = self.max_angle
            self.angular_velocity = D0
        elif self.angle < self.min_angle:
            self.angle = self.min_angle
            self.angular_velocity = D0

        self._update_lever_transform()

    def get_lever_surface_y_at_x(self, world_x: float) -> float:
        """
        Get the Y position of the lever surface at a given world X coordinate.
        Accounts for the lever's current rotation angle.
        """
        pivot_x = float(self.pivot_world.x)
        pivot_y = float(self.pivot_world.y)
        angle = float(self.angle)
        r = world_x - pivot_x
        # Y at this X on the rotated lever
        y = pivot_y + r * math.sin(angle) + float(self.lever.size[1]) * math.cos(angle)
        return y

    def to_dict(self) -> Dict[str, Any]:
        return {
            'lever_id': self.lever.entity_id,
            'pivot': self.pivot_world.to_dict(),
            'angle_deg': float(self.angle) * 180.0 / math.pi,
            'angular_velocity': float(self.angular_velocity),
            'moment_of_inertia': float(self.moment_of_inertia()),
            'topological_cost': float(self.topological_cost()),
        }


class UBPRigidBodyEngineV3:
    """
    Manages all rigid body constraints in the simulation.
    V3.2: push-to-torque, set_angle, reduced damping.
    """

    def __init__(self):
        self.constraints: List[PivotConstraintV3] = []

    def add_lever(
        self, lever_entity: UBPEntityV3,
        pivot_x_world: float, pivot_y_world: float, pivot_z_world: float,
    ) -> PivotConstraintV3:
        pivot_pos = Position(D(str(pivot_x_world)), D(str(pivot_y_world)), D(str(pivot_z_world)))
        pivot_local_x = pivot_pos.x - lever_entity.position.x
        constraint = PivotConstraintV3(
            lever=lever_entity,
            pivot_world=pivot_pos,
            pivot_local_x=pivot_local_x,
        )
        self.constraints.append(constraint)
        return constraint

    def get_constraint_for_lever(self, lever_id: int) -> Optional[PivotConstraintV3]:
        """Find the constraint for a given lever entity ID."""
        for c in self.constraints:
            if c.lever.entity_id == lever_id:
                return c
        return None

    def push_lever(self, lever_id: int, force_x: float, force_y: float, at_x: float) -> bool:
        """
        Apply a push force to a lever, converting it to torque.
        Returns True if the lever was found and pushed.
        """
        constraint = self.get_constraint_for_lever(lever_id)
        if constraint is None:
            return False
        constraint.apply_push_impulse(force_x, force_y, at_x)
        return True

    def set_lever_angle(self, lever_id: int, angle_deg: float) -> bool:
        """
        Directly set a lever's angle in degrees.
        Returns True if the lever was found.
        """
        constraint = self.get_constraint_for_lever(lever_id)
        if constraint is None:
            return False
        constraint.set_angle(angle_deg)
        return True

    def compute_lever_torques(
        self, constraint: PivotConstraintV3,
        all_entities: List[UBPEntityV3],
        gravity_per_tick_sq: Decimal,
    ) -> TorqueResult:
        """
        Compute net torque on a lever from all entities resting on it.
        V3.2: Uses rotated lever surface for entity detection.
        """
        net_torque = D0

        for entity in all_entities:
            if entity.is_static:
                continue
            if entity.entity_id == constraint.lever.entity_id:
                continue
            if not self._entity_on_lever(entity, constraint):
                continue

            F = entity.mass * gravity_per_tick_sq
            entity_com_x = entity.position.x + entity.size[0] / D('2')
            r = entity_com_x - constraint.pivot_world.x
            net_torque -= F * r

        I = constraint.moment_of_inertia()
        alpha = net_torque / I if I > D0 else D0
        topo_cost = constraint.topological_cost()

        return TorqueResult(
            entity_id=constraint.lever.entity_id,
            torque_x=D0, torque_y=D0, torque_z=net_torque,
            angular_acceleration_x=D0, angular_acceleration_y=D0,
            angular_acceleration_z=alpha,
            topological_cost=topo_cost,
        )

    def _entity_on_lever(
        self, entity: UBPEntityV3, constraint: PivotConstraintV3
    ) -> bool:
        """
        Check if an entity is resting on the lever arm.
        V3.2: Uses the lever's rotated surface Y at the entity's X position.
        """
        lever = constraint.lever
        lever_bb = lever.aabb()
        entity_bb = entity.aabb()

        # Entity must be within lever's X range (horizontal extent)
        lever_x_min = float(constraint.pivot_world.x) - float(lever.size[0]) / 2
        lever_x_max = float(constraint.pivot_world.x) + float(lever.size[0]) / 2
        x_overlap = (float(entity_bb.min_x) < lever_x_max and
                     float(entity_bb.max_x) > lever_x_min)
        z_overlap = (float(entity_bb.min_z) < float(lever_bb.max_z) and
                     float(entity_bb.max_z) > float(lever_bb.min_z))

        if not (x_overlap and z_overlap):
            return False

        # Get the actual lever surface Y at the entity's centre X
        entity_centre_x = float(entity.position.x) + float(entity.size[0]) / 2
        lever_surface_y = constraint.get_lever_surface_y_at_x(entity_centre_x)

        y_diff = abs(float(entity_bb.min_y) - lever_surface_y)
        return y_diff < 0.3  # Slightly larger tolerance for rotated surface

    def step(
        self, all_entities: List[UBPEntityV3],
        gravity_per_tick_sq: Decimal,
    ) -> List[TorqueResult]:
        results = []
        for constraint in self.constraints:
            torque_result = self.compute_lever_torques(
                constraint, all_entities, gravity_per_tick_sq
            )
            constraint.apply_torque(torque_result.torque_z)
            constraint.step()
            results.append(torque_result)
        return results

    def get_state(self) -> List[Dict[str, Any]]:
        return [c.to_dict() for c in self.constraints]
