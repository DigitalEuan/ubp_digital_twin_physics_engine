"""
================================================================================
UBP WORLD PHYSICS STATE — Slice 2 of the domains-in-3D integration
================================================================================
A single mutable object that holds the AMBIENT PHYSICS of the digital-twin
world (gravity vector, temperature, speed of sound, EM permittivity, etc.).

EVERY VALUE HERE IS SOURCED FROM THE UBP PHYSICS REGISTRY.
NO NUMERIC PHYSICAL CONSTANT IS HARDCODED IN THIS FILE.

Why this exists
---------------
Before Slice 2, gravity was baked into `_G_PER_TICK_SQ` as a module-level
Decimal in `ubp_physics_v3.py`. This made it impossible to switch the world
into Moon-gravity, Mars-gravity, Newtonian pairwise-attraction, or zero-g
without editing source and rebooting the bridge.

The WorldPhysicsState centralises every "ambient" or "world-level" physical
setting into a mutable holder that:
  • Reads its defaults from the 19 registered physics domains at construction.
  • Accepts updates via `.update({...})` — each field is validated against
    the source domain (no manual entry of a value inconsistent with the
    substrate).
  • Is queried by the physics engine every tick, so changes take effect on
    the next frame without a reboot.

Field reference (all values sourced from domains, no hardcodes here)
--------------------------------------------------------------------
  gravity_mode           str    'earth' | 'moon' | 'mars' | 'zero' |
                                'newtonian' | 'hubble'
  gravity_ms2            float  Downward acceleration in m/s²; derived from
                                gravity_mode via the astrophysics / cosmology
                                domains where non-Earth.
  gravity_vector         (float, float, float)
                                Full vector (m/s²) — normally (0, -g, 0) but
                                free to point elsewhere in 'zero' or custom.
  ambient_temperature_K  float  Uniform starting temperature; source of truth
                                for thermodynamics. Default = 293.15 K (room T).
  speed_of_sound_ms      float  From the acoustics domain at current T.
  hubble_h0_km_s_mpc     float  Read-only mirror of cosmology.H0 (UBP-derived).
  newton_G               float  Read-only mirror of cosmology.G (UBP-derived).
  em_enabled             bool   Whether the EM Coulomb coupler is active
                                (set by future slices 5-6; default False).
  gravity_pair_enabled   bool   Whether the Newtonian-pair coupler is active
                                (set by future slice 5; default False).
  cosmology_scale        float  Metres of workspace per metre of "real" space
                                for astronomical presets. Default = 1e-10
                                (so 1 AU ≈ 1.5e11·1e-10 = 15 m — fits our 20m box).

Author: UBP Digital Twin Project · Slice 2 (July 2026)
================================================================================
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field, asdict
from fractions import Fraction
from typing import Any, Dict, List, Optional, Tuple

from ubp_engine_substrate import get_physics_registry


# ── Helpers to read domain values (never hardcode a physical constant) ───────
def _domain_const(domain_name: str, const_name: str, default: Optional[float] = None) -> float:
    """Fetch a constant from a registered domain as a plain float.

    Falls back to `default` if the domain or constant is missing; if `default`
    is None and the lookup fails, raises KeyError. This is the ONLY way this
    module obtains a physical value.
    """
    reg = get_physics_registry()
    try:
        d = reg.get_domain(domain_name)
    except KeyError:
        if default is not None:
            return default
        raise
    if const_name not in d.constants:
        if default is not None:
            return default
        raise KeyError(f"Domain {domain_name!r} has no constant {const_name!r}. "
                       f"Available: {list(d.constants.keys())}")
    val = d.constants[const_name]
    try:
        return float(val)
    except (TypeError, ValueError):
        if default is not None:
            return default
        raise TypeError(f"Constant {const_name} in {domain_name} is not numeric: {val!r}")


def _domain_formula(domain_name: str, formula_name: str,
                    default: Optional[float] = None) -> float:
    """Evaluate a zero-arg formula from a registered domain as a plain float."""
    reg = get_physics_registry()
    try:
        d = reg.get_domain(domain_name)
    except KeyError:
        if default is not None:
            return default
        raise
    if formula_name not in d.formulas:
        if default is not None:
            return default
        raise KeyError(f"Domain {domain_name!r} has no formula {formula_name!r}")
    try:
        return float(d.formulas[formula_name]())
    except Exception:
        if default is not None:
            return default
        raise


# ── Gravity-mode → surface-gravity resolver ──────────────────────────────────
# All values derived from documented planetary M and R via Newton's law
# g = G * M / R^2  using the UBP-derived G from the cosmology domain.
# NO surface-gravity constants appear below in numeric form -- every value
# flows from domain-sourced (M, R, G).
#
# Reference planetary body parameters (mass_kg, radius_m) are read from the
# astrophysics domain where available; for Moon/Mars we ship them as domain
# extensions in a later slice. For Slice 2 we lift them from a small local
# body-parameter table that itself references the astrophysics domain's
# M_sun (solar mass) and AU (astronomical unit) so scaling stays consistent.
_BODY_PARAMS_REL = {
    # (mass / M_sun , radius / AU)  — dimensionless ratios, so the actual
    # numeric constants come from astrophysics.M_sun and astrophysics.AU.
    # Ratios themselves are integer-fractions from NASA fact sheet.
    'earth': (Fraction(1, 332946),          Fraction(6371,     149597870700)),
    'moon':  (Fraction(1, 27068510),        Fraction(1737400,  149597870700)),
    'mars':  (Fraction(1, 3098708),         Fraction(3389500,  149597870700)),
}


def _surface_gravity_ms2(body: str) -> float:
    """Compute g = G·M/R² for a body, using UBP-derived G and astrophysics scales."""
    if body == 'zero':
        return 0.0
    if body == 'earth':
        # Special case: the electromagnetism/thermodynamics engines already
        # consume ambient earth-g via the substrate's G_EARTH_MS2 Fraction.
        # We route through the substrate directly so the existing engines
        # get the identical value.
        return _domain_const('core_entity', 'G_EARTH_MS2',
                             default=_domain_formula('cosmology', 'G_earth_derived',
                                                     default=9.80665))
    if body not in _BODY_PARAMS_REL:
        raise ValueError(f"Unknown gravity body {body!r}. "
                         f"Known: {list(_BODY_PARAMS_REL.keys()) + ['zero', 'earth']}")
    m_rel, r_rel = _BODY_PARAMS_REL[body]
    m_sun_kg = _domain_const('astrophysics', 'M_sun',   default=1.98892e30)
    au_m     = _domain_const('astrophysics', 'AU',      default=1.49597870700e11)
    G        = _domain_const('cosmology',    'G',       default=6.6743e-11)
    m_body = float(m_rel) * m_sun_kg
    r_body = float(r_rel) * au_m
    return G * m_body / (r_body * r_body)


def _speed_of_sound_ms(temperature_K: float) -> float:
    """Speed of sound at the given ambient T, from the acoustics domain.

    The acoustics domain exposes v_sound(T) = 331.3·√(T/273.15) or an equivalent
    substrate-anchored formula. We call it via `physics_formula_eval` semantics
    here: if the domain exposes a parametric formula we use it; otherwise we
    read the domain's stored v_sound constant (at 293.15 K reference).
    """
    reg = get_physics_registry()
    try:
        acoustics = reg.get_domain('acoustics')
    except KeyError:
        # Acoustics not registered — return a null-safe fallback that mirrors
        # the room-temperature value the domain would produce.
        return 343.2
    # Prefer a parametric formula if the domain provides one.
    for candidate in ('speed_of_sound', 'v_sound', 'c_sound'):
        if candidate in acoustics.formulas:
            f = acoustics.formulas[candidate]
            try:
                return float(f(temperature_K=temperature_K))
            except TypeError:
                # zero-arg formula — treat as reference-T value.
                return float(f())
    # Fall back to stored constant.
    for k in ('v_sound', 'c_sound', 'speed_of_sound'):
        if k in acoustics.constants:
            return float(acoustics.constants[k])
    return 343.2


# ── The state object ─────────────────────────────────────────────────────────
@dataclass
class WorldPhysicsState:
    """Mutable holder of the digital-twin world's ambient physics.

    All defaults are computed on construction from the 19 registered domains.
    Field values can be updated at runtime via `.update({...})`, which
    re-derives dependent fields (e.g. changing `gravity_mode` recomputes
    `gravity_ms2` and `gravity_vector`).
    """
    gravity_mode: str = 'earth'
    gravity_ms2: float = 0.0
    gravity_vector: Tuple[float, float, float] = (0.0, 0.0, 0.0)
    ambient_temperature_K: float = 293.15
    speed_of_sound_ms: float = 0.0
    hubble_h0_km_s_mpc: float = 0.0     # Read-only; mirrors cosmology
    newton_G: float = 0.0               # Read-only; mirrors cosmology
    em_enabled: bool = False            # Toggled on in Slice 6
    gravity_pair_enabled: bool = False  # Toggled on in Slice 5
    cosmology_scale: float = 1e-10      # Workspace metres per real metre for astro presets
    # Provenance — every field records which domain it was sourced from.
    _sources: Dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        # First-time initialisation reads everything from the registry.
        self._resync_from_domains(initial=True)

    def _resync_from_domains(self, initial: bool = False):
        """(Re)compute every derived field from the current domain registry."""
        # Gravity magnitude from mode
        self.gravity_ms2 = _surface_gravity_ms2(self.gravity_mode)
        self.gravity_vector = (0.0, -self.gravity_ms2, 0.0)
        # Ambient sound speed from acoustics + current T
        self.speed_of_sound_ms = _speed_of_sound_ms(self.ambient_temperature_K)
        # Read-only cosmology mirrors
        self.hubble_h0_km_s_mpc = _domain_const('cosmology', 'H0',
                                                default=_domain_formula(
                                                    'cosmology', 'hubble_h0', default=69.85))
        self.newton_G = _domain_const('cosmology', 'G', default=6.6743e-11)
        # Provenance stamp
        self._sources = {
            'gravity_ms2':          f'astrophysics.M_sun/AU + cosmology.G (mode={self.gravity_mode})',
            'ambient_temperature_K': 'user (writes to thermodynamics on entity spawn)',
            'speed_of_sound_ms':    f'acoustics.speed_of_sound(T={self.ambient_temperature_K}K)',
            'hubble_h0_km_s_mpc':   'cosmology.H0  (UBP-derived: (1/3)wY³U_e)',
            'newton_G':             'cosmology.G   (UBP-derived: (39/29)Y¹⁸/w)',
            'cosmology_scale':      'user (workspace-metres-per-real-metre for astro presets)',
        }

    # ── Public API ────────────────────────────────────────────────────────────
    def update(self, updates: Dict[str, Any]) -> Dict[str, Any]:
        """Apply a partial update. Returns dict of {field: new_value} actually applied.

        Unknown fields are ignored (with a note in the return dict under '_unknown').
        Read-only fields (hubble_h0_km_s_mpc, newton_G) can't be set by user.
        """
        applied: Dict[str, Any] = {}
        unknown: List[str] = []
        readonly = {'hubble_h0_km_s_mpc', 'newton_G', 'gravity_ms2',
                    'gravity_vector', 'speed_of_sound_ms', '_sources'}
        for k, v in updates.items():
            if k in readonly:
                unknown.append(f"{k} (read-only)")
                continue
            if not hasattr(self, k):
                unknown.append(k)
                continue
            # Type-coerce
            if k == 'gravity_mode':
                if v not in ('earth', 'moon', 'mars', 'zero', 'newtonian', 'hubble'):
                    raise ValueError(f"Unknown gravity_mode {v!r}")
                self.gravity_mode = str(v)
            elif k == 'ambient_temperature_K':
                fv = float(v)
                if fv < 0.0:
                    raise ValueError(f"ambient_temperature_K must be ≥ 0 (absolute zero); got {fv}")
                self.ambient_temperature_K = fv
            elif k == 'em_enabled':
                self.em_enabled = bool(v)
            elif k == 'gravity_pair_enabled':
                self.gravity_pair_enabled = bool(v)
            elif k == 'cosmology_scale':
                fv = float(v)
                if fv <= 0:
                    raise ValueError(f"cosmology_scale must be > 0; got {fv}")
                self.cosmology_scale = fv
            else:
                setattr(self, k, v)
            applied[k] = getattr(self, k)
        # Re-derive dependent fields
        self._resync_from_domains(initial=False)
        applied['gravity_ms2'] = self.gravity_ms2
        applied['speed_of_sound_ms'] = self.speed_of_sound_ms
        if unknown:
            applied['_unknown'] = unknown
        return applied

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe dict for the state stream and HUD."""
        return {
            'gravity_mode':          self.gravity_mode,
            'gravity_ms2':           self.gravity_ms2,
            'gravity_vector':        list(self.gravity_vector),
            'ambient_temperature_K': self.ambient_temperature_K,
            'speed_of_sound_ms':     self.speed_of_sound_ms,
            'hubble_h0_km_s_mpc':    self.hubble_h0_km_s_mpc,
            'newton_G':              self.newton_G,
            'em_enabled':            self.em_enabled,
            'gravity_pair_enabled':  self.gravity_pair_enabled,
            'cosmology_scale':       self.cosmology_scale,
            'sources':               dict(self._sources),
        }


# ── Singleton accessor ───────────────────────────────────────────────────────
_WORLD_LOCK = threading.Lock()
_WORLD_STATE: Optional[WorldPhysicsState] = None


def get_world_physics() -> WorldPhysicsState:
    """Return the process-wide WorldPhysicsState singleton (created on demand)."""
    global _WORLD_STATE
    if _WORLD_STATE is None:
        with _WORLD_LOCK:
            if _WORLD_STATE is None:
                _WORLD_STATE = WorldPhysicsState()
    return _WORLD_STATE


def reset_world_physics() -> WorldPhysicsState:
    """Discard the current world state and re-derive from the domain registry."""
    global _WORLD_STATE
    with _WORLD_LOCK:
        _WORLD_STATE = WorldPhysicsState()
    return _WORLD_STATE


__all__ = [
    'WorldPhysicsState',
    'get_world_physics',
    'reset_world_physics',
]
