from dataclasses import dataclass, field

from ubp_field_sampling import sample_field_points


@dataclass
class P:
    x: float
    y: float
    z: float


@dataclass
class Dummy:
    position: P
    size: tuple[float, float, float] = (1.0, 1.0, 1.0)
    domain_tag: str | None = None
    domain_params: dict = field(default_factory=dict)
    temperature_K: float = 293.15


@dataclass
class World:
    newton_G: float = 6.6743e-11
    ambient_temperature_K: float = 293.15
    cosmology_scale: float = 1e-9


def test_gravity_field_points_toward_mass():
    world = World()
    body = Dummy(
        position=P(10.0, 2.0, 10.0),
        domain_tag='astrophysics',
        domain_params={
            'real_mass_kg': 5.972e24,
            'pairwise_gravity_enabled': True,
            'interaction_scale_m_per_cell': 1.0e6,
        },
    )
    res = sample_field_points('gravity', [{'x': 6.0, 'y': 2.5, 'z': 10.5}], [body], world)
    sample = res['samples'][0]
    assert sample['vector']['x'] > 0
    assert abs(sample['vector']['z']) < 1e-12


def test_em_field_points_away_from_positive_charge():
    world = World()
    charge = Dummy(
        position=P(10.0, 2.0, 10.0),
        domain_tag='electromagnetism',
        domain_params={
            'charge_C': 1.602176634e-19,
            'pairwise_em_enabled': True,
            'coulomb_constant': 8.9875517923e9,
            'interaction_scale_m_per_cell': 1.0e-9,
        },
    )
    res = sample_field_points('em', [{'x': 14.0, 'y': 2.5, 'z': 10.5}], [charge], world)
    sample = res['samples'][0]
    assert sample['vector']['x'] > 0


def test_thermal_field_reflects_hot_body():
    world = World(ambient_temperature_K=293.15)
    hot = Dummy(position=P(10.0, 2.0, 10.0), temperature_K=500.0)
    res = sample_field_points('thermal', [{'x': 10.0, 'y': 2.0, 'z': 12.0}], [hot], world)
    sample = res['samples'][0]
    assert sample['scalar'] > world.ambient_temperature_K
    assert sample['delta_K'] > 0
