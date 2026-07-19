"""
================================================================================
UBP FORCE COUPLERS — Slices 5 + 6 of the domains-in-3D integration
================================================================================
Implements the first real pairwise forces between domain-native objects:

  • Slice 5 — Newtonian pairwise gravity
      a = G * m_other / r^2

  • Slice 6 — Coulomb interaction
      a = k_e * q_self * q_other / (m_self * r^2)

Design goals
------------
1. Read all physical values from entity metadata and world state — no repeated
   spawn-specific logic here.
2. Be numerically stable in a small 20×20×20 workspace.
3. Produce real acceleration vectors in SI units first; the physics engine then
   converts them to engine tick units using the same Y/3600 transform it already
   uses for Earth gravity.
4. Never require a later rewrite of spawn metadata — this module only consumes
   `domain_params`, `domain_tag`, and `world_physics`.

Stability strategy
------------------
Real subatomic and astrophysical forces are wildly different scales. To keep the
simulation stable without lying about the underlying real values, we do three things:

  A. Every entity provides `interaction_scale_m_per_cell` in `domain_params`.
     This tells us how many real metres correspond to one workspace cell for the
     purpose of pairwise force evaluation.

  B. A softening length equal to ~half a cell in real units prevents singularities
     when two visual proxies overlap.

  C. The physics engine clips the resulting per-tick pairwise acceleration so
     objects remain inside the existing velocity budget. That clip is an ENGINE/UI
     stability limit, not a physical constant.

Author: UBP Digital Twin Project · Slices 5 + 6 (July 2026)
================================================================================
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Any, Dict, Iterable, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from ubp_world_physics import WorldPhysicsState


# ── Generic numeric helpers ──────────────────────────────────────────────────
def _f(x: Any) -> float:
    try:
        return float(x)
    except Exception:
        return 0.0


def _centre_xyz(entity: Any) -> Tuple[float, float, float]:
    """Centre position in workspace cells for either a real UBPEntityV3 or a dummy test object."""
    # Real engine entities carry Decimal position + Decimal size tuple.
    pos = getattr(entity, 'position', None)
    size = getattr(entity, 'size', None)
    if pos is None or size is None:
        return (0.0, 0.0, 0.0)
    try:
        sx, sy, sz = size
    except Exception:
        sx = sy = sz = 1.0
    return (
        _f(pos.x) + _f(sx) / 2.0,
        _f(pos.y) + _f(sy) / 2.0,
        _f(pos.z) + _f(sz) / 2.0,
    )


def _domain_params(entity: Any) -> Dict[str, Any]:
    return dict(getattr(entity, 'domain_params', {}) or {})


def _real_mass_kg(entity: Any) -> Optional[float]:
    m = _domain_params(entity).get('real_mass_kg')
    if m is None:
        return None
    m = _f(m)
    return m if m > 0.0 else None


def _charge_C(entity: Any) -> Optional[float]:
    params = _domain_params(entity)
    if 'charge_C' not in params:
        return None
    return _f(params['charge_C'])


def _interaction_scale_m_per_cell(entity: Any, world: 'WorldPhysicsState') -> float:
    params = _domain_params(entity)
    if 'interaction_scale_m_per_cell' in params:
        scale = _f(params['interaction_scale_m_per_cell'])
        if scale > 0:
            return scale
    # Sensible fallbacks by domain family when metadata is absent.
    tag = getattr(entity, 'domain_tag', None)
    if tag in ('astrophysics', 'cosmology') and world.cosmology_scale > 0:
        return 1.0 / world.cosmology_scale
    return 1.0  # neutral fallback — 1 real metre per workspace cell


def _pairwise_gravity_enabled(entity: Any) -> bool:
    return bool(_domain_params(entity).get('pairwise_gravity_enabled', False))


def _pairwise_em_enabled(entity: Any) -> bool:
    return bool(_domain_params(entity).get('pairwise_em_enabled', False))


def _coulomb_constant(entity: Any) -> Optional[float]:
    params = _domain_params(entity)
    if 'coulomb_constant' not in params:
        return None
    k = _f(params['coulomb_constant'])
    return k if k > 0 else None


# ── Force-vector dataclass ───────────────────────────────────────────────────
@dataclass
class ForceVector:
    ax_ms2: float = 0.0
    ay_ms2: float = 0.0
    az_ms2: float = 0.0
    contributors: int = 0

    def add(self, x: float, y: float, z: float) -> None:
        self.ax_ms2 += x
        self.ay_ms2 += y
        self.az_ms2 += z
        self.contributors += 1

    def as_tuple(self) -> Tuple[float, float, float]:
        return (self.ax_ms2, self.ay_ms2, self.az_ms2)


# ── Individual couplers ──────────────────────────────────────────────────────
class GravitationalCoupler:
    """Pairwise Newtonian attraction based on entity real masses and world.newton_G."""

    def enabled(self, world: 'WorldPhysicsState') -> bool:
        return bool(world.gravity_pair_enabled or world.gravity_mode == 'newtonian')

    def acceleration_ms2_on(self,
                            entity: Any,
                            all_entities: Iterable[Any],
                            world: 'WorldPhysicsState') -> ForceVector:
        if not self.enabled(world):
            return ForceVector()
        if not _pairwise_gravity_enabled(entity):
            return ForceVector()
        m_self = _real_mass_kg(entity)
        if m_self is None:
            return ForceVector()

        x1, y1, z1 = _centre_xyz(entity)
        scale_self = _interaction_scale_m_per_cell(entity, world)
        G = world.newton_G
        out = ForceVector()

        for other in all_entities:
            if other is entity:
                continue
            if not _pairwise_gravity_enabled(other):
                continue
            m_other = _real_mass_kg(other)
            if m_other is None or m_other <= 0.0:
                continue

            x2, y2, z2 = _centre_xyz(other)
            dx_cells, dy_cells, dz_cells = (x2 - x1, y2 - y1, z2 - z1)
            raw_len_cells = sqrt(dx_cells*dx_cells + dy_cells*dy_cells + dz_cells*dz_cells)
            if raw_len_cells <= 1e-12:
                continue

            scale_other = _interaction_scale_m_per_cell(other, world)
            scale_m_per_cell = max(scale_self, scale_other)
            softening_m = 0.5 * scale_m_per_cell
            r_m = max(raw_len_cells * scale_m_per_cell, softening_m)

            # a_self = G * m_other / r^2 toward the other mass
            a = G * m_other / (r_m * r_m)
            ux, uy, uz = (dx_cells / raw_len_cells, dy_cells / raw_len_cells, dz_cells / raw_len_cells)
            out.add(a * ux, a * uy, a * uz)

        return out


class ElectromagneticCoupler:
    """Pairwise Coulomb interaction based on entity charges and masses."""

    def enabled(self, world: 'WorldPhysicsState') -> bool:
        return bool(world.em_enabled)

    def acceleration_ms2_on(self,
                            entity: Any,
                            all_entities: Iterable[Any],
                            world: 'WorldPhysicsState') -> ForceVector:
        if not self.enabled(world):
            return ForceVector()
        if not _pairwise_em_enabled(entity):
            return ForceVector()

        q_self = _charge_C(entity)
        m_self = _real_mass_kg(entity)
        k_e = _coulomb_constant(entity)
        if q_self is None or m_self is None or k_e is None or m_self <= 0.0:
            return ForceVector()

        x1, y1, z1 = _centre_xyz(entity)
        scale_self = _interaction_scale_m_per_cell(entity, world)
        out = ForceVector()

        for other in all_entities:
            if other is entity:
                continue
            if not _pairwise_em_enabled(other):
                continue
            q_other = _charge_C(other)
            if q_other is None or abs(q_other) <= 0.0:
                continue

            x2, y2, z2 = _centre_xyz(other)
            dx_cells, dy_cells, dz_cells = (x2 - x1, y2 - y1, z2 - z1)
            raw_len_cells = sqrt(dx_cells*dx_cells + dy_cells*dy_cells + dz_cells*dz_cells)
            if raw_len_cells <= 1e-12:
                continue

            scale_other = _interaction_scale_m_per_cell(other, world)
            scale_m_per_cell = max(scale_self, scale_other)
            softening_m = 0.5 * scale_m_per_cell
            r_m = max(raw_len_cells * scale_m_per_cell, softening_m)

            # Coulomb: like charges repel, unlike attract.
            # Force on self points AWAY from other if q_self*q_other > 0 else TOWARD other.
            same_sign = (q_self * q_other) > 0
            F = k_e * abs(q_self * q_other) / (r_m * r_m)
            a = F / m_self
            ux, uy, uz = (dx_cells / raw_len_cells, dy_cells / raw_len_cells, dz_cells / raw_len_cells)
            sign = -1.0 if same_sign else 1.0  # repel = away from other (negative of dx vector)
            out.add(sign * a * ux, sign * a * uy, sign * a * uz)

        return out


# ── Combined system facade ───────────────────────────────────────────────────
class ForceCouplerSystem:
    """Aggregates all pairwise couplers and returns a structured acceleration payload."""

    def __init__(self):
        self.gravity = GravitationalCoupler()
        self.electromagnetism = ElectromagneticCoupler()

    def acceleration_ms2_on(self,
                            entity: Any,
                            all_entities: Iterable[Any],
                            world: 'WorldPhysicsState') -> Dict[str, ForceVector]:
        g = self.gravity.acceleration_ms2_on(entity, all_entities, world)
        e = self.electromagnetism.acceleration_ms2_on(entity, all_entities, world)
        total = ForceVector(
            ax_ms2=g.ax_ms2 + e.ax_ms2,
            ay_ms2=g.ay_ms2 + e.ay_ms2,
            az_ms2=g.az_ms2 + e.az_ms2,
            contributors=g.contributors + e.contributors,
        )
        return {
            'gravity_pair': g,
            'electromagnetic': e,
            'total': total,
        }


__all__ = [
    'ForceVector',
    'GravitationalCoupler',
    'ElectromagneticCoupler',
    'ForceCouplerSystem',
]
