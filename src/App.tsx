import React, { useEffect, useState, useRef, useMemo } from 'react';
import { Canvas, useFrame } from '@react-three/fiber';
import { OrbitControls, Grid } from '@react-three/drei';
import * as THREE from 'three';
import { Play, Pause, RotateCcw, Box as BoxIcon, Droplet, Activity, Thermometer, Zap } from 'lucide-react';

// ---------------------------------------------------------------------------
// TYPES — exactly matching the Python backend's to_threejs_state() output
// ---------------------------------------------------------------------------

interface Vec3 {
  x: number;
  y: number;
  z: number;
}

interface EntityState {
  id: number;
  label: string;
  type: string;
  material: string;
  /** Position is the MIN-CORNER of the AABB (not the centre). */
  position: Vec3;
  /** Rotation in radians (from the physics engine). */
  rotation: Vec3;
  /** Size in world units (width, height, depth). */
  size: Vec3;
  colour: string;
  is_static: boolean;
  is_resting: boolean;
  mass: number;
  nrci: number;
  /** Temperature in Kelvin (UBP-derived). */
  temperature_K: number;
  velocity: Vec3;
}

interface FluidParticleState {
  id: number;
  type: string;
  material: string;
  position: Vec3;
  velocity: Vec3;
  density: number;
  colour: string;
  size: Vec3;
}

interface LeverConstraintState {
  lever_id: number;
  /** Angle in DEGREES from the backend — convert to radians for Three.js. */
  angle_deg: number;
  pivot: Vec3;
  angular_velocity: number;
  topological_cost: number;
}

interface SimulationState {
  tick: number;
  time_s: number;
  is_running: boolean;
  ambient: {
    temperature_K: number;
    temperature_ubp: number;
  };
  entities: EntityState[];
  fluid_particles: FluidParticleState[];
  lever_constraints: LeverConstraintState[];
  stats: {
    entity_count: number;
    fluid_particle_count: number;
    avg_tick_ms: number;
  };
}

// ---------------------------------------------------------------------------
// ENTITY MESH — Box centred at the AABB centre (position + size/2)
// ---------------------------------------------------------------------------

const EntityMesh = React.memo(({ data }: { data: EntityState }) => {
  // Backend sends min-corner position; Three.js Box is centred.
  // Offset by half-size in each axis to place correctly.
  const cx = data.position.x + data.size.x / 2;
  const cy = data.position.y + data.size.y / 2;
  const cz = data.position.z + data.size.z / 2;

  // Rotation is already in radians from the physics engine.
  const rx = data.rotation.x;
  const ry = data.rotation.y;
  const rz = data.rotation.z;

  // Parse colour — backend sends hex string
  const colour = data.colour || '#888888';

  // Floor gets a special semi-transparent material
  if (data.is_static) {
    return (
      <mesh position={[cx, cy, cz]} rotation={[rx, ry, rz]}>
        <boxGeometry args={[data.size.x, data.size.y, data.size.z]} />
        <meshStandardMaterial color={colour} transparent opacity={0.35} wireframe={false} />
      </mesh>
    );
  }

  return (
    <mesh position={[cx, cy, cz]} rotation={[rx, ry, rz]} castShadow receiveShadow>
      <boxGeometry args={[data.size.x, data.size.y, data.size.z]} />
      <meshStandardMaterial
        color={colour}
        roughness={0.6}
        metalness={data.material === 'iron' || data.material === 'steel' ? 0.8 : 0.3}
      />
    </mesh>
  );
});

// ---------------------------------------------------------------------------
// FLUID INSTANCED MESH — single draw call for all particles
// ---------------------------------------------------------------------------

const FluidParticles = React.memo(({ particles }: { particles: FluidParticleState[] }) => {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const count = particles.length;

  // Reuse matrix and colour objects
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const colour = useMemo(() => new THREE.Color(), []);

  useEffect(() => {
    if (!meshRef.current || count === 0) return;
    const mesh = meshRef.current;

    particles.forEach((p, i) => {
      dummy.position.set(p.position.x, p.position.y, p.position.z);
      const r = p.size.x;
      dummy.scale.set(r, r, r);
      dummy.updateMatrix();
      mesh.setMatrixAt(i, dummy.matrix);

      colour.set(p.colour || '#4169E1');
      mesh.setColorAt(i, colour);
    });

    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
  }, [particles, dummy, colour]);

  if (count === 0) return null;

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, count]} castShadow>
      <sphereGeometry args={[1, 8, 8]} />
      <meshStandardMaterial transparent opacity={0.75} roughness={0.1} metalness={0.0} />
    </instancedMesh>
  );
});

// ---------------------------------------------------------------------------
// LEVER VISUAL — rendered as a thin box rotated around its pivot
// ---------------------------------------------------------------------------

const LeverVisual = React.memo(({
  constraint,
  entity,
}: {
  constraint: LeverConstraintState;
  entity?: EntityState;
}) => {
  if (!entity) return null;

  // Convert angle from degrees to radians
  const angle_rad = (constraint.angle_deg * Math.PI) / 180.0;

  // The lever rotates around the Z-axis at the pivot point.
  // We render it as a box whose centre is at the entity's AABB centre,
  // but rotated around the pivot.
  const lx = entity.size.x;
  const ly = entity.size.y;
  const lz = entity.size.z;

  // Pivot in world space
  const px = constraint.pivot.x;
  const py = constraint.pivot.y;
  const pz = constraint.pivot.z;

  // Entity centre relative to pivot (before rotation)
  const ecx = entity.position.x + lx / 2 - px;
  const ecy = entity.position.y + ly / 2 - py;

  // Rotate the centre around the pivot
  const cos_a = Math.cos(angle_rad);
  const sin_a = Math.sin(angle_rad);
  const rcx = ecx * cos_a - ecy * sin_a + px;
  const rcy = ecx * sin_a + ecy * cos_a + py;

  return (
    <mesh position={[rcx, rcy, pz]} rotation={[0, 0, angle_rad]} castShadow>
      <boxGeometry args={[lx, ly, lz]} />
      <meshStandardMaterial color={entity.colour || '#888888'} roughness={0.4} metalness={0.7} />
    </mesh>
  );
});

// ---------------------------------------------------------------------------
// PIVOT MARKER — small sphere at the lever pivot point
// ---------------------------------------------------------------------------

const PivotMarker = ({ pivot }: { pivot: Vec3 }) => (
  <mesh position={[pivot.x, pivot.y, pivot.z]}>
    <sphereGeometry args={[0.15, 12, 12]} />
    <meshStandardMaterial color="#ff6600" emissive="#ff3300" emissiveIntensity={0.5} />
  </mesh>
);

// ---------------------------------------------------------------------------
// SCENE — assembles all visual components
// ---------------------------------------------------------------------------

const Scene = ({ state }: { state: SimulationState | null }) => {
  if (!state) return null;

  // Build a lookup from entity_id to entity for lever rendering
  const entityById = useMemo(() => {
    const map: Record<number, EntityState> = {};
    state.entities.forEach(e => { map[e.id] = e; });
    return map;
  }, [state.entities]);

  // Separate lever entities from regular entities
  const leverIds = new Set(state.lever_constraints.map(c => c.lever_id));

  return (
    <>
      {/* Lighting */}
      <ambientLight intensity={0.4} />
      <directionalLight
        position={[15, 25, 15]}
        intensity={1.2}
        castShadow
        shadow-mapSize={[2048, 2048]}
      />
      <pointLight position={[-10, 10, -10]} intensity={0.3} color="#4488ff" />

      {/* Ground grid */}
      <Grid
        args={[40, 40]}
        position={[10, 0, 10]}
        cellColor="#334155"
        sectionColor="#475569"
        fadeDistance={60}
        infiniteGrid={false}
      />

      {/* Regular entities (non-lever) */}
      {state.entities
        .filter(e => !leverIds.has(e.id))
        .map(entity => (
          <EntityMesh key={entity.id} data={entity} />
        ))}

      {/* Lever entities — rendered with rotation around pivot */}
      {state.lever_constraints.map(constraint => (
        <React.Fragment key={`lever-${constraint.lever_id}`}>
          <LeverVisual
            constraint={constraint}
            entity={entityById[constraint.lever_id]}
          />
          <PivotMarker pivot={constraint.pivot} />
        </React.Fragment>
      ))}

      {/* Fluid particles — single instanced draw call */}
      <FluidParticles particles={state.fluid_particles} />
    </>
  );
};

// ---------------------------------------------------------------------------
// CONNECTION STATUS INDICATOR
// ---------------------------------------------------------------------------

const ConnectionStatus = ({ connected }: { connected: boolean }) => (
  <div className={`flex items-center gap-2 text-xs font-mono px-3 py-1 rounded-full border ${
    connected
      ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400'
      : 'bg-red-500/10 border-red-500/30 text-red-400'
  }`}>
    <div className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-400 animate-pulse' : 'bg-red-400'}`} />
    {connected ? 'Connected' : 'Disconnected'}
  </div>
);

// ---------------------------------------------------------------------------
// ENTITY DATA CARD
// ---------------------------------------------------------------------------

const EntityCard = ({ entity }: { entity: EntityState }) => (
  <div className="bg-slate-900 p-3 rounded-lg border border-slate-700 text-xs font-mono space-y-1.5">
    <div className="flex justify-between items-center">
      <span className="font-bold text-slate-200">{entity.label}</span>
      <span
        className="text-indigo-400 px-1.5 py-0.5 rounded text-[10px]"
        style={{ backgroundColor: entity.colour + '22', color: entity.colour }}
      >
        {entity.material}
      </span>
    </div>
    <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-slate-400">
      <div>Mass: <span className="text-slate-300">{entity.mass.toFixed(3)}</span></div>
      <div>NRCI: <span className="text-slate-300">{entity.nrci.toFixed(4)}</span></div>
      <div>Temp: <span className="text-slate-300">{entity.temperature_K.toFixed(1)} K</span></div>
      <div>Y: <span className="text-slate-300">{entity.position.y.toFixed(3)}</span></div>
      <div>Vx: <span className="text-slate-300">{entity.velocity.x.toFixed(4)}</span></div>
      <div>Vy: <span className="text-slate-300">{entity.velocity.y.toFixed(4)}</span></div>
    </div>
    <div className="flex gap-2 text-[10px]">
      {entity.is_static && <span className="text-amber-400">STATIC</span>}
      {entity.is_resting && <span className="text-emerald-400">AT REST</span>}
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// LEVER DATA CARD
// ---------------------------------------------------------------------------

const LeverCard = ({ constraint }: { constraint: LeverConstraintState }) => (
  <div className="bg-slate-900 p-3 rounded-lg border border-amber-700/40 text-xs font-mono space-y-1.5">
    <div className="flex justify-between items-center">
      <span className="font-bold text-amber-300">Lever #{constraint.lever_id}</span>
      <span className="text-slate-400">Pivot</span>
    </div>
    <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-slate-400">
      <div>Angle: <span className="text-slate-300">{constraint.angle_deg.toFixed(2)}°</span></div>
      <div>ω: <span className="text-slate-300">{constraint.angular_velocity.toFixed(4)}</span></div>
      <div>Cost: <span className="text-slate-300">{constraint.topological_cost.toFixed(4)}</span></div>
      <div>Pivot Y: <span className="text-slate-300">{constraint.pivot.y.toFixed(2)}</span></div>
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// MAIN APP
// ---------------------------------------------------------------------------

export default function App() {
  const [state, setState] = useState<SimulationState | null>(null);
  const [connected, setConnected] = useState(false);
  const [activeTab, setActiveTab] = useState<'controls' | 'data' | 'physics'>('controls');
  const wsRef = useRef<WebSocket | null>(null);

  // Reconnecting WebSocket
  useEffect(() => {
    let reconnectTimer: ReturnType<typeof setTimeout>;

    const connect = () => {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const socket = new WebSocket(`${protocol}//${window.location.host}/ws`);
      wsRef.current = socket;

      socket.onopen = () => {
        setConnected(true);
        console.log('[UBP] WebSocket connected');
      };

      socket.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === 'state') {
            setState(msg.data as SimulationState);
          }
        } catch (e) {
          console.error('[UBP] Parse error:', e);
        }
      };

      socket.onclose = () => {
        setConnected(false);
        wsRef.current = null;
        console.log('[UBP] WebSocket disconnected — reconnecting in 2s');
        reconnectTimer = setTimeout(connect, 2000);
      };

      socket.onerror = (err) => {
        console.error('[UBP] WebSocket error:', err);
        socket.close();
      };
    };

    connect();

    return () => {
      clearTimeout(reconnectTimer);
      wsRef.current?.close();
    };
  }, []);

  const sendCommand = (command: string, payload: Record<string, unknown> = {}) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'command', command, ...payload }));
    }
  };

  const isRunning = state?.is_running ?? false;

  return (
    <div className="flex h-screen w-full bg-slate-900 text-slate-100 font-sans overflow-hidden">

      {/* ------------------------------------------------------------------ */}
      {/* 3D VIEWPORT                                                         */}
      {/* ------------------------------------------------------------------ */}
      <div className="flex-1 relative">
        <Canvas
          shadows
          camera={{ position: [15, 18, 28], fov: 50, near: 0.1, far: 500 }}
          gl={{ antialias: true }}
        >
          <Scene state={state} />
          <OrbitControls makeDefault target={[10, 5, 5]} />
        </Canvas>

        {/* HUD — top-left overlay */}
        <div className="absolute top-4 left-4 bg-slate-900/85 backdrop-blur-sm p-4 rounded-xl border border-slate-700 shadow-lg pointer-events-none min-w-[220px]">
          <div className="flex items-center gap-2 mb-3">
            <Activity className="w-5 h-5 text-emerald-400 flex-shrink-0" />
            <h1 className="text-base font-bold text-white leading-tight">UBP Digital Twin v3.0</h1>
          </div>
          <div className="space-y-1 text-xs text-slate-300 font-mono">
            <div className="flex justify-between">
              <span className="text-slate-500">Tick</span>
              <span>{state?.tick ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Time</span>
              <span>{(state?.time_s ?? 0).toFixed(2)} s</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Status</span>
              <span className={isRunning ? 'text-emerald-400' : 'text-amber-400'}>
                {isRunning ? 'Running' : 'Paused'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Entities</span>
              <span>{state?.stats?.entity_count ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Fluid Particles</span>
              <span>{state?.stats?.fluid_particle_count ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Avg Tick</span>
              <span>{(state?.stats?.avg_tick_ms ?? 0).toFixed(2)} ms</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Ambient Temp</span>
              <span>{(state?.ambient?.temperature_K ?? 0).toFixed(1)} K</span>
            </div>
          </div>
        </div>

        {/* Connection status — bottom-left */}
        <div className="absolute bottom-4 left-4">
          <ConnectionStatus connected={connected} />
        </div>
      </div>

      {/* ------------------------------------------------------------------ */}
      {/* SIDEBAR                                                             */}
      {/* ------------------------------------------------------------------ */}
      <div className="w-80 bg-slate-800 border-l border-slate-700 flex flex-col">

        {/* Play / Pause / Reset */}
        <div className="p-4 border-b border-slate-700">
          <div className="flex gap-2">
            <button
              onClick={() => sendCommand(isRunning ? 'pause' : 'play')}
              className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg font-medium text-sm transition-colors ${
                isRunning
                  ? 'bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 border border-amber-500/30'
                  : 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 border border-emerald-500/30'
              }`}
            >
              {isRunning ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
              {isRunning ? 'Pause' : 'Play'}
            </button>
            <button
              onClick={() => sendCommand('reset')}
              className="p-2.5 bg-slate-700 text-slate-300 hover:bg-slate-600 rounded-lg transition-colors border border-slate-600"
              title="Reset Simulation"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Tab navigation */}
        <div className="flex border-b border-slate-700">
          {(['controls', 'data', 'physics'] as const).map(tab => (
            <button
              key={tab}
              className={`flex-1 py-3 text-xs font-medium transition-colors capitalize ${
                activeTab === tab
                  ? 'text-white border-b-2 border-indigo-500'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              onClick={() => setActiveTab(tab)}
            >
              {tab}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">

          {/* CONTROLS TAB */}
          {activeTab === 'controls' && (
            <>
              <div>
                <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Spawn Entities</h3>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { material: 'iron', label: 'Iron Block', icon: <BoxIcon className="w-5 h-5 text-slate-300" />, y: 15 },
                    { material: 'copper', label: 'Copper Block', icon: <BoxIcon className="w-5 h-5 text-amber-500" />, y: 15 },
                    { material: 'gold', label: 'Gold Block', icon: <BoxIcon className="w-5 h-5 text-yellow-400" />, y: 15 },
                    { material: 'aluminium', label: 'Al Block', icon: <BoxIcon className="w-5 h-5 text-sky-300" />, y: 15 },
                  ].map(({ material, label, icon, y }) => (
                    <button
                      key={material}
                      onClick={() => sendCommand('spawn_block', { material, y, x: 5 + Math.random() * 10, z: Math.random() * 4 - 2 })}
                      className="flex flex-col items-center gap-2 p-3 bg-slate-700/50 hover:bg-slate-700 rounded-lg border border-slate-600 transition-colors text-xs"
                    >
                      {icon}
                      <span>{label}</span>
                    </button>
                  ))}
                  <button
                    onClick={() => sendCommand('spawn_fluid', { x: 5 + Math.random() * 8, y: 8, z: Math.random() * 4 - 2 })}
                    className="flex flex-col items-center gap-2 p-3 bg-slate-700/50 hover:bg-slate-700 rounded-lg border border-slate-600 transition-colors text-xs col-span-2"
                  >
                    <Droplet className="w-5 h-5 text-blue-400" />
                    <span>Spawn Water Pool</span>
                  </button>
                </div>
              </div>

              <div>
                <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Environment</h3>
                <div className="space-y-2">
                  {[
                    { label: 'Arctic (253 K)', temp: 253.15, icon: '❄️' },
                    { label: 'Room (293 K)', temp: 293.15, icon: '🌡️' },
                    { label: 'Hot (373 K)', temp: 373.15, icon: '🔥' },
                  ].map(({ label, temp, icon }) => (
                    <button
                      key={temp}
                      onClick={() => sendCommand('set_temperature', { temperature_K: temp })}
                      className="w-full flex items-center gap-3 p-2.5 bg-slate-700/50 hover:bg-slate-700 rounded-lg border border-slate-600 transition-colors text-xs text-left"
                    >
                      <span className="text-base">{icon}</span>
                      <span className="text-slate-300">{label}</span>
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}

          {/* DATA TAB */}
          {activeTab === 'data' && (
            <>
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Entity Data</h3>
              {state?.entities.map(e => (
                <EntityCard key={e.id} entity={e} />
              ))}
              {(state?.lever_constraints ?? []).length > 0 && (
                <>
                  <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mt-2">Lever Constraints</h3>
                  {state!.lever_constraints.map(c => (
                    <LeverCard key={c.lever_id} constraint={c} />
                  ))}
                </>
              )}
              {!state && (
                <p className="text-slate-500 text-xs">No data yet — connect to the simulation.</p>
              )}
            </>
          )}

          {/* PHYSICS TAB */}
          {activeTab === 'physics' && (
            <div className="space-y-3">
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">UBP Physics Constants</h3>
              <div className="bg-slate-900 p-3 rounded-lg border border-slate-700 text-xs font-mono space-y-1.5">
                <div className="text-slate-500 mb-2">Substrate (LAW-derived)</div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Y constant</span>
                  <span className="text-emerald-400">0.26468</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">C_DRAG = Y²</span>
                  <span className="text-emerald-400">0.07005</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">V_MAX = 1/Y</span>
                  <span className="text-emerald-400">3.7782</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">g/tick²</span>
                  <span className="text-emerald-400">0.000721</span>
                </div>
              </div>
              <div className="bg-slate-900 p-3 rounded-lg border border-slate-700 text-xs font-mono space-y-1.5">
                <div className="text-slate-500 mb-2">Fluid (Kissing/Sink-derived)</div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Pressure k</span>
                  <span className="text-blue-400">SINK×24/KISSING</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Viscosity</span>
                  <span className="text-blue-400">Y/96</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Surface σ</span>
                  <span className="text-blue-400">Y²/KISSING</span>
                </div>
              </div>
              <div className="bg-slate-900 p-3 rounded-lg border border-slate-700 text-xs font-mono space-y-1.5">
                <div className="text-slate-500 mb-2">Rigid Body (Topological Torque)</div>
                <div className="flex justify-between">
                  <span className="text-slate-400">I = m×L²/12</span>
                  <span className="text-amber-400">×(1+NRCI)×Vol</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Hamming Damp</span>
                  <span className="text-amber-400">C_DRAG = Y²</span>
                </div>
              </div>
              <div className="bg-slate-900 p-3 rounded-lg border border-slate-700 text-xs font-mono space-y-1.5">
                <div className="text-slate-500 mb-2">Ambient</div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Temp</span>
                  <span className="text-orange-400">{(state?.ambient?.temperature_K ?? 293.15).toFixed(2)} K</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">T_ubp</span>
                  <span className="text-orange-400">{(state?.ambient?.temperature_ubp ?? 0).toFixed(6)}</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
