"""
================================================================================
UBP SERVER v3.0 — FastAPI Backend
================================================================================
Serves the UBP Digital Twin simulation state via WebSockets and HTTP.

This server uses UBPSpaceV3 as the single authoritative physics simulation.
UBPSpaceV3 integrates:
  - UBP Physics Engine V3 (Equivalence Principle gravity, UBP-derived constants)
  - Composite Material System (KB element aggregates)
  - Thermal Properties (temperature, heat transfer)
  - Rigid Body / Lever mechanics (Topological Torque)
  - UBP-SPH Fluid simulation (Kissing/Sink-derived constants)

Architecture:
  - Single Python FastAPI process
  - Serves the React/Three.js frontend from /dist
  - WebSocket /ws for real-time state streaming
  - HTTP GET /state for current state snapshot
  - HTTP POST /command for control commands
  - Simulation loop runs at 60 ticks/second in background
================================================================================
"""

import asyncio
import json
import logging
import os
import time
from decimal import Decimal
from typing import Dict, List, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# UBP Engine imports — all from the validated V3 modules
from ubp_engine_substrate import UBPEngineSubstrate
from ubp_entity_v3 import EntityFactoryV3, UBPEntityV3, Position, D
from ubp_space_v3 import UBPSpaceV3
from ubp_fluid_v3 import FluidBodyV3

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ubp_server")

# ---------------------------------------------------------------------------
# FASTAPI APP
# ---------------------------------------------------------------------------

app = FastAPI(title="UBP Digital Twin v3.0")

# Allow CORS for development (Vite dev server on different port)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# SIMULATION WRAPPER
# ---------------------------------------------------------------------------

class UBPSimulationManager:
    """
    Manages the UBPSpaceV3 simulation instance and provides the WebSocket
    state broadcasting interface.

    The UBPSpaceV3 is the single source of truth for all physics.
    This class only handles:
      - Lifecycle (reset, play, pause)
      - Command routing (spawn, push, pull, temperature)
      - State serialisation for the frontend
    """

    def __init__(self):
        self.substrate = UBPEngineSubstrate()
        self.space: Optional[UBPSpaceV3] = None
        self.is_running: bool = False
        self._entity_counter: int = 0
        self.reset()

    def reset(self):
        """Reset the simulation to its default starting state."""
        self.is_running = False
        self._entity_counter = 0

        # Create a fresh 20×20×20 space at room temperature
        self.space = UBPSpaceV3(
            width=20.0,
            height=20.0,
            depth=20.0,
            temperature_K=293.15,
            include_floor=True,
        )

        # Add two solid blocks at different heights and materials
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

        # Add a lever (steel bar, 8 units long, pivoted at centre)
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
        logger.info(f"Simulation reset: {len(self.space._entity_list)} entities, "
                    f"{sum(len(f.particles) for f in self.space._fluid_bodies)} fluid particles")

    def step(self):
        """Advance the simulation by one tick."""
        if self.is_running and self.space is not None:
            self.space.step()

    def get_state(self) -> Dict[str, Any]:
        """Return the current simulation state for the frontend."""
        if self.space is None:
            return {'tick': 0, 'is_running': False, 'entities': [], 'fluid_particles': []}
        state = self.space.get_threejs_state()
        state['is_running'] = self.is_running
        return state

    def spawn_block(self, material: str, x: float, y: float, z: float) -> Optional[int]:
        """Spawn a new block entity at the given position."""
        if self.space is None:
            return None
        self._entity_counter += 1
        label = f"{material.capitalize()}_{self._entity_counter}"
        block = EntityFactoryV3.make_block(
            label=label,
            material_name=material,
            position=Position(D(str(x)), D(str(y)), D(str(z))),
        )
        self.space.add_entity(block)
        return block.entity_id

    def spawn_fluid(self, x: float, y: float, z: float) -> None:
        """Spawn a new fluid pool at the given position."""
        if self.space is None:
            return
        fluid = FluidBodyV3(material_name='water')
        fluid.emit_pool(origin_x=x, origin_y=y, origin_z=z, width=4, height=3, depth=4)
        self.space.add_fluid(fluid)

    def push_entity(self, entity_id: int, fx: float, fy: float, fz: float) -> bool:
        """Apply a push force to an entity."""
        if self.space is None:
            return False
        return self.space.push_entity(entity_id, fx, fy, fz)

    def pull_entity(self, entity_id: int, fx: float, fy: float, fz: float) -> bool:
        """Apply a pull force to an entity."""
        if self.space is None:
            return False
        return self.space.pull_entity(entity_id, fx, fy, fz)

    def set_temperature(self, temperature_K: float) -> None:
        """Change the ambient temperature."""
        if self.space is not None:
            self.space.set_ambient_temperature(temperature_K)


# Global simulation manager
sim = UBPSimulationManager()

# ---------------------------------------------------------------------------
# WEBSOCKET CONNECTION MANAGER
# ---------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        # Send the current state immediately on connection
        try:
            await websocket.send_json({"type": "state", "data": sim.get_state()})
        except Exception as e:
            logger.error(f"Error sending initial state: {e}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, data: Dict[str, Any]):
        """Broadcast state to all connected clients."""
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

# ---------------------------------------------------------------------------
# BACKGROUND SIMULATION LOOP
# ---------------------------------------------------------------------------

async def simulation_loop():
    """
    Runs the UBP simulation at 60 ticks/second.
    Broadcasts state to all connected WebSocket clients at 30 fps
    (every 2 ticks) to avoid saturating the network.
    """
    broadcast_every = 2   # broadcast every N ticks
    tick_interval = 1.0 / 60.0

    while True:
        loop_start = time.monotonic()

        sim.step()

        # Broadcast at 30 fps
        if sim.space is not None and sim.space.tick % broadcast_every == 0:
            try:
                state = sim.get_state()
                await manager.broadcast(state)
            except Exception as e:
                logger.error(f"Broadcast error: {e}")

        # Maintain 60 Hz tick rate
        elapsed = time.monotonic() - loop_start
        sleep_time = max(0.0, tick_interval - elapsed)
        await asyncio.sleep(sleep_time)


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(simulation_loop())
    logger.info("UBP Digital Twin v3.0 started — simulation loop running at 60 Hz")


# ---------------------------------------------------------------------------
# WEBSOCKET ENDPOINT
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
            except json.JSONDecodeError:
                continue

            if msg.get("type") != "command":
                continue

            cmd = msg.get("command", "")

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

            elif cmd == "spawn_fluid":
                x = float(msg.get("x", 0))
                y = float(msg.get("y", 5))
                z = float(msg.get("z", 0))
                sim.spawn_fluid(x, y, z)
                logger.info(f"Spawned fluid pool at ({x},{y},{z})")

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

            # Broadcast updated state after any command
            state = sim.get_state()
            await manager.broadcast(state)

    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ---------------------------------------------------------------------------
# HTTP API ENDPOINTS
# ---------------------------------------------------------------------------

@app.get("/state")
async def get_state():
    """Return the current simulation state as JSON."""
    return JSONResponse(content=sim.get_state())


@app.get("/substrate")
async def get_substrate():
    """Return the UBP substrate validation report."""
    return JSONResponse(content=sim.substrate.validate())


class CommandRequest(BaseModel):
    command: str
    material: Optional[str] = "iron"
    x: Optional[float] = 0.0
    y: Optional[float] = 10.0
    z: Optional[float] = 0.0
    entity_id: Optional[int] = None
    fx: Optional[float] = 0.0
    fy: Optional[float] = 0.0
    fz: Optional[float] = 0.0
    temperature_K: Optional[float] = 293.15


@app.post("/command")
async def post_command(req: CommandRequest):
    """Execute a simulation command via HTTP POST."""
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
    elif cmd == "spawn_fluid":
        sim.spawn_fluid(req.x, req.y, req.z)
    elif cmd == "push" and req.entity_id is not None:
        ok = sim.push_entity(req.entity_id, req.fx, req.fy, req.fz)
        return JSONResponse(content={"ok": ok})
    elif cmd == "pull" and req.entity_id is not None:
        ok = sim.pull_entity(req.entity_id, req.fx, req.fy, req.fz)
        return JSONResponse(content={"ok": ok})
    elif cmd == "set_temperature":
        sim.set_temperature(req.temperature_K)
    else:
        return JSONResponse(content={"ok": False, "error": f"Unknown command: {cmd}"}, status_code=400)

    return JSONResponse(content={"ok": True})


# ---------------------------------------------------------------------------
# STATIC FILE SERVING (React/Three.js frontend)
# ---------------------------------------------------------------------------

# Serve the built React app from /dist
_DIST_DIR = os.path.join(os.path.dirname(__file__), "dist")
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

# Mount /assets for Vite build output
if os.path.isdir(os.path.join(_DIST_DIR, "assets")):
    app.mount("/assets", StaticFiles(directory=os.path.join(_DIST_DIR, "assets")), name="assets")


@app.get("/")
async def serve_root():
    """Serve the main frontend page."""
    # Try dist (production build) first, then static (development)
    for candidate in [
        os.path.join(_DIST_DIR, "index.html"),
        os.path.join(_STATIC_DIR, "index.html"),
        os.path.join(os.path.dirname(__file__), "index.html"),
    ]:
        if os.path.isfile(candidate):
            return FileResponse(candidate)
    return JSONResponse(
        content={"error": "Frontend not built. Run: npm run build"},
        status_code=503,
    )


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    """Serve static files from the dist directory, falling back to index.html."""
    # Try dist first
    for base in [_DIST_DIR, _STATIC_DIR]:
        candidate = os.path.join(base, full_path)
        if os.path.isfile(candidate):
            return FileResponse(candidate)
    # SPA fallback — serve index.html for all unknown routes
    for candidate in [
        os.path.join(_DIST_DIR, "index.html"),
        os.path.join(_STATIC_DIR, "index.html"),
    ]:
        if os.path.isfile(candidate):
            return FileResponse(candidate)
    return JSONResponse(content={"error": "Not found"}, status_code=404)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8765))
    logger.info(f"Starting UBP Digital Twin v3.0 on http://0.0.0.0:{port}")
    uvicorn.run("ubp_server_v3:app", host="0.0.0.0", port=port, log_level="info")
