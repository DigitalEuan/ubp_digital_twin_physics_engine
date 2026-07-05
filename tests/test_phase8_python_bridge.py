"""
Phase 8 tests — python_bridge.py v5.4 new commands.

Verifies that the bridge exposes all v5.4 features through the JSON-lines
protocol:
  1. v54_constants — returns all 13 v5.4 substrate constants
  2. v54_physics_predictions — returns 6 canonical formulas with error budgets
  3. physics_registry_status — returns all 7 core domains with GREEN status
  4. triad_status — returns Golay/Leech/Monster/BarnesWall/Triad level 3/3
  5. substrate_validate — returns the full validate_substrate() report
  6. engine_test — still works, now reports v5.4 version strings

Run:  pytest tests/test_phase8_python_bridge.py -v
"""
from __future__ import annotations

import sys
import json
import io
import contextlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))


@pytest.fixture(scope="module")
def sim():
    """Module-scoped UBPSimulation instance for all Phase 8 tests."""
    import python_bridge
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        s = python_bridge.UBPSimulation()
    return s


def _run_cmd(sim, cmd_dict):
    """Run a command on the simulation and capture the JSON response."""
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    try:
        sim.handle_command({"type": "command", **cmd_dict})
    finally:
        sys.stdout = old_stdout
    output = buf.getvalue().strip()
    # Parse the last JSON line that matches our expected type
    expected_type = cmd_dict.get("command")
    type_map = {
        'v54_constants': 'v54_constants',
        'v54_physics_predictions': 'v54_physics_predictions',
        'physics_registry_status': 'physics_registry_status',
        'triad_status': 'triad_status',
        'substrate_validate': 'substrate_validate',
        'engine_test': 'engine_test_result',
    }
    expected = type_map.get(expected_type, expected_type)
    for line in reversed(output.split('\n')):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if obj.get('type') == expected:
                return obj
        except json.JSONDecodeError:
            pass
    return None


# ── v54_constants ────────────────────────────────────────────────────────
def test_v54_constants_returns_all_constants(sim):
    """v54_constants must return all 13 v5.4 substrate constants."""
    r = _run_cmd(sim, {"command": "v54_constants"})
    assert r is not None
    assert r['type'] == 'v54_constants'
    assert 'constants' in r
    expected = {'Y', 'Y_INV', 'PI', 'PHI', 'E_CONST', 'MONAD', 'WOBBLE',
                'SINK_L', 'SINK_L_STEREO', 'SINK_SIGMA', 'EXISTENCE_UNIT',
                'SHEAR_1', 'SHEAR_2'}
    assert set(r['constants'].keys()) == expected


def test_v54_constants_values_match_substrate(sim):
    """v54_constants values must match the substrate (single source of truth)."""
    import ubp_engine_substrate as sub
    r = _run_cmd(sim, {"command": "v54_constants"})
    assert abs(r['constants']['Y'] - float(sub.Y_CONSTANT)) < 1e-15
    assert abs(r['constants']['SINK_L'] - float(sub.SINK_L)) < 1e-15
    assert abs(r['constants']['SHEAR_1'] - float(sub.SHEAR_1)) < 1e-15


# ── v54_physics_predictions ─────────────────────────────────────────────
def test_v54_physics_predictions_returns_all_6(sim):
    """v54_physics_predictions must return all 6 canonical formula predictions."""
    r = _run_cmd(sim, {"command": "v54_physics_predictions"})
    assert r is not None
    assert r['type'] == 'v54_physics_predictions'
    assert 'predictions' in r
    expected = {'muon_electron_ratio', 'strong_coupling_alpha_s', 'alpha_cubed',
                'hubble_H0', 'omega_k_base', 'gravitational_G'}
    assert set(r['predictions'].keys()) == expected


def test_v54_physics_predictions_all_in_budget(sim):
    """All 6 v5.4 physics predictions must be within their error budgets."""
    r = _run_cmd(sim, {"command": "v54_physics_predictions"})
    assert r['all_in_budget'] is True
    for name, pred in r['predictions'].items():
        assert pred['in_budget'] is True, (
            f"{name}: err={pred['error_pct']:.4f}% exceeds budget {pred['budget_pct']}%"
        )


def test_v54_physics_predictions_includes_formula_strings(sim):
    """Each prediction must include its formula string for documentation."""
    r = _run_cmd(sim, {"command": "v54_physics_predictions"})
    for name, pred in r['predictions'].items():
        assert 'formula' in pred, f"{name} missing formula"
        assert len(pred['formula']) > 0


# ── physics_registry_status ─────────────────────────────────────────────
def test_physics_registry_status_returns_7_domains(sim):
    """physics_registry_status must return all 7 core domains."""
    r = _run_cmd(sim, {"command": "physics_registry_status"})
    assert r is not None
    assert r['type'] == 'physics_registry_status'
    assert r['overall'] == 'GREEN'
    assert r['domain_count'] >= 7
    expected = {'core_mechanics', 'core_physics', 'core_fluid',
                'core_rigid_body', 'core_space', 'core_materials', 'core_entity'}
    assert expected.issubset(set(r['domains'].keys()))


def test_physics_registry_status_all_green(sim):
    """All 7 core domains must report GREEN status."""
    r = _run_cmd(sim, {"command": "physics_registry_status"})
    for name in ('core_mechanics', 'core_physics', 'core_fluid',
                 'core_rigid_body', 'core_space', 'core_materials', 'core_entity'):
        assert r['domains'][name]['status'] == 'GREEN', (
            f"{name} status = {r['domains'][name]['status']}"
        )


# ── triad_status ─────────────────────────────────────────────────────────
def test_triad_status_returns_full_triad(sim):
    """triad_status must return all Triad engine statuses."""
    r = _run_cmd(sim, {"command": "triad_status"})
    assert r is not None
    assert r['type'] == 'triad_status'
    assert 'status' in r
    s = r['status']
    assert s['golay_active'] is True
    assert s['leech_active'] is True
    assert s['monster_loaded'] is True
    assert s['monster_has_moonshine'] is True
    assert s['barnes_wall_dim'] == 256
    assert s['triad_instantiable'] is True
    assert s['triad_level'] == 3


# ── substrate_validate ──────────────────────────────────────────────────
def test_substrate_validate_returns_full_report(sim):
    """substrate_validate must return the full validate_substrate() report."""
    r = _run_cmd(sim, {"command": "substrate_validate", "req_id": "phase8"})
    assert r is not None
    assert r['type'] == 'substrate_validate'
    assert r['req_id'] == 'phase8'
    assert r['overall'] == 'GREEN'
    assert 'blocks' in r
    # Must include the v5.4-specific blocks
    for block in ('pi_precision', 'golay_roundtrip', 'particle_physics',
                  'v54_physics_predictions', 'triad_engines', 'sovereign_alu',
                  'physics_registry'):
        assert block in r['blocks'], f"Missing block: {block}"


# ── engine_test version strings ─────────────────────────────────────────
def test_engine_test_reports_v54_version(sim):
    """engine_test must now report v5.4 version strings (was v6.3.1)."""
    r = _run_cmd(sim, {"command": "engine_test", "req_id": "ver_check"})
    assert r is not None
    assert r['type'] == 'engine_test_result'
    assert 'v5.4' in r['ubp_version'], f"Expected v5.4 in ubp_version, got {r['ubp_version']}"
    assert 'v5.4' in r['engine_version'], f"Expected v5.4 in engine_version, got {r['engine_version']}"


# ── Bridge imports cleanly ──────────────────────────────────────────────
def test_bridge_imports_cleanly():
    """python_bridge must import without errors under v5.4."""
    import python_bridge
    assert python_bridge is not None
    assert hasattr(python_bridge, 'UBPSimulation')
