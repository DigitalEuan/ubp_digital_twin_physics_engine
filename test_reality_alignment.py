from dataclasses import dataclass, field

import ubp_reality_alignment as ura
from ubp_reality_alignment import score_alignment


@dataclass
class E:
    entity_id: int = 1
    label: str = 'x'
    domain_tag: str | None = None
    domain_role: str | None = None
    domain_params: dict = field(default_factory=dict)
    research_candidate: bool = False
    formula_source: str | None = None


def test_empty_world_returns_perfect_score():
    out = score_alignment([])
    assert out['reality_score'] == 100.0
    assert out['entity_alignment_count'] == 0


def test_sound_emitter_gets_scored_with_monkeypatched_canonical(monkeypatch):
    def fake_lookup(rule):
        if rule.get('only_role') == 'sound_emitter':
            return 343.2
        return None
    monkeypatch.setattr(ura, '_lookup_canonical', fake_lookup)
    e = E(
        entity_id=42,
        label='SoundEmitter_1',
        domain_tag='acoustics',
        domain_role='sound_emitter',
        domain_params={'speed_of_sound_ms': 343.2},
    )
    out = score_alignment([e])
    assert out['entity_alignment_count'] >= 1
    row = out['per_entity'][0]
    assert row['status'] == 'GREEN'
    assert row['canonical_value'] == 343.2


def test_research_candidate_flagged(monkeypatch):
    monkeypatch.setattr(ura, '_lookup_canonical', lambda rule: 5.0e-7 if rule.get('only_role') == 'photon' else None)
    e = E(
        entity_id=7,
        label='Photon_500nm',
        domain_tag='optics',
        domain_role='photon',
        domain_params={'wavelength_m': 5.0e-7},
        research_candidate=True,
    )
    out = score_alignment([e])
    assert out['research_candidate_count'] >= 1
    assert any(r['status'] == 'RESEARCH' for r in out['per_entity'])
