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


from ubp_engine_substrate import Y_CONSTANT, UBPEngineSubstrate
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
                    block = self.space.spawn_block_at_grid(grid_x, grid_z, mat, y, cell_size)
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
                    self.space.rigid_body.push_lever(lever_id, fx, fy, at_x)
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
                        from ubp_mechanics_v4 import UBP_MECHANICS
                        player_vec = [0,0,1,0,0,1,1,1,0,0,1,0,1,0,1,0,1,0,1,1,1,1,0,0]
                        wall_vec   = [1,1,0,1,1,0,1,0,1,1,1,0,1,1,1,1,1,1,0,1,0,0,0,1]
                        results = []
                        pv, wv = list(player_vec), list(wall_vec)
                        for i in range(5):
                            pv, pnrci = UBP_MECHANICS.tick(pv)
                            wv, wnrci = UBP_MECHANICS.tick(wv)
                            results.append({"tick": i + 1, "Player": float(pnrci), "Wall": float(wnrci)})
                        print(_dumps({
                            "type": "engine_test_result",
                            "req_id": req_id,
                            "pass": True,
                            "ticks": results,
                            "message": "Phi-Orbit sequence computed successfully",
                        }))
                    except Exception as e:
                        print(_dumps({
                            "type": "engine_test_result",
                            "req_id": req_id,
                            "pass": False,
                            "error": str(e),
                        }))
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