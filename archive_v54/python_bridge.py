import sys
import json
import time
import logging
import threading
import traceback
from decimal import Decimal
from fractions import Fraction
from typing import Dict, List, Any, Optional


class _UBPEncoder(json.JSONEncoder):
    """
    Robust encoder for simulation state.
    Handles Decimal, Fraction, and any other non-standard numeric type
    the UBP engine produces. Falls back to repr() so we never throw.
    """
    def default(self, obj: Any) -> Any:
        if isinstance(obj, (Decimal, Fraction)):
            return float(obj)
        if hasattr(obj, '__float__'):
            return float(obj)
        if hasattr(obj, '__int__'):
            return int(obj)
        if hasattr(obj, '__dict__'):
            return repr(obj)  # last resort — keeps the stream alive
        return super().default(obj)


def _dumps(obj: Any) -> str:
    return json.dumps(obj, cls=_UBPEncoder)


from ubp_engine_substrate import (
    Y_CONSTANT, UBPEngineSubstrate,
    # v5.4 NEW: Physics-prediction constants and registry access
    MUON_ELECTRON_RATIO, STRONG_COUPLING_ALPHA_S, ALPHA_CUBED,
    HUBBLE_H0, OMEGA_K_BASE, GRAVITATIONAL_G,
    SHEAR_1, SHEAR_2,
    SINK_L, SINK_L_STEREO, SINK_SIGMA, EXISTENCE_UNIT,
    MONAD, WOBBLE, PHI, E_CONST, Y_INV, PI,
    get_monster, get_barnes_wall, get_triad,
    get_noise_alu, get_physics_alu, get_linear_algebra_alu,
    get_physics_registry,
    validate_substrate,
)
from ubp_entity_v3 import EntityFactoryV3, UBPEntityV3, Position, D
from ubp_space_v3 import UBPSpaceV3
from ubp_fluid_v3 import FluidBodyV3
from ubp_materials import AmbientEnvironment

# Configure logging to stderr so it doesn't interfere with stdout JSON
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("ubp_bridge")

class UBPSimulation:
    """
    Manages the UBPSpaceV3 simulation instance.
    V4.0: Integrated Phi-Orbit, Synthesis, Leech Lattice, and new building tools.
    """
    def __init__(self):
        self.substrate = UBPEngineSubstrate()
        self.space: Optional[UBPSpaceV3] = None
        self.is_running = False
        self.lock = threading.RLock()
        self._entity_counter = 0
        self.reset()

    def reset(self):
        with self.lock:
            self.is_running = False
            self._entity_counter = 0
            
            # Create a fresh 20x20x20 space at room temperature
            self.space = UBPSpaceV3(
                width=20.0,
                height=20.0,
                depth=20.0,
                temperature_K=293.15,
                include_floor=True,
            )

            # Add initial blocks
            block1 = EntityFactoryV3.make_block(
                label="IronBlock",
                material_name='iron',
                position=Position(D('-3'), D('8'), D('0')),
            )
            block2 = EntityFactoryV3.make_block(
                label="CopperBlock",
                material_name='copper',
                position=Position(D('0'), D('12'), D('0')),
            )
            block3 = EntityFactoryV3.make_block(
                label="AlBlock",
                material_name='aluminium',
                position=Position(D('3'), D('6'), D('0')),
            )
            self.space.add_entity(block1)
            self.space.add_entity(block2)
            self.space.add_entity(block3)

            # Add a lever
            lever = EntityFactoryV3.make_block(
                label="SteelLever",
                material_name='steel',
                position=Position(D('6'), D('1'), D('0')),
                size=(8.0, 0.2, 0.5),
            )
            self.space.add_lever(lever, pivot_x=10.0, pivot_y=1.0, pivot_z=0.0)

            # Add a water pool
            fluid = FluidBodyV3(material_name='water')
            fluid.emit_pool(origin_x=12, origin_y=2, origin_z=-2, width=6, height=3, depth=4)
            self.space.add_fluid(fluid)

            self._entity_counter = len(self.space._entity_list)
            self.is_running = True
            logger.info("Simulation reset and auto-started")

    def step(self):
        with self.lock:
            if self.is_running and self.space:
                try:
                    self.space.step()
                except Exception as e:
                    logger.error(f"Simulation step error: {e}")
                    logger.error(traceback.format_exc())

    def get_state(self):
        with self.lock:
            if not self.space:
                return {}
            state = self.space.get_threejs_state()
            state['is_running'] = self.is_running
            return state

    def handle_command(self, msg):
        cmd = msg.get("command")
        with self.lock:
            try:
                if cmd == "play":
                    self.is_running = True
                elif cmd == "pause":
                    self.is_running = False
                elif cmd == "reset":
                    self.reset()
                elif cmd == "spawn_block":
                    mat = msg.get("material", "iron")
                    x = float(msg.get("x", 0))
                    y = float(msg.get("y", 10))
                    z = float(msg.get("z", 0))
                    self._entity_counter += 1
                    block = EntityFactoryV3.make_block(
                        label=f"{mat.capitalize()}_{self._entity_counter}",
                        material_name=mat,
                        position=Position(D(str(x)), D(str(y)), D(str(z)))
                    )
                    self.space.add_entity(block)
                elif cmd == "spawn_block_at_grid":
                    grid_x = int(msg.get("grid_x", 0))
                    grid_z = int(msg.get("grid_z", 0))
                    mat = msg.get("material", "iron")
                    y = float(msg.get("y", 15.0))
                    cell_size = float(msg.get("cell_size", 1.0))
                    width = float(msg.get("width", 1.0))
                    height = float(msg.get("height", 1.0))
                    depth = float(msg.get("depth", 1.0))
                    block = self.space.spawn_block_at_grid(grid_x, grid_z, mat, y, cell_size, width, height, depth)
                    self._entity_counter += 1
                elif cmd == "spawn_fluid":
                    x = float(msg.get("x", 0))
                    y = float(msg.get("y", 5))
                    z = float(msg.get("z", 0))
                    fluid = FluidBodyV3(material_name='water')
                    fluid.emit_pool(origin_x=x, origin_y=y, origin_z=z, width=4, height=4, depth=4)
                    self.space.add_fluid(fluid)
                elif cmd == "delete_fluid":
                    body_id = msg.get("body_id")
                    if body_id is not None:
                        body_id = int(body_id)
                    self.space.delete_fluid(body_id)
                elif cmd == "push":
                    eid = int(msg.get("entity_id", 0))
                    fx = float(msg.get("fx", 0))
                    fy = float(msg.get("fy", 0))
                    fz = float(msg.get("fz", 0))
                    self.space.push_entity(eid, fx, fy, fz)
                elif cmd == "pull":
                    eid = int(msg.get("entity_id", 0))
                    fx = float(msg.get("fx", 0))
                    fy = float(msg.get("fy", 0))
                    fz = float(msg.get("fz", 0))
                    self.space.pull_entity(eid, fx, fy, fz)
                elif cmd == "set_temperature":
                    temp_K = float(msg.get("temperature_K", 293.15))
                    self.space.set_ambient_temperature(temp_K)
                elif cmd == "delete_entity":
                    eid = int(msg.get("entity_id", 0))
                    self.space.remove_entity(eid)
                elif cmd == "add_lever":
                    mat = msg.get("material", "steel")
                    x = float(msg.get("x", 5))
                    y = float(msg.get("y", 1.2))
                    z = float(msg.get("z", 0))
                    length = float(msg.get("length", 8))
                    self._entity_counter += 1
                    lever = EntityFactoryV3.make_lever_arm(
                        label=f"Lever_{self._entity_counter}",
                        material_name=mat,
                        length=length,
                        position=Position(D(str(x)), D(str(y)), D(str(z))),
                    )
                    self.space.add_lever(lever, pivot_x=x + length/2, pivot_y=y + 0.1, pivot_z=z + 0.5)
                elif cmd == "set_lever_angle":
                    lever_id = int(msg.get("lever_id", 0))
                    angle_deg = float(msg.get("angle_deg", 0))
                    self.space.set_lever_angle(lever_id, angle_deg)
                elif cmd == "push_lever":
                    lever_id = int(msg.get("lever_id", 0))
                    fx = float(msg.get("fx", 0))
                    fy = float(msg.get("fy", 0))
                    at_x = float(msg.get("at_x", 0))
                    self.space.push_lever(lever_id, fx, fy, at_x)
                elif cmd == "spawn_wall":
                    x = float(msg.get("x", 0))
                    y = float(msg.get("y", 1))
                    z = float(msg.get("z", 0))
                    w = float(msg.get("width", 1))
                    h = float(msg.get("height", 5))
                    d = float(msg.get("depth", 1))
                    mat = msg.get("material", "silicon")
                    self.space.spawn_wall(x, y, z, w, h, d, mat)
                    self._entity_counter += 1
                elif cmd == "build_demo_building":
                    x = float(msg.get("x", 5))
                    z = float(msg.get("z", 5))
                    w = float(msg.get("width", 6))
                    d = float(msg.get("depth", 6))
                    h = float(msg.get("height", 8))
                    wt = float(msg.get("wall_thickness", 1))
                    mat = msg.get("material", "silicon")
                    walls = self.space.build_demo_building(x, z, w, d, h, wt, mat)
                    self._entity_counter += len(walls)
                elif cmd == "fill_building_with_water":
                    x = float(msg.get("x", 5))
                    z = float(msg.get("z", 5))
                    w = float(msg.get("width", 6))
                    d = float(msg.get("depth", 6))
                    h = float(msg.get("height", 8))
                    wt = float(msg.get("wall_thickness", 1))
                    fh = int(msg.get("fill_height", 3))
                    self.space.fill_building_with_water(x, z, w, d, h, wt, fh)
                elif cmd == "demo_displacement":
                    # Building parameters
                    bx, bz = 5.0, 5.0
                    bw, bd, bh = 6.0, 6.0, 8.0
                    wt = 1.0
                    self.space.build_demo_building(bx, bz, bw, bd, bh, wt, 'silicon')
                    self.space.fill_building_with_water(bx, bz, bw, bd, bh, wt, 5)
                    self._entity_counter += 1
                    block = EntityFactoryV3.make_block(
                        label=f"Iron_{self._entity_counter}",
                        material_name='iron',
                        position=Position(D(str(bx + bw/2 - 0.5)), D(str(bh + 5.0)), D(str(bz + bd/2 - 0.5)))
                    )
                    self.space.add_entity(block)
                elif cmd == "ubp_report":
                    eid = int(msg.get("entity_id", 0))
                    info = self.space.get_entity_info(eid)
                    print(_dumps({"type": "report", "data": info}))
                    sys.stdout.flush()

                elif cmd == "engine_test":
                    req_id = msg.get("req_id", "")
                    try:
                        # ============================================================
                        # UBP v5.4 ENGINE VALIDATION SUITE
                        # Tests all mechanics (v5.4 aligned)
                        # ============================================================
                        # v5.4: These are now imported at module level — no more inline imports
                        # (inline imports caused UnboundLocalError due to Python's scoping rules)
                        from ubp_mechanics_v4 import UBP_MECHANICS
                        from ubp_engine_substrate import (
                            vector_from_math_dna, calculate_nrci, calculate_symmetry_tax,
                            xor_interact,
                        )
                        from ubp_unified_v5 import BinaryLinearAlgebra, LEECH_ENGINE

                        tests = {}
                        all_pass = True

                        # --- TEST 1: Phi-Orbit Tick (LAW_PHI_ORBIT_1953) ---
                        iron_vec = vector_from_math_dna('UBP_MATERIAL|Fe26x1|phase=solid')
                        copper_vec = vector_from_math_dna('UBP_MATERIAL|Cu29x1|phase=solid')
                        iv, inrci = UBP_MECHANICS.tick(iron_vec)
                        cv, cnrci = UBP_MECHANICS.tick(copper_vec)
                        phi_pass = (len(iv) == 24 and 0.0 < inrci <= 1.0 and
                                    len(cv) == 24 and 0.0 < cnrci <= 1.0)
                        tests['phi_orbit_tick'] = {
                            'pass': phi_pass,
                            'iron_nrci': round(inrci, 6),
                            'copper_nrci': round(cnrci, 6),
                            'note': 'NRCI = 10/(10 + tax*(1-L)) with Sink Leakage rebate'
                        }
                        all_pass = all_pass and phi_pass

                        # --- TEST 2: Synthesis Superposition (v6.3.1 Flow) ---
                        synth_vec = xor_interact(iron_vec, copper_vec)
                        synth_nrci = float(calculate_nrci(synth_vec))
                        synth_pass = len(synth_vec) == 24 and 0.0 < synth_nrci <= 1.0
                        tests['synthesis_superposition'] = {
                            'pass': synth_pass,
                            'synth_nrci': round(synth_nrci, 6),
                            'note': 'Additive Superposition + Phenomenal Collapse (not XOR)'
                        }
                        all_pass = all_pass and synth_pass

                        # --- TEST 3: fold24_to3 returns 3 bits (v6.3.1 XOR fold) ---
                        folded = BinaryLinearAlgebra.fold24_to3(iron_vec)
                        fold_pass = (len(folded) == 3 and
                                     all(b in (0, 1) for b in folded))
                        tests['fold24_to3_binary'] = {
                            'pass': fold_pass,
                            'folded': list(folded),
                            'note': 'Recursive XOR fold: each output is 0 or 1 (not 0-8)'
                        }
                        all_pass = all_pass and fold_pass

                        # --- TEST 4: Leech Address octant (0-7) ---
                        addr = UBP_MECHANICS.get_address(iron_vec)
                        addr_pass = 0 <= addr.octant <= 7
                        tests['leech_address_octant'] = {
                            'pass': addr_pass,
                            'octant': addr.octant,
                            'cell': list(addr.to_dict()['cell']),
                            'note': '3-bit topological address maps to octant 0-7'
                        }
                        all_pass = all_pass and addr_pass

                        # --- TEST 5: Volumetric Rebate (compactness reduces tax) ---
                        base_tax = LEECH_ENGINE.calculate_symmetry_tax(iron_vec)
                        rebate_tax = LEECH_ENGINE.calculate_symmetry_tax(
                            iron_vec, compactness=Fraction(1, 2)
                        )
                        rebate_pass = rebate_tax < base_tax
                        tests['volumetric_rebate'] = {
                            'pass': rebate_pass,
                            'base_tax': float(base_tax),
                            'rebated_tax': float(rebate_tax),
                            'note': 'T_adj = T_base * (1 - C/13); compact entities pay less'
                        }
                        all_pass = all_pass and rebate_pass

                        # --- TEST 6: Domain Pivot (Phenomenal vs Noumenal) ---
                        phenom_vec = vector_from_math_dna('UBP_MATERIAL|Fe26x1|phase=solid')
                        noumen_vec = vector_from_math_dna('MATH_CONSTANT|pi')
                        domain_pass = phenom_vec != noumen_vec  # Different domain pivots
                        tests['domain_pivot'] = {
                            'pass': domain_pass,
                            'phenomenal_bit12': phenom_vec[11],
                            'noumenal_bit12': noumen_vec[11],
                            'note': 'Bit 12 (index 11): 1=Phenomenal, 0=Noumenal'
                        }
                        all_pass = all_pass and domain_pass

                        # --- TEST 7: Synthesis Collision Event (6-Step Flow) ---
                        syn_result = UBP_MECHANICS.collide(
                            iron_vec, copper_vec,
                            nrci_a=0.7, nrci_b=0.65
                        )
                        collision_pass = (
                            hasattr(syn_result, 'impact_gap') and
                            hasattr(syn_result, 'event_type') and
                            syn_result.event_type in ('ELASTIC', 'DAMAGE', 'DISSOLUTION')
                        )
                        tests['synthesis_collision'] = {
                            'pass': collision_pass,
                            'event_type': syn_result.event_type,
                            'impact_gap': syn_result.impact_gap,
                            'damage_a': round(syn_result.nrci_damage_a, 6),
                            'note': '6-Step Synthesis: XOR->Decode->Snap->Gap->Damage->Dissolve'
                        }
                        all_pass = all_pass and collision_pass

                        # --- TEST 8: 13D Sink Leakage (L = wobble/13) ---
                        sink_l_val = float(SINK_L)
                        sink_pass = 0.0 < sink_l_val < 0.1  # L is a small positive number
                        tests['sink_leakage'] = {
                            'pass': sink_pass,
                            'L': sink_l_val,
                            'note': 'L = (pi*phi*e % 1) / 13; small positive leakage'
                        }
                        all_pass = all_pass and sink_pass

                        # --- TEST 9: Substrate Validation ---
                        substrate_report = validate_substrate()
                        substrate_pass = substrate_report.get('overall') in ('GREEN', 'YELLOW')
                        tests['substrate_validation'] = {
                            'pass': substrate_pass,
                            'overall': substrate_report.get('overall'),
                            'pi_error_pct': substrate_report.get('pi_precision', {}).get('error_pct', 999),
                            'golay_roundtrip': substrate_report.get('golay_roundtrip', {}).get('status'),
                            'particle_physics_error_pct': substrate_report.get('particle_physics', {}).get('global_error_pct', 999),
                        }
                        all_pass = all_pass and substrate_pass

                        # --- TEST 10: TGIC 9-Neighbor Limit ---
                        from ubp_tgic_engine import TGICInteractionEngine
                        tgic = TGICInteractionEngine()
                        # Create 12 identical vectors (should trigger overheating)
                        crowded_manifold = [iron_vec] * 12
                        pressure = tgic.constraints.check_9_neighbor_limit(iron_vec, crowded_manifold)
                        tgic_pass = float(pressure) > 0.0  # Should have pressure with 12 neighbors
                        tests['tgic_9neighbor'] = {
                            'pass': tgic_pass,
                            'pressure': float(pressure),
                            'note': 'Overheating penalty for >9 Leech neighbors (Hamming <=8)'
                        }
                        all_pass = all_pass and tgic_pass

                        print(_dumps({
                            'type': 'engine_test_result',
                            'req_id': req_id,
                            'pass': all_pass,
                            'ubp_version': 'v5.4 (ubp_unified_v5)',
                            'engine_version': '5.2-v5.4',
                            'tests': tests,
                            'tests_passed': sum(1 for t in tests.values() if t.get('pass')),
                            'tests_total': len(tests),
                            'message': 'All UBP v5.4 mechanics validated' if all_pass else 'Some tests failed',
                        }))
                    except Exception as e:
                        print(_dumps({
                            'type': 'engine_test_result',
                            'req_id': req_id,
                            'pass': False,
                            'error': str(e),
                            'traceback': traceback.format_exc(),
                        }))
                    sys.stdout.flush()

                # ====================================================================
                # v5.4 NEW COMMANDS
                # ====================================================================

                elif cmd == "v54_constants":
                    # Returns all v5.4 substrate constants as floats
                    print(_dumps({
                        'type': 'v54_constants',
                        'constants': {
                            'Y':              float(Y_CONSTANT),
                            'Y_INV':          float(Y_INV),
                            'PI':             float(PI),
                            'PHI':            float(PHI),
                            'E_CONST':        float(E_CONST),
                            'MONAD':          float(MONAD),
                            'WOBBLE':         float(WOBBLE),
                            'SINK_L':         float(SINK_L),
                            'SINK_L_STEREO':  float(SINK_L_STEREO),
                            'SINK_SIGMA':     float(SINK_SIGMA),
                            'EXISTENCE_UNIT': float(EXISTENCE_UNIT),
                            'SHEAR_1':        float(SHEAR_1),
                            'SHEAR_2':        float(SHEAR_2),
                        },
                    }))
                    sys.stdout.flush()

                elif cmd == "v54_physics_predictions":
                    # Returns the 6 canonical v5.4 physics formula predictions
                    # with their targets, errors, and budgets (UBP_SKILL_1 §9)
                    preds = {
                        'muon_electron_ratio': {
                            'formula': '169 / w',
                            'predicted': float(MUON_ELECTRON_RATIO),
                            'target': 206.7683,
                            'budget_pct': 0.10,
                        },
                        'strong_coupling_alpha_s': {
                            'formula': '24 * Y^4',
                            'predicted': float(STRONG_COUPLING_ALPHA_S),
                            'target': 0.1181,
                            'budget_pct': 0.50,
                        },
                        'alpha_cubed': {
                            'formula': '(29/24) * Y^12 * e',
                            'predicted': float(ALPHA_CUBED),
                            'target': float(Fraction(1000, 137036) ** 3),
                            'budget_pct': 0.50,
                        },
                        'hubble_H0': {
                            'formula': '(1/3) * w * Y^3 * U_e',
                            'predicted': float(HUBBLE_H0),
                            'target': 70.0,
                            'budget_pct': 1.00,
                        },
                        'omega_k_base': {
                            'formula': '24 * Y^15 * U_e',
                            'predicted': float(OMEGA_K_BASE),
                            'target': 7.27e-4,
                            'budget_pct': 1.00,
                        },
                        'gravitational_G': {
                            'formula': '(39/29) * Y^18 / w',
                            'predicted': float(GRAVITATIONAL_G),
                            'target': 6.6743e-11,
                            'budget_pct': 0.50,
                        },
                    }
                    # Compute error_pct and in_budget for each
                    for k, v in preds.items():
                        err = abs(v['predicted'] - v['target']) / abs(v['target']) * 100
                        v['error_pct'] = err
                        v['in_budget'] = err < v['budget_pct']
                    all_in = all(v['in_budget'] for v in preds.values())
                    print(_dumps({
                        'type': 'v54_physics_predictions',
                        'predictions': preds,
                        'all_in_budget': all_in,
                        'ubp_skill_reference': 'UBP_SKILL_1 §9 Canonical Formula Table',
                    }))
                    sys.stdout.flush()

                elif cmd == "physics_registry_status":
                    # Returns the full physics registry validation report
                    # (all 7 core domains + any registered user domains)
                    registry = get_physics_registry()
                    results = registry.validate_all()
                    print(_dumps({
                        'type': 'physics_registry_status',
                        'overall': results.get('_overall'),
                        'domain_count': results.get('_domain_count'),
                        'domains': {k: v for k, v in results.items()
                                    if not k.startswith('_')},
                    }))
                    sys.stdout.flush()

                elif cmd == "triad_status":
                    # Returns the status of the Triad engines
                    # (Golay, Leech, Monster, BarnesWall, TriadActivation)
                    try:
                        monster = get_monster()
                        bw = get_barnes_wall(256)
                        triad = get_triad()
                        status = {
                            'golay_active': True,  # GOLAY_ENGINE loaded with substrate
                            'leech_active': True,  # LEECH_ENGINE loaded with substrate
                            'monster_loaded': monster is not None,
                            'monster_has_moonshine': hasattr(monster, 'MOONSHINE') and monster.MOONSHINE is not None,
                            'barnes_wall_dim': getattr(bw, 'dimension', None),
                            'triad_instantiable': triad is not None,
                        }
                        status['triad_level'] = 3 if all([
                            status['golay_active'], status['leech_active'],
                            status['monster_loaded'], status['triad_instantiable']
                        ]) else 0
                        print(_dumps({'type': 'triad_status', 'status': status}))
                    except Exception as e:
                        print(_dumps({'type': 'triad_status', 'error': str(e)}))
                    sys.stdout.flush()

                elif cmd == "alu_compute":
                    # Runs a Sovereign ALU operation with SM or SV mode
                    # Input: {command: "alu_compute", op: "add"|"subtract"|"multiply",
                    #         a: [24-bit list], b: [24-bit list], mode: "SM"|"SV",
                    #         alu_type: "noise"|"physics"|"linear_algebra"}
                    try:
                        op = msg.get("op", "add")
                        a = msg.get("a", [0]*24)
                        b = msg.get("b", [0]*24)
                        mode = msg.get("mode", "SV")
                        alu_type = msg.get("alu_type", "noise")

                        if alu_type == "physics":
                            alu = get_physics_alu(mode)
                        elif alu_type == "linear_algebra":
                            alu = get_linear_algebra_alu(mode)
                        else:
                            alu = get_noise_alu(mode)

                        # Map op to method name (ALU uses 'add', 'sub', 'mul' etc.)
                        method_map = {
                            'add': 'add', 'subtract': 'sub', 'sub': 'sub',
                            'multiply': 'mul', 'mul': 'mul',
                        }
                        method_name = method_map.get(op, op)
                        if not hasattr(alu, method_name):
                            print(_dumps({
                                'type': 'alu_compute', 'error': f"ALU has no method '{op}' (try add/subtract/multiply)",
                                'available_methods': [m for m in dir(alu) if not m.startswith('_') and callable(getattr(alu, m))][:20],
                            }))
                        else:
                            method = getattr(alu, method_name)
                            result = method(a, b)
                            print(_dumps({
                                'type': 'alu_compute',
                                'op': op,
                                'mode': mode,
                                'alu_type': alu_type,
                                'result': result,
                            }))
                    except Exception as e:
                        print(_dumps({'type': 'alu_compute', 'error': str(e),
                                      'traceback': traceback.format_exc()}))
                    sys.stdout.flush()

                elif cmd == "substrate_validate":
                    # Runs the full validate_substrate() and returns the report
                    req_id = msg.get("req_id", "")
                    try:
                        report = validate_substrate()
                        print(_dumps({
                            'type': 'substrate_validate',
                            'req_id': req_id,
                            'overall': report.get('overall'),
                            'blocks': {k: v for k, v in report.items() if k != 'overall'},
                        }))
                    except Exception as e:
                        print(_dumps({'type': 'substrate_validate', 'req_id': req_id,
                                      'error': str(e)}))
                    sys.stdout.flush()

            except Exception as e:
                logger.error(f"Command execution error ({cmd}): {e}")
                logger.error(traceback.format_exc())

def main():
    sim = UBPSimulation()
    
    # Thread to read commands from stdin
    def read_commands():
        for line in sys.stdin:
            try:
                msg = json.loads(line)
                if msg.get("type") == "command":
                    sim.handle_command(msg)
            except Exception as e:
                logger.error(f"Error parsing command line: {e}")

    t = threading.Thread(target=read_commands, daemon=True)
    t.start()
    
    # Main simulation loop
    # Broadcast every 2 ticks (30 fps)
    broadcast_every = 2
    tick_interval = 1.0 / 60.0
    
    while True:
        loop_start = time.monotonic()
        
        sim.step()
        
        if sim.space and sim.space.tick % broadcast_every == 0:
            try:
                state = sim.get_state()
                print(_dumps({"type": "state", "data": state}))
                sys.stdout.flush()
            except Exception as e:
                logger.error(f"State broadcast error: {e}")

        elapsed = time.monotonic() - loop_start
        sleep_time = max(0.0, tick_interval - elapsed)
        time.sleep(sleep_time)

if __name__ == "__main__":
    main()