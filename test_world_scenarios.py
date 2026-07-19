from ubp_world_scenarios import get_world_scenario_catalog, apply_world_scenario


class FakeWorld:
    def __init__(self):
        self.state = {
            'gravity_mode': 'earth',
            'ambient_temperature_K': 293.15,
            'gravity_pair_enabled': False,
            'em_enabled': False,
            'cosmology_scale': 1e-10,
        }

    def update(self, updates):
        self.state.update(updates)
        return dict(updates)

    def to_dict(self):
        return dict(self.state)


def test_catalog_contains_all_closeout_scenarios():
    catalog = get_world_scenario_catalog()
    assert {'earth_lab', 'lunar_vacuum', 'martian_surface', 'particle_sandbox', 'newtonian_orbit', 'hubble_demo'} <= set(catalog)


def test_apply_world_scenario_updates_world():
    world = FakeWorld()
    out = apply_world_scenario(world, 'particle_sandbox')
    assert out['scenario_id'] == 'particle_sandbox'
    assert out['data']['gravity_mode'] == 'zero'
    assert out['data']['em_enabled'] is True
