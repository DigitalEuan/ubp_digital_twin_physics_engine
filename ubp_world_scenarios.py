"""
================================================================================
UBP WORLD SCENARIOS — Slice 11 of the domains-in-3D integration
================================================================================
Preset world-physics recipes for the unified workspace.

These are NOT alternate sources of truth for physical constants. They are
operator-level bundles of `WorldPhysicsState.update(...)` inputs that make it
fast to switch the whole lab into a coherent mode:

  • earth_lab        — baseline terrestrial sandbox
  • lunar_vacuum     — Moon-g / cold vacuum-ish demo
  • martian_surface  — Mars gravity / colder atmosphere proxy
  • particle_sandbox — zero-g + EM on for charged-particle experiments
  • newtonian_orbit  — pairwise gravity on without Hubble drift
  • hubble_demo      — expansion mode with cosmology-friendly scale

Every preset returns plain metadata for the frontend HUD so it can surface the
scenario name, what it changed, and what it is for.
================================================================================
"""
from __future__ import annotations

from typing import Any, Dict


_WORLD_SCENARIOS: Dict[str, Dict[str, Any]] = {
    'earth_lab': {
        'label': 'Earth lab',
        'description': 'Baseline terrestrial workspace for rigid body / thermal demos.',
        'updates': {
            'gravity_mode': 'earth',
            'ambient_temperature_K': 293.15,
            'gravity_pair_enabled': False,
            'em_enabled': False,
            'cosmology_scale': 1.0e-10,
        },
        'use_cases': ['blocks', 'fluids', 'thermal relaxation'],
    },
    'lunar_vacuum': {
        'label': 'Lunar vacuum',
        'description': 'Moon gravity with cold ambient conditions for low-g experiments.',
        'updates': {
            'gravity_mode': 'moon',
            'ambient_temperature_K': 120.0,
            'gravity_pair_enabled': True,
            'em_enabled': False,
            'cosmology_scale': 1.0e-10,
        },
        'use_cases': ['low gravity drift', 'projectiles', 'decay demos'],
    },
    'martian_surface': {
        'label': 'Martian surface',
        'description': 'Mars gravity with colder ambient to contrast against Earth lab.',
        'updates': {
            'gravity_mode': 'mars',
            'ambient_temperature_K': 210.0,
            'gravity_pair_enabled': True,
            'em_enabled': False,
            'cosmology_scale': 1.0e-10,
        },
        'use_cases': ['comparative mechanics', 'thermal cooling'],
    },
    'particle_sandbox': {
        'label': 'Particle sandbox',
        'description': 'Zero-g charged-particle playground with EM coupling active.',
        'updates': {
            'gravity_mode': 'zero',
            'ambient_temperature_K': 293.15,
            'gravity_pair_enabled': False,
            'em_enabled': True,
            'cosmology_scale': 1.0e-12,
        },
        'use_cases': ['Coulomb interactions', 'photon propagation', 'optics'],
    },
    'newtonian_orbit': {
        'label': 'Newtonian orbit',
        'description': 'Pairwise gravity enabled without Hubble flow.',
        'updates': {
            'gravity_mode': 'newtonian',
            'ambient_temperature_K': 293.15,
            'gravity_pair_enabled': True,
            'em_enabled': False,
            'cosmology_scale': 1.0e-10,
        },
        'use_cases': ['pairwise attraction', 'astrophysics proxies'],
    },
    'hubble_demo': {
        'label': 'Hubble demo',
        'description': 'Expansion mode to showcase Slice 9 cosmological drift.',
        'updates': {
            'gravity_mode': 'hubble',
            'ambient_temperature_K': 2.725,
            'gravity_pair_enabled': True,
            'em_enabled': False,
            'cosmology_scale': 1.0e-8,
        },
        'use_cases': ['cosmology markers', 'expansion visualisation'],
    },
}


def get_world_scenario_catalog() -> Dict[str, Dict[str, Any]]:
    return {k: dict(v) for k, v in _WORLD_SCENARIOS.items()}


def apply_world_scenario(world: Any, scenario_id: str) -> Dict[str, Any]:
    if scenario_id not in _WORLD_SCENARIOS:
        raise ValueError(f'Unknown world scenario: {scenario_id}')
    spec = _WORLD_SCENARIOS[scenario_id]
    updates = dict(spec['updates'])
    applied = world.update(updates)
    return {
        'scenario_id': scenario_id,
        'label': spec['label'],
        'description': spec['description'],
        'use_cases': list(spec.get('use_cases', [])),
        'applied': applied,
        'data': world.to_dict(),
    }
