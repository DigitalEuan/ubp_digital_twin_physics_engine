from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def test_module_parses():
    ast.parse((REPO_ROOT / 'ubp_force_couplers.py').read_text())


@dataclass
class DummyPos:
    x: float
    y: float
    z: float


class DummyEntity:
    def __init__(self, *, x, y, z, size=(1, 1, 1), domain_tag='astrophysics', domain_params=None):
        self.position = DummyPos(x, y, z)
        self.size = size
        self.domain_tag = domain_tag
        self.domain_params = domain_params or {}


class DummyWorld:
    def __init__(self):
        self.gravity_pair_enabled = True
        self.gravity_mode = 'newtonian'
        self.em_enabled = True
        self.newton_G = 1.0
        self.cosmology_scale = 1.0


def test_gravity_attracts_toward_other_body():
    from ubp_force_couplers import GravitationalCoupler

    world = DummyWorld()
    left = DummyEntity(
        x=0, y=0, z=0,
        domain_params={'real_mass_kg': 2.0, 'interaction_scale_m_per_cell': 1.0, 'pairwise_gravity_enabled': True},
    )
    right = DummyEntity(
        x=4, y=0, z=0,
        domain_params={'real_mass_kg': 3.0, 'interaction_scale_m_per_cell': 1.0, 'pairwise_gravity_enabled': True},
    )
    a_left = GravitationalCoupler().acceleration_ms2_on(left, [left, right], world)
    a_right = GravitationalCoupler().acceleration_ms2_on(right, [left, right], world)

    assert a_left.ax_ms2 > 0, 'Left body should accelerate rightward toward right body'
    assert a_right.ax_ms2 < 0, 'Right body should accelerate leftward toward left body'
    assert abs(a_left.ay_ms2) < 1e-12 and abs(a_left.az_ms2) < 1e-12


def test_em_like_charges_repel():
    from ubp_force_couplers import ElectromagneticCoupler

    world = DummyWorld()
    left = DummyEntity(
        x=0, y=0, z=0, domain_tag='electromagnetism',
        domain_params={
            'real_mass_kg': 1.0,
            'charge_C': 1.0,
            'coulomb_constant': 1.0,
            'interaction_scale_m_per_cell': 1.0,
            'pairwise_em_enabled': True,
        },
    )
    right = DummyEntity(
        x=4, y=0, z=0, domain_tag='electromagnetism',
        domain_params={
            'real_mass_kg': 1.0,
            'charge_C': 1.0,
            'coulomb_constant': 1.0,
            'interaction_scale_m_per_cell': 1.0,
            'pairwise_em_enabled': True,
        },
    )
    a_left = ElectromagneticCoupler().acceleration_ms2_on(left, [left, right], world)
    a_right = ElectromagneticCoupler().acceleration_ms2_on(right, [left, right], world)

    assert a_left.ax_ms2 < 0, 'Like charges should repel: left charge moves left'
    assert a_right.ax_ms2 > 0, 'Like charges should repel: right charge moves right'


def test_em_opposite_charges_attract():
    from ubp_force_couplers import ElectromagneticCoupler

    world = DummyWorld()
    left = DummyEntity(
        x=0, y=0, z=0, domain_tag='electromagnetism',
        domain_params={
            'real_mass_kg': 1.0,
            'charge_C': -1.0,
            'coulomb_constant': 1.0,
            'interaction_scale_m_per_cell': 1.0,
            'pairwise_em_enabled': True,
        },
    )
    right = DummyEntity(
        x=4, y=0, z=0, domain_tag='electromagnetism',
        domain_params={
            'real_mass_kg': 1.0,
            'charge_C': 1.0,
            'coulomb_constant': 1.0,
            'interaction_scale_m_per_cell': 1.0,
            'pairwise_em_enabled': True,
        },
    )
    a_left = ElectromagneticCoupler().acceleration_ms2_on(left, [left, right], world)
    a_right = ElectromagneticCoupler().acceleration_ms2_on(right, [left, right], world)

    assert a_left.ax_ms2 > 0, 'Opposite charges should attract: left charge moves right'
    assert a_right.ax_ms2 < 0, 'Opposite charges should attract: right charge moves left'


def test_combined_system_returns_named_channels():
    from ubp_force_couplers import ForceCouplerSystem
    world = DummyWorld()
    a = DummyEntity(x=0, y=0, z=0, domain_tag='electromagnetism', domain_params={
        'real_mass_kg': 1.0,
        'charge_C': 1.0,
        'coulomb_constant': 1.0,
        'interaction_scale_m_per_cell': 1.0,
        'pairwise_em_enabled': True,
        'pairwise_gravity_enabled': True,
    })
    b = DummyEntity(x=4, y=0, z=0, domain_tag='electromagnetism', domain_params={
        'real_mass_kg': 2.0,
        'charge_C': -1.0,
        'coulomb_constant': 1.0,
        'interaction_scale_m_per_cell': 1.0,
        'pairwise_em_enabled': True,
        'pairwise_gravity_enabled': True,
    })
    out = ForceCouplerSystem().acceleration_ms2_on(a, [a, b], world)
    assert set(out.keys()) == {'gravity_pair', 'electromagnetic', 'total'}
    assert out['total'].contributors >= 2
