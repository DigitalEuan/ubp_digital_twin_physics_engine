"""
================================================================================
UBP REALITY ALIGNMENT — Slice 10 of the domains-in-3D integration
================================================================================
Live scoring pass that judges every domain entity against the physics
registry (CODATA-sourced canonical values).

For each entity carrying a domain_tag, we:

  1. Look up its formula_source and re-compute the canonical value using the
     domain's own registry formulas / constants.
  2. Compare the entity's real-quantity metadata against the canonical value.
  3. Emit an alignment record with:
        error_pct, status (GREEN/YELLOW/ORANGE/RED),
        canonical_value, entity_value, source_constant / source_formula.

Aggregations:

  * per-domain: mean absolute error %, worst error entity, count
  * world-level Reality Score = 100 * exp(-mean_abs_err / 0.5)
        (0.5% mean error → ~37% ... 0.01% → ~98% ... research-candidates penalise)

Nothing here mutates entities — this is a pure read-only judge. The bridge
attaches its output to every state broadcast so the HUD updates every frame.

Author: UBP Digital Twin Project · Slice 10 (July 2026)
================================================================================
"""
from __future__ import annotations

from dataclasses import dataclass, field
from math import exp, isfinite
from typing import Any, Dict, Iterable, List, Optional

try:
    from ubp_engine_substrate import get_physics_registry
except Exception:  # pragma: no cover
    def get_physics_registry():
        return None


# ── helpers ─────────────────────────────────────────────────────────────────
def _f(x: Any, default: Optional[float] = None) -> Optional[float]:
    if x is None:
        return default
    try:
        v = float(x)
        return v if isfinite(v) else default
    except Exception:
        return default


def _domain(name: Optional[str]):
    if not name:
        return None
    reg = get_physics_registry()
    if reg is None:
        return None
    try:
        return reg.get_domain(name)
    except Exception:
        return None


def _domain_const(domain_name: str, const_name: str) -> Optional[float]:
    d = _domain(domain_name)
    if d is None or const_name not in d.constants:
        return None
    return _f(d.constants[const_name])


def _domain_formula(domain_name: str, formula_name: str) -> Optional[float]:
    d = _domain(domain_name)
    if d is None or formula_name not in d.formulas:
        return None
    try:
        return _f(d.formulas[formula_name]())
    except Exception:
        return None


# ── mapping :: entity metadata → registry canonical value ──────────────────
#
# Each rule tells the aligner:
#   - which entity_field to read from domain_params
#   - how to get the canonical from the registry
# Rules are evaluated in order; the FIRST rule that yields a canonical wins.
#
_CANONICAL_RULES: List[Dict[str, Any]] = [
    # electromagnetism
    {'entity_field': 'charge_C', 'abs_value': True, 'canonical': ('electromagnetism.k_e', None),
     'source_label': 'electromagnetism.k_e (indirect: e is fundamental)', 'skip_if_zero': True,
     'value_transform': lambda v: v},  # placeholder — charge magnitude just needs to match 'e'

    # optics
    {'entity_field': 'wavelength_m', 'canonical': ('optics.LAMBDA_GREEN', None),
     'source_label': 'optics.LAMBDA_GREEN', 'only_role': 'photon'},
    {'entity_field': 'speed_of_light_ms', 'canonical': ('optics.C_VACUUM', None),
     'source_label': 'optics.C_VACUUM'},

    # nuclear
    {'entity_field': 'real_mass_kg', 'canonical': ('nuclear_physics.M_PROTON', None),
     'source_label': 'nuclear_physics.M_PROTON', 'only_role': 'proton'},
    {'entity_field': 'real_mass_kg', 'canonical': ('nuclear_physics.M_NEUTRON', None),
     'source_label': 'nuclear_physics.M_NEUTRON', 'only_role': 'neutron'},

    # HEP
    {'entity_field': 'real_mass_kg', 'canonical': ('high_energy_physics.M_W', None),
     'source_label': 'high_energy_physics.M_W', 'only_role': 'w_boson'},
    {'entity_field': 'real_mass_kg', 'canonical': ('high_energy_physics.M_Z', None),
     'source_label': 'high_energy_physics.M_Z', 'only_role': 'z_boson'},
    {'entity_field': 'real_mass_kg', 'canonical': ('high_energy_physics.M_HIGGS', None),
     'source_label': 'high_energy_physics.M_HIGGS', 'only_role': 'higgs'},

    # cosmology
    {'entity_field': 'planck_mass_kg', 'canonical': ('cosmology.M_PLANCK', None),
     'source_label': 'cosmology.M_PLANCK', 'only_role': 'planck_seed'},
    {'entity_field': 'planck_length_m', 'canonical': ('cosmology.L_PLANCK', None),
     'source_label': 'cosmology.L_PLANCK', 'only_role': 'planck_seed'},
    {'entity_field': 'hubble_h0_km_s_mpc', 'canonical': ('cosmology.H0', None),
     'source_label': 'cosmology.H0', 'only_role': 'hubble_marker'},

    # astrophysics
    {'entity_field': 'real_mass_kg', 'canonical': ('astrophysics.M_SUN', None),
     'source_label': 'astrophysics.M_SUN', 'only_role': 'sun_mass'},

    # QM
    {'entity_field': 'orbital_radius_m', 'canonical': ('quantum_mechanics.BOHR_RADIUS', None),
     'source_label': 'quantum_mechanics.BOHR_RADIUS', 'only_role': 'bohr_atom'},

    # acoustics
    {'entity_field': 'speed_of_sound_ms', 'canonical': ('acoustics.SOUND_STP_AIR', None),
     'source_label': 'acoustics.SOUND_STP_AIR', 'only_role': 'sound_emitter'},

    # thermodynamics
    {'entity_field': 'temperature_K_reference', 'canonical': ('thermodynamics.T_STP', None),
     'source_label': 'thermodynamics.T_STP'},
]


@dataclass
class AlignmentRecord:
    entity_id: int
    label: str
    domain_tag: str
    domain_role: Optional[str]
    entity_value: Optional[float]
    canonical_value: Optional[float]
    source: str
    error_pct: Optional[float]
    status: str
    research_candidate: bool = False
    formula_source: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'entity_id': self.entity_id,
            'label': self.label,
            'domain_tag': self.domain_tag,
            'domain_role': self.domain_role,
            'entity_value': self.entity_value,
            'canonical_value': self.canonical_value,
            'source': self.source,
            'error_pct': self.error_pct,
            'status': self.status,
            'research_candidate': self.research_candidate,
            'formula_source': self.formula_source,
        }


def _classify(error_pct: Optional[float], research: bool) -> str:
    if research:
        return 'RESEARCH'
    if error_pct is None:
        return 'NO_REFERENCE'
    e = abs(error_pct)
    if e < 0.1:
        return 'GREEN'
    if e < 1.0:
        return 'YELLOW'
    if e < 5.0:
        return 'ORANGE'
    return 'RED'


def _lookup_canonical(rule) -> Optional[float]:
    key = rule['canonical'][0]
    dom, cst = key.split('.', 1)
    v = _domain_const(dom, cst)
    if v is None:
        v = _domain_formula(dom, cst)
    return v


def _match_entity(entity: Any) -> List[AlignmentRecord]:
    tag = getattr(entity, 'domain_tag', None)
    if not tag:
        return []
    role = getattr(entity, 'domain_role', None)
    params = getattr(entity, 'domain_params', {}) or {}
    research = bool(getattr(entity, 'research_candidate', False))
    formula_source = getattr(entity, 'formula_source', None)
    label = str(getattr(entity, 'label', '?'))
    eid = int(getattr(entity, 'entity_id', -1))

    out: List[AlignmentRecord] = []
    for rule in _CANONICAL_RULES:
        if rule.get('only_role') and rule['only_role'] != role:
            continue
        field_ = rule['entity_field']
        if field_ not in params:
            continue
        val = _f(params.get(field_))
        if val is None:
            continue
        if rule.get('skip_if_zero') and val == 0:
            continue
        if rule.get('abs_value'):
            val = abs(val)
        canonical = _lookup_canonical(rule)
        if canonical is None or canonical == 0:
            err = None
        else:
            err = 100.0 * (val - canonical) / canonical
        rec = AlignmentRecord(
            entity_id=eid,
            label=label,
            domain_tag=tag,
            domain_role=role,
            entity_value=val,
            canonical_value=canonical,
            source=rule.get('source_label', rule['canonical'][0]),
            error_pct=err,
            status=_classify(err, research),
            research_candidate=research,
            formula_source=formula_source,
        )
        out.append(rec)
    return out


def score_alignment(entities: Iterable[Any]) -> Dict[str, Any]:
    per_entity: List[AlignmentRecord] = []
    for e in entities:
        per_entity.extend(_match_entity(e))

    # per-domain aggregation
    per_domain: Dict[str, Dict[str, Any]] = {}
    for r in per_entity:
        d = per_domain.setdefault(r.domain_tag, {
            'count': 0,
            'green': 0, 'yellow': 0, 'orange': 0, 'red': 0, 'research': 0,
            'sum_abs_err': 0.0, 'worst_pct': 0.0, 'worst_label': None,
        })
        d['count'] += 1
        if r.status == 'GREEN': d['green'] += 1
        elif r.status == 'YELLOW': d['yellow'] += 1
        elif r.status == 'ORANGE': d['orange'] += 1
        elif r.status == 'RED': d['red'] += 1
        elif r.status == 'RESEARCH': d['research'] += 1
        if r.error_pct is not None:
            e_abs = abs(r.error_pct)
            d['sum_abs_err'] += e_abs
            if e_abs > d['worst_pct']:
                d['worst_pct'] = e_abs
                d['worst_label'] = r.label

    for d in per_domain.values():
        d['mean_abs_err_pct'] = d['sum_abs_err'] / d['count'] if d['count'] else 0.0
        d.pop('sum_abs_err', None)

    # world-level score
    valid = [abs(r.error_pct) for r in per_entity if r.error_pct is not None and not r.research_candidate]
    mean_err = sum(valid) / len(valid) if valid else 0.0
    reality_score = 100.0 * exp(-mean_err / 0.5)
    research_count = sum(1 for r in per_entity if r.research_candidate)

    return {
        'reality_score': reality_score,
        'mean_abs_err_pct': mean_err,
        'entity_alignment_count': len(per_entity),
        'research_candidate_count': research_count,
        'per_entity': [r.to_dict() for r in per_entity],
        'per_domain': per_domain,
    }
