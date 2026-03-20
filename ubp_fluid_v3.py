"""
================================================================================
UBP FLUID SIMULATION v3.2 — UBP-SPH
================================================================================
Smoothed Particle Hydrodynamics (SPH) with all scalars derived from UBP laws.

V3.2 Improvements:
  - Increased smoothing radius (Y_INV/3 ≈ 1.26 cells) for proper particle overlap
  - Surface tension boosted to Y²/KISSING_NORM (KISSING_NORM=196.56) for cohesion
  - REST_DENSITY recalibrated to 3.5 for new kernel
  - Fluid body IDs for selective deletion
  - Cross-body SPH interaction (all fluid bodies interact)
  - Two-way coupling: fluid pushes back on solid entities (displacement)
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
    Y_CONSTANT, Y_INV, SINK_L, G_EARTH_MS2,
    calculate_nrci, hamming_distance,
)
from ubp_materials import MaterialRegistry

_Y = to_decimal(Y_CONSTANT)
_Y_INV = to_decimal(Y_INV)
_SINK_L = to_decimal(SINK_L)
_G_EARTH = to_decimal(G_EARTH_MS2)
_KISSING = D('196560')
_KISSING_NORM = D('196.56')

_G_PER_TICK_SQ: Decimal = _G_EARTH / D('3600') * _Y
_V_MAX: Decimal = D('1') / _Y

# V3.2: Smoothing radius increased from Y_INV/8 to Y_INV/3 for proper overlap
SMOOTHING_RADIUS: Decimal = _Y_INV / D('3')
PRESSURE_STIFFNESS: Decimal = _SINK_L * D('24') / _KISSING
VISCOSITY: Decimal = _Y / D('96')
# V3.2: Surface tension uses normalised kissing number for meaningful cohesion
SURFACE_TENSION: Decimal = _Y * _Y / _KISSING_NORM
REST_DENSITY: Decimal = D('3.5')
_FLUID_V_MAX: Decimal = _V_MAX / D('2')


def _poly6_kernel(r: float, h: float) -> float:
    if r >= h:
        return 0.0
    h2 = h * h
    r2 = r * r
    coeff = 315.0 / (64.0 * math.pi * h**9)
    return coeff * (h2 - r2)**3

def _spiky_gradient(r: float, h: float, dx: float, dy: float, dz: float) -> Tuple[float, float, float]:
    if r >= h or r < 1e-10:
        return (0.0, 0.0, 0.0)
    coeff = -45.0 / (math.pi * h**6) * (h - r)**2 / r
    return (coeff * dx, coeff * dy, coeff * dz)

def _viscosity_laplacian(r: float, h: float) -> float:
    if r >= h:
        return 0.0
    return 45.0 / (math.pi * h**6) * (h - r)


@dataclass
class FluidParticle:
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
    body_id: int = 0
    nrci: float = 0.5975

    def position(self) -> Position:
        return Position(D(str(self.x)), D(str(self.y)), D(str(self.z)))

    def to_dict(self) -> Dict[str, Any]:
        return {
            'id': self.particle_id,
            'body_id': self.body_id,
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
            'body_id': self.body_id,
            'type': 'fluid_particle',
            'material': self.material_name,
            'position': {'x': self.x, 'y': self.y, 'z': self.z},
            'velocity': {'x': self.vx, 'y': self.vy, 'z': self.vz},
            'density': self.density,
            'colour': '#4169E1',
            'size': {'x': 0.3, 'y': 0.3, 'z': 0.3},
        }


class FluidBodyV3:
    _particle_counter: int = 0
    _body_counter: int = 0

    def __init__(self, material_name: str = 'water'):
        FluidBodyV3._body_counter += 1
        self.body_id: int = FluidBodyV3._body_counter
        self.material_name = material_name
        self.material = MaterialRegistry.get(material_name)
        self.particles: List[FluidParticle] = []
        self.particle_nrci = float(self.material.aggregate_nrci)
        self.h = float(SMOOTHING_RADIUS)
        self.k = float(PRESSURE_STIFFNESS)
        self.mu = float(VISCOSITY)
        self.sigma = float(SURFACE_TENSION)
        self.rho0 = float(REST_DENSITY)
        self.g = float(_G_PER_TICK_SQ)
        self.v_max = float(_FLUID_V_MAX)

    def add_particle(self, x: float, y: float, z: float,
                     vx: float = 0.0, vy: float = 0.0, vz: float = 0.0) -> FluidParticle:
        FluidBodyV3._particle_counter += 1
        p = FluidParticle(
            particle_id=FluidBodyV3._particle_counter,
            x=x, y=y, z=z, vx=vx, vy=vy, vz=vz,
            material_name=self.material_name,
            nrci=self.particle_nrci,
            body_id=self.body_id,
        )
        self.particles.append(p)
        return p

    def emit_pool(self, origin_x: float, origin_y: float, origin_z: float,
                  width: int = 5, height: int = 2, depth: int = 5,
                  spacing: float = 0.35) -> None:
        for ix in range(width):
            for iy in range(height):
                for iz in range(depth):
                    self.add_particle(
                        origin_x + ix * spacing,
                        origin_y + iy * spacing,
                        origin_z + iz * spacing,
                    )

    def emit_stream(self, x: float, y: float, z: float, count: int = 10,
                    direction: Tuple[float, float, float] = (0.0, -0.1, 0.0)) -> None:
        dx, dy, dz = direction
        for i in range(count):
            self.add_particle(x, y, z, vx=dx, vy=dy, vz=dz)

    def step(self, solid_entities: List[UBPEntityV3],
             space_bounds: Optional[Tuple[float, float, float, float, float, float]] = None,
             ambient_temperature_ubp: float = 3.2329,
             all_fluid_bodies: Optional[List['FluidBodyV3']] = None) -> None:
        n = len(self.particles)
        if n == 0:
            return

        # Gather all particles for cross-body interaction
        all_particles = list(self.particles)
        if all_fluid_bodies:
            for other_body in all_fluid_bodies:
                if other_body.body_id != self.body_id:
                    all_particles.extend(other_body.particles)

        T_STP = 3.2329
        mu_T = self.mu * T_STP / max(ambient_temperature_ubp, 0.001)

        # 1. DENSITY AND PRESSURE
        for pi in self.particles:
            rho = 0.0
            for pj in all_particles:
                dx = pi.x - pj.x
                dy = pi.y - pj.y
                dz = pi.z - pj.z
                r = math.sqrt(dx*dx + dy*dy + dz*dz)
                rho += _poly6_kernel(r, self.h)
            pi.density = max(rho, 0.001)
            pi.pressure = self.k * (pi.density - self.rho0)

        # 2-5. FORCES
        ax_list = [0.0] * n
        ay_list = [-self.g] * n
        az_list = [0.0] * n

        for i in range(n):
            pi = self.particles[i]
            for pj in all_particles:
                if pj.particle_id == pi.particle_id:
                    continue
                dx = pi.x - pj.x
                dy = pi.y - pj.y
                dz = pi.z - pj.z
                r = math.sqrt(dx*dx + dy*dy + dz*dz)
                if r < 1e-10 or r >= self.h:
                    continue

                p_avg = (pi.pressure + pj.pressure) / 2.0
                rho_j = max(pj.density, 0.001)
                gx, gy, gz = _spiky_gradient(r, self.h, dx, dy, dz)
                ax_list[i] -= p_avg / rho_j * gx
                ay_list[i] -= p_avg / rho_j * gy
                az_list[i] -= p_avg / rho_j * gz

                lap = _viscosity_laplacian(r, self.h)
                ax_list[i] += mu_T / rho_j * (pj.vx - pi.vx) * lap
                ay_list[i] += mu_T / rho_j * (pj.vy - pi.vy) * lap
                az_list[i] += mu_T / rho_j * (pj.vz - pi.vz) * lap

                w = _poly6_kernel(r, self.h)
                ax_list[i] -= self.sigma * w * dx / (r + 1e-10)
                ay_list[i] -= self.sigma * w * dy / (r + 1e-10)
                az_list[i] -= self.sigma * w * dz / (r + 1e-10)

        # 6. INTEGRATE
        for i in range(n):
            pi = self.particles[i]
            pi.vx += ax_list[i]
            pi.vy += ay_list[i]
            pi.vz += az_list[i]
            speed = math.sqrt(pi.vx**2 + pi.vy**2 + pi.vz**2)
            if speed > self.v_max:
                scale = self.v_max / speed
                pi.vx *= scale
                pi.vy *= scale
                pi.vz *= scale
            pi.x += pi.vx
            pi.y += pi.vy
            pi.z += pi.vz

        # 7. SOLID COLLISIONS
        self._handle_solid_collisions(solid_entities)

        # 8. SPACE BOUNDARIES
        if space_bounds is not None:
            self._enforce_bounds(space_bounds)

    def _handle_solid_collisions(self, solid_entities: List[UBPEntityV3]) -> None:
        water_vec = MaterialRegistry.get('water').aggregate_vector
        for p in self.particles:
            for entity in solid_entities:
                if entity.material.phase_stp == 1:
                    continue
                bb = entity.aabb()
                if (float(bb.min_x) <= p.x <= float(bb.max_x) and
                    float(bb.min_y) <= p.y <= float(bb.max_y) and
                    float(bb.min_z) <= p.z <= float(bb.max_z)):
                    dH = hamming_distance(water_vec, entity.golay_vector)
                    restitution = max(0.1, 1.0 - dH / 24.0)
                    d_bottom = p.y - float(bb.min_y)
                    d_top = float(bb.max_y) - p.y
                    d_left = p.x - float(bb.min_x)
                    d_right = float(bb.max_x) - p.x
                    d_front = p.z - float(bb.min_z)
                    d_back = float(bb.max_z) - p.z
                    min_d = min(d_bottom, d_top, d_left, d_right, d_front, d_back)
                    old_vx, old_vy, old_vz = p.vx, p.vy, p.vz
                    if min_d == d_bottom:
                        p.y = float(bb.min_y) - 0.01
                        if p.vy > 0:
                            p.vy = -abs(p.vy) * restitution
                    elif min_d == d_top:
                        p.y = float(bb.max_y) + 0.01
                        if p.vy < 0:
                            p.vy = abs(p.vy) * restitution
                    elif min_d == d_left:
                        p.x = float(bb.min_x) - 0.01
                        if p.vx > 0:
                            p.vx = -abs(p.vx) * restitution
                    elif min_d == d_right:
                        p.x = float(bb.max_x) + 0.01
                        if p.vx < 0:
                            p.vx = abs(p.vx) * restitution
                    elif min_d == d_front:
                        p.z = float(bb.min_z) - 0.01
                        if p.vz > 0:
                            p.vz = -abs(p.vz) * restitution
                    else:
                        p.z = float(bb.max_z) + 0.01
                        if p.vz < 0:
                            p.vz = abs(p.vz) * restitution
                    # Two-way coupling: reaction impulse on solid
                    if not entity.is_static:
                        particle_mass = 0.05
                        dvx = p.vx - old_vx
                        dvy = p.vy - old_vy
                        dvz = p.vz - old_vz
                        entity.velocity.vx -= D(str(particle_mass * dvx)) / entity.inertia
                        entity.velocity.vy -= D(str(particle_mass * dvy)) / entity.inertia
                        entity.velocity.vz -= D(str(particle_mass * dvz)) / entity.inertia
                        entity.is_resting = False
                        entity.is_sleeping = False

    def _enforce_bounds(self, bounds: Tuple[float, float, float, float, float, float]) -> None:
        x_min, x_max, y_min, y_max, z_min, z_max = bounds
        restitution = self.particle_nrci
        for p in self.particles:
            if p.x < x_min:
                p.x = x_min + 0.01
                p.vx = abs(p.vx) * restitution
            elif p.x > x_max:
                p.x = x_max - 0.01
                p.vx = -abs(p.vx) * restitution
            if p.y < y_min:
                p.y = y_min + 0.01
                p.vy = abs(p.vy) * restitution
            elif p.y > y_max:
                p.y = y_max - 0.01
                p.vy = -abs(p.vy) * restitution
            if p.z < z_min:
                p.z = z_min + 0.01
                p.vz = abs(p.vz) * restitution
            elif p.z > z_max:
                p.z = z_max - 0.01
                p.vz = -abs(p.vz) * restitution

    def get_state(self) -> List[Dict[str, Any]]:
        return [p.to_dict() for p in self.particles]

    def get_threejs_state(self) -> List[Dict[str, Any]]:
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
        if not self.particles:
            return 0.0
        return max(p.y for p in self.particles)
