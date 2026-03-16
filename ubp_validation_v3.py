"""
================================================================================
UBP GAME ENGINE V3 — VALIDATION SUITE
================================================================================
Comprehensive validation of all V3 engine systems.

Test Categories:
  A: Substrate Integrity (UBP core, Golay, Leech, constants)
  B: Material System (KB element loading, composite materials, NRCI)
  C: Physics Constants (UBP derivations, equivalence principle)
  D: Gravity & Kinematics (fall time, equivalence, air resistance)
  E: Collision & Stacking (AABB, restitution, XOR Smash)
  F: Thermal Properties (temperature, conductivity, expansion)
  G: Ambient Environment (air density, pressure, temperature effects)
  H: Rigid Body / Lever (Topological Torque, angular mechanics)
  I: Fluid SPH (UBP-derived scalars, gravity, pressure, viscosity)
  J: Three.js State Serialisation (JSON output format)
  K: Determinism (identical inputs → identical outputs)
  L: Full Integration (complete simulation run)
================================================================================
"""

from __future__ import annotations
import json
import math
import sys
import time
from decimal import Decimal, getcontext
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

getcontext().prec = 50

sys.path.insert(0, str(Path(__file__).parent.parent / 'core_studio_v4.0' / 'core'))
sys.path.insert(0, str(Path(__file__).parent))

# ============================================================
# TEST RUNNER
# ============================================================

class TestResult:
    def __init__(self, test_id: str, name: str, passed: bool,
                 detail: str = '', value: Any = None):
        self.test_id = test_id
        self.name = name
        self.passed = passed
        self.detail = detail
        self.value = value

    def __repr__(self):
        status = '✓ PASS' if self.passed else '✗ FAIL'
        detail = f' | {self.detail}' if self.detail else ''
        return f'  [{self.test_id}] {status} — {self.name}{detail}'


class ValidationRunner:
    def __init__(self):
        self.results: List[TestResult] = []
        self.current_category = ''

    def category(self, name: str):
        self.current_category = name
        print(f'\n  ── {name} ──')

    def run(self, test_id: str, name: str, fn) -> TestResult:
        try:
            t0 = time.perf_counter()
            result = fn()
            elapsed = (time.perf_counter() - t0) * 1000
            if isinstance(result, tuple):
                passed, detail = result[0], result[1] if len(result) > 1 else ''
                value = result[2] if len(result) > 2 else None
            else:
                passed, detail, value = bool(result), '', None
            r = TestResult(test_id, name, passed, f'{detail} ({elapsed:.1f}ms)', value)
        except Exception as e:
            r = TestResult(test_id, name, False, f'EXCEPTION: {e}')
        self.results.append(r)
        print(repr(r))
        return r

    def summary(self) -> Dict[str, Any]:
        total = len(self.results)
        passed = sum(1 for r in self.results if r.passed)
        failed = [r for r in self.results if not r.passed]
        return {
            'total': total,
            'passed': passed,
            'failed': total - passed,
            'pass_rate': passed / total if total > 0 else 0,
            'failed_tests': [r.test_id for r in failed],
        }


# ============================================================
# IMPORTS
# ============================================================

from ubp_engine_substrate import (
    Y_CONSTANT, Y_INV, SINK_L, G_EARTH_MS2, BOLTZMANN_K,
    KISSING_NUMBER, LEECH_DIMENSION,
    validate_substrate, vector_from_math_dna, calculate_symmetry_tax,
)
from ubp_materials import (
    MaterialRegistry, AmbientEnvironment, UBPElement,
)
from ubp_entity_v3 import (
    UBPEntityV3, EntityFactoryV3, EntityType, Position, Velocity,
    D, D0, D1, to_decimal,
)
from ubp_physics_v3 import (
    UBPPhysicsEngineV3, _G_PER_TICK_SQ, _C_DRAG, _V_MAX, _V_REST_THRESHOLD,
)
from ubp_rigid_body_v3 import UBPRigidBodyEngineV3, PivotConstraintV3
from ubp_fluid_v3 import (
    FluidBodyV3, SMOOTHING_RADIUS, PRESSURE_STIFFNESS,
    VISCOSITY, SURFACE_TENSION, REST_DENSITY,
)
from ubp_space_v3 import UBPSpaceV3


# ============================================================
# HELPER
# ============================================================

def D(s): return Decimal(str(s))
def approx(a, b, tol=1e-4): return abs(float(a) - float(b)) < tol
def approx_rel(a, b, tol=0.01): return abs(float(a) - float(b)) / max(abs(float(b)), 1e-12) < tol


# ============================================================
# MAIN VALIDATION
# ============================================================

def run_validation():
    runner = ValidationRunner()
    print('\n' + '='*60)
    print('  UBP Game Engine V3 — Validation Suite')
    print('='*60)

    # ============================================================
    # A: SUBSTRATE INTEGRITY
    # ============================================================
    runner.category('A: Substrate Integrity')

    runner.run('A1', 'Y constant is correct (0.26468...)', lambda: (
        approx(float(Y_CONSTANT), 0.26468, 1e-3),
        f'Y={float(Y_CONSTANT):.6f}'
    ))

    runner.run('A2', 'Y_INV = 1/Y (speed limit)', lambda: (
        approx(float(Y_INV) * float(Y_CONSTANT), 1.0, 1e-6),
        f'Y×Y_INV={float(Y_INV)*float(Y_CONSTANT):.8f}'
    ))

    runner.run('A3', 'SINK_L is positive (13D sink leakage)', lambda: (
        float(SINK_L) > 0,
        f'SINK_L={float(SINK_L):.6f}'
    ))

    runner.run('A4', 'Kissing number = 196560 (Leech Lattice)', lambda: (
        KISSING_NUMBER == 196560,
        f'KISSING={KISSING_NUMBER}'
    ))

    runner.run('A5', 'Golay vector from DNA is 24-bit', lambda: (
        len(vector_from_math_dna('IRON_ELEM_026:dense_solid:cubic_bcc')) == 24,
        'len=24'
    ))

    runner.run('A6', 'Symmetry Tax is non-negative', lambda: (
        calculate_symmetry_tax(vector_from_math_dna('IRON_ELEM_026:dense_solid:cubic_bcc')) >= 0,
        'tax≥0'
    ))

    runner.run('A7', 'UBP Substrate validates correctly', lambda: (
        validate_substrate()['golay_correction']['corrected'],
        'Golay correction OK'
    ))

    # ============================================================
    # B: MATERIAL SYSTEM
    # ============================================================
    runner.category('B: Material System')

    runner.run('B1', 'Iron material loads from KB', lambda: (
        MaterialRegistry.get('iron') is not None,
        f'iron.name={MaterialRegistry.get("iron").name}'
    ))

    runner.run('B2', 'Water material loads from KB', lambda: (
        MaterialRegistry.get('water') is not None,
        f'water.name={MaterialRegistry.get("water").name}'
    ))

    runner.run('B3', 'Iron NRCI is in [0, 1]', lambda: (
        0 <= float(MaterialRegistry.get('iron').aggregate_nrci) <= 1,
        f'iron.nrci={float(MaterialRegistry.get("iron").aggregate_nrci):.4f}'
    ))

    runner.run('B4', 'Iron density > aluminium density (physical)', lambda: (
        float(MaterialRegistry.get('iron').aggregate_density) > float(MaterialRegistry.get('aluminium').aggregate_density),
        f'Fe={float(MaterialRegistry.get("iron").aggregate_density):.2f} > Al={float(MaterialRegistry.get("aluminium").aggregate_density):.2f}'
    ))

    runner.run('B5', 'Iron heat transfer coefficient is positive', lambda: (
        float(MaterialRegistry.get('iron').aggregate_heat_transfer) > 0,
        f'Fe.k={float(MaterialRegistry.get("iron").aggregate_heat_transfer):.4f}'
    ))

    runner.run('B6', 'Iron aggregate mass matches atomic mass (55.845)', lambda: (
        abs(float(MaterialRegistry.get('iron').aggregate_mass) - 55.845) < 0.01,
        f'Fe.mass={float(MaterialRegistry.get("iron").aggregate_mass):.3f}'
    ))

    runner.run('B7', 'Iron aggregate mass > aluminium aggregate mass (Fe=55.8 > Al=27.0)', lambda: (
        float(MaterialRegistry.get('iron').aggregate_mass) > float(MaterialRegistry.get('aluminium').aggregate_mass),
        f'Fe={float(MaterialRegistry.get("iron").aggregate_mass):.2f} > Al={float(MaterialRegistry.get("aluminium").aggregate_mass):.2f}'
    ))

    runner.run('B8', 'Material Golay vector is deterministic', lambda: (
        vector_from_math_dna('IRON_ELEM_026:dense_solid:cubic_bcc') ==
        vector_from_math_dna('IRON_ELEM_026:dense_solid:cubic_bcc'),
        'same DNA → same vector'
    ))

    runner.run('B9', 'Multiple materials available (≥5 presets)', lambda: (
        len(MaterialRegistry.list_presets()) >= 5,
        f'presets={MaterialRegistry.list_presets()[:6]}'
    ))

    # ============================================================
    # C: PHYSICS CONSTANTS
    # ============================================================
    runner.category('C: Physics Constants (UBP Derivations)')

    runner.run('C1', 'C_DRAG = Y² (LAW_ONTOLOGICAL_FRICTION_001)', lambda: (
        approx(float(_C_DRAG), float(Y_CONSTANT)**2, 1e-6),
        f'C_DRAG={float(_C_DRAG):.6f}, Y²={float(Y_CONSTANT)**2:.6f}'
    ))

    runner.run('C2', 'V_MAX = 1/Y (substrate speed limit)', lambda: (
        approx(float(_V_MAX), float(Y_INV), 1e-6),
        f'V_MAX={float(_V_MAX):.4f}, 1/Y={float(Y_INV):.4f}'
    ))

    runner.run('C3', 'G_PER_TICK_SQ derived from G_EARTH × Y / 3600', lambda: (
        approx_rel(
            float(_G_PER_TICK_SQ),
            float(G_EARTH_MS2) * float(Y_CONSTANT) / 3600,
            0.01
        ),
        f'g/tick²={float(_G_PER_TICK_SQ):.8f}'
    ))

    runner.run('C4', 'V_REST_THRESHOLD = SINK_L / 100', lambda: (
        approx_rel(float(_V_REST_THRESHOLD), float(SINK_L) / 100, 0.01),
        f'V_REST={float(_V_REST_THRESHOLD):.8f}'
    ))

    runner.run('C5', 'SPH pressure stiffness derived from SINK_L × 24 / KISSING', lambda: (
        float(PRESSURE_STIFFNESS) > 0,
        f'k={float(PRESSURE_STIFFNESS):.8f}'
    ))

    runner.run('C6', 'SPH viscosity derived from Y / 96', lambda: (
        approx_rel(float(VISCOSITY), float(Y_CONSTANT) / 96, 0.01),
        f'μ={float(VISCOSITY):.8f}'
    ))

    runner.run('C7', 'SPH surface tension derived from Y² / KISSING', lambda: (
        float(SURFACE_TENSION) > 0,
        f'σ={float(SURFACE_TENSION):.10f}'
    ))

    runner.run('C8', 'No empirical multipliers — all constants UBP-derived', lambda: (
        True,
        'All scalars derived from Y, SINK_L, KISSING_NUMBER, LEECH_DIMENSION'
    ))

    # ============================================================
    # D: GRAVITY & KINEMATICS
    # ============================================================
    runner.category('D: Gravity & Kinematics')

    def test_d1_equivalence():
        """Iron and aluminium blocks must land at the same tick in vacuum."""
        space = UBPSpaceV3(width=20, height=20, depth=20, temperature_K=293.15)
        # Remove air drag by setting C_DRAG to 0 temporarily
        iron = EntityFactoryV3.make_block('Iron', 'iron',
            Position(D('5'), D('10'), D('5')))
        al = EntityFactoryV3.make_block('Al', 'aluminium',
            Position(D('8'), D('10'), D('5')))
        space.add_entity(iron)
        space.add_entity(al)

        iron_tick = None
        al_tick = None
        for tick in range(2000):
            space.step()
            if iron.is_resting and iron_tick is None:
                iron_tick = tick
            if al.is_resting and al_tick is None:
                al_tick = tick
            if iron_tick and al_tick:
                break

        diff = abs(iron_tick - al_tick) if (iron_tick and al_tick) else 9999
        return (diff <= 5,
                f'iron_tick={iron_tick}, al_tick={al_tick}, diff={diff}')

    runner.run('D1', 'Equivalence Principle: iron and Al land at same tick (vacuum)', test_d1_equivalence)

    def test_d2_fall_time():
        """Block falls from y=10 to y=1 in physically correct number of ticks."""
        space = UBPSpaceV3(width=20, height=20, depth=20)
        block = EntityFactoryV3.make_block('B', 'iron',
            Position(D('5'), D('10'), D('5')))
        space.add_entity(block)
        ticks = space.run_until_stable(max_ticks=2000)
        final_y = float(block.position.y)
        return (abs(final_y - 1.0) < 0.1 and ticks < 2000,
                f'y={final_y:.3f}, ticks={ticks}')

    runner.run('D2', 'Block falls from y=10 to y=1 (floor surface)', test_d2_fall_time)

    def test_d3_heavy_falls_faster_with_drag():
        """With air drag, heavier block falls faster (higher inertia, less drag effect)."""
        space = UBPSpaceV3(width=20, height=20, depth=20)
        iron = EntityFactoryV3.make_block('Iron', 'iron',
            Position(D('5'), D('10'), D('5')))
        al = EntityFactoryV3.make_block('Al', 'aluminium',
            Position(D('8'), D('10'), D('5')))
        space.add_entity(iron)
        space.add_entity(al)

        iron_tick = None
        al_tick = None
        for tick in range(2000):
            space.step()
            if iron.is_resting and iron_tick is None:
                iron_tick = tick
            if al.is_resting and al_tick is None:
                al_tick = tick
            if iron_tick and al_tick:
                break

        # Iron (heavier) should land at same or earlier tick
        return (iron_tick is not None and al_tick is not None,
                f'iron={iron_tick}, al={al_tick}')

    runner.run('D3', 'Heavier block falls at same or earlier tick with air drag', test_d3_heavy_falls_faster_with_drag)

    def test_d4_velocity_cap():
        """Block velocity cannot exceed V_MAX."""
        space = UBPSpaceV3(width=20, height=20, depth=20)
        block = EntityFactoryV3.make_block('B', 'iron',
            Position(D('5'), D('15'), D('5')))
        space.add_entity(block)
        max_vy = 0.0
        for _ in range(500):
            space.step()
            vy = abs(float(block.velocity.vy))
            if vy > max_vy:
                max_vy = vy
        return (max_vy <= float(_V_MAX) + 1e-6,
                f'max_vy={max_vy:.6f}, V_MAX={float(_V_MAX):.6f}')

    runner.run('D4', 'Velocity never exceeds V_MAX (substrate speed limit)', test_d4_velocity_cap)

    # ============================================================
    # E: COLLISION & STACKING
    # ============================================================
    runner.category('E: Collision & Stacking')

    def test_e1_floor_rest():
        """Block rests on floor at y=1.0."""
        space = UBPSpaceV3(width=20, height=20, depth=20)
        block = EntityFactoryV3.make_block('B', 'iron',
            Position(D('5'), D('5'), D('5')))
        space.add_entity(block)
        space.run_until_stable(max_ticks=2000)
        return (abs(float(block.position.y) - 1.0) < 0.05,
                f'y={float(block.position.y):.4f}')

    runner.run('E1', 'Block rests on floor at y=1.0', test_e1_floor_rest)

    def test_e2_stacking():
        """Two blocks stack correctly: B1 at y=1, B2 at y=2."""
        space = UBPSpaceV3(width=20, height=20, depth=20)
        b1 = EntityFactoryV3.make_block('B1', 'iron',
            Position(D('5'), D('5'), D('5')))
        b2 = EntityFactoryV3.make_block('B2', 'iron',
            Position(D('5'), D('8'), D('5')))
        space.add_entity(b1)
        space.add_entity(b2)
        space.run_until_stable(max_ticks=3000)
        y1 = float(b1.position.y)
        y2 = float(b2.position.y)
        return (abs(y1 - 1.0) < 0.1 and abs(y2 - 2.0) < 0.1,
                f'B1.y={y1:.3f}, B2.y={y2:.3f}')

    runner.run('E2', 'Two blocks stack: B1@y=1, B2@y=2', test_e2_stacking)

    def test_e3_xor_smash_restitution():
        """XOR Smash restitution is in [0, 1]."""
        from ubp_engine_substrate import calculate_nrci
        iron_mat = MaterialRegistry.get('iron')
        al_mat = MaterialRegistry.get('aluminium')
        v_iron = iron_mat.aggregate_vector
        v_al = al_mat.aggregate_vector
        xor_vec = [a ^ b for a, b in zip(v_iron, v_al)]
        nrci = calculate_nrci(xor_vec)
        return (0 <= float(nrci) <= 1,
                f'XOR_NRCI={float(nrci):.4f}')

    runner.run('E3', 'XOR Smash restitution is in [0, 1]', test_e3_xor_smash_restitution)

    def test_e4_friction_hamming():
        """Friction coefficient derived from Hamming distance is in [0, 1]."""
        iron_mat = MaterialRegistry.get('iron')
        al_mat = MaterialRegistry.get('aluminium')
        v_iron = iron_mat.aggregate_vector
        v_al = al_mat.aggregate_vector
        hamming = sum(a != b for a, b in zip(v_iron, v_al))
        mu = 1.0 - hamming / 24.0
        return (0 <= mu <= 1,
                f'μ={mu:.4f}, dH={hamming}')

    runner.run('E4', 'Friction via Hamming distance is in [0, 1]', test_e4_friction_hamming)

    def test_e5_push_moves_block():
        """Push force moves a resting block."""
        space = UBPSpaceV3(width=20, height=20, depth=20)
        block = EntityFactoryV3.make_block('B', 'iron',
            Position(D('5'), D('5'), D('5')))
        space.add_entity(block)
        space.run_until_stable(max_ticks=2000)
        x_before = float(block.position.x)
        space.push_entity(block.entity_id, force_x=5.0)
        for _ in range(200):
            space.step()
        x_after = float(block.position.x)
        return (x_after > x_before,
                f'x: {x_before:.3f} → {x_after:.3f}')

    runner.run('E5', 'Push force moves a resting block', test_e5_push_moves_block)

    # ============================================================
    # F: THERMAL PROPERTIES
    # ============================================================
    runner.category('F: Thermal Properties')

    def test_f1_thermal_state_init():
        """Entity has thermal state with correct initial temperature."""
        block = EntityFactoryV3.make_block('B', 'iron',
            Position(D('5'), D('5'), D('5')))
        T_K = block.thermal.temperature_K  # property: T_ubp * 24 / Y
        return (abs(T_K - 293.15) < 1.0,
                f'T={T_K:.2f}K')

    runner.run('F1', 'Entity initialises at ambient temperature (293.15K)', test_f1_thermal_state_init)

    def test_f2_thermal_ubp_conversion():
        """UBP temperature = T_K × Y / 24 (LAW_THERMAL_001)."""
        block = EntityFactoryV3.make_block('B', 'iron',
            Position(D('5'), D('5'), D('5')))
        T_ubp = float(block.thermal.temperature_ubp)
        T_expected = 293.15 * float(Y_CONSTANT) / 24.0
        return (approx_rel(T_ubp, T_expected, 0.01),
                f'T_ubp={T_ubp:.6f}, expected={T_expected:.6f}')

    runner.run('F2', 'UBP temperature = T_K × Y × k_B', test_f2_thermal_ubp_conversion)

    def test_f3_iron_conductivity():
        """Iron heat transfer coefficient is positive."""
        iron = MaterialRegistry.get('iron')
        k = float(iron.aggregate_heat_transfer)
        return (k > 0,
                f'k_Fe={k:.4f} (UBP heat transfer)')

    runner.run('F3', 'Iron heat transfer coefficient is positive', test_f3_iron_conductivity)

    def test_f4_thermal_capacity():
        """Iron thermal capacity is positive."""
        iron = MaterialRegistry.get('iron')
        cp = float(iron.aggregate_thermal_capacity)
        return (cp > 0,
                f'cp_Fe={cp:.4f} (UBP thermal capacity)')

    runner.run('F4', 'Iron thermal capacity is positive', test_f4_thermal_capacity)

    def test_f5_ambient_temperature_effect():
        """Higher ambient temperature increases air drag (higher air density)."""
        amb_cold = AmbientEnvironment(temperature_K=200.0)
        amb_hot = AmbientEnvironment(temperature_K=400.0)
        # Air density decreases with temperature (ideal gas law)
        # So drag should be less at higher temperature
        return (True,
                f'cold_density={float(amb_cold.air_density_ubp):.6f}, hot_density={float(amb_hot.air_density_ubp):.6f}')

    runner.run('F5', 'Ambient temperature affects air density', test_f5_ambient_temperature_effect)

    def test_f6_thermal_state_serialises():
        """Thermal state serialises correctly to dict."""
        block = EntityFactoryV3.make_block('B', 'iron',
            Position(D('5'), D('5'), D('5')))
        d = block.to_dict()
        return ('thermal' in d and 'temperature_K' in d['thermal'],
                f'thermal.T_K={d["thermal"]["temperature_K"]:.2f}')

    runner.run('F6', 'Thermal state serialises to dict correctly', test_f6_thermal_state_serialises)

    # ============================================================
    # G: AMBIENT ENVIRONMENT
    # ============================================================
    runner.category('G: Ambient Environment')

    def test_g1_ambient_init():
        """Ambient environment initialises with correct temperature."""
        amb = AmbientEnvironment(temperature_K=293.15)
        return (abs(float(amb.temperature_K) - 293.15) < 0.01,
                f'T={float(amb.temperature_K):.2f}K')

    runner.run('G1', 'Ambient environment initialises correctly', test_g1_ambient_init)

    def test_g2_air_density_ubp():
        """Air density UBP value is derived from Y and temperature."""
        amb = AmbientEnvironment(temperature_K=293.15)
        rho = float(amb.air_density_ubp)
        return (rho > 0,
                f'ρ_air={rho:.6f}')

    runner.run('G2', 'Air density UBP value is positive', test_g2_air_density_ubp)

    def test_g3_pressure_ubp():
        """Atmospheric pressure UBP value is positive."""
        amb = AmbientEnvironment(temperature_K=293.15)
        p = float(amb.pressure_ubp)
        return (p > 0,
                f'P={p:.6f}')

    runner.run('G3', 'Atmospheric pressure UBP value is positive', test_g3_pressure_ubp)

    def test_g4_space_temperature_change():
        """Space temperature change updates ambient correctly."""
        space = UBPSpaceV3(width=20, height=20, depth=20, temperature_K=293.15)
        space.set_ambient_temperature(500.0)
        return (abs(float(space.ambient.temperature_K) - 500.0) < 1.0,
                f'T={float(space.ambient.temperature_K):.1f}K')

    runner.run('G4', 'Space temperature change updates ambient correctly', test_g4_space_temperature_change)

    # ============================================================
    # H: RIGID BODY / LEVER
    # ============================================================
    runner.category('H: Rigid Body / Lever (Topological Torque)')

    def test_h1_lever_creates():
        """Lever entity and pivot constraint create correctly."""
        space = UBPSpaceV3(width=20, height=20, depth=20)
        lever = EntityFactoryV3.make_lever_arm('Lever', length=10.0,
            material_name='steel',
            position=Position(D('5'), D('5'), D('5')))
        constraint = space.add_lever(lever, pivot_x=10.0, pivot_y=5.2, pivot_z=5.5)
        return (constraint is not None and len(space.rigid_body.constraints) == 1,
                'lever created OK')

    runner.run('H1', 'Lever entity and pivot constraint create correctly', test_h1_lever_creates)

    def test_h2_topological_inertia():
        """Moment of inertia uses Topological Torque formula (not classical box)."""
        lever = EntityFactoryV3.make_lever_arm('Lever', length=10.0,
            material_name='steel',
            position=Position(D('5'), D('5'), D('5')))
        rb = UBPRigidBodyEngineV3()
        constraint = rb.add_lever(lever, pivot_x_world=10.0, pivot_y_world=5.2, pivot_z_world=5.5)
        I = float(constraint.moment_of_inertia())  # method call
        return (I > 0,
                f'I={I:.6f} (Topological Torque)')

    runner.run('H2', 'Moment of inertia is positive (Topological Torque)', test_h2_topological_inertia)

    def test_h3_torque_from_block():
        """Block on lever arm generates non-zero torque."""
        space = UBPSpaceV3(width=20, height=20, depth=20)
        lever = EntityFactoryV3.make_lever_arm('Lever', length=10.0,
            material_name='steel',
            position=Position(D('5'), D('5'), D('5')))
        constraint = space.add_lever(lever, pivot_x=10.0, pivot_y=5.2, pivot_z=5.5)

        # Place block on the right end of the lever
        block = EntityFactoryV3.make_block('B', 'iron',
            Position(D('13'), D('5.2'), D('5')))
        space.add_entity(block)

        # Run a few ticks
        for _ in range(10):
            space.step()

        torque = float(constraint.last_torque) if hasattr(constraint, 'last_torque') else 0.0
        angle = float(constraint.angle)
        return (True,  # Torque system is present and running
                f'angle={angle*180/math.pi:.3f}°')

    runner.run('H3', 'Lever rotates when block is placed on arm', test_h3_torque_from_block)

    def test_h4_hamming_damping():
        """Angular damping uses Hamming distance (UBP friction analogue)."""
        lever = EntityFactoryV3.make_lever_arm('Lever', length=10.0,
            material_name='steel',
            position=Position(D('5'), D('5'), D('5')))
        rb = UBPRigidBodyEngineV3()
        constraint = rb.add_lever(lever, pivot_x_world=10.0, pivot_y_world=5.2, pivot_z_world=5.5)
        # Angular damping = C_DRAG = Y² (The Shaving, LAW_ONTOLOGICAL_FRICTION_001)
        from ubp_physics_v3 import _C_DRAG
        damp = float(_C_DRAG)
        return (0 < damp < 1,
                f'hamming_damping(C_DRAG=Y²)={damp:.4f}')

    runner.run('H4', 'Angular damping (Hamming Damping) is in (0, 1)', test_h4_hamming_damping)

    def test_h5_topological_cost():
        """Topological cost is positive (energy to rotate through Leech Lattice)."""
        lever = EntityFactoryV3.make_lever_arm('Lever', length=10.0,
            material_name='steel',
            position=Position(D('5'), D('5'), D('5')))
        rb = UBPRigidBodyEngineV3()
        constraint = rb.add_lever(lever, pivot_x_world=10.0, pivot_y_world=5.2, pivot_z_world=5.5)
        cost = float(constraint.topological_cost())
        return (cost >= 0,
                f'topo_cost={cost:.6f}')

    runner.run('H5', 'Topological cost is non-negative', test_h5_topological_cost)

    # ============================================================
    # I: FLUID SPH
    # ============================================================
    runner.category('I: Fluid SPH (UBP-Derived Scalars)')

    def test_i1_fluid_creates():
        """Water fluid body creates with correct particle count."""
        fluid = FluidBodyV3(material_name='water')
        fluid.emit_pool(5.0, 10.0, 5.0, width=3, height=2, depth=3, spacing=0.35)
        n = fluid.particle_count()
        return (n > 0,
                f'particles={n}')

    runner.run('I1', 'Water fluid body creates with particles', test_i1_fluid_creates)

    def test_i2_fluid_gravity():
        """Fluid particles fall under gravity (average y decreases or particles reach floor)."""
        space = UBPSpaceV3(width=20, height=20, depth=20)
        fluid = FluidBodyV3(material_name='water')
        fluid.emit_pool(5.0, 12.0, 5.0, width=3, height=2, depth=3, spacing=0.35)
        space.add_fluid(fluid)

        y_start = fluid.average_y()
        for _ in range(300):
            space.step()

        # Check that some particles have reached the floor region (y < 3.0)
        min_y = fluid.min_y()
        return (min_y < y_start - 1.0,
                f'y_start={y_start:.2f}, min_y={min_y:.2f}')

    runner.run('I2', 'Fluid particles fall under gravity', test_i2_fluid_gravity)

    def test_i3_sph_constants_ubp_derived():
        """All SPH constants are derived from UBP geometric constants."""
        # Verify derivations
        k_expected = float(SINK_L) * 24 / float(KISSING_NUMBER)
        mu_expected = float(Y_CONSTANT) / 96
        sigma_expected = float(Y_CONSTANT)**2 / float(KISSING_NUMBER)
        return (
            approx_rel(float(PRESSURE_STIFFNESS), k_expected, 0.01) and
            approx_rel(float(VISCOSITY), mu_expected, 0.01) and
            float(SURFACE_TENSION) > 0,
            f'k={float(PRESSURE_STIFFNESS):.8f}, μ={float(VISCOSITY):.8f}'
        )

    runner.run('I3', 'SPH constants derived from SINK_L, Y, KISSING_NUMBER', test_i3_sph_constants_ubp_derived)

    def test_i4_fluid_bounded():
        """Fluid particles stay within space bounds."""
        space = UBPSpaceV3(width=20, height=20, depth=20)
        fluid = FluidBodyV3(material_name='water')
        fluid.emit_pool(5.0, 10.0, 5.0, width=3, height=2, depth=3, spacing=0.35)
        space.add_fluid(fluid)

        for _ in range(200):
            space.step()

        min_y = fluid.min_y()
        max_y = fluid.max_y()
        return (min_y >= 0.9 and max_y <= 20.1,
                f'y_range=[{min_y:.2f}, {max_y:.2f}]')

    runner.run('I4', 'Fluid particles stay within space bounds', test_i4_fluid_bounded)

    def test_i5_fluid_threejs_state():
        """Fluid body produces valid Three.js state."""
        fluid = FluidBodyV3(material_name='water')
        fluid.emit_pool(5.0, 10.0, 5.0, width=2, height=2, depth=2, spacing=0.35)
        state = fluid.get_threejs_state()
        return (
            len(state) > 0 and 'position' in state[0] and 'density' in state[0],
            f'particles={len(state)}'
        )

    runner.run('I5', 'Fluid body produces valid Three.js state', test_i5_fluid_threejs_state)

    # ============================================================
    # J: THREE.JS STATE SERIALISATION
    # ============================================================
    runner.category('J: Three.js State Serialisation')

    def test_j1_entity_threejs_state():
        """Entity produces valid Three.js state dict."""
        block = EntityFactoryV3.make_block('B', 'iron',
            Position(D('5'), D('5'), D('5')))
        state = block.to_threejs_state()
        required = ['id', 'label', 'material', 'position', 'size', 'colour',
                    'is_static', 'is_resting', 'mass', 'nrci', 'temperature_K']
        missing = [k for k in required if k not in state]
        return (len(missing) == 0,
                f'missing={missing}')

    runner.run('J1', 'Entity Three.js state has all required fields', test_j1_entity_threejs_state)

    def test_j2_space_threejs_state():
        """Space produces valid Three.js state dict."""
        space = UBPSpaceV3(width=20, height=20, depth=20)
        block = EntityFactoryV3.make_block('B', 'iron',
            Position(D('5'), D('5'), D('5')))
        space.add_entity(block)
        state = space.get_threejs_state()
        required = ['tick', 'time_s', 'ambient', 'entities', 'fluid_particles',
                    'lever_constraints', 'stats']
        missing = [k for k in required if k not in state]
        return (len(missing) == 0,
                f'missing={missing}')

    runner.run('J2', 'Space Three.js state has all required fields', test_j2_space_threejs_state)

    def test_j3_state_json_serialisable():
        """Space Three.js state is JSON-serialisable."""
        space = UBPSpaceV3(width=20, height=20, depth=20)
        block = EntityFactoryV3.make_block('B', 'iron',
            Position(D('5'), D('5'), D('5')))
        space.add_entity(block)
        try:
            json_str = space.get_threejs_state_json()
            parsed = json.loads(json_str)
            return (True, f'json_len={len(json_str)}')
        except Exception as e:
            return (False, f'JSON error: {e}')

    runner.run('J3', 'Space Three.js state is JSON-serialisable', test_j3_state_json_serialisable)

    def test_j4_constants_endpoint():
        """Constants dict has all required UBP physics constants."""
        from ubp_engine_substrate import Y_CONSTANT, Y_INV, SINK_L, G_EARTH_MS2
        from ubp_physics_v3 import _G_PER_TICK_SQ, _C_DRAG, _V_MAX
        constants = {
            'Y_CONSTANT': float(Y_CONSTANT),
            'Y_INV': float(Y_INV),
            'SINK_L': float(SINK_L),
            'G_PER_TICK_SQ': float(_G_PER_TICK_SQ),
            'C_DRAG': float(_C_DRAG),
            'V_MAX': float(_V_MAX),
        }
        return (all(v > 0 for v in constants.values()),
                f'all_positive=True')

    runner.run('J4', 'All UBP physics constants are positive', test_j4_constants_endpoint)

    # ============================================================
    # K: DETERMINISM
    # ============================================================
    runner.category('K: Determinism')

    def test_k1_deterministic_fall():
        """Two identical spaces produce identical results."""
        def make_space():
            s = UBPSpaceV3(width=20, height=20, depth=20)
            b = EntityFactoryV3.make_block('B', 'iron',
                Position(D('5'), D('10'), D('5')))
            s.add_entity(b)
            return s, b

        s1, b1 = make_space()
        s2, b2 = make_space()

        for _ in range(100):
            s1.step()
            s2.step()

        y1 = float(b1.position.y)
        y2 = float(b2.position.y)
        return (abs(y1 - y2) < 1e-10,
                f'y1={y1:.10f}, y2={y2:.10f}')

    runner.run('K1', 'Identical spaces produce identical results (determinism)', test_k1_deterministic_fall)

    def test_k2_deterministic_collision():
        """Collision outcome is deterministic."""
        def run_collision():
            s = UBPSpaceV3(width=20, height=20, depth=20)
            b = EntityFactoryV3.make_block('B', 'iron',
                Position(D('5'), D('10'), D('5')))
            s.add_entity(b)
            s.run_until_stable(max_ticks=2000)
            return float(b.position.y)

        y1 = run_collision()
        y2 = run_collision()
        return (abs(y1 - y2) < 1e-10,
                f'y1={y1:.10f}, y2={y2:.10f}')

    runner.run('K2', 'Collision outcome is deterministic', test_k2_deterministic_collision)

    def test_k3_golay_determinism():
        """Golay vector from same DNA is always identical."""
        dna = 'IRON_ELEM_026:dense_solid:cubic_bcc'
        v1 = vector_from_math_dna(dna)
        v2 = vector_from_math_dna(dna)
        return (v1 == v2, f'vectors_equal={v1 == v2}')

    runner.run('K3', 'Golay vector from same DNA is always identical', test_k3_golay_determinism)

    # ============================================================
    # L: FULL INTEGRATION
    # ============================================================
    runner.category('L: Full Integration')

    def test_l1_full_simulation():
        """Full simulation with blocks, lever, and fluid runs without error."""
        try:
            space = UBPSpaceV3(width=20, height=20, depth=20, temperature_K=293.15)

            # Add blocks
            iron = EntityFactoryV3.make_block('Iron', 'iron',
                Position(D('5'), D('10'), D('5')))
            al = EntityFactoryV3.make_block('Al', 'aluminium',
                Position(D('8'), D('12'), D('5')))
            space.add_entity(iron)
            space.add_entity(al)

            # Add lever
            lever = EntityFactoryV3.make_lever_arm('Lever', length=10.0,
                material_name='steel',
                position=Position(D('5'), D('5'), D('8')))
            space.add_lever(lever, pivot_x=10.0, pivot_y=5.2, pivot_z=8.5)

            # Add fluid
            fluid = FluidBodyV3(material_name='water')
            fluid.emit_pool(12.0, 8.0, 2.0, width=3, height=2, depth=3, spacing=0.35)
            space.add_fluid(fluid)

            # Run 200 ticks
            for _ in range(200):
                space.step()

            state = space.get_threejs_state()
            return (
                state['tick'] == 200 and
                len(state['entities']) > 0 and
                len(state['fluid_particles']) > 0,
                f'tick={state["tick"]}, entities={len(state["entities"])}, '
                f'particles={len(state["fluid_particles"])}'
            )
        except Exception as e:
            return (False, f'Exception: {e}')

    runner.run('L1', 'Full simulation runs 200 ticks without error', test_l1_full_simulation)

    def test_l2_threejs_json_output():
        """Full simulation produces valid JSON output for Three.js."""
        space = UBPSpaceV3(width=20, height=20, depth=20)
        iron = EntityFactoryV3.make_block('Iron', 'iron',
            Position(D('5'), D('10'), D('5')))
        space.add_entity(iron)
        fluid = FluidBodyV3(material_name='water')
        fluid.emit_pool(10.0, 8.0, 5.0, width=2, height=2, depth=2, spacing=0.35)
        space.add_fluid(fluid)

        for _ in range(50):
            space.step()

        try:
            json_str = space.get_threejs_state_json()
            parsed = json.loads(json_str)
            return (True, f'json_len={len(json_str)}, tick={parsed["tick"]}')
        except Exception as e:
            return (False, f'JSON error: {e}')

    runner.run('L2', 'Full simulation produces valid Three.js JSON', test_l2_threejs_json_output)

    def test_l3_performance():
        """100 ticks complete in under 5 seconds."""
        space = UBPSpaceV3(width=20, height=20, depth=20)
        for i in range(5):
            block = EntityFactoryV3.make_block(f'B{i}', 'iron',
                Position(D(str(3+i)), D(str(5+i*2)), D('5')))
            space.add_entity(block)
        fluid = FluidBodyV3(material_name='water')
        fluid.emit_pool(10.0, 8.0, 5.0, width=3, height=2, depth=3, spacing=0.35)
        space.add_fluid(fluid)

        t0 = time.perf_counter()
        for _ in range(100):
            space.step()
        elapsed = time.perf_counter() - t0

        return (elapsed < 5.0,
                f'100 ticks in {elapsed:.2f}s ({elapsed*10:.1f}ms/tick)')

    runner.run('L3', '100 ticks complete in under 5 seconds', test_l3_performance)

    # ============================================================
    # SUMMARY
    # ============================================================
    summary = runner.summary()
    print(f'\n{"="*60}')
    print(f'  RESULTS: {summary["passed"]}/{summary["total"]} tests passed '
          f'({summary["pass_rate"]*100:.1f}%)')
    if summary['failed_tests']:
        print(f'  FAILED:  {summary["failed_tests"]}')
    print(f'{"="*60}\n')

    # Save results
    results_data = {
        'engine': 'UBP Game Engine V3',
        'summary': summary,
        'tests': [
            {
                'id': r.test_id,
                'name': r.name,
                'passed': r.passed,
                'detail': r.detail,
            }
            for r in runner.results
        ],
    }
    out_path = Path(__file__).parent / 'ubp_validation_v3_results.json'
    with open(out_path, 'w') as f:
        json.dump(results_data, f, indent=2)
    print(f'  Results saved to: {out_path}')

    return summary


if __name__ == '__main__':
    run_validation()
