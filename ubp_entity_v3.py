"""
================================================================================
UBP ENTITY SYSTEM v4.0
================================================================================
Every object in the V4 simulation is a UBPEntityV3. Unlike V2's monolithic
vectors, V3/V4 entities are built from composite materials (UBP KB elements).

Key upgrades from V3:
  1. Phi-Orbit Tick integration (LAW_PHI_ORBIT_1953) — vector evolves each tick
  2. NRCI live state via NCRIState (LAW_13D_SINK_001)
  3. Leech Lattice address (LAW_KISSING_EXPANSION_001) in to_threejs_state
  4. Metabolic rendering: opacity and tilt derived from live NRCI
  5. Synthesis Collision Event support via ubp_mechanics_v4
  6. Dissolution flag: entities below NRCI threshold flagged for removal
  7. Hybrid Stereoscopy Sigma (LAW_HYBRID_STEREOSCOPY_002) in mass calc

Key upgrades from V2 (retained from V3):
  1. Composite material system — entities have a MaterialRecipe
  2. Thermal state — temperature, heat capacity, heat transfer
  3. Topological Torque moment of inertia (LAW_TOPOLOGICAL_TORQUE_001)
  4. Volumetric Rebate applied to inertia (LAW_VOLUMETRIC_REBATE_001)
  5. Continuous Decimal positions (10^-12 Planck grid)
  6. Full Three.js serialisation (to_threejs_state)
================================================================================
"""

from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from enum import Enum
from fractions import Fraction
from typing import Any, Dict, List, Optional, Tuple

# Set Decimal precision to 50 significant figures (matches UBP 50-term π)
getcontext().prec = 50

# ---------------------------------------------------------------------------
# DECIMAL HELPERS
# ---------------------------------------------------------------------------
D = Decimal
D0 = D('0')
D1 = D('1')
D_HALF = D('0.5')
PLANCK_GRID = D('1E-12')  # Quantisation grid (Planck anchor)

def to_decimal(x) -> Decimal:
    """Convert Fraction, int, float, or str to Decimal."""
    if isinstance(x, Decimal):
        return x
    if isinstance(x, Fraction):
        return D(x.numerator) / D(x.denominator)
    return D(str(x))

# ---------------------------------------------------------------------------
# SUBSTRATE CONSTANTS (imported once at module load)
# ---------------------------------------------------------------------------
from ubp_engine_substrate import (
    Y_CONSTANT, Y_INV, PI, SINK_L, G_EARTH_MS2,
    calculate_symmetry_tax, calculate_nrci, hamming_distance,
    vector_from_math_dna, coherence_snap, encode_to_golay,
    _construction_tax_from_dna, GOLAY_BLOCK_LENGTH,
)
from ubp_materials import MaterialRecipe, MaterialRegistry, AmbientEnvironment

# UBP v4.0 Mechanics (Phi-Orbit, Synthesis, NRCI, Leech Addressing)
try:
    from ubp_mechanics_v4 import UBP_MECHANICS, NCRIState
    _UBP_MECHANICS_AVAILABLE = True
except ImportError:
    _UBP_MECHANICS_AVAILABLE = False
    UBP_MECHANICS = None

# Convert physics constants to Decimal for simulation use
_Y = to_decimal(Y_CONSTANT)
_Y_INV = to_decimal(Y_INV)
_SINK_L = to_decimal(SINK_L)
_G_EARTH = to_decimal(G_EARTH_MS2)

# Kissing number of the Leech Lattice (196560)
_KISSING = D('196560')

# Gravity per tick² (60 ticks/s, Equivalence Principle: uniform for all masses)
# g_tick = G_EARTH / 60² = 9.80665 / 3600 ≈ 0.002724 m/s² per tick²
# Scaled to simulation units (1 cell = 1 m): g_ubp = g_tick * Y (coherence scaling)
_G_PER_TICK_SQ: Decimal = _G_EARTH / D('3600') * _Y
_V_MAX: Decimal = D('1') / _Y  # Speed limit = 1/Y ≈ 3.778 cells/tick
_C_DRAG: Decimal = _Y * _Y    # Drag coefficient = Y² (The Shaving)

# Rest threshold = SINK_L / 100 (13D Sink leakage, normalised)
_V_REST_THRESHOLD: Decimal = _SINK_L / D('100')

# ---------------------------------------------------------------------------
# ENTITY TYPES
# ---------------------------------------------------------------------------

class EntityType(Enum):
    BLOCK        = "block"
    FLOOR        = "floor"
    WALL         = "wall"
    LEVER_ARM    = "lever_arm"
    LEVER_PIVOT  = "lever_pivot"
    FLUID_EMITTER = "fluid_emitter"
    SENSOR       = "sensor"
    CUSTOM       = "custom"

# ---------------------------------------------------------------------------
# POSITION AND VELOCITY
# ---------------------------------------------------------------------------

@dataclass
class Position:
    """Continuous 3D position in Decimal (Planck-grid quantised)."""
    x: Decimal = D0
    y: Decimal = D0
    z: Decimal = D0

    def quantise(self) -> 'Position':
        """Snap to Planck grid (10^-12)."""
        return Position(
            self.x.quantize(PLANCK_GRID),
            self.y.quantize(PLANCK_GRID),
            self.z.quantize(PLANCK_GRID),
        )

    def __add__(self, other: 'Position') -> 'Position':
        return Position(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: 'Position') -> 'Position':
        return Position(self.x - other.x, self.y - other.y, self.z - other.z)

    def to_dict(self) -> Dict[str, float]:
        return {'x': float(self.x), 'y': float(self.y), 'z': float(self.z)}


@dataclass
class Velocity:
    """3D velocity in Decimal (cells/tick)."""
    vx: Decimal = D0
    vy: Decimal = D0
    vz: Decimal = D0

    def magnitude_sq(self) -> Decimal:
        return self.vx * self.vx + self.vy * self.vy + self.vz * self.vz

    def magnitude(self) -> Decimal:
        return self.magnitude_sq().sqrt()

    def to_dict(self) -> Dict[str, float]:
        return {'vx': float(self.vx), 'vy': float(self.vy), 'vz': float(self.vz)}


@dataclass
class AngularVelocity:
    """Angular velocity (radians/tick) around each axis."""
    wx: Decimal = D0  # Roll
    wy: Decimal = D0  # Yaw
    wz: Decimal = D0  # Pitch

    def magnitude(self) -> Decimal:
        return (self.wx**2 + self.wy**2 + self.wz**2).sqrt()

    def to_dict(self) -> Dict[str, float]:
        return {'wx': float(self.wx), 'wy': float(self.wy), 'wz': float(self.wz)}


@dataclass
class Orientation:
    """Quaternion orientation (w, x, y, z) in Decimal."""
    w: Decimal = D1
    x: Decimal = D0
    y: Decimal = D0
    z: Decimal = D0

    def normalise(self) -> 'Orientation':
        mag = (self.w**2 + self.x**2 + self.y**2 + self.z**2).sqrt()
        if mag == D0:
            return Orientation()
        return Orientation(self.w/mag, self.x/mag, self.y/mag, self.z/mag)

    def to_dict(self) -> Dict[str, float]:
        return {'w': float(self.w), 'x': float(self.x),
                'y': float(self.y), 'z': float(self.z)}

    def to_euler_degrees(self) -> Tuple[float, float, float]:
        """Convert quaternion to Euler angles (degrees) for Three.js."""
        import math
        w, x, y, z = float(self.w), float(self.x), float(self.y), float(self.z)
        # Roll (x-axis)
        sinr_cosp = 2 * (w * x + y * z)
        cosr_cosp = 1 - 2 * (x * x + y * y)
        roll = math.atan2(sinr_cosp, cosr_cosp)
        # Pitch (y-axis)
        sinp = 2 * (w * y - z * x)
        pitch = math.asin(max(-1.0, min(1.0, sinp)))
        # Yaw (z-axis)
        siny_cosp = 2 * (w * z + x * y)
        cosy_cosp = 1 - 2 * (y * y + z * z)
        yaw = math.atan2(siny_cosp, cosy_cosp)
        return (math.degrees(roll), math.degrees(pitch), math.degrees(yaw))


# ---------------------------------------------------------------------------
# THERMAL STATE
# ---------------------------------------------------------------------------

@dataclass
class ThermalState:
    """
    Thermal state of an entity.

    temperature_ubp: current temperature in UBP units (T_K * Y / 24)
    heat_capacity: from material (LAW_TOPO_EFFICIENCY_001)
    heat_transfer: from material (The Shaving applied to thermal flow)
    """
    temperature_ubp: Decimal = D('3.2329')  # 293.15 K ambient
    heat_capacity: Decimal = D('0.0882')    # Iron default
    heat_transfer: Decimal = D('0.0234')    # Iron default

    @property
    def temperature_K(self) -> float:
        """Convert UBP temperature back to Kelvin: T_K = T_ubp × 24 / Y"""
        return float(self.temperature_ubp) * 24.0 / 0.26468

    def to_dict(self) -> Dict[str, float]:
        return {
            'temperature_ubp': float(self.temperature_ubp),
            'temperature_K': self.temperature_K,
            'heat_capacity': float(self.heat_capacity),
            'heat_transfer': float(self.heat_transfer),
        }


# ---------------------------------------------------------------------------
# AABB (Axis-Aligned Bounding Box)
# ---------------------------------------------------------------------------

@dataclass
class AABB:
    """Axis-Aligned Bounding Box in Decimal coordinates."""
    min_x: Decimal
    min_y: Decimal
    min_z: Decimal
    max_x: Decimal
    max_y: Decimal
    max_z: Decimal

    def overlaps(self, other: 'AABB') -> bool:
        """Test if two AABBs overlap (strict inequality — touching is not overlap)."""
        return (self.min_x < other.max_x and self.max_x > other.min_x and
                self.min_y < other.max_y and self.max_y > other.min_y and
                self.min_z < other.max_z and self.max_z > other.min_z)

    def centre(self) -> Position:
        return Position(
            (self.min_x + self.max_x) / D('2'),
            (self.min_y + self.max_y) / D('2'),
            (self.min_z + self.max_z) / D('2'),
        )


# ---------------------------------------------------------------------------
# UBP ENTITY V3
# ---------------------------------------------------------------------------

class UBPEntityV3:
    """
    A single entity in the V3 simulation space.

    Every entity has:
    - A UBP identity (Golay vector, Symmetry Tax, NRCI)
    - A composite material (MaterialRecipe from KB elements)
    - A thermal state (temperature, heat capacity, heat transfer)
    - A physical state (position, velocity, orientation, angular velocity)
    - A Topological Torque moment of inertia
    """

    _id_counter: int = 0

    def __init__(
        self,
        label: str,
        material_name: str = 'iron',
        position: Optional[Position] = None,
        size: Tuple[float, float, float] = (1.0, 1.0, 1.0),
        entity_type: EntityType = EntityType.BLOCK,
        is_static: bool = False,
        temperature_K: float = 293.15,
        custom_material: Optional[MaterialRecipe] = None,
    ):
        UBPEntityV3._id_counter += 1
        self.entity_id: int = UBPEntityV3._id_counter
        self.label: str = label
        self.entity_type: EntityType = entity_type
        self.is_static: bool = is_static

        # Size (width, height, depth) in simulation cells
        self.size: Tuple[Decimal, Decimal, Decimal] = (
            D(str(size[0])), D(str(size[1])), D(str(size[2]))
        )

        # Material
        if custom_material is not None:
            self.material: MaterialRecipe = custom_material
        else:
            self.material: MaterialRecipe = MaterialRegistry.get(material_name)

        # UBP Identity — derived from material type (not label) for consistency
        # The type_dna encodes the material composition, not the instance name
        self._type_dna = self._build_type_dna()
        self.golay_vector: List[int] = vector_from_math_dna(self._type_dna)
        self.symmetry_tax: Fraction = calculate_symmetry_tax(self.golay_vector)
        self.nrci: Fraction = calculate_nrci(self.golay_vector)
        self.construction_tax: Fraction = _construction_tax_from_dna(self._type_dna)

        # Mass: construction_tax (primary) + symmetry_tax (secondary correction)
        # construction_tax correctly orders heavy > standard > light
        self.mass: Decimal = to_decimal(
            self.construction_tax + self.symmetry_tax * Fraction(1, 10)
        )
        if self.mass <= D0:
            self.mass = D('0.1')

        # Moment of inertia (Topological Torque — LAW_TOPOLOGICAL_TORQUE_001)
        self.moment_of_inertia: Decimal = self._compute_topological_inertia()

        # Inertia (mass × (1 + NRCI)) — resistance to linear force
        self.inertia: Decimal = self.mass * (D1 + to_decimal(self.nrci))

        # Physical state
        self.position: Position = position or Position()
        self.velocity: Velocity = Velocity()
        self.orientation: Orientation = Orientation()
        self.angular_velocity: AngularVelocity = AngularVelocity()

        # Sub-cell accumulators (fractional position carry-over)
        self._sub_x: Decimal = D0
        self._sub_y: Decimal = D0
        self._sub_z: Decimal = D0

        # Thermal state
        from ubp_engine_substrate import Y_CONSTANT
        _Y_frac = Y_CONSTANT
        T_ubp = D(str(float(temperature_K) * float(_Y_frac) / 24.0))
        self.thermal: ThermalState = ThermalState(
            temperature_ubp=T_ubp,
            heat_capacity=to_decimal(self.material.aggregate_thermal_capacity),
            heat_transfer=to_decimal(self.material.aggregate_heat_transfer),
        )

        # Physics state flags
        self.is_resting: bool = False
        self.is_sleeping: bool = False  # No forces acting, skip physics
        self._sleep_counter: int = 0
        self._cells_cache: Optional[set] = None

        # Coherence snap counter (snap every 10 ticks to avoid overhead)
        self._snap_counter: int = 0
        self._snap_interval: int = 10

        # UBP v4.0 — Phi-Orbit NRCI state (LAW_PHI_ORBIT_1953 + LAW_13D_SINK_001)
        if _UBP_MECHANICS_AVAILABLE:
            self.nrci_state: NCRIState = UBP_MECHANICS.make_nrci_state(self.golay_vector)
        else:
            self.nrci_state = None

        # Leech Lattice address (LAW_KISSING_EXPANSION_001)
        self.lattice_cell: Tuple[int, int, int] = (0, 0, 0)
        if _UBP_MECHANICS_AVAILABLE:
            self.lattice_cell = UBP_MECHANICS.fold_to_cell(self.golay_vector)

        # Dissolution flag (LAW_TOPOLOGICAL_BUFFER_001)
        self.is_dissolving: bool = False

        # Phi-Orbit tick counter
        self._phi_tick_counter: int = 0
        self._phi_tick_interval: int = 5  # Apply Phi-Orbit every 5 simulation ticks

    def _build_type_dna(self) -> str:
        """
        Build the type DNA string from the material composition.
        This ensures all entities of the same material type share the same
        Golay vector (and thus the same Symmetry Tax and NRCI).
        """
        # Use the material's aggregate properties as the DNA
        mat = self.material
        parts = []
        for elem, count in mat.elements:
            parts.append(f"{elem.ubp_id}x{count}")
        composition_str = '+'.join(parts)
        return f"UBP_MATERIAL|{composition_str}|phase={mat.phase_stp}"

    def _compute_topological_inertia(self) -> Decimal:
        """
        Compute the moment of inertia using Topological Torque.

        LAW_TOPOLOGICAL_TORQUE_001: Power = Tax(Jagged) - Tax(Snapped)
        The rotational inertia is the energy cost of rotating a Golay codeword
        through the Leech Lattice. This is the Tax differential between the
        jagged (rotating) state and the snapped (aligned) state.

        Formula:
          I = mass * (w² + h² + d²) / 12 * (1 + NRCI) * Volumetric_Rebate

        The (1 + NRCI) factor is the Topological Torque correction:
          - High NRCI (coherent) = more resistance to rotation
          - Low NRCI (chaotic) = less resistance to rotation

        The Volumetric Rebate (LAW_VOLUMETRIC_REBATE_001):
          Rebate = 1 - (Compactness / 13)
          Compactness = V^(2/3) / Surface_Area
        """
        w, h, d = self.size
        # Classical box inertia
        I_classical = self.mass * (w*w + h*h + d*d) / D('12')

        # Topological Torque correction
        nrci_d = to_decimal(self.nrci)
        I_topo = I_classical * (D1 + nrci_d)

        # Volumetric Rebate
        volume = w * h * d
        surface = D('2') * (w*h + h*d + w*d)
        if surface > D0:
            compactness = (volume ** D('0.6667')) / surface
            rebate = D1 - compactness / D('13')
            rebate = max(D('0.5'), min(D1, rebate))  # Clamp to [0.5, 1.0]
        else:
            rebate = D1

        return I_topo * rebate

    def aabb(self) -> AABB:
        """Return the current Axis-Aligned Bounding Box."""
        w, h, d = self.size
        return AABB(
            min_x=self.position.x,
            min_y=self.position.y,
            min_z=self.position.z,
            max_x=self.position.x + w,
            max_y=self.position.y + h,
            max_z=self.position.z + d,
        )

    def centre_of_mass(self) -> Position:
        """Return the centre of mass position."""
        w, h, d = self.size
        return Position(
            self.position.x + w / D('2'),
            self.position.y + h / D('2'),
            self.position.z + d / D('2'),
        )

    def apply_coherence_snap(self) -> None:
        """
        Periodically snap the Golay vector to the nearest valid codeword.
        V4.0: Uses Phi-Orbit tick instead of plain coherence snap when
        ubp_mechanics_v4 is available (LAW_PHI_ORBIT_1953).
        Only runs every _snap_interval ticks to avoid overhead.
        """
        self._snap_counter += 1
        if self._snap_counter < self._snap_interval:
            return
        self._snap_counter = 0

        if _UBP_MECHANICS_AVAILABLE and self.nrci_state is not None:
            # V4.0 path: Phi-Orbit tick updates vector + NRCI atomically
            self._phi_tick_counter += 1
            if self._phi_tick_counter >= self._phi_tick_interval:
                self._phi_tick_counter = 0
                new_vec, new_nrci = UBP_MECHANICS.tick(self.golay_vector)
                self.golay_vector = new_vec
                self.nrci = calculate_nrci(self.golay_vector)
                self.symmetry_tax = calculate_symmetry_tax(self.golay_vector)
                # Update NCRIState
                self.nrci_state.vector = new_vec
                self.nrci_state.nrci = new_nrci
                self.nrci_state.tick_phase = (self.nrci_state.tick_phase + 1) % 1953
                self.nrci_state.total_ticks += 1
                # Update lattice cell
                self.lattice_cell = UBP_MECHANICS.fold_to_cell(new_vec)
                # Check dissolution
                if new_nrci < 0.40 and not self.is_static:
                    self.is_dissolving = True
        else:
            # V3.x fallback: plain coherence snap
            snapped, _ = coherence_snap(self.golay_vector)
            self.golay_vector = snapped
            self.symmetry_tax = calculate_symmetry_tax(self.golay_vector)
            self.nrci = calculate_nrci(self.golay_vector)

    def apply_synthesis_damage(self, damage: float) -> None:
        """
        Apply NRCI damage from a Synthesis Collision Event.
        (LAW_13D_SINK_001 — Symmetry Tax accumulation from collision)
        """
        if _UBP_MECHANICS_AVAILABLE and self.nrci_state is not None:
            self.nrci_state = UBP_MECHANICS.apply_damage(self.nrci_state, damage)
            self.nrci = Fraction(str(round(self.nrci_state.nrci, 10)))
            if self.nrci_state.dissolution_pending and not self.is_static:
                self.is_dissolving = True

    def apply_thermal_exchange(self, ambient: AmbientEnvironment) -> None:
        """
        Apply thermal exchange with the ambient environment.
        ΔT = exchange_rate * (T_ambient - T_entity) / heat_capacity
        """
        exchange_rate = to_decimal(ambient.thermal_exchange_rate(self.material))
        T_ambient = to_decimal(ambient.temperature_ubp)
        delta_T = exchange_rate * (T_ambient - self.thermal.temperature_ubp)
        if self.thermal.heat_capacity > D0:
            self.thermal.temperature_ubp += delta_T / self.thermal.heat_capacity

    def to_dict(self) -> Dict[str, Any]:
        """Serialise entity state to a dictionary."""
        return {
            'entity_id': self.entity_id,
            'label': self.label,
            'entity_type': self.entity_type.value,
            'material': self.material.name,
            'is_static': self.is_static,
            'is_resting': self.is_resting,
            'position': self.position.to_dict(),
            'velocity': self.velocity.to_dict(),
            'orientation': self.orientation.to_dict(),
            'angular_velocity': self.angular_velocity.to_dict(),
            'size': [float(s) for s in self.size],
            'mass': float(self.mass),
            'inertia': float(self.inertia),
            'moment_of_inertia': float(self.moment_of_inertia),
            'nrci': float(self.nrci),
            'symmetry_tax': float(self.symmetry_tax),
            'construction_tax': float(self.construction_tax),
            'golay_vector': self.golay_vector,
            'thermal': self.thermal.to_dict(),
        }

    def to_threejs_state(self) -> Dict[str, Any]:
        """
        Serialise entity state for Three.js rendering.
        Returns position, rotation (Euler degrees), size, colour, and metadata.
        """
        roll, pitch, yaw = self.orientation.to_euler_degrees()
        # Colour based on material
        colour_map = {
            'iron': '#8B7355',    # Rusty brown
            'steel': '#708090',   # Slate grey
            'copper': '#B87333',  # Copper orange
            'aluminium': '#C0C0C0', # Silver
            'gold': '#FFD700',    # Gold
            'carbon': '#2F4F4F',  # Dark slate
            'silicon': '#6A5ACD', # Slate blue
            'water': '#4169E1',   # Royal blue
            'air': '#87CEEB',     # Sky blue
            'standard': '#8B7355',
            'heavy': '#FFD700',
            'light': '#C0C0C0',
        }
        colour = colour_map.get(self.material.name, '#888888')

        # Metabolic rendering: opacity and tilt from live NRCI
        nrci_float = float(self.nrci)
        if _UBP_MECHANICS_AVAILABLE and self.nrci_state is not None:
            nrci_float = self.nrci_state.nrci
            health_status = self.nrci_state.health_status
            opacity = round(self.nrci_state.opacity, 3)
            tilt_deg = round(self.nrci_state.tilt_degrees, 2)
            tick_phase = self.nrci_state.tick_phase
        else:
            health_status = 'STABLE' if nrci_float >= 0.60 else 'STRESSED'
            opacity = max(0.2, min(1.0, nrci_float))
            tilt_deg = round((1.0 - nrci_float) * 90.0, 2)
            tick_phase = 0

        # Leech Lattice address
        lc = self.lattice_cell

        return {
            'id': self.entity_id,
            'label': self.label,
            'type': self.entity_type.value,
            'material': self.material.name,
            'position': {'x': float(self.position.x), 'y': float(self.position.y), 'z': float(self.position.z)},
            'rotation': {'x': roll, 'y': pitch, 'z': yaw},
            'size': {'x': float(self.size[0]), 'y': float(self.size[1]), 'z': float(self.size[2])},
            'colour': colour,
            'is_static': self.is_static,
            'is_resting': self.is_resting,
            'is_dissolving': self.is_dissolving,
            'mass': float(self.mass),
            'nrci': round(nrci_float, 6),
            'health_status': health_status,
            'opacity': opacity,
            'tilt_degrees': tilt_deg,
            'tick_phase': tick_phase,
            'lattice_cell': {'x': lc[0], 'y': lc[1], 'z': lc[2]},
            'golay_vector': self.golay_vector,
            'temperature_K': float(self.thermal.temperature_ubp) * 24.0 / float(_Y),
            'velocity': {'x': float(self.velocity.vx), 'y': float(self.velocity.vy), 'z': float(self.velocity.vz)},
        }


# ---------------------------------------------------------------------------
# ENTITY FACTORY V3
# ---------------------------------------------------------------------------

class EntityFactoryV3:
    """
    Factory for creating standard V3 entities with correct UBP properties.
    All entities are built from real KB materials.
    """

    @staticmethod
    def make_block(
        label: str,
        material_name: str = 'iron',
        position: Optional[Position] = None,
        size: Tuple[float, float, float] = (1.0, 1.0, 1.0),
        temperature_K: float = 293.15,
    ) -> UBPEntityV3:
        """Create a solid block entity."""
        return UBPEntityV3(
            label=label,
            material_name=material_name,
            position=position or Position(),
            size=size,
            entity_type=EntityType.BLOCK,
            is_static=False,
            temperature_K=temperature_K,
        )

    @staticmethod
    def make_floor(
        label: str = 'Floor',
        width: float = 20.0,
        depth: float = 20.0,
        material_name: str = 'silicon',  # Stone/concrete proxy
        position: Optional[Position] = None,
    ) -> UBPEntityV3:
        """Create a static floor entity."""
        return UBPEntityV3(
            label=label,
            material_name=material_name,
            position=position or Position(D0, D0, D0),
            size=(width, 1.0, depth),
            entity_type=EntityType.FLOOR,
            is_static=True,
        )

    @staticmethod
    def make_wall(
        label: str,
        width: float,
        height: float,
        depth: float,
        material_name: str = 'silicon',
        position: Optional[Position] = None,
    ) -> UBPEntityV3:
        """Create a static wall entity."""
        return UBPEntityV3(
            label=label,
            material_name=material_name,
            position=position or Position(),
            size=(width, height, depth),
            entity_type=EntityType.WALL,
            is_static=True,
        )

    @staticmethod
    def make_lever_arm(
        label: str,
        length: float = 10.0,
        material_name: str = 'steel',
        position: Optional[Position] = None,
    ) -> UBPEntityV3:
        """Create a lever arm entity (thin, long beam)."""
        return UBPEntityV3(
            label=label,
            material_name=material_name,
            position=position or Position(),
            size=(length, 0.2, 1.0),
            entity_type=EntityType.LEVER_ARM,
            is_static=False,
        )
