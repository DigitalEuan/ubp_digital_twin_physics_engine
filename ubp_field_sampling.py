"""
================================================================================
UBP FIELD SAMPLING — Slices 7 + 8 of the domains-in-3D integration
================================================================================
Provides lightweight field sampling for the live 3D workspace.

Slice 7: static domain overlays rely on entity metadata only.
Slice 8: this module exposes sampled gravity / electromagnetic / thermal fields
         at arbitrary workspace coordinates so the frontend can draw live glyphs.

Design notes
------------
- Reads all real quantities from entity domain metadata and world state.
- Uses the same interaction-scale metadata introduced in earlier slices.
- Returns SI-first quantities (m/s², N/C, K). Frontend visualisation rescales
  them for readability without mutating the underlying values.
================================================================================
"""
from __future__ import annotations

from math import sqrt
from typing import Any, Dict, Iterable, List

from ubp_force_couplers import (
    _centre_xyz,
    _charge_C,
    _coulomb_constant,
    _domain_params,
    _f,
    _interaction_scale_m_per_cell,
    _pairwise_em_enabled,
    _pairwise_gravity_enabled,
    _real_mass_kg,
)


def _sample_point_xyz(point: Dict[str, Any]) -> tuple[float, float, float]:
    return (
        _f(point.get('x', 0.0)),
        _f(point.get('y', 0.0)),
        _f(point.get('z', 0.0)),
    )


def _vector_payload(px: float, py: float, pz: float, vx: float, vy: float, vz: float) -> Dict[str, Any]:
    mag = sqrt(vx * vx + vy * vy + vz * vz)
    return {
        'point': {'x': px, 'y': py, 'z': pz},
        'vector': {'x': vx, 'y': vy, 'z': vz},
        'magnitude': mag,
    }


def sample_gravity_field(points: List[Dict[str, Any]], entities: Iterable[Any], world: Any) -> List[Dict[str, Any]]:
    entities = list(entities)
    out: List[Dict[str, Any]] = []
    G = _f(getattr(world, 'newton_G', 0.0))
    for point in points:
        px, py, pz = _sample_point_xyz(point)
        gx = gy = gz = 0.0
        contributors = 0
        for entity in entities:
            if not _pairwise_gravity_enabled(entity):
                continue
            m = _real_mass_kg(entity)
            if m is None or m <= 0.0:
                continue
            ex, ey, ez = _centre_xyz(entity)
            dx_cells, dy_cells, dz_cells = (ex - px, ey - py, ez - pz)
            raw_len_cells = sqrt(dx_cells * dx_cells + dy_cells * dy_cells + dz_cells * dz_cells)
            if raw_len_cells <= 1e-12:
                continue
            scale = _interaction_scale_m_per_cell(entity, world)
            softening_m = max(0.5 * scale, 1e-12)
            r_m = max(raw_len_cells * scale, softening_m)
            a = G * m / (r_m * r_m)
            ux, uy, uz = (dx_cells / raw_len_cells, dy_cells / raw_len_cells, dz_cells / raw_len_cells)
            gx += a * ux
            gy += a * uy
            gz += a * uz
            contributors += 1
        payload = _vector_payload(px, py, pz, gx, gy, gz)
        payload['contributors'] = contributors
        out.append(payload)
    return out


def sample_em_field(points: List[Dict[str, Any]], entities: Iterable[Any], world: Any) -> List[Dict[str, Any]]:
    entities = list(entities)
    out: List[Dict[str, Any]] = []
    default_ke = None
    for entity in entities:
        maybe = _coulomb_constant(entity)
        if maybe:
            default_ke = maybe
            break
    if default_ke is None:
        default_ke = 8.9875517923e9

    for point in points:
        px, py, pz = _sample_point_xyz(point)
        ex_total = ey_total = ez_total = 0.0
        contributors = 0
        for entity in entities:
            if not _pairwise_em_enabled(entity):
                continue
            q = _charge_C(entity)
            if q is None or abs(q) <= 0.0:
                continue
            ex, ey, ez = _centre_xyz(entity)
            dx_cells, dy_cells, dz_cells = (px - ex, py - ey, pz - ez)
            raw_len_cells = sqrt(dx_cells * dx_cells + dy_cells * dy_cells + dz_cells * dz_cells)
            if raw_len_cells <= 1e-12:
                continue
            scale = _interaction_scale_m_per_cell(entity, world)
            softening_m = max(0.5 * scale, 1e-12)
            r_m = max(raw_len_cells * scale, softening_m)
            E = default_ke * q / (r_m * r_m)
            ux, uy, uz = (dx_cells / raw_len_cells, dy_cells / raw_len_cells, dz_cells / raw_len_cells)
            ex_total += E * ux
            ey_total += E * uy
            ez_total += E * uz
            contributors += 1
        payload = _vector_payload(px, py, pz, ex_total, ey_total, ez_total)
        payload['contributors'] = contributors
        out.append(payload)
    return out


def sample_thermal_field(points: List[Dict[str, Any]], entities: Iterable[Any], world: Any) -> List[Dict[str, Any]]:
    entities = list(entities)
    ambient = _f(getattr(world, 'ambient_temperature_K', 293.15))
    out: List[Dict[str, Any]] = []
    for point in points:
        px, py, pz = _sample_point_xyz(point)
        numerator = 0.0
        denominator = 0.0
        hottest_delta = 0.0
        contributors = 0
        for entity in entities:
            temp = getattr(entity, 'temperature_k', None)
            if temp is None:
                temp = getattr(entity, 'temperature_K', None)
            temp = _f(temp)
            if temp <= 0:
                continue
            ex, ey, ez = _centre_xyz(entity)
            dx, dy, dz = (ex - px, ey - py, ez - pz)
            r2 = dx * dx + dy * dy + dz * dz
            weight = 1.0 / max(r2, 1.0)
            delta = temp - ambient
            numerator += delta * weight
            denominator += weight
            hottest_delta = max(hottest_delta, abs(delta))
            contributors += 1
        scalar = ambient + (numerator / denominator if denominator > 0 else 0.0)
        out.append({
            'point': {'x': px, 'y': py, 'z': pz},
            'scalar': scalar,
            'ambient_temperature_K': ambient,
            'delta_K': scalar - ambient,
            'contributors': contributors,
            'magnitude': abs(scalar - ambient) / max(hottest_delta, 1.0),
        })
    return out


def sample_field_points(field: str, points: List[Dict[str, Any]], entities: Iterable[Any], world: Any) -> Dict[str, Any]:
    field = str(field or '').strip().lower()
    if field == 'gravity':
        samples = sample_gravity_field(points, entities, world)
    elif field in ('em', 'electromagnetism', 'electric'):
        field = 'em'
        samples = sample_em_field(points, entities, world)
    elif field in ('thermal', 'temperature', 'thermodynamics'):
        field = 'thermal'
        samples = sample_thermal_field(points, entities, world)
    else:
        raise ValueError(f'Unsupported field: {field}')
    return {
        'type': 'domain_field_sample',
        'field': field,
        'sample_count': len(samples),
        'samples': samples,
    }
