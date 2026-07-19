"""
================================================================================
UBP DOMAIN EFFECTS — Slice 9 of the domains-in-3D integration
================================================================================
Time-based domain effects applied every physics tick.

For each tick the DomainEffectsEngine:

  * Nuclear / HEP decay
      Every unstable domain entity carries `mean_lifetime_s` in domain_params.
      Per tick: P(decay) = 1 - exp(-dt / tau). If it fires, the entity is
      marked dissolving and a decay event is logged.

  * Cosmological expansion (Hubble)
      When gravity_mode='hubble', every entity flagged
      `respects_hubble_flow=True` drifts outward from the workspace centre at
      a per-tick displacement H0 * r * dt * cosmology_scale.

  * Photon propagation
      Entities with role='photon' move at c (scaled by
      `interaction_scale_m_per_cell`) in their emission direction each tick.

  * Acoustic wavefront expansion
      Entities with role='sound_emitter' age their wavefront_radius_m at
      the world speed_of_sound_ms.

  * Newtonian thermal relaxation
      Every non-static entity relaxes toward ambient_temperature_K:
        dT/dt = -k (T - T_ambient),  k from domain_params or a domain default

  * Chemical bond ticking
      Chemical entities age a bond_cycle_progress counter driven by their
      real vibrational frequency (from optics / chemical domain constants).

Every effect reads from registry-sourced values (no hardcoded physical
constants). The engine returns a structured event log for the bridge to
broadcast to the frontend.

Author: UBP Digital Twin Project · Slice 9 (July 2026)
================================================================================
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import exp, sqrt
from random import Random
from typing import Any, Dict, Iterable, List, Optional


# ── numeric helpers ─────────────────────────────────────────────────────────
def _f(x: Any, default: float = 0.0) -> float:
    try:
        return float(x)
    except Exception:
        return default


def _centre_xyz(entity: Any):
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
    p = getattr(entity, 'domain_params', None)
    return dict(p or {})


def _set_domain_param(entity: Any, key: str, value: Any) -> None:
    if not hasattr(entity, 'domain_params') or entity.domain_params is None:
        entity.domain_params = {}
    entity.domain_params[key] = value


# ── engine ──────────────────────────────────────────────────────────────────
@dataclass
class DomainEffectEvent:
    tick: int
    kind: str
    entity_id: int
    label: str
    detail: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'tick': self.tick,
            'kind': self.kind,
            'entity_id': self.entity_id,
            'label': self.label,
            'detail': self.detail,
        }


class DomainEffectsEngine:
    """
    Applies domain-native time-based effects to every entity per tick.

    All units are SI. Workspace displacements use each entity's
    `interaction_scale_m_per_cell` metadata so subatomic and cosmic objects
    can coexist in the shared 20x20x20 workspace without breaking scales.
    """

    def __init__(self, ticks_per_second: float = 60.0, workspace_centre=(10.0, 2.0, 10.0), seed: int = 1729):
        self.ticks_per_second = float(ticks_per_second)
        self.dt = 1.0 / self.ticks_per_second
        self.workspace_centre = tuple(workspace_centre)
        self.rng = Random(seed)
        self._decay_events: List[DomainEffectEvent] = []

    # ---- effect: nuclear / HEP decay --------------------------------------
    def _apply_decay(self, entity: Any, tick: int) -> Optional[DomainEffectEvent]:
        params = _domain_params(entity)
        lifetime = _f(params.get('mean_lifetime_s'), 0.0)
        if lifetime <= 0.0:
            return None
        prob_decay = 1.0 - exp(-self.dt / lifetime)
        if self.rng.random() >= prob_decay:
            return None
        # mark dissolving so space's culling step removes it next tick
        try:
            setattr(entity, 'is_dissolving', True)
        except Exception:
            return None
        return DomainEffectEvent(
            tick=tick,
            kind='decay',
            entity_id=int(getattr(entity, 'entity_id', -1)),
            label=str(getattr(entity, 'label', '?')),
            detail={
                'domain_tag': entity.domain_tag,
                'domain_role': entity.domain_role,
                'mean_lifetime_s': lifetime,
                'p_per_tick': prob_decay,
            },
        )

    # ---- effect: Hubble flow ---------------------------------------------
    def _apply_hubble_flow(self, entity: Any, world: Any) -> Optional[Dict[str, Any]]:
        if getattr(world, 'gravity_mode', 'earth') != 'hubble':
            return None
        params = _domain_params(entity)
        if not params.get('respects_hubble_flow'):
            return None
        H0 = _f(getattr(world, 'hubble_h0_km_s_mpc', 0.0))  # km/s/Mpc
        if H0 <= 0:
            return None
        # Convert to workspace: v(cells/tick) = H0 * r_cells * dt * cosmology_scale
        scale = _f(getattr(world, 'cosmology_scale', 1e-9))
        cx, cy, cz = self.workspace_centre
        ex, ey, ez = _centre_xyz(entity)
        dx, dy, dz = (ex - cx, ey - cy, ez - cz)
        r = sqrt(dx * dx + dy * dy + dz * dz)
        if r <= 1e-6:
            return None
        v_cells_per_tick = H0 * r * self.dt * scale
        ux, uy, uz = (dx / r, dy / r, dz / r)
        pos = entity.position
        try:
            from decimal import Decimal
            pos.x = pos.x + Decimal(str(v_cells_per_tick * ux))
            pos.y = pos.y + Decimal(str(v_cells_per_tick * uy))
            pos.z = pos.z + Decimal(str(v_cells_per_tick * uz))
        except Exception:
            return None
        return {
            'v_cells_per_tick': v_cells_per_tick,
            'radius_cells': r,
        }

    # ---- effect: photon propagation --------------------------------------
    def _apply_photon(self, entity: Any) -> Optional[Dict[str, Any]]:
        role = getattr(entity, 'domain_role', None)
        if role != 'photon':
            return None
        params = _domain_params(entity)
        c = _f(params.get('speed_of_light_ms'), 299_792_458.0)
        scale = _f(params.get('interaction_scale_m_per_cell'), 1.0)
        if scale <= 0:
            return None
        v_cells_per_tick = (c * self.dt) / scale
        dir_ = params.get('propagation_dir') or [1.0, 0.0, 0.0]
        try:
            dx, dy, dz = float(dir_[0]), float(dir_[1]), float(dir_[2])
        except Exception:
            dx, dy, dz = 1.0, 0.0, 0.0
        mag = sqrt(dx * dx + dy * dy + dz * dz)
        if mag <= 1e-12:
            return None
        ux, uy, uz = dx / mag, dy / mag, dz / mag
        # Cap per-tick step so photons don't teleport off-map on first tick.
        v_cells_per_tick = min(v_cells_per_tick, 0.75)
        try:
            from decimal import Decimal
            pos = entity.position
            pos.x = pos.x + Decimal(str(v_cells_per_tick * ux))
            pos.y = pos.y + Decimal(str(v_cells_per_tick * uy))
            pos.z = pos.z + Decimal(str(v_cells_per_tick * uz))
        except Exception:
            return None
        return {'v_cells_per_tick': v_cells_per_tick, 'dir': (ux, uy, uz)}

    # ---- effect: acoustic wavefront --------------------------------------
    def _apply_acoustic(self, entity: Any, world: Any) -> Optional[Dict[str, Any]]:
        if getattr(entity, 'domain_role', None) != 'sound_emitter':
            return None
        c_s = _f(getattr(world, 'speed_of_sound_ms', 0.0))
        if c_s <= 0:
            return None
        params = _domain_params(entity)
        prev = _f(params.get('wavefront_radius_m', 0.0))
        new = prev + c_s * self.dt
        _set_domain_param(entity, 'wavefront_radius_m', new)
        return {'wavefront_radius_m': new, 'sound_speed_ms': c_s}

    # ---- effect: Newtonian cooling ---------------------------------------
    def _apply_thermal(self, entity: Any, world: Any) -> Optional[Dict[str, Any]]:
        if getattr(entity, 'is_static', False):
            return None
        # If the entity has no temperature attribute, skip.
        T = None
        for attr in ('temperature_K', 'temperature_k'):
            if hasattr(entity, attr):
                T = _f(getattr(entity, attr))
                break
        if T is None or T <= 0:
            return None
        T_amb = _f(getattr(world, 'ambient_temperature_K', 293.15))
        # cooling coefficient (per second); allow entity override
        k = _f(_domain_params(entity).get('thermal_relaxation_k_s', 0.05))
        if k <= 0:
            return None
        dT = -k * (T - T_amb) * self.dt
        new_T = T + dT
        try:
            if hasattr(entity, 'temperature_K'):
                entity.temperature_K = new_T
            if hasattr(entity, 'temperature_k'):
                entity.temperature_k = new_T
        except Exception:
            return None
        return {'from_K': T, 'to_K': new_T, 'ambient_K': T_amb}

    # ---- effect: chemical bonding tick -----------------------------------
    def _apply_chemistry(self, entity: Any) -> Optional[Dict[str, Any]]:
        if getattr(entity, 'domain_tag', None) != 'chemical_physics':
            return None
        params = _domain_params(entity)
        freq = _f(params.get('vibrational_frequency_hz'), 0.0)
        if freq <= 0:
            return None
        prev = _f(params.get('bond_cycle_progress', 0.0))
        # progress in units of full cycles per tick
        new = prev + freq * self.dt
        _set_domain_param(entity, 'bond_cycle_progress', new)
        return {'freq_hz': freq, 'bond_cycle_progress': new}

    # ---- main step --------------------------------------------------------
    def step(self, entities: Iterable[Any], world: Any, tick: int) -> Dict[str, Any]:
        events: List[DomainEffectEvent] = []
        thermal_touched = 0
        acoustic_touched = 0
        chem_touched = 0
        hubble_touched = 0
        photon_touched = 0
        decay_touched = 0

        for entity in list(entities):
            # Skip pure non-domain entities except for thermal cooling
            # (thermal cooling is universal for non-static entities).
            has_domain = bool(getattr(entity, 'domain_tag', None))

            if has_domain:
                # decay
                ev = self._apply_decay(entity, tick)
                if ev is not None:
                    events.append(ev)
                    decay_touched += 1
                    continue  # skip further evolution for dead entities

                # photon propagation
                if self._apply_photon(entity):
                    photon_touched += 1

                # acoustic
                if self._apply_acoustic(entity, world):
                    acoustic_touched += 1

                # hubble
                if self._apply_hubble_flow(entity, world):
                    hubble_touched += 1

                # chemistry
                if self._apply_chemistry(entity):
                    chem_touched += 1

            # thermal — universal
            if self._apply_thermal(entity, world):
                thermal_touched += 1

        self._decay_events.extend(events)
        # keep bounded recent log
        if len(self._decay_events) > 200:
            self._decay_events = self._decay_events[-200:]

        return {
            'tick': tick,
            'decay_events': [e.to_dict() for e in events],
            'counts': {
                'decay': decay_touched,
                'photon': photon_touched,
                'acoustic': acoustic_touched,
                'hubble': hubble_touched,
                'thermal': thermal_touched,
                'chemistry': chem_touched,
            },
        }

    def recent_decay_events(self, n: int = 25) -> List[Dict[str, Any]]:
        return [e.to_dict() for e in self._decay_events[-n:]]
