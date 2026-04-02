import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Grid } from '@react-three/drei';
import * as THREE from 'three';
import {
  Play, Pause, RotateCcw, Box as BoxIcon, Droplet, Activity,
  Trash2, ArrowRight, ArrowLeft, ArrowUp, ArrowDown,
  ChevronRight, ChevronLeft, Layers, Building2, Zap,
  Thermometer, Grid3X3, FlaskConical,
} from 'lucide-react';

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
  is_dissolving?: boolean;
  mass: number;
  nrci: number;
  /** V4.0: UBP health status string */
  health_status?: string;
  /** V4.0: Metabolic opacity driven by NRCI */
  opacity?: number;
  /** V4.0: Phi-Orbit tick phase (0–1952) */
  tick_phase?: number;
  /** V4.0: Leech Lattice cell address */
  lattice_cell?: Vec3;
  /** V4.0: 24-bit Golay codeword vector */
  golay_vector?: number[];
  /** Temperature in Kelvin (UBP-derived). */
  temperature_K: number;
  velocity: Vec3;
}

interface FluidParticleState {
  id: number;
  body_id: number;
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

interface FluidBodyInfo {
  body_id: number;
  material: string;
  particle_count: number;
  avg_y: number;
}

interface SimulationState {
  tick: number;
  time_s: number;
  is_running: boolean;
  /** V4.0: engine version string */
  engine_version?: string;
  /** V4.0: whether UBP mechanics module is active */
  ubp_mechanics?: boolean;
  ambient: {
    temperature_K: number;
    temperature_ubp: number;
  };
  entities: EntityState[];
  fluid_particles: FluidParticleState[];
  fluid_bodies: FluidBodyInfo[];
  lever_constraints: LeverConstraintState[];
  stats: {
    entity_count: number;
    fluid_particle_count: number;
    fluid_body_count: number;
    avg_tick_ms: number;
    /** V4.0: average NRCI across all non-static entities */
    avg_nrci?: number;
    /** V4.0: count of entities currently dissolving */
    dissolving_count?: number;
  };
}

// ---------------------------------------------------------------------------
// ENTITY MESH — Box centred at the AABB centre (position + size/2)
// ---------------------------------------------------------------------------

const EntityMesh = React.memo(({
  data,
  selected,
  onClick,
}: {
  data: EntityState;
  selected: boolean;
  onClick: (id: number) => void;
}) => {
  const cx = data.position.x + data.size.x / 2;
  const cy = data.position.y + data.size.y / 2;
  const cz = data.position.z + data.size.z / 2;

  const rx = data.rotation?.x ?? 0;
  const ry = data.rotation?.y ?? 0;
  const rz = data.rotation?.z ?? 0;

  const colour = data.colour || '#888888';

  // Temperature-based emissive glow (hot = red glow)
  const tempNorm = Math.min(Math.max((data.temperature_K - 293) / 500, 0), 1);
  const emissiveColour = tempNorm > 0.05 ? `hsl(${Math.round(20 - tempNorm * 20)}, 100%, 40%)` : '#000000';

  // V4.0: Metabolic opacity — NRCI drives how "solid" the entity appears
  const metabolicOpacity = data.opacity ?? 1.0;
  const isDissolving = data.is_dissolving ?? false;
  const dissolveColour = isDissolving ? '#ff2222' : colour;

  if (data.is_static) {
    return (
      <mesh
        position={[cx, cy, cz]}
        rotation={[rx, ry, rz]}
        onClick={(e) => { e.stopPropagation(); onClick(data.id); }}
      >
        <boxGeometry args={[data.size.x, data.size.y, data.size.z]} />
        <meshStandardMaterial color={colour} transparent opacity={0.35} />
      </mesh>
    );
  }

  return (
    <mesh
      position={[cx, cy, cz]}
      rotation={[rx, ry, rz]}
      castShadow
      receiveShadow
      onClick={(e) => { e.stopPropagation(); onClick(data.id); }}
    >
      <boxGeometry args={[data.size.x, data.size.y, data.size.z]} />
      <meshStandardMaterial
        color={selected ? '#ffffff' : dissolveColour}
        emissive={selected ? colour : (isDissolving ? '#ff0000' : emissiveColour)}
        emissiveIntensity={selected ? 0.4 : (isDissolving ? 0.6 : tempNorm * 0.8)}
        roughness={0.6}
        metalness={
          data.material === 'iron' || data.material === 'steel' ? 0.8 : 0.3
        }
        transparent={metabolicOpacity < 0.99 || isDissolving}
        opacity={isDissolving ? 0.4 : metabolicOpacity}
      />
      {selected && (
        <lineSegments>
          <edgesGeometry args={[new THREE.BoxGeometry(data.size.x + 0.04, data.size.y + 0.04, data.size.z + 0.04)]} />
          <lineBasicMaterial color="#ffffff" linewidth={2} />
        </lineSegments>
      )}
    </mesh>
  );
});

// ---------------------------------------------------------------------------
// FLUID INSTANCED MESH — single draw call for all particles
// ---------------------------------------------------------------------------

const FluidParticles = React.memo(({ particles }: { particles: FluidParticleState[] }) => {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const count = particles.length;

  const dummy = useMemo(() => new THREE.Object3D(), []);
  const colour = useMemo(() => new THREE.Color(), []);

  useEffect(() => {
    if (!meshRef.current || count === 0) return;
    const mesh = meshRef.current;

    particles.forEach((p, i) => {
      dummy.position.set(p.position.x, p.position.y, p.position.z);
      const r = p.size?.x ?? 0.3;
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
  selected,
  onClick,
}: {
  constraint: LeverConstraintState;
  entity?: EntityState;
  selected: boolean;
  onClick: (id: number) => void;
}) => {
  if (!entity) return null;

  const angle_rad = (constraint.angle_deg * Math.PI) / 180.0;
  const lx = entity.size.x;
  const ly = entity.size.y;
  const lz = entity.size.z;
  const px = constraint.pivot.x;
  const py = constraint.pivot.y;
  const pz = constraint.pivot.z;
  const ecx = entity.position.x + lx / 2 - px;
  const ecy = entity.position.y + ly / 2 - py;
  const cos_a = Math.cos(angle_rad);
  const sin_a = Math.sin(angle_rad);
  const rcx = ecx * cos_a - ecy * sin_a + px;
  const rcy = ecx * sin_a + ecy * cos_a + py;

  return (
    <mesh
      position={[rcx, rcy, pz]}
      rotation={[0, 0, angle_rad]}
      castShadow
      onClick={(e) => { e.stopPropagation(); onClick(entity.id); }}
    >
      <boxGeometry args={[lx, ly, lz]} />
      <meshStandardMaterial
        color={selected ? '#ffffff' : (entity.colour || '#888888')}
        emissive={selected ? (entity.colour || '#888888') : '#000000'}
        emissiveIntensity={selected ? 0.4 : 0}
        roughness={0.4}
        metalness={0.7}
      />
    </mesh>
  );
});

// ---------------------------------------------------------------------------
// PIVOT MARKER
// ---------------------------------------------------------------------------

const PivotMarker = ({ pivot }: { pivot: Vec3 }) => (
  <mesh position={[pivot.x, pivot.y, pivot.z]}>
    <sphereGeometry args={[0.15, 12, 12]} />
    <meshStandardMaterial color="#ff6600" emissive="#ff3300" emissiveIntensity={0.5} />
  </mesh>
);

// ---------------------------------------------------------------------------
// CLICKABLE GRID PLANE — for block placement
// ---------------------------------------------------------------------------

const GridPlane = ({
  visible,
  onGridClick,
  cellSize,
}: {
  visible: boolean;
  onGridClick: (gridX: number, gridZ: number) => void;
  cellSize: number;
}) => {
  if (!visible) return null;

  return (
    <mesh
      position={[10, 1.002, 10]}
      rotation={[-Math.PI / 2, 0, 0]}
      onClick={(e) => {
        e.stopPropagation();
        const x = e.point.x;
        const z = e.point.z;
        const gx = Math.round(x / cellSize);
        const gz = Math.round(z / cellSize);
        onGridClick(gx, gz);
      }}
    >
      <planeGeometry args={[40, 40]} />
      <meshBasicMaterial color="#4488ff" transparent opacity={0.08} side={THREE.DoubleSide} />
    </mesh>
  );
};

// ---------------------------------------------------------------------------
// SCENE — assembles all visual components
// ---------------------------------------------------------------------------

const Scene = ({
  state,
  selectedId,
  onSelectEntity,
  gridPlacementMode,
  gridCellSize,
  onGridClick,
}: {
  state: SimulationState | null;
  selectedId: number | null;
  onSelectEntity: (id: number | null) => void;
  gridPlacementMode: boolean;
  gridCellSize: number;
  onGridClick: (gx: number, gz: number) => void;
}) => {
  if (!state) return null;

  const entityById = useMemo(() => {
    const map: Record<number, EntityState> = {};
    (state.entities || []).forEach(e => { map[e.id] = e; });
    return map;
  }, [state.entities]);

  const leverIds = new Set((state.lever_constraints || []).map(c => c.lever_id));

  return (
    <>
      <ambientLight intensity={0.4} />
      <directionalLight
        position={[15, 25, 15]}
        intensity={1.2}
        castShadow
        shadow-mapSize={[2048, 2048]}
      />
      <pointLight position={[-10, 10, -10]} intensity={0.3} color="#4488ff" />

      <Grid
        args={[40, 40]}
        position={[10, 1.001, 10]}
        cellColor="#334155"
        sectionColor="#475569"
        fadeDistance={60}
        infiniteGrid={false}
      />

      {/* Clickable grid for block placement */}
      <GridPlane
        visible={gridPlacementMode}
        onGridClick={onGridClick}
        cellSize={gridCellSize}
      />

      {/* Background deselect plane */}
      {!gridPlacementMode && (
        <mesh
          position={[10, -5, 10]}
          onClick={() => onSelectEntity(null)}
          visible={false}
        >
          <planeGeometry args={[200, 200]} />
          <meshBasicMaterial />
        </mesh>
      )}

      {/* Regular entities (non-lever) */}
      {(state.entities || [])
        .filter(e => !leverIds.has(e.id))
        .map(entity => (
          <EntityMesh
            key={entity.id}
            data={entity}
            selected={selectedId === entity.id}
            onClick={onSelectEntity}
          />
        ))}

      {/* Lever entities */}
      {(state.lever_constraints || []).map(constraint => (
        <React.Fragment key={`lever-${constraint.lever_id}`}>
          <LeverVisual
            constraint={constraint}
            entity={entityById[constraint.lever_id]}
            selected={selectedId === constraint.lever_id}
            onClick={onSelectEntity}
          />
          <PivotMarker pivot={constraint.pivot} />
        </React.Fragment>
      ))}

      {/* Fluid particles */}
      <FluidParticles particles={state.fluid_particles || []} />
    </>
  );
};

// ---------------------------------------------------------------------------
// CONNECTION STATUS
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

const EntityCard = ({
  entity,
  selected,
  onSelect,
  onDelete,
}: {
  entity: EntityState;
  selected: boolean;
  onSelect: (id: number) => void;
  onDelete: (id: number) => void;
}) => {
  const tempDelta = entity.temperature_K - 293.15;
  const tempColour = tempDelta > 5 ? '#f97316' : tempDelta > 1 ? '#fbbf24' : '#94a3b8';

  return (
    <div
      className={`bg-slate-900 p-3 rounded-lg border text-xs font-mono space-y-1.5 cursor-pointer transition-colors ${
        selected ? 'border-indigo-500 ring-1 ring-indigo-500/40' : 'border-slate-700 hover:border-slate-500'
      }`}
      onClick={() => onSelect(entity.id)}
    >
      <div className="flex justify-between items-center">
        <span className="font-bold text-slate-200">{entity.label}</span>
        <div className="flex items-center gap-1.5">
          <span
            className="px-1.5 py-0.5 rounded text-[10px]"
            style={{ backgroundColor: entity.colour + '22', color: entity.colour }}
          >
            {entity.material}
          </span>
          {!entity.is_static && (
            <button
              onClick={(e) => { e.stopPropagation(); onDelete(entity.id); }}
              className="p-0.5 text-red-400/60 hover:text-red-400 transition-colors"
              title="Delete entity"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>
      {/* V4.0: NRCI Health Bar */}
      {(() => {
        const nrci = entity.nrci;
        const healthPct = Math.round(nrci * 100);
        const barColour = nrci > 0.7 ? '#22c55e' : nrci > 0.4 ? '#f59e0b' : '#ef4444';
        const status = entity.health_status ?? (nrci > 0.7 ? 'COHERENT' : nrci > 0.4 ? 'STRESSED' : 'CRITICAL');
        return (
          <div className="space-y-1">
            <div className="flex justify-between items-center text-[10px]">
              <span className="text-slate-500">NRCI Health</span>
              <span style={{ color: barColour }} className="font-bold">{status}</span>
            </div>
            <div className="w-full h-1.5 bg-slate-700 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-300"
                style={{ width: `${healthPct}%`, backgroundColor: barColour }}
              />
            </div>
            <div className="flex justify-between text-[10px] text-slate-500">
              <span>NRCI {nrci.toFixed(4)}</span>
              <span>{healthPct}%</span>
            </div>
          </div>
        );
      })()}
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-slate-400">
        <div>Mass: <span className="text-slate-300">{entity.mass.toFixed(3)}</span></div>
        <div>Temp: <span style={{ color: tempColour }}>{entity.temperature_K.toFixed(2)} K</span></div>
        <div>Y: <span className="text-slate-300">{entity.position.y.toFixed(3)}</span></div>
        <div>Vx: <span className="text-slate-300">{entity.velocity.x.toFixed(4)}</span></div>
        {entity.lattice_cell && (
          <div className="col-span-2 text-[10px] text-slate-500">
            Lattice: <span className="text-violet-400 font-mono">
              [{entity.lattice_cell.x},{entity.lattice_cell.y},{entity.lattice_cell.z}]
            </span>
          </div>
        )}
      </div>
      <div className="flex gap-2 text-[10px] flex-wrap">
        {entity.is_static && <span className="text-amber-400">STATIC</span>}
        {entity.is_resting && <span className="text-emerald-400">AT REST</span>}
        {entity.is_dissolving && <span className="text-red-400 animate-pulse">◉ DISSOLVING</span>}
        {selected && <span className="text-indigo-400">SELECTED</span>}
        {tempDelta > 1 && <span style={{ color: tempColour }}>▲ HOT +{tempDelta.toFixed(1)}K</span>}
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// LEVER DATA CARD — with angle setter
// ---------------------------------------------------------------------------

const LeverCard = ({
  constraint,
  onSetAngle,
  onPush,
}: {
  constraint: LeverConstraintState;
  onSetAngle: (leverId: number, angle: number) => void;
  onPush: (leverId: number, fy: number, atX: number) => void;
}) => {
  const [targetAngle, setTargetAngle] = useState(0);
  const [pushForce, setPushForce] = useState(2.0);
  const [pushAtX, setPushAtX] = useState(constraint.pivot.x - 3);

  return (
    <div className="bg-slate-900 p-3 rounded-lg border border-amber-700/40 text-xs font-mono space-y-2">
      <div className="flex justify-between items-center">
        <span className="font-bold text-amber-300">Lever #{constraint.lever_id}</span>
        <span className="text-slate-400">{constraint.angle_deg.toFixed(1)}°</span>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-slate-400">
        <div>ω: <span className="text-slate-300">{constraint.angular_velocity.toFixed(4)}</span></div>
        <div>Cost: <span className="text-slate-300">{constraint.topological_cost.toFixed(4)}</span></div>
        <div>Pivot X: <span className="text-slate-300">{constraint.pivot.x.toFixed(2)}</span></div>
        <div>Pivot Y: <span className="text-slate-300">{constraint.pivot.y.toFixed(2)}</span></div>
      </div>

      {/* Set angle */}
      <div className="border-t border-slate-700 pt-2 space-y-1.5">
        <div className="text-slate-400">Set angle (°)</div>
        <div className="flex gap-2 items-center">
          <input
            type="range"
            min={-45}
            max={45}
            step={1}
            value={targetAngle}
            onChange={e => setTargetAngle(parseInt(e.target.value))}
            className="flex-1 accent-amber-500"
          />
          <span className="w-10 text-right text-slate-300">{targetAngle}°</span>
        </div>
        <button
          onClick={() => onSetAngle(constraint.lever_id, targetAngle)}
          className="w-full py-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/30 rounded transition-colors"
        >
          Set Lever Angle
        </button>
      </div>

      {/* Push lever */}
      <div className="border-t border-slate-700 pt-2 space-y-1.5">
        <div className="text-slate-400">Push lever</div>
        <div className="flex gap-2 items-center text-[10px]">
          <span className="text-slate-500 w-14">Force</span>
          <input
            type="range" min={0.5} max={10} step={0.5}
            value={pushForce}
            onChange={e => setPushForce(parseFloat(e.target.value))}
            className="flex-1 accent-amber-500"
          />
          <span className="w-8 text-right text-slate-300">{pushForce}</span>
        </div>
        <div className="flex gap-2 items-center text-[10px]">
          <span className="text-slate-500 w-14">At X</span>
          <input
            type="range" min={constraint.pivot.x - 6} max={constraint.pivot.x + 6} step={0.5}
            value={pushAtX}
            onChange={e => setPushAtX(parseFloat(e.target.value))}
            className="flex-1 accent-amber-500"
          />
          <span className="w-8 text-right text-slate-300">{pushAtX.toFixed(1)}</span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => onPush(constraint.lever_id, pushForce, pushAtX)}
            className="flex-1 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/30 rounded transition-colors"
          >
            ↑ Push Up
          </button>
          <button
            onClick={() => onPush(constraint.lever_id, -pushForce, pushAtX)}
            className="flex-1 py-1.5 bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/30 rounded transition-colors"
          >
            ↓ Push Down
          </button>
        </div>
      </div>
    </div>
  );
};

// ---------------------------------------------------------------------------
// FLUID BODY CARD — with delete button
// ---------------------------------------------------------------------------

const FluidBodyCard = ({
  body,
  onDelete,
}: {
  body: FluidBodyInfo;
  onDelete: (bodyId: number) => void;
}) => (
  <div className="bg-slate-900 p-3 rounded-lg border border-blue-700/40 text-xs font-mono space-y-1.5">
    <div className="flex justify-between items-center">
      <span className="font-bold text-blue-300">Fluid Body #{body.body_id}</span>
      <button
        onClick={() => onDelete(body.body_id)}
        className="p-0.5 text-red-400/60 hover:text-red-400 transition-colors"
        title="Delete fluid body"
      >
        <Trash2 className="w-3 h-3" />
      </button>
    </div>
    <div className="grid grid-cols-2 gap-x-4 gap-y-0.5 text-slate-400">
      <div>Material: <span className="text-blue-300">{body.material}</span></div>
      <div>Particles: <span className="text-slate-300">{body.particle_count}</span></div>
      <div>Avg Y: <span className="text-slate-300">{body.avg_y.toFixed(2)}</span></div>
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// INTERACTION PANEL — push/pull selected entity
// ---------------------------------------------------------------------------

const InteractionPanel = ({
  entity,
  onPush,
  onDelete,
}: {
  entity: EntityState;
  onPush: (fx: number, fy: number, fz: number) => void;
  onDelete: (id: number) => void;
}) => {
  const [force, setForce] = useState(1.0);

  return (
    <div className="bg-slate-900 rounded-lg border border-indigo-500/40 p-3 space-y-3 text-xs">
      <div className="flex justify-between items-center">
        <span className="font-bold text-indigo-300">
          Selected: <span className="text-white">{entity.label}</span>
        </span>
        <span
          className="px-1.5 py-0.5 rounded text-[10px]"
          style={{ backgroundColor: entity.colour + '22', color: entity.colour }}
        >
          {entity.material}
        </span>
      </div>

      <div className="space-y-1">
        <div className="flex justify-between text-slate-400">
          <span>Force magnitude</span>
          <span className="text-slate-200 font-mono">{force.toFixed(1)}</span>
        </div>
        <input
          type="range" min={0.1} max={50.0} step={0.5}
          value={force}
          onChange={e => setForce(parseFloat(e.target.value))}
          className="w-full accent-indigo-500"
        />
        <div className="text-[10px] text-slate-500">
          {force > 20 ? '⚠ High force — will generate heat on impact' : 'Normal force range'}
        </div>
      </div>

      <div className="space-y-1">
        <div className="text-slate-400 mb-1">Push direction</div>
        <div className="flex gap-2 items-center">
          <span className="w-4 text-slate-500">X</span>
          <button onClick={() => onPush(-force, 0, 0)} className="flex-1 flex items-center justify-center gap-1 py-1.5 bg-slate-700 hover:bg-slate-600 rounded text-slate-300 transition-colors">
            <ChevronLeft className="w-3 h-3" /> −X
          </button>
          <button onClick={() => onPush(force, 0, 0)} className="flex-1 flex items-center justify-center gap-1 py-1.5 bg-slate-700 hover:bg-slate-600 rounded text-slate-300 transition-colors">
            +X <ChevronRight className="w-3 h-3" />
          </button>
        </div>
        <div className="flex gap-2 items-center">
          <span className="w-4 text-slate-500">Y</span>
          <button onClick={() => onPush(0, -force, 0)} className="flex-1 flex items-center justify-center gap-1 py-1.5 bg-slate-700 hover:bg-slate-600 rounded text-slate-300 transition-colors">
            <ArrowDown className="w-3 h-3" /> −Y
          </button>
          <button onClick={() => onPush(0, force, 0)} className="flex-1 flex items-center justify-center gap-1 py-1.5 bg-slate-700 hover:bg-slate-600 rounded text-slate-300 transition-colors">
            +Y <ArrowUp className="w-3 h-3" />
          </button>
        </div>
        <div className="flex gap-2 items-center">
          <span className="w-4 text-slate-500">Z</span>
          <button onClick={() => onPush(0, 0, -force)} className="flex-1 flex items-center justify-center gap-1 py-1.5 bg-slate-700 hover:bg-slate-600 rounded text-slate-300 transition-colors">
            <ArrowLeft className="w-3 h-3" /> −Z
          </button>
          <button onClick={() => onPush(0, 0, force)} className="flex-1 flex items-center justify-center gap-1 py-1.5 bg-slate-700 hover:bg-slate-600 rounded text-slate-300 transition-colors">
            +Z <ArrowRight className="w-3 h-3" />
          </button>
        </div>
      </div>

      {!entity.is_static && (
        <button
          onClick={() => onDelete(entity.id)}
          className="w-full flex items-center justify-center gap-2 py-2 bg-red-500/10 hover:bg-red-500/20 text-red-400 border border-red-500/30 rounded-lg transition-colors"
        >
          <Trash2 className="w-3.5 h-3.5" />
          Delete Entity
        </button>
      )}
    </div>
  );
};

// ---------------------------------------------------------------------------
// GRID PLACEMENT PANEL
// ---------------------------------------------------------------------------

const GridPlacementPanel = ({
  active,
  material,
  onSetMaterial,
  onToggle,
  onCancel,
}: {
  active: boolean;
  material: string;
  onSetMaterial: (m: string) => void;
  onToggle: () => void;
  onCancel: () => void;
}) => (
  <div className={`rounded-lg border p-3 space-y-2 text-xs transition-colors ${
    active ? 'border-emerald-500/50 bg-emerald-500/5' : 'border-slate-700 bg-slate-900/60'
  }`}>
    <div className="flex justify-between items-center">
      <span className="font-semibold text-slate-300 flex items-center gap-2">
        <Grid3X3 className="w-3.5 h-3.5" />
        Grid Placement
      </span>
      {active && (
        <span className="text-emerald-400 text-[10px] animate-pulse">● ACTIVE — click grid</span>
      )}
    </div>
    <div className="flex gap-2">
      {['iron', 'copper', 'gold', 'aluminium', 'silicon'].map(m => (
        <button
          key={m}
          onClick={() => onSetMaterial(m)}
          className={`flex-1 py-1 rounded text-[10px] transition-colors ${
            material === m ? 'bg-indigo-500/30 text-indigo-300 border border-indigo-500/40' : 'bg-slate-700 text-slate-400 hover:text-slate-200'
          }`}
        >
          {m.slice(0, 2).toUpperCase()}
        </button>
      ))}
    </div>
    <div className="flex gap-2">
      <button
        onClick={onToggle}
        className={`flex-1 py-1.5 rounded border transition-colors ${
          active
            ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30'
            : 'bg-slate-700 text-slate-300 border-slate-600 hover:bg-slate-600'
        }`}
      >
        {active ? 'Placing…' : 'Enable Grid Place'}
      </button>
      {active && (
        <button
          onClick={onCancel}
          className="px-3 py-1.5 rounded border bg-red-500/10 text-red-400 border-red-500/30 hover:bg-red-500/20 transition-colors"
        >
          Cancel
        </button>
      )}
    </div>
  </div>
);

// ---------------------------------------------------------------------------
// MAIN APP
// ---------------------------------------------------------------------------

export default function App() {
  const [state, setState] = useState<SimulationState | null>(null);
  const [connected, setConnected] = useState(false);
  const [activeTab, setActiveTab] = useState<'controls' | 'data' | 'physics' | 'ubp'>('controls');
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [gridPlacementMode, setGridPlacementMode] = useState(false);
  const [gridMaterial, setGridMaterial] = useState('iron');
  const [demoStatus, setDemoStatus] = useState<string | null>(null);
  // V4.0: UBP mechanics state
  const [engineTestResult, setEngineTestResult] = useState<any>(null);
  const [engineTestLoading, setEngineTestLoading] = useState(false);
  const [synthesisLog, setSynthesisLog] = useState<Array<{tick: number; a: string; b: string; hamming: number; restitution: number}>>([]);
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
          } else if (msg.type === 'synthesis_event') {
            // V4.0: Log Synthesis Collision Events
            setSynthesisLog(prev => {
              const entry = {
                tick: msg.tick ?? 0,
                a: msg.material_a ?? '?',
                b: msg.material_b ?? '?',
                hamming: msg.hamming_distance ?? 0,
                restitution: msg.restitution ?? 0,
              };
              return [entry, ...prev].slice(0, 20); // keep last 20
            });
          }
        } catch (e) {
          console.error('[UBP] Parse error:', e);
        }
      };

      socket.onclose = () => {
        setConnected(false);
        wsRef.current = null;
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

  const sendCommand = useCallback((command: string, payload: Record<string, unknown> = {}) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'command', command, ...payload }));
    }
  }, []);

  const handlePush = useCallback((fx: number, fy: number, fz: number) => {
    if (selectedId !== null) {
      sendCommand('push', { entity_id: selectedId, fx, fy, fz });
    }
  }, [selectedId, sendCommand]);

  const handleDelete = useCallback((id: number) => {
    sendCommand('delete_entity', { entity_id: id });
    setSelectedId(null);
  }, [sendCommand]);

  const handleDeleteFluid = useCallback((bodyId: number) => {
    sendCommand('delete_fluid', { body_id: bodyId });
  }, [sendCommand]);

  const handleDeleteAllFluid = useCallback(() => {
    sendCommand('delete_fluid', {});
  }, [sendCommand]);

  const handleSelectEntity = useCallback((id: number | null) => {
    setSelectedId(prev => (prev === id ? null : id));
  }, []);

  const handleSetLeverAngle = useCallback((leverId: number, angle: number) => {
    sendCommand('set_lever_angle', { lever_id: leverId, angle_deg: angle });
  }, [sendCommand]);

  const handlePushLever = useCallback((leverId: number, fy: number, atX: number) => {
    sendCommand('push_lever', { lever_id: leverId, fx: 0, fy, at_x: atX });
  }, [sendCommand]);

  const handleGridClick = useCallback((gx: number, gz: number) => {
    sendCommand('spawn_block_at_grid', {
      grid_x: gx,
      grid_z: gz,
      material: gridMaterial,
      y: 15.0,
      cell_size: 1.0,
    });
    // Keep placement mode active for rapid building
  }, [gridMaterial, sendCommand]);

  const handleDemoDisplacement = useCallback(() => {
    setDemoStatus('Setting up displacement demo…');
    sendCommand('demo_displacement');
    setTimeout(() => setDemoStatus('Demo running — watch the water!'), 1500);
    setTimeout(() => setDemoStatus(null), 8000);
  }, [sendCommand]);

  // V4.0: Run engine_test validation against README spec
  const handleRunEngineTest = useCallback(async () => {
    setEngineTestLoading(true);
    setEngineTestResult(null);
    try {
      const res = await fetch('/engine_test');
      const data = await res.json();
      setEngineTestResult(data);
    } catch (e) {
      setEngineTestResult({ error: String(e) });
    } finally {
      setEngineTestLoading(false);
    }
  }, []);

  const selectedEntity = useMemo(() => {
    if (selectedId === null || !state) return null;
    return state.entities.find(e => e.id === selectedId) ?? null;
  }, [selectedId, state]);

  const isRunning = state?.is_running ?? false;

  // Fluid bodies derived from particles
  const fluidBodies: FluidBodyInfo[] = useMemo(() => {
    return state?.fluid_bodies ?? [];
  }, [state]);

  return (
    <div className="flex h-screen w-full bg-slate-900 text-slate-100 font-sans overflow-hidden">

      {/* 3D VIEWPORT */}
      <div className="flex-1 relative">
        <Canvas
          shadows
          camera={{ position: [15, 18, 28], fov: 50, near: 0.1, far: 500 }}
          gl={{ antialias: true }}
        >
          <Scene
            state={state}
            selectedId={selectedId}
            onSelectEntity={handleSelectEntity}
            gridPlacementMode={gridPlacementMode}
            gridCellSize={1.0}
            onGridClick={handleGridClick}
          />
          <OrbitControls makeDefault target={[10, 5, 5]} />
        </Canvas>

        {/* HUD — top-left */}
        <div className="absolute top-4 left-4 bg-slate-900/85 backdrop-blur-sm p-4 rounded-xl border border-slate-700 shadow-lg pointer-events-none min-w-[240px]">
          <div className="flex items-center gap-2 mb-3">
            <Activity className="w-5 h-5 text-emerald-400 flex-shrink-0" />
            <h1 className="text-base font-bold text-white leading-tight">
              UBP Digital Twin v4.0
              {state?.ubp_mechanics && (
                <span className="ml-2 text-[10px] text-violet-400 font-normal align-middle">◉ UBP</span>
              )}
            </h1>
          </div>
          <div className="space-y-1 text-xs text-slate-300 font-mono">
            <div className="flex justify-between">
              <span className="text-slate-500">Tick</span>
              <span className="text-emerald-300">{state?.tick ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Time</span>
              <span className="text-emerald-300">{(state?.time_s ?? 0).toFixed(2)} s</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Status</span>
              <span className={isRunning ? 'text-emerald-400' : 'text-amber-400'}>
                {isRunning ? 'Running' : 'Paused'}
              </span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Entities</span>
              <span className="text-sky-300">{state?.stats?.entity_count ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Fluid Particles</span>
              <span className="text-blue-400">{state?.stats?.fluid_particle_count ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Fluid Bodies</span>
              <span className="text-blue-400">{state?.stats?.fluid_body_count ?? 0}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Avg Tick</span>
              <span className="text-amber-300">{(state?.stats?.avg_tick_ms ?? 0).toFixed(2)} ms</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Ambient Temp</span>
              <span className="text-orange-300">{(state?.ambient?.temperature_K ?? 0).toFixed(1)} K</span>
            </div>
            {state?.stats?.avg_nrci !== undefined && (
              <div className="flex justify-between">
                <span className="text-slate-500">Avg NRCI</span>
                <span className="text-violet-400">{state.stats.avg_nrci.toFixed(4)}</span>
              </div>
            )}
            {(state?.stats?.dissolving_count ?? 0) > 0 && (
              <div className="flex justify-between">
                <span className="text-slate-500">Dissolving</span>
                <span className="text-red-400 animate-pulse">{state!.stats.dissolving_count}</span>
              </div>
            )}
          </div>
        </div>

        {/* Grid placement mode indicator */}
        {gridPlacementMode && (
          <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-emerald-500/20 backdrop-blur-sm px-4 py-2 rounded-xl border border-emerald-500/40 text-sm font-semibold text-emerald-300 pointer-events-none">
            Grid Placement Mode — Click the floor to place a {gridMaterial} block
          </div>
        )}

        {/* Demo status */}
        {demoStatus && (
          <div className="absolute top-16 left-1/2 -translate-x-1/2 bg-indigo-500/20 backdrop-blur-sm px-4 py-2 rounded-xl border border-indigo-500/40 text-sm font-semibold text-indigo-300 pointer-events-none">
            {demoStatus}
          </div>
        )}

        {/* Selected entity mini-HUD — bottom-left */}
        {selectedEntity && (
          <div className="absolute bottom-14 left-4 bg-slate-900/90 backdrop-blur-sm px-3 py-2 rounded-lg border border-indigo-500/40 text-xs font-mono pointer-events-none">
            <span className="text-indigo-400">▶ </span>
            <span className="text-white">{selectedEntity.label}</span>
            <span className="text-slate-400 ml-2">
              ({selectedEntity.position.x.toFixed(1)}, {selectedEntity.position.y.toFixed(1)}, {selectedEntity.position.z.toFixed(1)})
            </span>
            <span className="text-orange-400 ml-2">
              {selectedEntity.temperature_K.toFixed(1)} K
            </span>
            {selectedEntity.lattice_cell && (
              <span className="text-violet-400 ml-2 text-[10px]">
                ◇[{selectedEntity.lattice_cell.x},{selectedEntity.lattice_cell.y},{selectedEntity.lattice_cell.z}]
              </span>
            )}
          </div>
        )}

        {/* Connection status — bottom-left */}
        <div className="absolute bottom-4 left-4">
          <ConnectionStatus connected={connected} />
        </div>
      </div>

      {/* SIDEBAR */}
      <div className="w-80 bg-slate-800 border-l border-slate-700 flex flex-col">

        {/* Play / Pause / Reset */}
        <div className="p-4 border-b border-slate-700 space-y-3">
          <div className="flex items-center justify-between text-[10px] text-slate-500 font-mono uppercase tracking-wider">
            <span>Simulation Engine</span>
            <span className={isRunning ? "text-emerald-400 animate-pulse" : "text-slate-600"}>
              {isRunning ? "● Running" : "○ Paused"}
            </span>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => sendCommand(isRunning ? 'pause' : 'play')}
              className={`flex-1 flex items-center justify-center gap-2 py-2.5 rounded-lg font-medium text-sm transition-all ${
                isRunning
                  ? 'bg-amber-500/20 text-amber-400 hover:bg-amber-500/30 border border-amber-500/40 shadow-[0_0_15px_rgba(245,158,11,0.1)]'
                  : 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 border border-emerald-500/40 shadow-[0_0_15px_rgba(16,185,129,0.1)]'
              }`}
            >
              {isRunning ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
              {isRunning ? 'Pause' : 'Play'}
            </button>
            {!isRunning && (
              <button
                onClick={() => sendCommand('step')}
                className="p-2.5 bg-indigo-500/10 text-indigo-400 hover:bg-indigo-500/20 rounded-lg transition-colors border border-indigo-500/30"
                title="Single Step"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            )}
            <button
              onClick={() => { sendCommand('reset'); setSelectedId(null); setGridPlacementMode(false); setDemoStatus(null); }}
              className="p-2.5 bg-slate-700/50 text-slate-400 hover:bg-slate-600 hover:text-slate-200 rounded-lg transition-colors border border-slate-600"
              title="Reset Simulation"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          </div>
          <div className="flex justify-between items-center px-1">
            <div className="text-[10px] text-slate-500 font-mono">
              TICK: <span className="text-slate-300">{state?.tick ?? 0}</span>
            </div>
            <div className="text-[10px] text-slate-500 font-mono">
              TIME: <span className="text-slate-300">{(state?.time_s ?? 0).toFixed(2)}s</span>
            </div>
          </div>
        </div>

        {/* Tab navigation */}
        <div className="flex border-b border-slate-700">
          {(['controls', 'data', 'physics', 'ubp'] as const).map(tab => (
            <button
              key={tab}
              className={`flex-1 py-3 text-xs font-medium transition-colors capitalize ${
                activeTab === tab
                  ? tab === 'ubp' ? 'text-violet-300 border-b-2 border-violet-500' : 'text-white border-b-2 border-indigo-500'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
              onClick={() => setActiveTab(tab)}
            >
              {tab === 'ubp' ? '◉ UBP' : tab}
            </button>
          ))}
        </div>

        {/* Tab content */}
        <div className="flex-1 overflow-y-auto p-4 space-y-4">

          {/* CONTROLS TAB */}
          {activeTab === 'controls' && (
            <>
              {/* Selected entity interaction panel */}
              {selectedEntity && !selectedEntity.is_static && (
                <InteractionPanel
                  entity={selectedEntity}
                  onPush={handlePush}
                  onDelete={handleDelete}
                />
              )}

              {/* Grid Placement */}
              <GridPlacementPanel
                active={gridPlacementMode}
                material={gridMaterial}
                onSetMaterial={setGridMaterial}
                onToggle={() => setGridPlacementMode(v => !v)}
                onCancel={() => setGridPlacementMode(false)}
              />

              {/* Spawn Entities */}
              <div>
                <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Spawn Entities</h3>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { material: 'iron',      label: 'Iron Block',   colour: '#8B7355', y: 15 },
                    { material: 'copper',    label: 'Copper Block', colour: '#B87333', y: 15 },
                    { material: 'gold',      label: 'Gold Block',   colour: '#FFD700', y: 15 },
                    { material: 'aluminium', label: 'Al Block',     colour: '#C0C0C0', y: 15 },
                  ].map(({ material, label, colour, y }) => (
                    <button
                      key={material}
                      onClick={() => sendCommand('spawn_block', {
                        material, y,
                        x: 5 + Math.random() * 10,
                        z: Math.random() * 4 - 2,
                      })}
                      className="flex flex-col items-center gap-2 p-3 bg-slate-700/50 hover:bg-slate-700 rounded-lg border border-slate-600 transition-colors text-xs"
                    >
                      <BoxIcon className="w-5 h-5" style={{ color: colour }} />
                      <span>{label}</span>
                    </button>
                  ))}

                  {/* Spawn Water Pool */}
                  <button
                    onClick={() => sendCommand('spawn_fluid', {
                      x: 5 + Math.random() * 8,
                      y: 8,
                      z: Math.random() * 4 - 2,
                    })}
                    className="flex flex-col items-center gap-2 p-3 bg-slate-700/50 hover:bg-slate-700 rounded-lg border border-slate-600 transition-colors text-xs col-span-2"
                  >
                    <Droplet className="w-5 h-5 text-blue-400" />
                    <span>Spawn Water Pool</span>
                  </button>

                  {/* Delete all fluid */}
                  <button
                    onClick={handleDeleteAllFluid}
                    className="flex flex-col items-center gap-2 p-3 bg-slate-700/50 hover:bg-red-900/30 rounded-lg border border-slate-600 hover:border-red-500/40 transition-colors text-xs col-span-2"
                  >
                    <Trash2 className="w-5 h-5 text-red-400" />
                    <span>Delete All Fluid</span>
                  </button>

                  {/* Spawn Lever */}
                  <button
                    onClick={() => sendCommand('add_lever', {
                      material: 'steel',
                      x: 3 + Math.random() * 8,
                      y: 1.0,
                      z: Math.random() * 4 - 2,
                      length: 8,
                    })}
                    className="flex flex-col items-center gap-2 p-3 bg-slate-700/50 hover:bg-slate-700 rounded-lg border border-slate-600 transition-colors text-xs col-span-2"
                  >
                    <Layers className="w-5 h-5 text-amber-400" />
                    <span>Spawn Steel Lever</span>
                  </button>
                </div>
              </div>

              {/* Building Tools */}
              <div>
                <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Building Tools</h3>
                <div className="space-y-2">
                  <button
                    onClick={() => sendCommand('build_demo_building', {
                      x: 3, z: 3, width: 6, depth: 6, height: 8,
                      wall_thickness: 1, material: 'silicon',
                    })}
                    className="w-full flex items-center gap-3 p-2.5 bg-slate-700/50 hover:bg-slate-700 rounded-lg border border-slate-600 transition-colors text-xs text-left"
                  >
                    <Building2 className="w-4 h-4 text-slate-300 flex-shrink-0" />
                    <span>Build Hollow Building (6×6×8)</span>
                  </button>
                  <button
                    onClick={() => sendCommand('fill_building_with_water', {
                      x: 3, z: 3, width: 6, depth: 6, height: 8,
                      wall_thickness: 1, fill_height: 5,
                    })}
                    className="w-full flex items-center gap-3 p-2.5 bg-slate-700/50 hover:bg-slate-700 rounded-lg border border-slate-600 transition-colors text-xs text-left"
                  >
                    <FlaskConical className="w-4 h-4 text-blue-400 flex-shrink-0" />
                    <span>Fill Building with Water</span>
                  </button>
                  <button
                    onClick={handleDemoDisplacement}
                    className="w-full flex items-center gap-3 p-2.5 bg-indigo-500/10 hover:bg-indigo-500/20 rounded-lg border border-indigo-500/30 transition-colors text-xs text-left"
                  >
                    <Zap className="w-4 h-4 text-indigo-400 flex-shrink-0" />
                    <span className="text-indigo-300 font-semibold">Run Displacement Demo</span>
                  </button>
                </div>
              </div>

              {/* Environment */}
              <div>
                <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mb-3">Environment</h3>
                <div className="space-y-2">
                  {[
                    { label: 'Arctic (253 K)',  temp: 253.15, icon: '❄️' },
                    { label: 'Room (293 K)',    temp: 293.15, icon: '🌡️' },
                    { label: 'Hot (373 K)',     temp: 373.15, icon: '🔥' },
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

              {/* Usage hints */}
              <div className="bg-slate-900/60 rounded-lg border border-slate-700 p-3 text-xs text-slate-500 space-y-1">
                <div className="text-slate-400 font-semibold mb-1">How to interact</div>
                <div>• Click any block to select it, then push it</div>
                <div>• Enable Grid Place, then click the floor grid</div>
                <div>• High force (20+) generates heat on impact</div>
                <div>• Use Lever cards in Data tab to set angle</div>
                <div>• Build → Fill → Demo for displacement test</div>
                <div>• Delete individual fluid bodies in Data tab</div>
              </div>
            </>
          )}

          {/* DATA TAB */}
          {activeTab === 'data' && (
            <>
              <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Entity Data</h3>
              {(state?.entities || []).map(e => (
                <EntityCard
                  key={e.id}
                  entity={e}
                  selected={selectedId === e.id}
                  onSelect={handleSelectEntity}
                  onDelete={handleDelete}
                />
              ))}

              {(state?.lever_constraints ?? []).length > 0 && (
                <>
                  <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider mt-2">Lever Constraints</h3>
                  {(state?.lever_constraints ?? []).map(c => (
                    <LeverCard
                      key={c.lever_id}
                      constraint={c}
                      onSetAngle={handleSetLeverAngle}
                      onPush={handlePushLever}
                    />
                  ))}
                </>
              )}

              {fluidBodies.length > 0 && (
                <>
                  <div className="flex justify-between items-center mt-2">
                    <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wider">Fluid Bodies</h3>
                    <button
                      onClick={handleDeleteAllFluid}
                      className="text-[10px] text-red-400/70 hover:text-red-400 flex items-center gap-1"
                    >
                      <Trash2 className="w-3 h-3" /> Delete All
                    </button>
                  </div>
                  {fluidBodies.map(b => (
                    <FluidBodyCard
                      key={b.body_id}
                      body={b}
                      onDelete={handleDeleteFluid}
                    />
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
                <div className="text-slate-500 mb-2">Collision (Continuous Detection)</div>
                <div className="text-slate-400 text-[10px] leading-relaxed">
                  Using swept-AABB continuous collision detection. Every
                  tick, each entity's swept volume is tested against all others,
                  preventing tunnelling at any velocity. Restitution is derived
                  from the Hamming distance between Golay codewords of the two
                  colliding materials.
                </div>
              </div>
              <div className="bg-slate-900 p-3 rounded-lg border border-slate-700 text-xs font-mono space-y-1.5">
                <div className="text-slate-500 mb-2">Thermal (Kinetic→Heat)</div>
                <div className="text-slate-400 text-[10px] leading-relaxed">
                  On impact, kinetic energy ½mv² is partially converted to
                  thermal energy via ΔT = KE × (1−e) / (m × Cp), where e is
                  the restitution coefficient and Cp is the UBP heat capacity.
                  A 50 N force impact raises temperature by ~222 K.
                </div>
                {selectedEntity && (
                  <div className="mt-2 border-t border-slate-700 pt-2">
                    <div className="text-slate-500 mb-1">Selected entity</div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">{selectedEntity.label}</span>
                      <span className="text-orange-400">{selectedEntity.temperature_K.toFixed(2)} K</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-400">NRCI</span>
                      <span className="text-indigo-400">{selectedEntity.nrci.toFixed(4)}</span>
                    </div>
                  </div>
                )}
              </div>
              <div className="bg-slate-900 p-3 rounded-lg border border-slate-700 text-xs font-mono space-y-1.5">
                <div className="text-slate-500 mb-2">Fluid SPH (UBP-derived)</div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Smoothing h</span>
                  <span className="text-blue-400">Y_INV / 3 ≈ 1.26</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Pressure k</span>
                  <span className="text-blue-400">SINK×24/KISSING</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Viscosity μ</span>
                  <span className="text-blue-400">Y/96</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Surface σ</span>
                  <span className="text-blue-400">Y²/KISSING_NORM</span>
                </div>
                <div className="text-slate-400 text-[10px] mt-1 leading-relaxed">
                  Cohesion: molecules attract via surface tension kernel.
                  Two-way coupling: fluid pushes back on solid bodies.
                  Cross-body SPH: all fluid bodies interact with each other.
                </div>
              </div>
              <div className="bg-slate-900 p-3 rounded-lg border border-slate-700 text-xs font-mono space-y-1.5">
                <div className="text-slate-500 mb-2">Lever (Topological Torque)</div>
                <div className="flex justify-between">
                  <span className="text-slate-400">I = m×L²/12</span>
                  <span className="text-amber-400">×(1+NRCI)×Vol</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Damping</span>
                  <span className="text-amber-400">C_DRAG = Y²</span>
                </div>
                <div className="text-slate-400 text-[10px] mt-1 leading-relaxed">
                  Lever angle can be set directly via slider in Data tab.
                  Blocks placed on the lever arm create torque proportional
                  to mass × distance from pivot. The lever will tip and the
                  block will roll or slide depending on its NRCI.
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
          {/* UBP MECHANICS TAB */}
          {activeTab === 'ubp' && (
            <div className="space-y-4">
              <h3 className="text-xs font-semibold text-violet-400 uppercase tracking-wider">UBP Mechanics v4.0</h3>

              {/* Engine version badge */}
              <div className="bg-violet-900/20 border border-violet-500/30 rounded-lg p-3 text-xs font-mono">
                <div className="flex justify-between items-center">
                  <span className="text-violet-300 font-bold">Engine</span>
                  <span className="text-slate-300">{state?.engine_version ?? 'v4.0'}</span>
                </div>
                <div className="flex justify-between items-center mt-1">
                  <span className="text-violet-300">UBP Mechanics</span>
                  <span className={state?.ubp_mechanics ? 'text-emerald-400' : 'text-red-400'}>
                    {state?.ubp_mechanics ? '◉ ACTIVE' : '○ INACTIVE'}
                  </span>
                </div>
              </div>

              {/* Phi-Orbit Tick */}
              <div className="bg-slate-900 p-3 rounded-lg border border-violet-700/40 text-xs font-mono space-y-1.5">
                <div className="text-violet-400 font-semibold mb-1">Φ Phi-Orbit Tick (LAW_PHI_ORBIT_1953)</div>
                <div className="text-slate-400 text-[10px] leading-relaxed">
                  Each tick advances a 1-bit shift register XOR’d with a
                  phi-primitive derived from φ = 1.6180339887… The register
                  cycles through 1953 states, producing a deterministic
                  pseudo-random sequence with no floating-point drift.
                </div>
                <div className="flex justify-between mt-1">
                  <span className="text-slate-500">φ (golden ratio)</span>
                  <span className="text-violet-300">1.6180339887…</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Cycle length</span>
                  <span className="text-violet-300">1953 ticks</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Current tick mod 1953</span>
                  <span className="text-violet-300">{(state?.tick ?? 0) % 1953}</span>
                </div>
              </div>

              {/* Synthesis Collision */}
              <div className="bg-slate-900 p-3 rounded-lg border border-cyan-700/40 text-xs font-mono space-y-1.5">
                <div className="text-cyan-400 font-semibold mb-1">△ Synthesis Collision (Golay/Leech)</div>
                <div className="text-slate-400 text-[10px] leading-relaxed">
                  On entity collision, each material’s 24-bit Golay codeword
                  is XOR’d. The Hamming weight of the result determines the
                  restitution coefficient — high Hamming = more elastic,
                  low Hamming = more inelastic (materials “fit” together).
                </div>
                {synthesisLog.length > 0 ? (
                  <div className="mt-2 space-y-1">
                    <div className="text-slate-500 text-[10px] mb-1">Recent events (last 20)</div>
                    {synthesisLog.slice(0, 8).map((ev, i) => (
                      <div key={i} className="flex justify-between text-[10px] border-t border-slate-800 pt-1">
                        <span className="text-slate-400">t{ev.tick}: <span className="text-cyan-300">{ev.a}</span> × <span className="text-cyan-300">{ev.b}</span></span>
                        <span className="text-slate-300">H={ev.hamming} e={ev.restitution.toFixed(3)}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-slate-600 text-[10px] mt-1">No collisions yet — spawn blocks and push them together</div>
                )}
              </div>

              {/* NRCI / 13D Sink */}
              <div className="bg-slate-900 p-3 rounded-lg border border-red-700/40 text-xs font-mono space-y-1.5">
                <div className="text-red-400 font-semibold mb-1">★ NRCI / 13D Sink (LAW_13D_SINK_001)</div>
                <div className="text-slate-400 text-[10px] leading-relaxed">
                  NRCI (Non-Random Coherence Index) measures how well an
                  entity’s UBP vector aligns with the Golay codeword lattice.
                  When NRCI drops below the 13D Sink threshold (0.1618), the
                  entity enters dissolution and is culled from the simulation.
                </div>
                <div className="flex justify-between mt-1">
                  <span className="text-slate-500">Sink threshold</span>
                  <span className="text-red-400">0.1618 (φ⁻¹ × 0.2618)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Coherent (≥ 0.7)</span>
                  <span className="text-emerald-400">Green health bar</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Stressed (0.4–0.7)</span>
                  <span className="text-amber-400">Amber health bar</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Critical (&lt; 0.4)</span>
                  <span className="text-red-400">Red — near dissolution</span>
                </div>
              </div>

              {/* Leech Lattice */}
              <div className="bg-slate-900 p-3 rounded-lg border border-indigo-700/40 text-xs font-mono space-y-1.5">
                <div className="text-indigo-400 font-semibold mb-1">◇ Leech Lattice (LAW_TOPOLOGICAL_BUFFER_001)</div>
                <div className="text-slate-400 text-[10px] leading-relaxed">
                  Every entity’s 3D position is snapped to the nearest valid
                  Leech Lattice cell (24-dimensional Λ₂₄ projected to 3D via
                  the first three coordinates). The cell address is shown
                  in the entity card and the bottom-left HUD when selected.
                </div>
                <div className="flex justify-between mt-1">
                  <span className="text-slate-500">Lattice scale</span>
                  <span className="text-indigo-300">Y⁻¹ × 2 ≈ 7.556</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Cell notation</span>
                  <span className="text-indigo-300">[cx, cy, cz] integers</span>
                </div>
              </div>

              {/* Hybrid Stereoscopy (new KB entry) */}
              <div className="bg-slate-900 p-3 rounded-lg border border-yellow-700/40 text-xs font-mono space-y-1.5">
                <div className="text-yellow-400 font-semibold mb-1">★ Myo Oo Refinement (LAW_HYBRID_STEREOSCOPY_002)</div>
                <div className="text-slate-400 text-[10px] leading-relaxed">
                  The Baryonic Base mass is set by the 29/24 Sigma ratio,
                  locking the Proton phase to the Leech Lattice kissing
                  number (196560). This constant is used in the particle
                  physics substrate to derive rest mass from UBP geometry.
                </div>
                <div className="flex justify-between mt-1">
                  <span className="text-slate-500">Σ ratio</span>
                  <span className="text-yellow-300">29/24 = 1.20833…</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-500">Kissing number</span>
                  <span className="text-yellow-300">196560 (Λ₂₄)</span>
                </div>
              </div>

              {/* Engine Test Validator */}
              <div className="bg-slate-900 p-3 rounded-lg border border-emerald-700/40 text-xs font-mono space-y-2">
                <div className="text-emerald-400 font-semibold">Engine Test Validator</div>
                <div className="text-slate-400 text-[10px] leading-relaxed">
                  Runs the README engine_test.json scenario and checks all
                  NRCI values match the specification exactly.
                </div>
                <button
                  onClick={handleRunEngineTest}
                  disabled={engineTestLoading}
                  className="w-full py-2 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/30 rounded transition-colors disabled:opacity-50"
                >
                  {engineTestLoading ? 'Running…' : 'Run Engine Test'}
                </button>
                {engineTestResult && (
                  <div className="mt-2 space-y-1">
                    {engineTestResult.error ? (
                      <div className="text-red-400">✗ {engineTestResult.error}</div>
                    ) : (
                      <>
                        <div className={`font-bold ${engineTestResult.pass ? 'text-emerald-400' : 'text-red-400'}`}>
                          {engineTestResult.pass ? '✓ PHI-ORBIT PASS' : '✗ PHI-ORBIT FAIL'}
                        </div>
                        <div className="text-slate-400 text-[10px] mt-1">{engineTestResult.message}</div>
                        {(engineTestResult.ticks ?? []).slice(0, 5).map((t: any, i: number) => (
                          <div key={i} className="flex justify-between text-[10px] border-t border-slate-800 pt-1">
                            <span className="text-slate-500">Tick {t.tick}</span>
                            <span className="text-violet-300">P={t.Player?.toFixed(4)} W={t.Wall?.toFixed(4)}</span>
                          </div>
                        ))}
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
