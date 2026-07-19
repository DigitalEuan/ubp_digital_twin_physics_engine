"""
Slice 3/4 smoke tests for the domain-native spawn registry.

These are intentionally lightweight: they validate the durable ABI
    domain registry -> spawn catalog -> spawn spec
without requiring the full bridge to boot.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


def test_module_parses():
    src = (REPO_ROOT / 'ubp_domain_spawns.py').read_text()
    ast.parse(src)


def test_catalog_declares_all_12_pack_domains():
    from ubp_domain_spawns import DOMAIN_SPAWN_CATALOG
    expected = {
        'electromagnetism', 'thermodynamics', 'quantum_mechanics',
        'nuclear_physics', 'cosmology', 'condensed_matter',
        'astrophysics', 'chemical_physics', 'information_theory',
        'acoustics', 'high_energy_physics', 'optics',
    }
    missing = expected - set(DOMAIN_SPAWN_CATALOG.keys())
    assert not missing, f"Missing domains from spawn catalog: {missing}"


def test_every_domain_has_at_least_one_preset():
    from ubp_domain_spawns import DOMAIN_SPAWN_CATALOG
    bad = [k for k, v in DOMAIN_SPAWN_CATALOG.items() if not v.get('presets')]
    assert not bad, f"Domains without presets: {bad}"
