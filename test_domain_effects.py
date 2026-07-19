from dataclasses import dataclass, field
from decimal import Decimal

from ubp_domain_effects import DomainEffectsEngine


@dataclass
class Pos:
    x: Decimal = Decimal('0')
    y: Decimal = Decimal('0')
    z: Decimal = Decimal('0')


@dataclass
class Ent:
    entity_id: int
    label: str = 'e'
    position: Pos = field(default_factory=Pos)
    size: tuple = (1.0, 1.0, 1.0)
    is_static: bool = False
    is_dissolving: bool = False
    temperature_K: float = 500.0
    domain_tag: str | None = None
    domain_role: str | None = None
    domain_params: dict = field(default_factory=dict)


@dataclass
class World:
    gravity_mode: str = 'earth'
    hubble_h0_km_s_mpc: float = 69.85
    cosmology_scale: float = 1e-3
    speed_of_sound_ms: float = 343.0
    ambient_temperature_K: float = 293.15


def test_thermal_cooling_reduces_temperature():
    eng = DomainEffectsEngine(ticks_per_second=60.0)
    e = Ent(entity_id=1, temperature_K=500.0, domain_params={'thermal_relaxation_k_s': 1.0})
    world = World()
    report = eng.step([e], world, tick=1)
    assert e.temperature_K < 500.0
    assert report['counts']['thermal'] >= 1


def test_photon_moves_at_scaled_c():
    eng = DomainEffectsEngine(ticks_per_second=60.0)
    e = Ent(
        entity_id=1,
        domain_tag='optics',
        domain_role='photon',
        position=Pos(Decimal('5'), Decimal('2'), Decimal('5')),
        domain_params={'speed_of_light_ms': 299_792_458.0,
                       'interaction_scale_m_per_cell': 1e9,
                       'propagation_dir': [1.0, 0.0, 0.0]},
    )
    world = World()
    prev_x = float(e.position.x)
    eng.step([e], world, tick=1)
    assert float(e.position.x) > prev_x


def test_hubble_flow_only_when_mode_hubble():
    eng = DomainEffectsEngine(ticks_per_second=60.0, workspace_centre=(0.0, 0.0, 0.0))
    e = Ent(
        entity_id=1,
        domain_tag='cosmology',
        domain_role='hubble_marker',
        position=Pos(Decimal('4'), Decimal('0'), Decimal('0')),
        domain_params={'respects_hubble_flow': True},
    )
    # earth mode → no drift
    world = World(gravity_mode='earth')
    prev = float(e.position.x)
    eng.step([e], world, tick=1)
    assert float(e.position.x) == prev
    # hubble mode → drifts outward
    world2 = World(gravity_mode='hubble')
    eng.step([e], world2, tick=2)
    assert float(e.position.x) > prev


def test_acoustic_wavefront_grows():
    eng = DomainEffectsEngine(ticks_per_second=60.0)
    e = Ent(
        entity_id=1,
        domain_tag='acoustics',
        domain_role='sound_emitter',
        domain_params={'wavefront_radius_m': 0.0},
    )
    world = World(speed_of_sound_ms=343.0)
    eng.step([e], world, tick=1)
    assert e.domain_params['wavefront_radius_m'] > 0
