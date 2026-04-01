"""
================================================================================
UBP SERVER v4.0 — FastAPI Backend
================================================================================
V4.0 New Endpoints:
  - GET /mechanics: UBP mechanics system status (Phi-Orbit, NRCI, Leech)
  - GET /engine_test: Run the engine_test.json validation (README verification)
  - POST /command {command: "ubp_report", entity_id}: Full UBP entity report

V3.2 Commands (retained):
  - delete_fluid: delete a fluid body by body_id, or all fluid if no id
  - set_lever_angle: directly set a lever's angle in degrees
  - push_lever: push a lever with a force vector (converted to torque)
  - spawn_block_at_grid: spawn a block at a grid cell coordinate
  - spawn_wall: spawn a static wall entity
  - build_demo_building: create a hollow building of blocks
  - fill_building_with_water: fill a building interior with water
  - demo_displacement: run the full water-displacement demo scenario
================================================================================
"""

import asyncio
import json
import logging
import os
import time

print("[Python] UBP Server v4.0 is starting...")

from decimal import Decimal
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from ubp_engine_substrate import UBPEngineSubstrate
from ubp_entity_v3 import EntityFactoryV3, UBPEntityV3, Position, D
from ubp_space_v3 import UBPSpaceV3
from ubp_fluid_v3 import FluidBodyV3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ubp_server")

app = FastAPI(title="UBP Digital Twin v4.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class UBPSimulationManager:
    """
    Manages the UBPSpaceV3 simulation instance.
    V3.2: Added fluid deletion, lever angle control, grid placement, building helpers.
    """

    def __init__(self):
        self.substrate = UBPEngineSubstrate()
        self.space: Optional[UBPSpaceV3] = None
        self.is_running: bool = False
        self._entity_counter: int = 0
        self.reset()

    def reset(self):
        self.is_running = False
        self._entity_counter = 0

        self.space = UBPSpaceV3(
            width=20.0, height=20.0, depth=20.0,
            temperature_K=293.15, include_floor=True,
        )

        block1 = EntityFactoryV3.make_block(
            label="IronBlock", material_name='iron',
            position=Position(D('-3'), D('8'), D('0')),
        )
        block2 = EntityFactoryV3.make_block(
            label="CopperBlock", material_name='copper',
            position=Position(D('0'), D('12'), D('0')),
        )
        block3 = EntityFactoryV3.make_block(
            label="AlBlock", material_name='aluminium',
            position=Position(D('3'), D('6'), D('0')),
        )
        self.space.add_entity(block1)
        self.space.add_entity(block2)
        self.space.add_entity(block3)

        # Lever: 8 units long, pivoted at its centre
        lever = EntityFactoryV3.make_block(
            label="SteelLever", material_name='steel',
            position=Position(D('6'), D('1'), D('0')),
            size=(8.0, 0.2, 0.5),
        )
        self.space.add_lever(lever, pivot_x=10.0, pivot_y=1.0, pivot_z=0.0)

        # Water pool
        fluid = FluidBodyV3(material_name='water')
        fluid.emit_pool(origin_x=12, origin_y=2, origin_z=-2, width=6, height=3, depth=4)
        self.space.add_fluid(fluid)

        self._entity_counter = len(self.space._entity_list)
        self.is_running = True
        logger.info(f"Simulation reset: {len(self.space._entity_list)} entities, "
                    f"{sum(len(f.particles) for f in self.space._fluid_bodies)} fluid particles")

    def step(self):
        if self.is_running and self.space is not None:
            self.space.step()

    def get_state(self) -> Dict[str, Any]:
        if self.space is None:
            return {
                'tick': 0, 'time_s': 0.0, 'is_running': False,
                'ambient': {'temperature_K': 293.15, 'temperature_ubp': 0.0},
                'entities': [], 'fluid_particles': [], 'fluid_bodies': [],
                'lever_constraints': [],
                'stats': {'entity_count': 0, 'fluid_particle_count': 0,
                          'fluid_body_count': 0, 'avg_tick_ms': 0.0}
            }
        state = self.space.get_threejs_state()
        state['is_running'] = self.is_running
        return state

    def spawn_block(self, material: str, x: float, y: float, z: float) -> Optional[int]:
        if self.space is None:
            return None
        from ubp_entity_v3 import AABB
        test_x = D(str(x))
        test_y = D(str(y))
        test_z = D(str(z))
        block_size = D('1')
        for _ in range(20):
            test_aabb = AABB(test_x, test_y, test_z,
                             test_x + block_size, test_y + block_size, test_z + block_size)
            overlap = any(test_aabb.overlaps(e.aabb()) for e in self.space._entity_list)
            if not overlap:
                break
            test_y += block_size
        self._entity_counter += 1
        label = f"{material.capitalize()}_{self._entity_counter}"
        block = EntityFactoryV3.make_block(
            label=label, material_name=material,
            position=Position(test_x, test_y, test_z),
        )
        self.space.add_entity(block)
        return block.entity_id

    def spawn_block_at_grid(
        self, grid_x: int, grid_z: int,
        material: str = 'iron', y: float = 15.0,
        grid_cell_size: float = 1.0,
    ) -> Optional[int]:
        """Spawn a block at a grid cell coordinate."""
        if self.space is None:
            return None
        block = self.space.spawn_block_at_grid(
            grid_x=grid_x, grid_z=grid_z,
            material_name=material, y=y,
            grid_cell_size=grid_cell_size,
        )
        self._entity_counter += 1
        return block.entity_id

    def delete_entity(self, entity_id: int) -> bool:
        if self.space is None:
            return False
        entity = self.space.get_entity(entity_id)
        if entity is None or entity.is_static:
            return False
        self.space.remove_entity(entity_id)
        return True

    def delete_fluid(self, body_id: Optional[int] = None) -> int:
        """Delete a fluid body by body_id, or all fluid if body_id is None."""
        if self.space is None:
            return 0
        return self.space.delete_fluid(body_id)

    def spawn_fluid(self, x: float, y: float, z: float) -> int:
        if self.space is None:
            return -1
        fluid = FluidBodyV3(material_name='water')
        fluid.emit_pool(origin_x=x, origin_y=y, origin_z=z, width=4, height=3, depth=4)
        self.space.add_fluid(fluid)
        return fluid.body_id

    def push_entity(self, entity_id: int, fx: float, fy: float, fz: float) -> bool:
        if self.space is None:
            return False
        return self.space.push_entity(entity_id, fx, fy, fz)

    def pull_entity(self, entity_id: int, fx: float, fy: float, fz: float) -> bool:
        if self.space is None:
            return False
        return self.space.pull_entity(entity_id, fx, fy, fz)

    def spawn_lever(
        self, material: str, x: float, y: float, z: float, length: float = 8.0
    ) -> Optional[int]:
        if self.space is None:
            return None
        self._entity_counter += 1
        label = f"Lever_{self._entity_counter}"
        lever = EntityFactoryV3.make_lever_arm(
            label=label, material_name=material, length=length,
            position=Position(D(str(x)), D(str(y)), D(str(z))),
        )
        pivot_x = x + length / 2.0
        self.space.add_lever(lever, pivot_x=pivot_x, pivot_y=y + 0.1, pivot_z=z + 0.5)
        return lever.entity_id

    def set_lever_angle(self, lever_id: int, angle_deg: float) -> bool:
        """Directly set a lever's angle in degrees."""
        if self.space is None:
            return False
        return self.space.set_lever_angle(lever_id, angle_deg)

    def push_lever(self, lever_id: int, fx: float, fy: float, at_x: float) -> bool:
        """Push a lever with a force, converting to torque."""
        if self.space is None:
            return False
        return self.space.rigid_body.push_lever(lever_id, fx, fy, at_x)

    def spawn_wall(
        self, x: float, y: float, z: float,
        width: float = 1.0, height: float = 5.0, depth: float = 1.0,
        material: str = 'silicon',
    ) -> Optional[int]:
        if self.space is None:
            return None
        wall = self.space.spawn_wall(x, y, z, width, height, depth, material)
        self._entity_counter += 1
        return wall.entity_id

    def build_demo_building(
        self, x: float = 5.0, z: float = 5.0,
        width: float = 6.0, depth: float = 6.0,
        height: float = 8.0, wall_thickness: float = 1.0,
        material: str = 'silicon',
    ) -> List[int]:
        if self.space is None:
            return []
        walls = self.space.build_demo_building(
            x=x, z=z, width=width, depth=depth,
            height=height, wall_thickness=wall_thickness,
            material_name=material,
        )
        self._entity_counter += len(walls)
        return [w.entity_id for w in walls]

    def fill_building_with_water(
        self, x: float, z: float,
        width: float, depth: float, height: float,
        wall_thickness: float = 1.0, fill_height: int = 3,
    ) -> int:
        if self.space is None:
            return -1
        fluid = self.space.fill_building_with_water(
            x=x, z=z, width=width, depth=depth, height=height,
            wall_thickness=wall_thickness, fill_height=fill_height,
        )
        return fluid.body_id

    def run_displacement_demo(self) -> Dict[str, Any]:
        """
        Set up the full water-displacement demo:
        1. Build a hollow building
        2. Fill it with water
        3. Spawn a heavy block above the building
        4. The block falls into the water, displacing it over the top
        Returns the entity IDs for the demo objects.
        """
        if self.space is None:
            return {}
        # Building parameters
        bx, bz = 5.0, 5.0
        bw, bd, bh = 6.0, 6.0, 8.0
        wt = 1.0

        wall_ids = self.build_demo_building(
            x=bx, z=bz, width=bw, depth=bd,
            height=bh, wall_thickness=wt, material='silicon',
        )
        fluid_id = self.fill_building_with_water(
            x=bx, z=bz, width=bw, depth=bd, height=bh,
            wall_thickness=wt, fill_height=5,
        )
        # Spawn a heavy iron block above the building centre
        block_id = self.spawn_block(
            material='iron',
            x=bx + bw/2 - 0.5,
            y=bh + 5.0,
            z=bz + bd/2 - 0.5,
        )
        return {
            'wall_ids': wall_ids,
            'fluid_body_id': fluid_id,
            'projectile_block_id': block_id,
            'building': {'x': bx, 'z': bz, 'width': bw, 'depth': bd, 'height': bh},
        }

    def get_ubp_report(self, entity_id: int) -> dict:
        """
        Return detailed UBP mechanics info for a specific entity.
        v5.0-ubp6.3.1: Updated to use current UBPEntityV3 API.
        """
        if self.space is None:
            return {"error": "Space not initialized"}

        # Use the correct _entities dict from UBPSpaceV3
        entity = self.space._entities.get(entity_id)
        if not entity:
            return {"error": f"Entity {entity_id} not found"}

        from ubp_mechanics_v4 import UBP_MECHANICS
        from ubp_engine_substrate import calculate_symmetry_tax, calculate_nrci

        # Build the report using the correct entity attributes
        nrci_val = float(entity.nrci)
        health = 'STABLE'
        if entity.nrci_state is not None:
            nrci_val = entity.nrci_state.nrci
            health = entity.nrci_state.health_status
        elif nrci_val < 0.60:
            health = 'STRESSED'

        # Leech address (v6.3.1: 3-bit octant)
        addr = UBP_MECHANICS.get_address(entity.golay_vector)

        info = {
            "id": entity.entity_id,
            "label": entity.label,
            "material": entity.material.name,
            "nrci": round(nrci_val, 6),
            "symmetry_tax": float(entity.symmetry_tax),
            "construction_tax": float(entity.construction_tax),
            "health": health,
            "is_dissolving": entity.is_dissolving,
            "is_static": entity.is_static,
            "lattice_cell": list(entity.lattice_cell),
            "leech_octant": addr.octant,
            "golay_vector": entity.golay_vector,
            "mass": float(entity.mass),
            "inertia": float(entity.inertia),
            "moment_of_inertia": float(entity.moment_of_inertia),
            "position": entity.position.to_dict(),
            "velocity": entity.velocity.to_dict(),
            "temperature_K": entity.thermal.temperature_K,
            "sigma_mass": UBP_MECHANICS.sigma_mass(float(entity.mass)),
        }

        return info

    def set_temperature(self, temperature_K: float) -> None:
        if self.space is not None:
            self.space.set_ambient_temperature(temperature_K)


sim = UBPSimulationManager()


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        try:
            await websocket.send_json({"type": "state", "data": sim.get_state()})
        except Exception as e:
            logger.error(f"Error sending initial state: {e}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: Dict[str, Any]):
        message = json.dumps({"type": "state", "data": data})
        dead = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                dead.append(connection)
        for d in dead:
            self.disconnect(d)


manager = ConnectionManager()


async def simulation_loop():
    broadcast_every = 2
    tick_interval = 1.0 / 60.0
    while True:
        loop_start = time.monotonic()
        sim.step()
        if sim.space is not None and sim.space.tick % broadcast_every == 0:
            try:
                state = sim.get_state()
                await manager.broadcast(state)
            except Exception as e:
                logger.error(f"Broadcast error: {e}")
        elapsed = time.monotonic() - loop_start
        sleep_time = max(0.0, tick_interval - elapsed)
        await asyncio.sleep(sleep_time)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(simulation_loop())
    logger.info("UBP Digital Twin v4.0 started — simulation loop running at 60 Hz")


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    print(f"[Python] New WebSocket connection request from {websocket.client}")
    await manager.connect(websocket)
    print(f"[Python] WebSocket connection accepted")
    try:
        while True:
            data = await websocket.receive_text()
            print(f"[Python] Received WebSocket message: {data[:100]}...")
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                print(f"[Python] JSON Decode Error: {data}")
                continue

            if msg.get("type") != "command":
                continue

            cmd = msg.get("command", "")
            print(f"[Python] Processing command: {cmd}")

            if cmd == "play":
                sim.is_running = True
                logger.info("Simulation started")

            elif cmd == "pause":
                sim.is_running = False
                logger.info("Simulation paused")

            elif cmd == "reset":
                sim.reset()
                state = sim.get_state()
                await manager.broadcast(state)
                logger.info("Simulation reset")

            elif cmd == "spawn_block":
                mat = msg.get("material", "iron")
                x = float(msg.get("x", 0))
                y = float(msg.get("y", 10))
                z = float(msg.get("z", 0))
                eid = sim.spawn_block(mat, x, y, z)
                logger.info(f"Spawned {mat} block (id={eid}) at ({x},{y},{z})")

            elif cmd == "spawn_block_at_grid":
                grid_x = int(msg.get("grid_x", 0))
                grid_z = int(msg.get("grid_z", 0))
                mat = msg.get("material", "iron")
                y = float(msg.get("y", 15.0))
                cell_size = float(msg.get("cell_size", 1.0))
                eid = sim.spawn_block_at_grid(grid_x, grid_z, mat, y, cell_size)
                logger.info(f"Spawned {mat} block at grid ({grid_x},{grid_z}) -> entity {eid}")

            elif cmd == "spawn_fluid":
                x = float(msg.get("x", 0))
                y = float(msg.get("y", 5))
                z = float(msg.get("z", 0))
                bid = sim.spawn_fluid(x, y, z)
                logger.info(f"Spawned fluid pool (body_id={bid}) at ({x},{y},{z})")

            elif cmd == "delete_fluid":
                body_id = msg.get("body_id", None)
                if body_id is not None:
                    body_id = int(body_id)
                count = sim.delete_fluid(body_id)
                logger.info(f"Deleted {count} fluid body/bodies (body_id={body_id})")

            elif cmd == "push":
                eid = int(msg.get("entity_id", 0))
                fx = float(msg.get("fx", 0))
                fy = float(msg.get("fy", 0))
                fz = float(msg.get("fz", 0))
                ok = sim.push_entity(eid, fx, fy, fz)
                logger.info(f"Push entity {eid} ({fx},{fy},{fz}) -> {ok}")

            elif cmd == "pull":
                eid = int(msg.get("entity_id", 0))
                fx = float(msg.get("fx", 0))
                fy = float(msg.get("fy", 0))
                fz = float(msg.get("fz", 0))
                ok = sim.pull_entity(eid, fx, fy, fz)
                logger.info(f"Pull entity {eid} ({fx},{fy},{fz}) -> {ok}")

            elif cmd == "set_temperature":
                temp_K = float(msg.get("temperature_K", 293.15))
                sim.set_temperature(temp_K)
                logger.info(f"Ambient temperature set to {temp_K} K")

            elif cmd == "delete_entity":
                eid = int(msg.get("entity_id", 0))
                ok = sim.delete_entity(eid)
                logger.info(f"Delete entity {eid} -> {ok}")

            elif cmd == "add_lever":
                mat = msg.get("material", "steel")
                x = float(msg.get("x", 5))
                y = float(msg.get("y", 1.2))
                z = float(msg.get("z", 0))
                length = float(msg.get("length", 8))
                eid = sim.spawn_lever(mat, x, y, z, length)
                logger.info(f"Added lever (id={eid}) at ({x},{y},{z}) length={length}")

            elif cmd == "set_lever_angle":
                lever_id = int(msg.get("lever_id", 0))
                angle_deg = float(msg.get("angle_deg", 0))
                ok = sim.set_lever_angle(lever_id, angle_deg)
                logger.info(f"Set lever {lever_id} angle to {angle_deg}° -> {ok}")

            elif cmd == "push_lever":
                lever_id = int(msg.get("lever_id", 0))
                fx = float(msg.get("fx", 0))
                fy = float(msg.get("fy", 0))
                at_x = float(msg.get("at_x", 0))
                ok = sim.push_lever(lever_id, fx, fy, at_x)
                logger.info(f"Push lever {lever_id} force=({fx},{fy}) at_x={at_x} -> {ok}")

            elif cmd == "spawn_wall":
                x = float(msg.get("x", 0))
                y = float(msg.get("y", 1))
                z = float(msg.get("z", 0))
                w = float(msg.get("width", 1))
                h = float(msg.get("height", 5))
                d = float(msg.get("depth", 1))
                mat = msg.get("material", "silicon")
                eid = sim.spawn_wall(x, y, z, w, h, d, mat)
                logger.info(f"Spawned wall (id={eid}) at ({x},{y},{z}) {w}x{h}x{d}")

            elif cmd == "build_demo_building":
                x = float(msg.get("x", 5))
                z = float(msg.get("z", 5))
                w = float(msg.get("width", 6))
                d = float(msg.get("depth", 6))
                h = float(msg.get("height", 8))
                wt = float(msg.get("wall_thickness", 1))
                mat = msg.get("material", "silicon")
                wall_ids = sim.build_demo_building(x, z, w, d, h, wt, mat)
                logger.info(f"Built demo building: {len(wall_ids)} walls")

            elif cmd == "fill_building_with_water":
                x = float(msg.get("x", 5))
                z = float(msg.get("z", 5))
                w = float(msg.get("width", 6))
                d = float(msg.get("depth", 6))
                h = float(msg.get("height", 8))
                wt = float(msg.get("wall_thickness", 1))
                fh = int(msg.get("fill_height", 3))
                bid = sim.fill_building_with_water(x, z, w, d, h, wt, fh)
                logger.info(f"Filled building with water (body_id={bid})")

            elif cmd == "demo_displacement":
                result = sim.run_displacement_demo()
                state = sim.get_state()
                await manager.broadcast(state)
                logger.info(f"Displacement demo set up: {result}")
                continue  # Already broadcast

            elif cmd == "spawn_block_at_grid":
                gx = int(msg.get("grid_x", 0))
                gz = int(msg.get("grid_z", 0))
                mat = msg.get("material", "silicon")
                y = float(msg.get("y", 1.0))
                cs = float(msg.get("cell_size", 1.0))
                eid = sim.spawn_block_at_grid(gx, gz, mat, y, cs)
                logger.info(f"Spawned block at grid ({gx},{gz}) -> {eid}")

            elif cmd == "ubp_report":
                eid = int(msg.get("entity_id", 0))
                report = sim.get_ubp_report(eid)
                await websocket.send_json({"type": "report", "entity_id": eid, "report": report})
                continue

            # Broadcast updated state after any command
            state = sim.get_state()
            await manager.broadcast(state)

    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/state")
async def get_state():
    return JSONResponse(content=sim.get_state())


@app.get("/health")
async def get_root_health():
    return JSONResponse(content={"status": "ok", "server": "fastapi"})


@app.get("/api/health")
async def get_health():
    return JSONResponse(content={"status": "ok", "version": "4.0"})


@app.get("/substrate")
async def get_substrate():
    return JSONResponse(content=sim.substrate.validate())


@app.get("/mechanics")
async def get_mechanics():
    """Return UBP v6.3.1 mechanics system status and constants."""
    try:
        from ubp_mechanics_v4 import UBP_MECHANICS, PHI_VEC, PHI_ORBIT_PERIOD, SIGMA
        from fractions import Fraction
        return JSONResponse(content={
            'available': True,
            'version': '5.0-ubp6.3.1',
            'constants': {
                'Y': round(float(UBP_MECHANICS.Y), 10),
                'Y_inv': round(float(UBP_MECHANICS.Y_INV), 10),
                'SINK_L': round(float(UBP_MECHANICS.SINK_L), 10),
                'KISSING': UBP_MECHANICS.KISSING,
                'SIGMA': round(float(UBP_MECHANICS.SIGMA), 6),
                'PHI_ORBIT_PERIOD': PHI_ORBIT_PERIOD,
                'NRCI_NOISE_FLOOR': UBP_MECHANICS.NRCI_NOISE_FLOOR,
                'NRCI_DISSOLUTION_THRESHOLD': UBP_MECHANICS.NRCI_DISSOLUTION_THRESHOLD,
            },
            'phi_vector': PHI_VEC,
            'laws': [
                'LAW_PHI_ORBIT_1953',
                'LAW_13D_SINK_001',
                'LAW_TOPOLOGICAL_BUFFER_001',
                'LAW_KISSING_EXPANSION_001',
                'LAW_HYBRID_STEREOSCOPY_002',
                'LAW_GEO_FOLD_001',
                'LAW_VOLUMETRIC_REBATE_001',
                'LAW_TGIC_9NEIGHBOR_001',
                'LAW_SYNTHESIS_SUPERPOSITION_001',
                'LAW_DOMAIN_PIVOT_001',
            ],
            'v6_3_1_changes': [
                'fold24_to3: recursive XOR fold (3 bits, not 3 octets)',
                'xor_interact: Additive Superposition + Phenomenal Collapse',
                'NRCI: Sink Leakage rebate applied (10/(10+tax*(1-L)))',
                'Volumetric Rebate: T_adj = T_base*(1-C/13)',
                'Domain Pivot: Bit 12 (index 11) encodes Phenomenal/Noumenal',
                'TGIC 9-neighbor overheating pressure in space step loop',
                'Collision restitution: Synthesis Superposition (not XOR)',
                'Lever torque: Topological Resistance + Hamming friction',
                'Fluid pressure: NRCI-modulated stiffness',
            ],
        })
    except ImportError:
        return JSONResponse(content={'available': False, 'version': 'fallback'})


@app.get("/engine_test")
async def get_engine_test():
    """
    Run the full UBP v6.3.1 engine validation suite.
    Tests all mechanics updated in v6.3.1.
    """
    try:
        from ubp_mechanics_v4 import UBP_MECHANICS, SINK_L
        from ubp_engine_substrate import (
            vector_from_math_dna, calculate_nrci, calculate_symmetry_tax,
            xor_interact, validate_substrate, Y_CONSTANT
        )
        from ubp_core_v5_3_merged import BinaryLinearAlgebra, LEECH_ENGINE
        from ubp_tgic_engine import TGICInteractionEngine
        from fractions import Fraction

        tests = {}
        all_pass = True

        # TEST 1: Phi-Orbit Tick with Sink Leakage rebate
        iron_vec = vector_from_math_dna('UBP_MATERIAL|Fe26x1|phase=solid')
        copper_vec = vector_from_math_dna('UBP_MATERIAL|Cu29x1|phase=solid')
        iv, inrci = UBP_MECHANICS.tick(iron_vec)
        cv, cnrci = UBP_MECHANICS.tick(copper_vec)
        phi_pass = len(iv) == 24 and 0.0 < inrci <= 1.0
        tests['phi_orbit_tick'] = {'pass': phi_pass, 'iron_nrci': round(inrci, 6), 'copper_nrci': round(cnrci, 6)}
        all_pass = all_pass and phi_pass

        # TEST 2: Synthesis Superposition (Additive, not XOR)
        synth_vec = xor_interact(iron_vec, copper_vec)
        synth_nrci = float(calculate_nrci(synth_vec))
        synth_pass = len(synth_vec) == 24 and 0.0 < synth_nrci <= 1.0
        tests['synthesis_superposition'] = {'pass': synth_pass, 'synth_nrci': round(synth_nrci, 6)}
        all_pass = all_pass and synth_pass

        # TEST 3: fold24_to3 returns 3 bits
        folded = BinaryLinearAlgebra.fold24_to3(iron_vec)
        fold_pass = len(folded) == 3 and all(b in (0, 1) for b in folded)
        tests['fold24_to3_binary'] = {'pass': fold_pass, 'folded': list(folded)}
        all_pass = all_pass and fold_pass

        # TEST 4: Leech Address octant 0-7
        addr = UBP_MECHANICS.get_address(iron_vec)
        addr_pass = 0 <= addr.octant <= 7
        tests['leech_address_octant'] = {'pass': addr_pass, 'octant': addr.octant}
        all_pass = all_pass and addr_pass

        # TEST 5: Volumetric Rebate reduces tax
        base_tax = LEECH_ENGINE.calculate_symmetry_tax(iron_vec)
        rebate_tax = LEECH_ENGINE.calculate_symmetry_tax(iron_vec, compactness=Fraction(1, 2))
        rebate_pass = rebate_tax < base_tax
        tests['volumetric_rebate'] = {'pass': rebate_pass, 'base': float(base_tax), 'rebated': float(rebate_tax)}
        all_pass = all_pass and rebate_pass

        # TEST 6: Domain Pivot (Phenomenal vs Noumenal)
        noumen_vec = vector_from_math_dna('MATH_CONSTANT|pi')
        domain_pass = iron_vec[11] == 1 and noumen_vec[11] == 0
        tests['domain_pivot'] = {'pass': domain_pass, 'phenom_bit12': iron_vec[11], 'noumen_bit12': noumen_vec[11]}
        all_pass = all_pass and domain_pass

        # TEST 7: Synthesis Collision Event
        syn_result = UBP_MECHANICS.collide(iron_vec, copper_vec, nrci_a=0.7, nrci_b=0.65)
        collision_pass = hasattr(syn_result, 'event_type') and syn_result.event_type in ('ELASTIC', 'DAMAGE', 'DISSOLUTION')
        tests['synthesis_collision'] = {'pass': collision_pass, 'event_type': syn_result.event_type if collision_pass else 'ERROR'}
        all_pass = all_pass and collision_pass

        # TEST 8: Sink Leakage L is small positive
        sink_l_val = float(SINK_L)
        sink_pass = 0.0 < sink_l_val < 0.1
        tests['sink_leakage'] = {'pass': sink_pass, 'L': sink_l_val}
        all_pass = all_pass and sink_pass

        # TEST 9: Substrate validation
        substrate_report = validate_substrate()
        substrate_pass = substrate_report.get('overall') in ('GREEN', 'YELLOW')
        tests['substrate_validation'] = {'pass': substrate_pass, 'overall': substrate_report.get('overall')}
        all_pass = all_pass and substrate_pass

        # TEST 10: TGIC 9-neighbor overheating
        tgic = TGICInteractionEngine()
        pressure = tgic.constraints.check_9_neighbor_limit(iron_vec, [iron_vec] * 12)
        tgic_pass = float(pressure) > 0.0
        tests['tgic_9neighbor'] = {'pass': tgic_pass, 'pressure': float(pressure)}
        all_pass = all_pass and tgic_pass

        return JSONResponse(content={
            'pass': all_pass,
            'ubp_version': 'v6.3.1',
            'engine_version': '5.0-ubp6.3.1',
            'tests': tests,
            'tests_passed': sum(1 for t in tests.values() if t.get('pass')),
            'tests_total': len(tests),
            'message': 'All UBP v6.3.1 mechanics validated' if all_pass else 'Some tests failed',
        })
    except Exception as e:
        import traceback
        return JSONResponse(content={'pass': False, 'error': str(e), 'traceback': traceback.format_exc()}, status_code=500)


class CommandRequest(BaseModel):
    command: str
    material: Optional[str] = "iron"
    x: Optional[float] = 0.0
    y: Optional[float] = 10.0
    z: Optional[float] = 0.0
    entity_id: Optional[int] = None
    lever_id: Optional[int] = None
    body_id: Optional[int] = None
    fx: Optional[float] = 0.0
    fy: Optional[float] = 0.0
    fz: Optional[float] = 0.0
    at_x: Optional[float] = 0.0
    temperature_K: Optional[float] = 293.15
    length: Optional[float] = 8.0
    width: Optional[float] = 1.0
    height: Optional[float] = 5.0
    depth: Optional[float] = 1.0
    wall_thickness: Optional[float] = 1.0
    fill_height: Optional[int] = 3
    grid_x: Optional[int] = 0
    grid_z: Optional[int] = 0
    cell_size: Optional[float] = 1.0
    angle_deg: Optional[float] = 0.0


@app.post("/command")
async def post_command(req: CommandRequest):
    cmd = req.command

    if cmd == "play":
        sim.is_running = True
    elif cmd == "pause":
        sim.is_running = False
    elif cmd == "reset":
        sim.reset()
    elif cmd == "spawn_block":
        eid = sim.spawn_block(req.material, req.x, req.y, req.z)
        return JSONResponse(content={"ok": True, "entity_id": eid})
    elif cmd == "spawn_block_at_grid":
        eid = sim.spawn_block_at_grid(req.grid_x, req.grid_z, req.material, req.y, req.cell_size)
        return JSONResponse(content={"ok": True, "entity_id": eid})
    elif cmd == "spawn_fluid":
        bid = sim.spawn_fluid(req.x, req.y, req.z)
        return JSONResponse(content={"ok": True, "body_id": bid})
    elif cmd == "delete_fluid":
        count = sim.delete_fluid(req.body_id)
        return JSONResponse(content={"ok": True, "deleted": count})
    elif cmd == "push" and req.entity_id is not None:
        ok = sim.push_entity(req.entity_id, req.fx, req.fy, req.fz)
        return JSONResponse(content={"ok": ok})
    elif cmd == "pull" and req.entity_id is not None:
        ok = sim.pull_entity(req.entity_id, req.fx, req.fy, req.fz)
        return JSONResponse(content={"ok": ok})
    elif cmd == "set_temperature":
        sim.set_temperature(req.temperature_K)
    elif cmd == "delete_entity" and req.entity_id is not None:
        ok = sim.delete_entity(req.entity_id)
        return JSONResponse(content={"ok": ok})
    elif cmd == "add_lever":
        eid = sim.spawn_lever(req.material, req.x, req.y, req.z, req.length or 8.0)
        return JSONResponse(content={"ok": True, "entity_id": eid})
    elif cmd == "set_lever_angle" and req.lever_id is not None:
        ok = sim.set_lever_angle(req.lever_id, req.angle_deg)
        return JSONResponse(content={"ok": ok})
    elif cmd == "push_lever" and req.lever_id is not None:
        ok = sim.push_lever(req.lever_id, req.fx, req.fy, req.at_x)
        return JSONResponse(content={"ok": ok})
    elif cmd == "spawn_wall":
        eid = sim.spawn_wall(req.x, req.y, req.z, req.width, req.height, req.depth, req.material)
        return JSONResponse(content={"ok": True, "entity_id": eid})
    elif cmd == "build_demo_building":
        wall_ids = sim.build_demo_building(
            req.x, req.z, req.width, req.depth, req.height, req.wall_thickness, req.material
        )
        return JSONResponse(content={"ok": True, "wall_ids": wall_ids})
    elif cmd == "fill_building_with_water":
        bid = sim.fill_building_with_water(
            req.x, req.z, req.width, req.depth, req.height, req.wall_thickness, req.fill_height
        )
        return JSONResponse(content={"ok": True, "body_id": bid})
    elif cmd == "ubp_report" and req.entity_id is not None:
        report = sim.get_ubp_report(req.entity_id)
        return JSONResponse(content={"ok": True, "report": report})
    elif cmd == "demo_displacement":
        result = sim.run_displacement_demo()
        return JSONResponse(content={"ok": True, **result})
    else:
        return JSONResponse(content={"ok": False, "error": f"Unknown command: {cmd}"}, status_code=400)

    return JSONResponse(content={"ok": True})


_DIST_DIR = os.path.join(os.path.dirname(__file__), "dist")
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

if os.path.isdir(os.path.join(_DIST_DIR, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(_DIST_DIR, "assets")), name="assets")


@app.get("/")
async def serve_root():
    for candidate in [
        os.path.join(_DIST_DIR, "index.html"),
        os.path.join(_STATIC_DIR, "index.html"),
        os.path.join(os.path.dirname(__file__), "index.html"),
    ]:
        if os.path.isfile(candidate):
            return FileResponse(candidate)
    return JSONResponse(content={"error": "Frontend not built. Run: npm run build"}, status_code=503)


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    for base in [_DIST_DIR, _STATIC_DIR]:
        candidate = os.path.join(base, full_path)
        if os.path.isfile(candidate):
            return FileResponse(candidate)
    for candidate in [
        os.path.join(_DIST_DIR, "index.html"),
        os.path.join(_STATIC_DIR, "index.html"),
    ]:
        if os.path.isfile(candidate):
            return FileResponse(candidate)
    return JSONResponse(content={"error": "Not found"}, status_code=404)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
