import sys
import json
import time
import logging
import threading
from decimal import Decimal

from ubp_engine_substrate import Y_CONSTANT
from ubp_entity_v3 import EntityFactoryV3, UBPEntityV3, Position, D
from ubp_fluid_v3 import FluidBodyV3
from ubp_materials import AmbientEnvironment

# Configure logging to stderr so it doesn't interfere with stdout JSON
logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logger = logging.getLogger("ubp_bridge")

class UBPSimulation:
    def __init__(self):
        self.entities = []
        self.fluid = FluidBodyV3(material_name='water')
        self.ambient = AmbientEnvironment()
        
        self.tick_count = 0
        self.is_running = False
        self.space_bounds = (-10.0, 10.0, 0.0, 20.0, -10.0, 10.0)
        self.lock = threading.RLock()
        
        self.reset()

    def reset(self):
        with self.lock:
            self.entities.clear()
            self.fluid.particles.clear()
            self.tick_count = 0
            
            floor = EntityFactoryV3.make_floor(
                label="Floor",
                material_name='iron',
                width=20.0,
                depth=20.0
            )
            self.entities.append(floor)
            
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
            
            self.fluid.emit_pool(origin_x=-1, origin_y=1, origin_z=-1, width=4, height=4, depth=4)

    def step(self):
        with self.lock:
            if not self.is_running:
                return
                
            self.tick_count += 1
            
            from ubp_entity_v3 import to_decimal
            g_per_tick = Decimal('9.81') / Decimal('3600') * to_decimal(Y_CONSTANT)
            
            for entity in self.entities:
                if entity.is_static:
                    continue
                    
                entity.velocity.vy -= g_per_tick
                
                entity.position.x += entity.velocity.vx
                entity.position.y += entity.velocity.vy
                entity.position.z += entity.velocity.vz
                
                if entity.position.y < Decimal('0.5'):
                    entity.position.y = Decimal('0.5')
                    entity.velocity.vy = -entity.velocity.vy * Decimal('0.5')
                    entity.velocity.vx *= Decimal('0.9')
                    entity.velocity.vz *= Decimal('0.9')

            self.fluid.step(
                solid_entities=self.entities,
                space_bounds=self.space_bounds,
                ambient_temperature_ubp=float(self.ambient.temperature_ubp)
            )

    def get_state(self):
        with self.lock:
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

def main():
    sim = UBPSimulation()
    
    # Send initial state
    print(json.dumps({"type": "state", "data": sim.get_state()}))
    sys.stdout.flush()
    
    import threading
    
    # Thread to read commands from stdin
    def read_commands():
        for line in sys.stdin:
            try:
                msg = json.loads(line)
                if msg.get("type") == "command":
                    cmd = msg.get("command")
                    with sim.lock:
                        if cmd == "play":
                            sim.is_running = True
                        elif cmd == "pause":
                            sim.is_running = False
                        elif cmd == "reset":
                            sim.reset()
                            print(json.dumps({"type": "state", "data": sim.get_state()}))
                            sys.stdout.flush()
                        elif cmd == "spawn_block":
                            mat = msg.get("material", "iron")
                            x = msg.get("x", 0)
                            y = msg.get("y", 10)
                            z = msg.get("z", 0)
                            block = EntityFactoryV3.make_block(
                                label=f"Block_{sim.tick_count}",
                                material_name=mat,
                                position=Position(D(str(x)), D(str(y)), D(str(z)))
                            )
                            sim.entities.append(block)
                            print(json.dumps({"type": "state", "data": sim.get_state()}))
                            sys.stdout.flush()
                        elif cmd == "spawn_fluid":
                            sim.fluid.emit_pool(origin_x=0, origin_y=5, origin_z=0, width=4, height=4, depth=4)
                            print(json.dumps({"type": "state", "data": sim.get_state()}))
                            sys.stdout.flush()
            except Exception as e:
                logger.error(f"Error parsing command: {e}")

    t = threading.Thread(target=read_commands, daemon=True)
    t.start()
    
    # Main simulation loop
    while True:
        if sim.is_running:
            sim.step()
            print(json.dumps({"type": "state", "data": sim.get_state()}))
            sys.stdout.flush()
        time.sleep(1/60)

if __name__ == "__main__":
    main()
