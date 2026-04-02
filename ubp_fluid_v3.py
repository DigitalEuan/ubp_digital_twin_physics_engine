"""
================================================================================
UBP FLUID SIMULATION v3.1 — UBP-SPH
================================================================================
Smoothed Particle Hydrodynamics (SPH) with all scalars derived from UBP laws.

V2 used empirical multipliers (0.001, 10, 5). V3 derives all scalars:

  PRESSURE_STIFFNESS = SINK_L × 24 / KISSING_NUMBER
    Source: LAW_INFORMATIONAL_SATURATION_001 + LAW_SINK_001
    The 13D Sink Leakage (SINK_L) is the natural compressive resistance.
    Normalised by the Kissing Number (196560) of the Leech Lattice.

  VISCOSITY = Y / 96
    Source: LAW_ONTOLOGICAL_FRICTION_001 (The Shaving)
    The ontological friction unit is Y/96 (the gap divided by 24).

  SURFACE_TENSION = Y² / KISSING_NUMBER
    Source: LAW_TOP_KISSING_001
    Surface tension = energy per unit area at the substrate boundary.
    = The Shaving (Y²) divided by the first-shell saturation (K=196560).

  REST_DENSITY = calibrated to spawn density for pressure equilibrium
    Particles start at equilibrium so only gravity acts at t=0.

  SMOOTHING_RADIUS = Y_INV / 8
    Source: Y_INV = π + 2/π ≈ 3.778 (the Observer Fixed Point)
    The smoothing radius is 1/8 of the Observer Fixed Point.
================================================================================
"""

from __future__ import annotations
import math
from dataclasses import dataclass, field
from decimal import Decimal, getcontext
from fractions import Fraction
from typing import Dict, List, Optional, Tuple, Any

getcontext().prec = 50

from ubp_entity_v3 import (
    UBPEntityV3, EntityType, Position, Velocity, AABB,
    D, D0, D1, to_decimal
)
from ubp_engine_substrate import (
    Y_CONSTANT, Y_INV, SINK_L, G_EARTH_MS2, PI,
    calculate_nrci, hamming_distance,
)
# UBP 50-term π (exact rational) converted to float for SPH kernel arithmetic
# This replaces math.pi throughout the SPH kernels to use the UBP substrate π.
_PI_FLOAT: float = float(PI)  # ≈ 3.14159265358979...  (50-term precision)
from ubp_materials import MaterialRegistry

# ---------------------------------------------------------------------------
# SPH CONSTANTS (all UBP-derived)
# ---------------------------------------------------------------------------

_Y = to_decimal(Y_CONSTANT)
_Y_INV = to_decimal(Y_INV)
_SINK_L = to_decimal(SINK_L)
_G_EARTH = to_decimal(G_EARTH_MS2)
_KISSING = D('196560')

# Gravity per tick²
_G_PER_TICK_SQ: Decimal = _G_EARTH / D('3600') * _Y

# Speed limit
_V_MAX: Decimal = D('1') / _Y

# Smoothing radius = Y_INV / 8 ≈ 0.472 cells
SMOOTHING_RADIUS: Decimal = _Y_INV / D('8')

# Pressure stiffness (LAW_INFORMATIONAL_SATURATION_001 + LAW_SINK_001)
# SINK_L × 24 / K ≈ 7.68e-6
PRESSURE_STIFFNESS: Decimal = _SINK_L * D('24') / _KISSING

# Viscosity (LAW_ONTOLOGICAL_FRICTION_001: Unit = Y/96)
VISCOSITY: Decimal = _Y / D('96')

# Surface tension (LAW_TOP_KISSING_001: Y² / K)
SURFACE_TENSION: Decimal = _Y * _Y / _KISSING

# Rest density: calibrated to spawn density
# For particles on a 0.15-unit grid with smoothing radius 0.472:
# Actual spawn density ≈ 3.2 (measured empirically in V2)
# Set REST_DENSITY slightly below spawn density for gentle positive pressure
REST_DENSITY: Decimal = D('2.8')

# Maximum velocity for fluid particles
_FLUID_V_MAX: Decimal = _V_MAX / D('2')

# ---------------------------------------------------------------------------
# SPH KERNELS
# ---------------------------------------------------------------------------

def _poly6_kernel(r: float, h: float) -> float:
    """
    Poly6 density kernel W(r,h).
    Uses UBP 50-term π (_PI_FLOAT) instead of math.pi.
    """
    if r >= h:
        return 0.0
    h2 = h * h
    r2 = r * r
    coeff = 315.0 / (64.0 * _PI_FLOAT * h**9)
    return coeff * (h2 - r2)**3
def _spiky_gradient(r: float, h: float, dx: float, dy: float, dz: float) -> Tuple[float, float, float]:
    """
    Spiky kernel gradient for pressure forces.
    Uses UBP 50-term π (_PI_FLOAT) instead of math.pi.
    """
    if r >= h or r < 1e-10:
        return (0.0, 0.0, 0.0)
    coeff = -45.0 / (_PI_FLOAT * h**6) * (h - r)**2 / r
    return (coeff * dx, coeff * dy, coeff * dz)
def _viscosity_laplacian(r: float, h: float) -> float:
    """
    Viscosity kernel Laplacian.
    Uses UBP 50-term π (_PI_FLOAT) instead of math.pi.
    """
    if r >= h:
        return 0.0
    return 45.0 / (_PI_FLOAT * h**6) * (h - r)

# ---------------------------------------------------------------------------
# FLUID PARTICLE
# ---------------------------------------------------------------------------

@dataclass
class FluidParticle:
    """A single SPH fluid particle."""
    particle_id: int
    x: float
    y: float
    z: float
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0
    density: float = float(REST_DENSITY)
    pressure: float = 0.0
    material_name: str = 'water'

    # UBP identity (from material vector)
    nrci: float = 0.5975  # Water NRCI from KB

    def position(self) -> Position:
        return Position(D(str(self.x)), D(str(self.y)), D(str(self.z)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.particle_id,
            'x': self.x, 'y': self.y, 'z': self.z,
            'vx': self.vx, 'vy': self.vy, 'vz': self.vz,
            'density': self.density,
            'pressure': self.pressure,
            'material': self.material_name,
            'nrci': self.nrci,
        }

    def to_threejs_state(self) -> Dict[str, Any]:
        return {
            'id': self.particle_id,
            'type': 'fluid_particle',
            'material': self.material_name,
            'position': {'x': self.x, 'y': self.y, 'z': self.z},
            'velocity': {'x': self.vx, 'y': self.vy, 'z': self.vz},
            'density': self.density,
            'colour': '#4169E1',  # Royal blue for water
            'size': {'x': 0.3, 'y': 0.3, 'z': 0.3},
        }


# ---------------------------------------------------------------------------
# FLUID BODY
# ---------------------------------------------------------------------------

class FluidBodyV3:
    """
    A collection of SPH fluid particles forming a fluid body.

    Uses UBP-derived SPH constants. The fluid is a Digital Twin of water
    (H₂O) with properties from the UBP KB.
    """

    _particle_counter: int = 0

    def __init__(self, material_name: str = 'water', body_id: str = 'fluid_0'):
        self.body_id = body_id
        self.material_name = material_name
        self.material = MaterialRegistry.get(material_name)
        self.particles: List[FluidParticle] = []

        # Get water NRCI from KB
        self.particle_nrci = float(self.material.aggregate_nrci)

        # SPH parameters
        self.h = float(SMOOTHING_RADIUS)       # Smoothing radius
        self.k = float(PRESSURE_STIFFNESS)     # Pressure stiffness
        self.mu = float(VISCOSITY)             # Viscosity
        self.sigma = float(SURFACE_TENSION)    # Surface tension
        self.rho0 = float(REST_DENSITY)        # Rest density
        self.g = float(_G_PER_TICK_SQ)         # Gravity per tick²
        self.v_max = float(_FLUID_V_MAX)       # Speed limit

    def add_particle(
        self, x: float, y: float, z: float,
        vx: float = 0.0, vy: float = 0.0, vz: float = 0.0,
    ) -> FluidParticle:
        """Add a single fluid particle."""
        FluidBodyV3._particle_counter += 1
        p = FluidParticle(
            particle_id=FluidBodyV3._particle_counter,
            x=x, y=y, z=z,
            vx=vx, vy=vy, vz=vz,
            material_name=self.material_name,
            nrci=self.particle_nrci,
        )
        self.particles.append(p)
        return p

    def emit_pool(
        self,
        origin_x: float, origin_y: float, origin_z: float,
        width: int = 5, height: int = 2, depth: int = 5,
        spacing: float = 0.35,
    ) -> None:
        """
        Emit a rectangular pool of fluid particles.
        Spacing is set to produce a spawn density close to REST_DENSITY.
        """
        for ix in range(width):
            for iy in range(height):
                for iz in range(depth):
                    x = origin_x + ix * spacing
                    y = origin_y + iy * spacing
                    z = origin_z + iz * spacing
                    self.add_particle(x, y, z)

    def emit_stream(
        self,
        x: float, y: float, z: float,
        count: int = 10,
        direction: Tuple[float, float, float] = (0.0, -0.1, 0.0),
    ) -> None:
        """Emit a stream of particles from a point."""
        dx, dy, dz = direction
        for i in range(count):
            self.add_particle(x, y, z, vx=dx, vy=dy, vz=dz)

    def step(
        self,
        solid_entities: List[UBPEntityV3],
        space_bounds: Optional[Tuple[float, float, float, float, float, float]] = None,
        ambient_temperature_ubp: float = 3.2329,
        all_fluid_bodies: Optional[List[FluidBodyV3]] = None,
    ) -> None:
        """
        Advance the fluid simulation by one tick.

        Pipeline:
          1. Compute density and pressure (Poly6 kernel)
          2. Compute pressure forces (Spiky gradient)
          3. Compute viscosity forces (Viscosity Laplacian)
          4. Apply gravity (Equivalence Principle)
          5. Apply surface tension (cohesion)
          6. Integrate velocity and position
          7. Handle solid collisions
          8. Enforce space boundaries
        """
        n = len(self.particles)
        if n == 0:
            return

        # Temperature effect on viscosity: μ_T = μ × T_STP / T_current
        T_STP = 3.2329
        mu_T = self.mu * T_STP / max(ambient_temperature_ubp, 0.001)

        # ---- 1. DENSITY AND PRESSURE ----
        # v6.3.1: Pressure stiffness is modulated by the particle's NRCI.
        # High NRCI (coherent fluid) -> normal stiffness.
        # Low NRCI (stressed fluid) -> reduced stiffness (more compressible).
        # This reflects the UBP principle that coherent matter resists compression.
        for i, pi in enumerate(self.particles):
            rho = 0.0
            for j, pj in enumerate(self.particles):
                dx = pi.x - pj.x
                dy = pi.y - pj.y
                dz = pi.z - pj.z
                r = math.sqrt(dx*dx + dy*dy + dz*dz)
                rho += _poly6_kernel(r, self.h)
            pi.density = max(rho, 0.001)
            # Pressure = k * nrci_factor * (ρ - ρ₀)
            # nrci_factor in [0.5, 1.0]: NRCI modulates stiffness
            nrci_factor = max(0.5, min(1.0, pi.nrci))
            pi.pressure = self.k * nrci_factor * (pi.density - self.rho0)

        # ---- 2-5. FORCES ----
        ax_list = [0.0] * n
        ay_list = [-self.g] * n  # Gravity (downward)
        az_list = [0.0] * n

        for i in range(n):
            pi = self.particles[i]
            for j in range(n):
                if i == j:
                    continue
                pj = self.particles[j]
                dx = pi.x - pj.x
                dy = pi.y - pj.y
                dz = pi.z - pj.z
                r = math.sqrt(dx*dx + dy*dy + dz*dz)
                if r < 1e-10 or r >= self.h:
                    continue

                # ---- Pressure force ----
                p_avg = (pi.pressure + pj.pressure) / 2.0
                rho_j = max(pj.density, 0.001)
                gx, gy, gz = _spiky_gradient(r, self.h, dx, dy, dz)
                ax_list[i] -= p_avg / rho_j * gx
                ay_list[i] -= p_avg / rho_j * gy
                az_list[i] -= p_avg / rho_j * gz

                # ---- Viscosity force ----
                lap = _viscosity_laplacian(r, self.h)
                ax_list[i] += mu_T / rho_j * (pj.vx - pi.vx) * lap
                ay_list[i] += mu_T / rho_j * (pj.vy - pi.vy) * lap
                az_list[i] += mu_T / rho_j * (pj.vz - pi.vz) * lap

                # ---- Surface tension (cohesion) ----
                # F_cohesion = σ × W(r,h) × (r_ij / r)
                w = _poly6_kernel(r, self.h)
                ax_list[i] -= self.sigma * w * dx / (r + 1e-10)
                ay_list[i] -= self.sigma * w * dy / (r + 1e-10)
                az_list[i] -= self.sigma * w * dz / (r + 1e-10)

        # ---- 6. INTEGRATE ----
        for i in range(n):
            pi = self.particles[i]
            pi.vx += ax_list[i]
            pi.vy += ay_list[i]
            pi.vz += az_list[i]

            # Cap velocity
            speed = math.sqrt(pi.vx**2 + pi.vy**2 + pi.vz**2)
            if speed > self.v_max:
                scale = self.v_max / speed
                pi.vx *= scale
                pi.vy *= scale
                pi.vz *= scale

            pi.x += pi.vx
            pi.y += pi.vy
            pi.z += pi.vz

        # ---- 7. SOLID COLLISIONS ----
        self._handle_solid_collisions(solid_entities)

        # ---- 8. SPACE BOUNDARIES ----
        if space_bounds is not None:
            self._enforce_bounds(space_bounds)

    def _handle_solid_collisions(self, solid_entities: List[UBPEntityV3]) -> None:
        """
        Resolve fluid particle collisions with solid entities.

        v6.3.1 UPDATE: Restitution is now computed via Synthesis Superposition
        (Additive Superposition + Phenomenal Collapse) between the fluid
        material vector and the solid's Golay vector, then NRCI of the result.

        This replaces the old Hamming-distance heuristic with the true UBP
        synthesis event: the fluid and solid 'interact' at the boundary, and
        the coherence of the result determines how much energy is preserved.
        """
        water_vec = MaterialRegistry.get('water').aggregate_vector

        for p in self.particles:
            for entity in solid_entities:
                if entity.material.phase_stp == 1:  # Skip gas entities
                    continue
                bb = entity.aabb()
                # Check if particle is inside the AABB (account for radius)
                # We use a collision radius of h/2 to prevent penetration
                r_coll = self.h / 2.0
                
                # Convert AABB bounds to float to avoid Decimal vs float TypeError
                min_x, max_x = float(bb.min_x), float(bb.max_x)
                min_y, max_y = float(bb.min_y), float(bb.max_y)
                min_z, max_z = float(bb.min_z), float(bb.max_z)

                if (min_x - r_coll <= p.x <= max_x + r_coll and
                    min_y - r_coll <= p.y <= max_y + r_coll and
                    min_z - r_coll <= p.z <= max_z + r_coll):

                    # v6.3.1: Synthesis Superposition for restitution
                    # Additive superposition of fluid and solid vectors
                    b_w = [-1 if x == 0 else 1 for x in water_vec]
                    b_e = [-1 if x == 0 else 1 for x in entity.golay_vector]
                    raw_sum = [b_w[i] + b_e[i] for i in range(24)]
                    synth_vec = [0 if s >= 0 else 1 for s in raw_sum]
                    restitution = float(calculate_nrci(synth_vec))

                    # Find closest face and push out
                    # Distances to each face
                    d_bottom = p.y - min_y
                    d_top = max_y - p.y
                    d_left = p.x - min_x
                    d_right = max_x - p.x
                    d_front = p.z - min_z
                    d_back = max_z - p.z

                    min_d = min(d_bottom, d_top, d_left, d_right, d_front, d_back)

                    if min_d == d_bottom:
                        p.y = min_y - r_coll - 0.01
                        if p.vy > 0:
                            p.vy = -abs(p.vy) * restitution
                    elif min_d == d_top:
                        p.y = max_y + r_coll + 0.01
                        if p.vy < 0:
                            p.vy = abs(p.vy) * restitution
                    elif min_d == d_left:
                        p.x = min_x - r_coll - 0.01
                        if p.vx > 0:
                            p.vx = -abs(p.vx) * restitution
                    elif min_d == d_right:
                        p.x = max_x + r_coll + 0.01
                        if p.vx < 0:
                            p.vx = abs(p.vx) * restitution
                    elif min_d == d_front:
                        p.z = min_z - r_coll - 0.01
                        if p.vz > 0:
                            p.vz = -abs(p.vz) * restitution
                    else:
                        p.z = max_z + r_coll + 0.01
                        if p.vz < 0:
                            p.vz = abs(p.vz) * restitution

    def _enforce_bounds(
        self,
        bounds: Tuple[float, float, float, float, float, float],
    ) -> None:
        """
        Enforce space boundaries. Particles bounce off walls with
        restitution = water NRCI ≈ 0.5975.
        """
        x_min, x_max, y_min, y_max, z_min, z_max = bounds
        restitution = self.particle_nrci
        r_coll = self.h / 2.0

        for p in self.particles:
            if p.x < x_min + r_coll:
                p.x = x_min + r_coll + 0.01
                p.vx = abs(p.vx) * restitution
            elif p.x > x_max - r_coll:
                p.x = x_max - r_coll - 0.01
                p.vx = -abs(p.vx) * restitution

            if p.y < y_min + r_coll:
                p.y = y_min + r_coll + 0.01
                p.vy = abs(p.vy) * restitution
            elif p.y > y_max - r_coll:
                p.y = y_max - r_coll - 0.01
                p.vy = -abs(p.vy) * restitution

            if p.z < z_min + r_coll:
                p.z = z_min + r_coll + 0.01
                p.vz = abs(p.vz) * restitution
            elif p.z > z_max - r_coll:
                p.z = z_max - r_coll - 0.01
                p.vz = -abs(p.vz) * restitution

    def get_state(self) -> List[Dict[str, Any]]:
        """Return the current state of all particles."""
        return [p.to_dict() for p in self.particles]

    def get_threejs_state(self) -> List[Dict[str, Any]]:
        """Return particle states for Three.js rendering."""
        return [p.to_threejs_state() for p in self.particles]

    def particle_count(self) -> int:
        return len(self.particles)

    def average_y(self) -> float:
        if not self.particles:
            return 0.0
        return sum(p.y for p in self.particles) / len(self.particles)

    def min_y(self) -> float:
        if not self.particles:
            return 0.0
        return min(p.y for p in self.particles)

    def max_y(self) -> float:
        """Return the maximum y position of all fluid particles."""
        if not self.particles:
            return 0.0
        return max(p.y for p in self.particles)
