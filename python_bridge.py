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

# ── SLICE 1: load the 12-domain physics pack ────────────────────────────────
# Importing this module runs `register_all_physics_domains()` at import time,
# which registers 12 additional physics domains (electromagnetism, thermodynamics,
# quantum_mechanics, nuclear_physics, cosmology, condensed_matter, astrophysics,
# chemical_physics, information_theory, acoustics, high_energy_physics, optics)
# alongside the 7 core domains already registered by the substrate.
# After this import, get_physics_registry() reports 19 domains total.
import ubp_physics_domains_pack  # noqa: F401  (side-effect import — registers 12 domains)

# ── SLICE 2: world physics state (single source of truth for gravity, T, c_sound…) ──
# Introduces WorldPhysicsState, a mutable holder whose values are ALL sourced
# from the 19 registered physics domains (no hardcoded 9.81, no hardcoded 343 m/s).
# The physics engine reads live from this object each tick.
from ubp_world_physics import get_world_physics, WorldPhysicsState
from ubp_domain_spawns import get_domain_spawn_catalog, build_spawn_spec
from ubp_field_sampling import sample_field_points
from ubp_reality_alignment import score_alignment
from ubp_world_scenarios import get_world_scenario_catalog, apply_world_scenario

# Configure logging to stderr so it doesn't interfere with stdout JSON
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("ubp_bridge")

# Log domain count on boot so operators can confirm the pack loaded correctly.
_registry = get_physics_registry()
logger.info(f"UBP physics registry loaded with {len(_registry.registered_names)} domains: "
            f"{', '.join(_registry.registered_names)}")


class UBPSimulation:
    """
    Manages the UBPSpaceV3 simulation instance.
    V4.0: Integrated Phi-Orbit, Synthesis, Leech Lattice, and new building tools.
    v5.4-Slice1+2: 19-domain physics registry + WorldPhysicsState.
    """
    def __init__(self):
        self.substrate = UBPEngineSubstrate()
        self.space: Optional[UBPSpaceV3] = None
        self.is_running = False
        self.lock = threading.RLock()
        self._entity_counter = 0
        # World physics state — every value here is domain-sourced, not hardcoded.
        self.world_physics: WorldPhysicsState = get_world_physics()
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
                temperature_K=float(self.world_physics.ambient_temperature_K),
            )

            # Wire the world-physics object into the physics engine so gravity/thermal
            # updates propagate on the next tick.
            if hasattr(self.space, 'physics'):
                try:
                    self.space.physics.set_world_physics(self.world_physics)
                except AttributeError:
                    # Older engine — fall back silently; world_physics only affects new spawns.
                    pass

            # Give the sim a couple of demo blocks so the scene isn't empty on reset.
            block1 = EntityFactoryV3.make_block(
                label='Iron_seed',
                material_name='iron',
                position=Position(D('-3'), D('12'), D('0')),
            )
            block2 = EntityFactoryV3.make_block(
                label='Copper_seed',
                material_name='copper',
                position=Position(D('0'), D('14'), D('0')),
            )
            block3 = EntityFactoryV3.make_block(
                label='Aluminium_seed',
                material_name='aluminium',
                position=Position(D('3'), D('16'), D('0')),
            )
            self.space.add_entity(block1)
            self.space.add_entity(block2)
            self.space.add_entity(block3)

            # Demo lever
            lever = EntityFactoryV3.make_block(
                label='Lever_seed',
                material_name='steel',
                position=Position(D('-8'), D('4'), D('4')),
                size=(D('6'), D('0.4'), D('0.4')),
            )
            self.space.add_entity(lever)

            # Demo fluid
            fluid = FluidBodyV3(material_name='water')
            fluid.spawn_particles_in_box(
                center=(6.0, 4.0, 4.0), size=(3.0, 3.0, 3.0),
            )
            self.space.add_fluid_body(fluid)

            self._entity_counter = 4

    def step(self):
        with self.lock:
            if self.is_running and self.space is not None:
                self.space.step()

    def get_state(self) -> Dict[str, Any]:
        with self.lock:
            if self.space is None:
                return {'tick': 0, 'entities': [], 'fluid_bodies': [], 'constraints': [],
                        'is_running': False, 'world_physics': self.world_physics.to_dict(),
                        'reality_alignment': {'reality_score': 100.0, 'per_entity': [], 'per_domain': {}}}
            state = self.space.to_threejs_state()
            state['is_running'] = self.is_running
            # SLICE 2: expose world-physics to the frontend HUD every broadcast.
            state['world_physics'] = self.world_physics.to_dict()
            # SLICE 10: score every domain entity vs the physics registry canonical values.
            try:
                state['reality_alignment'] = score_alignment(self.space._entity_list)
            except Exception as _e:
                state['reality_alignment'] = {
                    'reality_score': 0.0, 'per_entity': [], 'per_domain': {},
                    'error': f'{type(_e).__name__}: {_e}',
                }
            # SLICE 9: recent decay events for the HUD event log.
            try:
                de = getattr(self.space, '_domain_effects', None)
                state['recent_decay_events'] = de.recent_decay_events(25) if de else []
            except Exception:
                state['recent_decay_events'] = []
            return state

    def handle_command(self, msg: Dict[str, Any]):
        cmd = msg.get("command")
        req_id = msg.get("req_id")

        def _reply(payload: Dict[str, Any]):
            """Attach req_id (if present) and emit a single JSON line."""
            if req_id is not None:
                payload['req_id'] = req_id
            print(_dumps(payload))
            sys.stdout.flush()

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
                    block = self.space.spawn_block_at_grid(
                        grid_x, grid_z, mat, y, cell_size, width, height, depth
                    )
                    self._entity_counter += 1

                elif cmd == "spawn_fluid":
                    fluid = FluidBodyV3(material_name='water')
                    fluid.spawn_particles_in_box(
                        center=(float(msg.get("x", 0)),
                                float(msg.get("y", 10)),
                                float(msg.get("z", 0))),
                        size=(3.0, 3.0, 3.0),
                    )
                    self.space.add_fluid_body(fluid)

                elif cmd == "delete_fluid":
                    idx = int(msg.get("fluid_id", 0))
                    self.space.delete_fluid_body(idx)

                elif cmd == "push":
                    entity_id = int(msg["entity_id"])
                    fx, fy, fz = float(msg.get("fx", 0)), float(msg.get("fy", 0)), float(msg.get("fz", 0))
                    self.space.push_entity(entity_id, D(str(fx)), D(str(fy)), D(str(fz)))

                elif cmd == "pull":
                    entity_id = int(msg["entity_id"])
                    fx, fy, fz = float(msg.get("fx", 0)), float(msg.get("fy", 0)), float(msg.get("fz", 0))
                    self.space.push_entity(entity_id, -D(str(fx)), -D(str(fy)), -D(str(fz)))

                elif cmd == "set_temperature":
                    entity_id = int(msg["entity_id"])
                    T = float(msg["temperature"])
                    self.space.set_entity_temperature(entity_id, T)

                elif cmd == "delete_entity":
                    entity_id = int(msg["entity_id"])
                    self.space.remove_entity(entity_id)

                elif cmd == "add_lever":
                    x = float(msg.get("x", 0))
                    y = float(msg.get("y", 4))
                    z = float(msg.get("z", 0))
                    mat = msg.get("material", "steel")
                    self._entity_counter += 1
                    lever = EntityFactoryV3.make_lever_arm(
                        label=f"Lever_{self._entity_counter}",
                        material_name=mat,
                        position=Position(D(str(x)), D(str(y)), D(str(z))),
                        length=D('6'),
                    )
                    self.space.add_entity(lever)
                    # Auto-add a pivot constraint at the middle of the lever
                    self.space.add_lever_pivot_at(lever.id, D('0.5'))

                elif cmd == "set_lever_angle":
                    entity_id = int(msg["entity_id"])
                    angle = float(msg["angle"])
                    self.space.set_lever_angle(entity_id, angle)

                elif cmd == "push_lever":
                    entity_id = int(msg["entity_id"])
                    force = float(msg.get("force", 2.0))
                    at_x = float(msg.get("at_x", 0.0))
                    self.space.apply_force_at_point(entity_id, D(str(force)), D(str(at_x)))

                elif cmd == "spawn_wall":
                    x = float(msg.get("x", 0))
                    y = float(msg.get("y", 0))
                    z = float(msg.get("z", 0))
                    length = float(msg.get("length", 4))
                    height = float(msg.get("height", 4))
                    mat = msg.get("material", "iron")
                    self.space.spawn_wall(
                        x_start=D(str(x)), y_start=D(str(y)), z_start=D(str(z)),
                        length=D(str(length)), height=D(str(height)),
                        material_name=mat,
                    )

                elif cmd == "build_demo_building":
                    self.space.build_demo_building(
                        x_center=float(msg.get("x", 0)),
                        z_center=float(msg.get("z", 0)),
                        floors=int(msg.get("floors", 2)),
                    )

                elif cmd == "fill_building_with_water":
                    fluid = FluidBodyV3(material_name='water')
                    fluid.spawn_particles_in_box(
                        center=(float(msg.get("x", 0)),
                                float(msg.get("y", 3)),
                                float(msg.get("z", 0))),
                        size=(3.5, 3.0, 3.5),
                    )
                    self.space.add_fluid_body(fluid)

                elif cmd == "demo_displacement":
                    self.space.demo_displacement()

                elif cmd == "ubp_report":
                    info = {
                        'y_constant': float(Y_CONSTANT),
                        'domain_count': len(get_physics_registry().registered_names),
                        'domains': get_physics_registry().registered_names,
                    }
                    _reply({'type': 'report', 'data': info})

                elif cmd == "engine_test":
                    tests: Dict[str, Any] = {}
                    all_pass = True
                    # 1. Sub-substrate Y constant sanity
                    y_val = float(Y_CONSTANT)
                    tests['y_constant'] = {'value': y_val, 'pass': 0.05 < y_val < 0.15}
                    all_pass = all_pass and tests['y_constant']['pass']
                    # 2. Registry has at least 19 domains (7 core + 12 pack)
                    n_domains = len(get_physics_registry().registered_names)
                    tests['domain_count'] = {'value': n_domains, 'pass': n_domains >= 19}
                    all_pass = all_pass and tests['domain_count']['pass']
                    # 3. Every domain validates GREEN or SKIP
                    reg_results = get_physics_registry().validate_all()
                    domain_statuses = {
                        k: v.get('status', 'MISSING')
                        for k, v in reg_results.items()
                        if not k.startswith('_')
                    }
                    tests['domain_statuses'] = domain_statuses
                    all_green = all(s in ('GREEN', 'SKIP') for s in domain_statuses.values())
                    tests['all_domains_green'] = {'value': all_green, 'pass': all_green}
                    all_pass = all_pass and all_green
                    # 4. World physics state initialised
                    wp = self.world_physics.to_dict()
                    tests['world_physics'] = wp
                    tests['world_physics_gravity_positive'] = {
                        'value': wp['gravity_ms2'], 'pass': wp['gravity_ms2'] > 0
                    }
                    all_pass = all_pass and (wp['gravity_ms2'] > 0)

                    _reply({'type': 'engine_test', 'pass': all_pass, 'tests': tests})

                elif cmd == "v54_constants":
                    _reply({
                        'type': 'v54_constants',
                        'constants': {
                            'Y': float(Y_CONSTANT),
                            'Y_INV': float(Y_INV),
                            'PI': float(PI),
                            'PHI': float(PHI),
                            'E': float(E_CONST),
                            'MONAD': float(MONAD),
                            'WOBBLE': float(WOBBLE),
                            'SINK_L': float(SINK_L),
                            'SINK_L_STEREO': float(SINK_L_STEREO),
                            'SINK_SIGMA': float(SINK_SIGMA),
                            'EXISTENCE_UNIT': float(EXISTENCE_UNIT),
                            'SHEAR_1': float(SHEAR_1),
                            'SHEAR_2': float(SHEAR_2),
                        },
                    })

                elif cmd == "v54_physics_predictions":
                    preds = {
                        'muon_electron_ratio': {
                            'predicted': float(MUON_ELECTRON_RATIO),
                            'target': 206.7682830,
                            'budget_pct': 0.10,
                        },
                        'strong_coupling_alpha_s': {
                            'predicted': float(STRONG_COUPLING_ALPHA_S),
                            'target': 0.1181,
                            'budget_pct': 0.50,
                        },
                        'alpha_cubed': {
                            'predicted': float(ALPHA_CUBED),
                            'target': 3.886e-7,
                            'budget_pct': 0.50,
                        },
                        'hubble_h0': {
                            'predicted': float(HUBBLE_H0),
                            'target': 70.0,
                            'budget_pct': 1.00,
                        },
                        'omega_k': {
                            'predicted': float(OMEGA_K_BASE),
                            'target': 7.27e-4,
                            'budget_pct': 1.00,
                        },
                        'gravitational_G': {
                            'predicted': float(GRAVITATIONAL_G),
                            'target': 6.6743e-11,
                            'budget_pct': 0.50,
                        },
                    }
                    all_in = True
                    for k, v in preds.items():
                        v['error_pct'] = abs(v['predicted'] - v['target']) / v['target'] * 100
                        v['in_budget'] = v['error_pct'] < v['budget_pct']
                        all_in = all_in and v['in_budget']
                    _reply({
                        'type': 'v54_physics_predictions',
                        'predictions': preds,
                        'all_in_budget': all_in,
                        'ubp_skill_reference': 'UBP_SKILL_1 §9 Canonical Formula Table',
                    })

                elif cmd == "physics_registry_status":
                    # Returns the full physics registry validation report
                    # (7 core + 12 pack = 19 domains after Slice 1)
                    registry = get_physics_registry()
                    results = registry.validate_all()
                    _reply({
                        'type': 'physics_registry_status',
                        'overall': results.get('_overall'),
                        'domain_count': results.get('_domain_count',
                                                    len(registry.registered_names)),
                        'domains': {k: v for k, v in results.items()
                                    if not k.startswith('_')},
                    })

                # ── SLICE 1: three new commands exposing the domain pack ─────────
                elif cmd == "physics_domain_detail":
                    # Deep-inspect one domain: constants, formula names, layer tag, version.
                    name = msg.get("name", "")
                    registry = get_physics_registry()
                    try:
                        domain = registry.get_domain(name)
                    except KeyError as e:
                        _reply({'type': 'physics_domain_detail', 'error': str(e),
                                'available': registry.registered_names})
                    else:
                        # Marshal constants to floats (they are typically Fractions).
                        constants: Dict[str, Any] = {}
                        for k, v in domain.constants.items():
                            try:
                                constants[k] = float(v)
                            except (TypeError, ValueError):
                                constants[k] = repr(v)
                        _reply({
                            'type': 'physics_domain_detail',
                            'name': domain.name,
                            'version': domain.version,
                            'description': domain.description,
                            'constants': constants,
                            'formula_names': list(domain.formulas.keys()),
                            'engine_names': list(domain.engines.keys()),
                            'depends_on': list(domain.depends_on),
                            'has_validator': domain.validate is not None,
                        })

                elif cmd == "physics_formula_eval":
                    # Evaluate one formula from one domain — returns a plain float.
                    # Usage: {command: 'physics_formula_eval', domain: 'optics',
                    #         formula: 'photon_energy', params: {wavelength_nm: 500}}
                    domain_name = msg.get("domain", "")
                    formula_name = msg.get("formula", "")
                    params = msg.get("params", {}) or {}
                    registry = get_physics_registry()
                    try:
                        domain = registry.get_domain(domain_name)
                        if formula_name not in domain.formulas:
                            raise KeyError(
                                f"Domain {domain_name!r} has no formula {formula_name!r}. "
                                f"Available: {list(domain.formulas.keys())}"
                            )
                        formula = domain.formulas[formula_name]
                        # Most pack formulas are zero-arg lambdas returning Fractions.
                        # A few may accept kwargs; try both signatures.
                        try:
                            raw = formula(**params) if params else formula()
                        except TypeError:
                            raw = formula()
                        _reply({
                            'type': 'physics_formula_eval',
                            'domain': domain_name,
                            'formula': formula_name,
                            'params': params,
                            'value': float(raw),
                            'raw_repr': repr(raw),
                        })
                    except Exception as e:
                        _reply({
                            'type': 'physics_formula_eval',
                            'domain': domain_name,
                            'formula': formula_name,
                            'error': f"{type(e).__name__}: {e}",
                        })

                elif cmd == "physics_domains_full_report":
                    # One-shot dump of all 19 domains: full constants + formula list +
                    # validation status + layer classification (parsed from description).
                    registry = get_physics_registry()
                    validate_results = registry.validate_all()
                    layers = {
                        'reality':     ['nuclear_physics', 'astrophysics'],
                        'information': ['electromagnetism', 'quantum_mechanics',
                                        'condensed_matter', 'information_theory', 'optics'],
                        'activation':  ['thermodynamics', 'chemical_physics', 'acoustics'],
                        'potential':   ['cosmology'],
                        'reality+potential': ['high_energy_physics'],
                        'core':        ['core_mechanics', 'core_physics', 'core_fluid',
                                        'core_rigid_body', 'core_space', 'core_materials',
                                        'core_entity'],
                    }
                    def _layer_of(name: str) -> str:
                        for layer, members in layers.items():
                            if name in members:
                                return layer
                        return 'unclassified'
                    domains_payload: Dict[str, Any] = {}
                    for name in registry.registered_names:
                        d = registry.get_domain(name)
                        consts: Dict[str, Any] = {}
                        for k, v in d.constants.items():
                            try:
                                consts[k] = float(v)
                            except (TypeError, ValueError):
                                consts[k] = repr(v)
                        domains_payload[name] = {
                            'version': d.version,
                            'description': d.description,
                            'layer': _layer_of(name),
                            'constants': consts,
                            'formulas': list(d.formulas.keys()),
                            'engines': list(d.engines.keys()),
                            'validation': validate_results.get(name, {'status': 'MISSING'}),
                        }
                    _reply({
                        'type': 'physics_domains_full_report',
                        'overall': validate_results.get('_overall'),
                        'domain_count': len(registry.registered_names),
                        'core_count':  sum(1 for n in registry.registered_names
                                           if n in layers['core']),
                        'pack_count':  sum(1 for n in registry.registered_names
                                           if n not in layers['core']),
                        'domains': domains_payload,
                    })

                # ── SLICE 2: world-physics query + update ────────────────────────
                elif cmd == "domain_spawn_catalog":
                    # Returns the frontend-facing schema for all domain-native presets.
                    _reply({
                        'type': 'domain_spawn_catalog',
                        'catalog': get_domain_spawn_catalog(),
                        'world_physics': self.world_physics.to_dict(),
                    })

                elif cmd == "spawn_domain_entity":
                    # Generic domain-native spawner. This is the durable ABI for later
                    # slices: every spawned object carries real-world metadata in
                    # domain_params even before live force-coupling is added.
                    domain = str(msg.get('domain', ''))
                    preset = str(msg.get('preset', ''))
                    params = msg.get('params', {}) or {}
                    x = float(msg.get('x', 10))
                    y = float(msg.get('y', 12))
                    z = float(msg.get('z', 0))
                    spec = build_spawn_spec(domain, preset, params, self.world_physics)
                    self._entity_counter += 1
                    spec = dict(spec)
                    # Ensure unique label in-world while preserving the semantic preset name.
                    spec['label'] = f"{spec.get('label', domain)}_{self._entity_counter}"
                    entity = EntityFactoryV3.make_domain_entity(
                        spec,
                        position=Position(D(str(x)), D(str(y)), D(str(z))),
                    )
                    self.space.add_entity(entity)
                    _reply({
                        'type': 'spawn_domain_entity',
                        'ok': True,
                        'entity_id': entity.entity_id,
                        'label': entity.label,
                        'domain': spec.get('domain_tag'),
                        'preset': preset,
                        'spec': {
                            k: v for k, v in spec.items()
                            if k not in ('domain_params',)
                        },
                        'domain_params': spec.get('domain_params', {}),
                    })

                elif cmd == "get_world_physics":
                    _reply({'type': 'world_physics', 'data': self.world_physics.to_dict()})

                elif cmd == "world_scenario_catalog":
                    _reply({
                        'type': 'world_scenario_catalog',
                        'catalog': get_world_scenario_catalog(),
                        'world_physics': self.world_physics.to_dict(),
                    })

                elif cmd == "apply_world_scenario":
                    scenario_id = str(msg.get('scenario_id', ''))
                    result = apply_world_scenario(self.world_physics, scenario_id)
                    if self.space is not None and hasattr(self.space, 'physics'):
                        try:
                            self.space.physics.set_world_physics(self.world_physics)
                        except AttributeError:
                            pass
                    _reply({
                        'type': 'world_scenario_applied',
                        **result,
                    })

                elif cmd == "roadmap_status":
                    _reply({
                        'type': 'roadmap_status',
                        'completed_slices': list(range(1, 13)),
                        'remaining_slices': [],
                        'features': {
                            'world_physics': True,
                            'domain_spawns': True,
                            'pairwise_gravity': True,
                            'pairwise_em': True,
                            'static_overlays': True,
                            'live_field_sampling': True,
                            'time_effects': True,
                            'reality_alignment': True,
                            'world_scenarios': True,
                            'docs_and_tests': True,
                        },
                    })

                elif cmd == "reality_alignment":
                    _reply({
                        'type': 'reality_alignment',
                        'data': score_alignment(self.space._entity_list) if self.space else {
                            'reality_score': 100.0, 'per_entity': [], 'per_domain': {},
                        },
                    })

                elif cmd == "domain_field_sample":
                    field = str(msg.get('field', 'gravity'))
                    points = msg.get('points', []) or []
                    payload = sample_field_points(field, points, list(self.space.entities.values()), self.world_physics)
                    _reply(payload)

                elif cmd == "set_world_physics":
                    # Accepts any subset of the world-physics fields.
                    # Every field is validated against the source domain before applying.
                    updates = msg.get("updates", {}) or {}
                    try:
                        applied = self.world_physics.update(updates)
                        # Propagate the change into any live physics engines.
                        if self.space is not None and hasattr(self.space, 'physics'):
                            try:
                                self.space.physics.set_world_physics(self.world_physics)
                            except AttributeError:
                                pass
                        _reply({
                            'type': 'world_physics',
                            'applied': applied,
                            'data': self.world_physics.to_dict(),
                        })
                    except Exception as e:
                        _reply({
                            'type': 'world_physics',
                            'error': f"{type(e).__name__}: {e}",
                            'data': self.world_physics.to_dict(),
                        })

                elif cmd == "triad_status":
                    try:
                        monster = get_monster()
                        bw = get_barnes_wall(256)
                        triad = get_triad()
                        status = {
                            'golay_active': True,
                            'leech_active': True,
                            'monster_loaded': monster is not None,
                            'monster_has_moonshine': hasattr(monster, 'MOONSHINE')
                                                     and monster.MOONSHINE is not None,
                            'barnes_wall_dim': getattr(bw, 'dimension', None),
                            'triad_instantiable': triad is not None,
                        }
                        status['triad_level'] = 3 if all([
                            status['golay_active'], status['leech_active'],
                            status['monster_loaded'], status['triad_instantiable']
                        ]) else 0
                        _reply({'type': 'triad_status', 'status': status})
                    except Exception as e:
                        _reply({'type': 'triad_status', 'error': str(e)})

                elif cmd == "alu_compute":
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

                        if op == "add":
                            result = alu.add(a, b)
                        elif op == "subtract":
                            result = alu.subtract(a, b)
                        elif op == "multiply":
                            result = alu.multiply(a, b)
                        else:
                            result = a
                        _reply({'type': 'alu_compute', 'op': op, 'mode': mode,
                                'alu_type': alu_type, 'result': list(result)})
                    except Exception as e:
                        _reply({'type': 'alu_compute', 'error': str(e)})

                elif cmd == "substrate_validate":
                    try:
                        report = validate_substrate()
                        _reply({'type': 'substrate_validate', 'report': report})
                    except Exception as e:
                        _reply({'type': 'substrate_validate', 'error': str(e)})

            except Exception as e:
                logger.error(f"Command execution error ({cmd}): {e}")
                logger.error(traceback.format_exc())
                if req_id is not None:
                    _reply({'type': 'error', 'command': cmd,
                            'error': f"{type(e).__name__}: {e}"})


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
