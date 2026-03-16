import React, { useEffect, useState, useRef } from 'react';
import { Canvas } from '@react-three/fiber';
import { OrbitControls, Box, Sphere, Text } from '@react-three/drei';
import { Play, Pause, RotateCcw, Box as BoxIcon, Droplet, Activity } from 'lucide-react';

// --- Types ---
interface Vector3 {
  x: number;
  y: number;
  z: number;
}

interface EntityState {
  id: string;
  type: string;
  material: string;
  position: Vector3;
  rotation: Vector3;
  size: Vector3;
  colour: string;
  mass: number;
  nrci: number;
  temperature: number;
}

interface FluidParticleState {
  id: number;
  type: string;
  material: string;
  position: Vector3;
  velocity: Vector3;
  density: number;
  colour: string;
  size: Vector3;
}

interface SimulationState {
  tick: number;
  is_running: boolean;
  ambient: {
    temperature_K: number;
    pressure_ubp: number;
  };
  entities: EntityState[];
  fluid: FluidParticleState[];
}

// --- Components ---

const Entity = ({ data }: { data: EntityState }) => {
  return (
    <Box
      position={[data.position.x, data.position.y, data.position.z]}
      rotation={[data.rotation.x, data.rotation.y, data.rotation.z]}
      args={[data.size.x, data.size.y, data.size.z]}
    >
      <meshStandardMaterial color={data.colour} />
    </Box>
  );
};

const FluidParticle = ({ data }: { data: FluidParticleState }) => {
  return (
    <Sphere
      position={[data.position.x, data.position.y, data.position.z]}
      args={[data.size.x, 16, 16]}
    >
      <meshStandardMaterial color={data.colour} transparent opacity={0.8} />
    </Sphere>
  );
};

export default function App() {
  const [state, setState] = useState<SimulationState | null>(null);
  const [ws, setWs] = useState<WebSocket | null>(null);
  const [activeTab, setActiveTab] = useState('controls');

  useEffect(() => {
    // Connect to WebSocket
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws`);

    socket.onopen = () => {
      console.log('Connected to UBP Server');
      setWs(socket);
    };

    socket.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === 'state') {
        setState(msg.data);
      }
    };

    socket.onclose = () => {
      console.log('Disconnected from UBP Server');
      setWs(null);
    };

    return () => {
      socket.close();
    };
  }, []);

  const sendCommand = (command: string, payload: any = {}) => {
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: 'command', command, ...payload }));
    }
  };

  return (
    <div className="flex h-screen w-full bg-slate-900 text-slate-100 font-sans overflow-hidden">
      {/* 3D Viewport */}
      <div className="flex-1 relative">
        <Canvas camera={{ position: [0, 15, 25], fov: 50 }}>
          <ambientLight intensity={0.5} />
          <directionalLight position={[10, 20, 10]} intensity={1} castShadow />
          <OrbitControls makeDefault />
          
          {state?.entities.map((entity) => (
            <Entity key={entity.id} data={entity} />
          ))}
          
          {state?.fluid.map((particle) => (
            <FluidParticle key={`fluid-${particle.id}`} data={particle} />
          ))}
          
          <gridHelper args={[40, 40, '#475569', '#1e293b']} position={[0, 0, 0]} />
        </Canvas>

        {/* HUD */}
        <div className="absolute top-4 left-4 bg-slate-800/80 backdrop-blur-sm p-4 rounded-xl border border-slate-700 shadow-lg pointer-events-none">
          <h1 className="text-xl font-bold text-white mb-2 flex items-center gap-2">
            <Activity className="w-5 h-5 text-emerald-400" />
            UBP Digital Twin v3.0
          </h1>
          <div className="space-y-1 text-sm text-slate-300 font-mono">
            <p>Tick: {state?.tick || 0}</p>
            <p>Status: {state?.is_running ? <span className="text-emerald-400">Running</span> : <span className="text-amber-400">Paused</span>}</p>
            <p>Entities: {state?.entities.length || 0}</p>
            <p>Fluid Particles: {state?.fluid.length || 0}</p>
            <p>Ambient Temp: {state?.ambient.temperature_K.toFixed(2)} K</p>
          </div>
        </div>
      </div>

      {/* Sidebar Controls */}
      <div className="w-80 bg-slate-800 border-l border-slate-700 flex flex-col">
        <div className="p-4 border-b border-slate-700">
          <div className="flex gap-2">
            <button
              onClick={() => sendCommand(state?.is_running ? 'pause' : 'play')}
              className={`flex-1 flex items-center justify-center gap-2 py-2 rounded-lg font-medium transition-colors ${
                state?.is_running 
                  ? 'bg-amber-500/20 text-amber-400 hover:bg-amber-500/30' 
                  : 'bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30'
              }`}
            >
              {state?.is_running ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4" />}
              {state?.is_running ? 'Pause' : 'Play'}
            </button>
            <button
              onClick={() => sendCommand('reset')}
              className="p-2 bg-slate-700 text-slate-300 hover:bg-slate-600 rounded-lg transition-colors"
              title="Reset Simulation"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          </div>
        </div>

        <div className="flex border-b border-slate-700">
          <button
            className={`flex-1 py-3 text-sm font-medium transition-colors ${activeTab === 'controls' ? 'text-white border-b-2 border-indigo-500' : 'text-slate-400 hover:text-slate-200'}`}
            onClick={() => setActiveTab('controls')}
          >
            Controls
          </button>
          <button
            className={`flex-1 py-3 text-sm font-medium transition-colors ${activeTab === 'data' ? 'text-white border-b-2 border-indigo-500' : 'text-slate-400 hover:text-slate-200'}`}
            onClick={() => setActiveTab('data')}
          >
            Data
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4">
          {activeTab === 'controls' && (
            <div className="space-y-6">
              <div>
                <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider mb-3">Spawn Entities</h3>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    onClick={() => sendCommand('spawn_block', { material: 'iron', y: 15 })}
                    className="flex flex-col items-center gap-2 p-3 bg-slate-700/50 hover:bg-slate-700 rounded-lg border border-slate-600 transition-colors"
                  >
                    <BoxIcon className="w-5 h-5 text-slate-300" />
                    <span className="text-xs">Iron Block</span>
                  </button>
                  <button
                    onClick={() => sendCommand('spawn_block', { material: 'copper', y: 15 })}
                    className="flex flex-col items-center gap-2 p-3 bg-slate-700/50 hover:bg-slate-700 rounded-lg border border-slate-600 transition-colors"
                  >
                    <BoxIcon className="w-5 h-5 text-amber-500" />
                    <span className="text-xs">Copper Block</span>
                  </button>
                  <button
                    onClick={() => sendCommand('spawn_block', { material: 'gold', y: 15 })}
                    className="flex flex-col items-center gap-2 p-3 bg-slate-700/50 hover:bg-slate-700 rounded-lg border border-slate-600 transition-colors"
                  >
                    <BoxIcon className="w-5 h-5 text-yellow-400" />
                    <span className="text-xs">Gold Block</span>
                  </button>
                  <button
                    onClick={() => sendCommand('spawn_fluid')}
                    className="flex flex-col items-center gap-2 p-3 bg-slate-700/50 hover:bg-slate-700 rounded-lg border border-slate-600 transition-colors"
                  >
                    <Droplet className="w-5 h-5 text-blue-400" />
                    <span className="text-xs">Water Pool</span>
                  </button>
                </div>
              </div>
            </div>
          )}

          {activeTab === 'data' && (
            <div className="space-y-4">
              <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">Entity Data</h3>
              {state?.entities.map(e => (
                <div key={e.id} className="bg-slate-900 p-3 rounded-lg border border-slate-700 text-xs font-mono space-y-1">
                  <div className="flex justify-between text-slate-300">
                    <span className="font-bold">{e.id}</span>
                    <span className="text-indigo-400">{e.material}</span>
                  </div>
                  <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-slate-400">
                    <div>Mass: {e.mass.toFixed(2)}</div>
                    <div>NRCI: {e.nrci.toFixed(4)}</div>
                    <div>Temp: {e.temperature.toFixed(1)}K</div>
                    <div>Y: {e.position.y.toFixed(2)}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
