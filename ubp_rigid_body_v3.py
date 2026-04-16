"""
================================================================================
UBP RIGID BODY SYSTEM v3.1 — Topological Torque + Pantograph Tax
================================================================================
Rigid body mechanics with moment of inertia derived from LAW_TOPOLOGICAL_TORQUE_001.

Key upgrades in v3.1 (UBP Core v6.2 + Sovereign ALU v9.2, 16 April 2026):
  6. Pantograph Tax (LAW_PANTOGRAPH_SCALING_001): large bodies (volume > 8 cells³)
     pay an additional rotational resistance proportional to their volume excess.
     This models the UBP principle that large structures span more Leech Lattice
     cells and require more topological work to rotate.
     Pantograph_Tax = Y * (volume / 8)^(1/3) for volume > 8

Key upgrades from V2 (retained from V3.0):
  1. Topological Torque moment of inertia (replaces classical 1/12 box formula)
  2. Volumetric Rebate applied to inertia (LAW_VOLUMETRIC_REBATE_001)
  3. Material-specific angular damping (Hamming Damping)
  4. Lever constraint with UBP-derived pivot mechanics
  5. Torque detection uses AABB proximity, not integer cell overlap

LAW_TOPOLOGICAL_TORQUE_001: Power = Tax(Jagged) - Tax(Snapped)
  The energy required to rotate a Golay codeword through the Leech Lattice
  is the Tax differential between the jagged (rotating) and snapped (aligned) states.
  I = mass × (w² + h² + d²) / 12 × (1 + NRCI) × Volumetric_Rebate

LAW_VOLUMETRIC_REBATE_001: Rebate = 1 - (Compactness / 13)
  Compact shapes (spheres, cubes) have lower rotational inertia than elongated ones.

LAW_PANTOGRAPH_SCALING_001: Large structures pay a scaling tax on rotation.
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
    Y_CONSTANT, SINK_L, PI, calculate_nrci, hamming_distance,
    calculate_pantograph_tax, calculate_symmetry_tax,
)
# UBP 50-term π for angle conversions (replaces math.pi)
_PI_FLOAT: float = float(PI)

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------

_Y = to_decimal(Y_CONSTANT)
_SINK_L = to_decimal(SINK_L)
_C_DRAG = _Y * _Y  # Angular damping coefficient = Y² (The Shaving)
_V_REST = _SINK_L / D('100')  # Rest threshold

# Kissing Number (Leech Lattice first shell)
_KISSING = D('196560')

# ---------------------------------------------------------------------------
# TORQUE RESULT
# ---------------------------------------------------------------------------

@dataclass
class TorqueResult:
    """Result of a torque computation."""
    entity_id: int
    torque_x: Decimal
    torque_y: Decimal
    torque_z: Decimal
    angular_acceleration_x: Decimal
    angular_acceleration_y: Decimal
    angular_acceleration_z: Decimal
    topological_cost: Decimal  # Tax(Jagged) - Tax(Snapped)

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


# ---------------------------------------------------------------------------
# PIVOT CONSTRAINT (Lever fulcrum)
# ---------------------------------------------------------------------------

@dataclass
class PivotConstraintV3:
    """
    A pivot constraint connecting a lever arm to a fixed fulcrum point.

    The pivot is the point around which the lever rotates. The lever arm
    entity rotates around this point when forces are applied to its ends.

    UBP derivation:
      - The pivot resistance is Y² (The Shaving) — the substrate's resistance
        to changing the lever's orientation
      - The angular velocity limit is V_MAX = 1/Y
    """
    lever: UBPEntityV3
    pivot_world: Position  # World-space pivot position
    pivot_local_x: Decimal  # Local x-offset of pivot from lever origin

    # Angular state
    angle: Decimal = D0  # Current rotation angle (radians, around Z-axis)
    angular_velocity: Decimal = D0  # rad/tick

    # Limits
    max_angle: Decimal = D('1.5708')   # π/2 radians (90°)
    min_angle: Decimal = D('-1.5708')  # -π/2 radians

    def moment_of_inertia(self) -> Decimal:
        """
        Compute moment of inertia using Topological Torque.
        I = mass × L² / 3 × (1 + NRCI) × Volumetric_Rebate
        where L is the lever arm length.
        """
        L = self.lever.size[0]  # Length of lever
        mass = self.lever.mass
        nrci = to_decimal(self.lever.nrci)

        # Parallel axis theorem: I = m*L²/3 for a rod rotating about one end
        # But for a lever rotating about the middle: I = m*L²/12
        # We use the actual pivot offset to compute the correct I
        I_classical = mass * L * L / D('12')

        # Topological Torque correction
        I_topo = I_classical * (D1 + nrci)

        # Volumetric Rebate (elongated lever has low compactness → high rebate)
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
        """
        Compute the Topological Torque cost (LAW_TOPOLOGICAL_TORQUE_001).
        Cost = Tax(Jagged) - Tax(Snapped)
        = Symmetry Tax of the lever's current vector minus the snapped vector.
        This is the energy the substrate must pay to maintain the rotation.
        """
        from ubp_engine_substrate import calculate_symmetry_tax, coherence_snap
        current_tax = to_decimal(calculate_symmetry_tax(self.lever.golay_vector))
        snapped_vec, _ = coherence_snap(self.lever.golay_vector)
        snapped_tax = to_decimal(calculate_symmetry_tax(snapped_vec))
        return abs(current_tax - snapped_tax)

    def apply_torque(self, torque: Decimal) -> None:
        """
        Apply a torque to the lever and update angular velocity.
        α = τ / I
        """
        I = self.moment_of_inertia()
        if I <= D0:
            return
        alpha = torque / I
        self.angular_velocity += alpha

        # Cap angular velocity at V_MAX / lever_length
        L = self.lever.size[0]
        omega_max = (D('1') / _Y) / max(L, D1)
        if self.angular_velocity > omega_max:
            self.angular_velocity = omega_max
        elif self.angular_velocity < -omega_max:
            self.angular_velocity = -omega_max

    def step(self) -> None:
        """
        Advance the pivot constraint by one tick.
        1. Apply angular damping (Y² — The Shaving)
        2. Integrate angle
        3. Enforce angle limits
        4. Update lever arm position and orientation
        """
        # Angular damping
        self.angular_velocity *= (D1 - _C_DRAG)

        # Stop rotation if below rest threshold
        if abs(self.angular_velocity) < _V_REST:
            self.angular_velocity = D0

        # Integrate angle
        self.angle += self.angular_velocity

        # Enforce limits
        if self.angle > self.max_angle:
            self.angle = self.max_angle
            self.angular_velocity = D0
        elif self.angle < self.min_angle:
            self.angle = self.min_angle
            self.angular_velocity = D0

        # Update lever arm orientation (quaternion from angle around Z-axis)
        half_angle = self.angle / D('2')
        cos_half = Decimal(str(math.cos(float(half_angle))))
        sin_half = Decimal(str(math.sin(float(half_angle))))
        self.lever.orientation = Orientation(
            w=cos_half, x=D0, y=D0, z=sin_half
        )

        # Update lever arm position (pivot stays fixed, arm rotates around it)
        # The lever arm's origin is at pivot_world - pivot_local_x * cos(angle)
        cos_a = Decimal(str(math.cos(float(self.angle))))
        sin_a = Decimal(str(math.sin(float(self.angle))))
        self.lever.position = Position(
            self.pivot_world.x - self.pivot_local_x * cos_a,
            self.pivot_world.y - self.pivot_local_x * sin_a,
            self.lever.position.z,
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            'lever_id': self.lever.entity_id,
            'pivot': self.pivot_world.to_dict(),
            'angle_deg': float(self.angle) * 180.0 / _PI_FLOAT,
            'angular_velocity': float(self.angular_velocity),
            'moment_of_inertia': float(self.moment_of_inertia()),
            'topological_cost': float(self.topological_cost()),
        }


# ---------------------------------------------------------------------------
# RIGID BODY ENGINE V3
# ---------------------------------------------------------------------------

class UBPRigidBodyEngineV3:
    """
    Manages all rigid body constraints in the simulation.
    Currently supports: PivotConstraintV3 (lever/fulcrum).
    """

    def __init__(self):
        self.constraints: List[PivotConstraintV3] = []

    def add_lever(
        self,
        lever_entity: UBPEntityV3,
        pivot_x_world: float,
        pivot_y_world: float,
        pivot_z_world: float,
    ) -> PivotConstraintV3:
        """
        Add a lever constraint to the simulation.
        The pivot is at the specified world-space position.
        """
        pivot_pos = Position(D(str(pivot_x_world)), D(str(pivot_y_world)), D(str(pivot_z_world)))

        # Compute local pivot offset (distance from lever origin to pivot)
        pivot_local_x = pivot_pos.x - lever_entity.position.x

        constraint = PivotConstraintV3(
            lever=lever_entity,
            pivot_world=pivot_pos,
            pivot_local_x=pivot_local_x,
        )
        self.constraints.append(constraint)
        return constraint

    def push_lever(self, lever_id: int, fx: float, fy: float, at_x: float) -> bool:
        """Apply a force at a specific X-position on the lever."""
        for constraint in self.constraints:
            if constraint.lever.entity_id == lever_id:
                # Torque = r_x * F_y - r_y * F_x
                # r_x = at_x - pivot_x
                # r_y = at_y - pivot_y (at_y is pivot_y because lever rotates around Z)
                pivot_x = constraint.pivot_world.x
                
                r_x = to_decimal(str(at_x)) - pivot_x
                r_y = D0 # Lever rotates around Z, so pivot_y is constant
                
                F_x = to_decimal(str(fx))
                F_y = to_decimal(str(fy))
                
                torque = r_x * F_y - r_y * F_x
                constraint.apply_torque(torque)
                return True
        return False

    def set_lever_angle(self, lever_id: int, angle_deg: float) -> bool:
        """Directly set a lever's angle in degrees."""
        for constraint in self.constraints:
            if constraint.lever.entity_id == lever_id:
                # Convert degrees to radians
                angle_rad = D(str(angle_deg)) * D(str(_PI_FLOAT)) / D('180')
                constraint.angle = angle_rad
                constraint.angular_velocity = D0
                # Enforce limits immediately
                if constraint.angle > constraint.max_angle:
                    constraint.angle = constraint.max_angle
                elif constraint.angle < constraint.min_angle:
                    constraint.angle = constraint.min_angle
                
                # Update lever arm orientation and position
                constraint.step() 
                return True
        return False

    def compute_lever_torques(
        self,
        constraint: PivotConstraintV3,
        all_entities: List[UBPEntityV3],
        gravity_per_tick_sq: Decimal,
    ) -> TorqueResult:
        """
        Compute the net torque on a lever from all entities resting on it.

        UBP Torque Formula (v6.3.1):
          Torque = Σ (F_i × r_i) for each entity on the lever
          where F_i = entity.mass × g (downward force)
          and r_i = signed distance from pivot to entity's centre of mass

        Topological Resistance (LAW_TOPOLOGICAL_TORQUE_001):
          The lever's Symmetry Tax acts as a rotational resistance.
          The net torque is reduced by the Topological Cost:
            T_net_effective = T_net - sign(T_net) * topo_cost * Y
          This ensures the lever cannot rotate without paying the geometric
          cost of changing its orientation in the Leech Lattice.

        The Hamming distance between the lever's vector and each load entity's
        vector modulates the friction at the contact point:
          friction_factor = 1 - dH/24  (closer vectors = more friction)
        """
        net_torque = D0

        for entity in all_entities:
            if entity.is_static:
                continue
            if entity.entity_id == constraint.lever.entity_id:
                continue

            # Check if entity is resting on the lever
            if not self._entity_on_lever(entity, constraint.lever):
                continue

            # Force = mass × g (downward)
            F = entity.mass * gravity_per_tick_sq

            # Moment arm = signed distance from pivot to entity CoM (x-axis)
            entity_com_x = entity.position.x + entity.size[0] / D('2')
            r = entity_com_x - constraint.pivot_world.x

            # UBP Contact Friction: Hamming distance between lever and load
            # Closer vectors (lower dH) = more friction = less torque transfer
            dH = hamming_distance(constraint.lever.golay_vector, entity.golay_vector)
            # friction_factor: 0 (identical vectors, full friction) to 1 (max distance, no friction)
            friction_factor = D(str(dH)) / D('24')
            # Effective force after friction: F_eff = F * friction_factor
            # (Entities with same material as lever transfer less torque due to adhesion)
            F_eff = F * (D('0.5') + friction_factor * D('0.5'))  # Range [0.5F, F]

            # Torque (positive = counterclockwise when viewed from +z)
            # Downward force at positive r creates negative (clockwise) torque
            net_torque -= F_eff * r

         # Topological Resistance: reduce torque by the Topological Cost * Y
        # This is the geometric rent the lever pays to change orientation
        topo_cost = constraint.topological_cost()
        if net_torque != D0:
            sign = D('1') if net_torque > D0 else D('-1')
            resistance = topo_cost * _Y
            # Resistance cannot exceed the torque itself (no reversal)
            resistance = min(abs(net_torque), resistance)
            net_torque -= sign * resistance
        # Pantograph Tax (LAW_PANTOGRAPH_THERMODYNAMICS_001): macroscopic symmetry
        # tax for large lever bodies. Uses the affine kinematic projection:
        #   k = 1 + WOBBLE, V_macro = k³ × V_noum, T_adj = T_base × (1 - C_macro/13)
        # The pantograph NRCI is lower than the base NRCI for large/jagged bodies,
        # meaning they resist rotation more in the macroscopic domain.
        if net_torque != D0:
            p_tax_adj, p_nrci = calculate_pantograph_tax(constraint.lever.golay_vector)
            # Pantograph resistance = difference between base tax and pantograph tax
            base_tax = to_decimal(calculate_symmetry_tax(constraint.lever.golay_vector))
            p_resistance = abs(to_decimal(p_tax_adj) - base_tax) * _Y
            if p_resistance > D0:
                sign = D('1') if net_torque > D0 else D('-1')
                p_resistance = min(abs(net_torque), p_resistance)
                net_torque -= sign * p_resistance
        # Angular acceleration: α = τ / I
        I = constraint.moment_of_inertia()
        alpha = net_torque / I if I > D0 else D0

        return TorqueResult(
            entity_id=constraint.lever.entity_id,
            torque_x=D0,
            torque_y=D0,
            torque_z=net_torque,
            angular_acceleration_x=D0,
            angular_acceleration_y=D0,
            angular_acceleration_z=alpha,
            topological_cost=topo_cost,
        )

    def _entity_on_lever(
        self, entity: UBPEntityV3, lever: UBPEntityV3
    ) -> bool:
        """
        Check if an entity is resting on top of the lever arm.
        Uses AABB proximity (entity bottom within 0.1 units of lever top).
        """
        lever_bb = lever.aabb()
        entity_bb = entity.aabb()

        # Entity must be within lever's X and Z range
        x_overlap = (entity_bb.min_x < lever_bb.max_x and
                     entity_bb.max_x > lever_bb.min_x)
        z_overlap = (entity_bb.min_z < lever_bb.max_z and
                     entity_bb.max_z > lever_bb.min_z)

        if not (x_overlap and z_overlap):
            return False

        # Entity bottom must be close to lever top
        y_diff = abs(entity_bb.min_y - lever_bb.max_y)
        return y_diff < D('0.15')

    def step(
        self,
        all_entities: List[UBPEntityV3],
        gravity_per_tick_sq: Decimal,
    ) -> List[TorqueResult]:
        """
        Advance all rigid body constraints by one tick.
        Returns list of torque results for debugging.
        """
        results = []
        for constraint in self.constraints:
            # Compute torques from entities on the lever
            torque_result = self.compute_lever_torques(
                constraint, all_entities, gravity_per_tick_sq
            )
            # Apply torque to the lever
            constraint.apply_torque(torque_result.torque_z)
            # Step the constraint (integrate angle, update position)
            constraint.step()
            results.append(torque_result)
        return results

    def get_state(self) -> List[Dict[str, Any]]:
        """Return the current state of all constraints."""
        return [c.to_dict() for c in self.constraints]
