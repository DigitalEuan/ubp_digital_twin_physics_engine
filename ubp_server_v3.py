"""
================================================================================
UBP SERVER v3.0 — FastAPI Backend
================================================================================
Serves the UBP Digital Twin simulation state via WebSockets and HTTP.
Integrates the UBP Engine Substrate, Entity System, and Fluid System.
================================================================================
"""

import asyncio
import json
import logging
from decimal import Decimal
from typing import Dict, List, Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ubp_engine_substrate import UBPEngineSubstrate
from ubp_entity_v3 import EntityFactoryV3, UBPEntityV3
from ubp_fluid_v3 import FluidBodyV3, AmbientEnvironment

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ubp_server")

app = FastAPI(title="UBP Digital Twin v3.0")

# ---------------------------------------------------------------------------
# SIMULATION STATE
# ---------------------------------------------------------------------------

class UBPSimulation:
    def __init__(self):
        self.substrate = UBPEngineSubstrate()
        self.entities: List[UBPEntityV3] = []
        self.fluid = FluidBodyV3(material_name='water')
        self.ambient = AmbientEnvironment()
        
        self.tick_count = 0
        self.is_running = False
        self.space_bounds = (-10.0, 10.0, 0.0, 20.0, -10.0, 10.0) # x_min, x_max, y_min, y_max, z_min, z_max
        
        # Initialize with some default entities
        self.reset()

    def reset(self):
        self.entities.clear()
        self.fluid.particles.clear()
        self.tick_count = 0
        
        # Add a floor
        floor = EntityFactoryV3.make_floor(
            label="Floor",
            material_name='iron',
            width=20.0,
            depth=20.0
        )
        self.entities.append(floor)
        
        # Add some blocks
        from ubp_entity_v3 import Position, D
        block1 = EntityFactoryV3.make_block(
            label="Block1",
            material_name='copper',
            position=Position(D('-2'), D('5'), D('0'))
        )
        block2 = EntityFactoryV3.make_block(
            label="Block2",
            material_name='aluminium',
            position=Position(D('2'), D('8'), D('0'))
        )
        self.entities.extend([block1, block2])
        
        # Add some fluid
        self.fluid.emit_pool(origin_x=-2, origin_y=1, origin_z=-2, width=8, height=4, depth=8)

    def step(self):
        if not self.is_running:
            return
            
        self.tick_count += 1
        
        # 1. Update solid entities (gravity, simple floor collision)
        # In a full engine, we'd use TGIC for relational gravity and full collision detection.
        # For this demo, we apply simple downward gravity and floor boundary.
        from ubp_entity_v3 import to_decimal
        g_per_tick = Decimal('9.81') / Decimal('3600') * to_decimal(self.substrate.Y_CONSTANT)
        
        for entity in self.entities:
            if entity.is_static:
                continue
                
            # Apply gravity
            entity.velocity.y -= g_per_tick
            
            # Integrate position
            entity.position.x += entity.velocity.x
            entity.position.y += entity.velocity.y
            entity.position.z += entity.velocity.z
            
            # Simple floor collision (y=0 is top of floor)
            if entity.position.y < Decimal('0.5'): # Assuming 1x1x1 block
                entity.position.y = Decimal('0.5')
                entity.velocity.y = -entity.velocity.y * Decimal('0.5') # Restitution
                
                # Apply friction
                entity.velocity.x *= Decimal('0.9')
                entity.velocity.z *= Decimal('0.9')

        # 2. Update fluid
        self.fluid.step(
            solid_entities=self.entities,
            space_bounds=self.space_bounds,
            ambient_temperature_ubp=float(self.ambient.temperature_ubp)
        )

    def get_state(self) -> Dict[str, Any]:
        return {
            'tick': self.tick_count,
            'is_running': self.is_running,
            'ambient': {
                'temperature_K': float(self.ambient.temperature_K),
                'pressure_ubp': float(self.ambient.pressure_ubp)
            },
            'entities': [e.to_threejs_state() for e in self.entities],
            'fluid': self.fluid.get_threejs_state()
        }

sim = UBPSimulation()

# ---------------------------------------------------------------------------
# WEBSOCKET MANAGER
# ---------------------------------------------------------------------------

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        # Send initial state
        await websocket.send_json({"type": "state", "data": sim.get_state()})

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error sending to websocket: {e}")

manager = ConnectionManager()

# ---------------------------------------------------------------------------
# BACKGROUND TASK
# ---------------------------------------------------------------------------

async def simulation_loop():
    """Runs the simulation loop at approximately 60Hz."""
    while True:
        if sim.is_running:
            sim.step()
            state = sim.get_state()
            await manager.broadcast(json.dumps({"type": "state", "data": state}))
        await asyncio.sleep(1/60)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(simulation_loop())

# ---------------------------------------------------------------------------
# API ENDPOINTS
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            msg = json.loads(data)
            
            if msg.get("type") == "command":
                cmd = msg.get("command")
                if cmd == "play":
                    sim.is_running = True
                elif cmd == "pause":
                    sim.is_running = False
                elif cmd == "reset":
                    sim.reset()
                    await manager.broadcast(json.dumps({"type": "state", "data": sim.get_state()}))
                elif cmd == "spawn_block":
                    mat = msg.get("material", "iron")
                    x = msg.get("x", 0)
                    y = msg.get("y", 10)
                    z = msg.get("z", 0)
                    from ubp_entity_v3 import Position, D
                    block = EntityFactoryV3.make_block(
                        label=f"Block_{sim.tick_count}",
                        material_name=mat,
                        position=Position(D(str(x)), D(str(y)), D(str(z)))
                    )
                    sim.entities.append(block)
                elif cmd == "spawn_fluid":
                    sim.fluid.emit_pool(origin_x=0, origin_y=5, origin_z=0, width=4, height=4, depth=4)
                    
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ---------------------------------------------------------------------------
# STATIC FILES
# ---------------------------------------------------------------------------

import os

@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    # If the file exists in dist, serve it directly
    file_path = os.path.join("dist", full_path)
    if os.path.isfile(file_path):
        return FileResponse(file_path)
    # Otherwise, serve index.html for SPA routing
    return FileResponse("dist/index.html")
