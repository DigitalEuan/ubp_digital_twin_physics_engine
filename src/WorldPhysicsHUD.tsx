import React, { useState, useEffect, useCallback, useMemo } from 'react';

export interface WorldPhysicsData {
  gravity_mode: 'earth' | 'moon' | 'mars' | 'zero' | 'newtonian' | 'hubble' | string;
  gravity_ms2: number;
  gravity_vector: [number, number, number] | number[];
  ambient_temperature_K: number;
  speed_of_sound_ms: number;
  hubble_h0_km_s_mpc: number;
  newton_G: number;
  em_enabled: boolean;
  gravity_pair_enabled: boolean;
  cosmology_scale: number;
  sources?: Record<string, string>;
}

export interface AlignmentSummary {
  reality_score?: number;
  mean_abs_err_pct?: number;
  entity_alignment_count?: number;
}

interface WorldScenarioSpec {
  label: string;
  description: string;
  updates: Partial<WorldPhysicsData>;
  use_cases?: string[];
}

const GRAVITY_MODES: Array<{ id: WorldPhysicsData['gravity_mode']; label: string; hint: string }> = [
  { id: 'earth',     label: 'Earth',      hint: 'g = 9.81 m/s² (core_entity.G_EARTH_MS2)' },
  { id: 'moon',      label: 'Moon',       hint: 'g ≈ 1.62 m/s² (derived from astrophysics + cosmology.G)' },
  { id: 'mars',      label: 'Mars',       hint: 'g ≈ 3.71 m/s² (derived from astrophysics + cosmology.G)' },
  { id: 'zero',      label: 'Zero-g',     hint: 'gravity_ms2 = 0 (freefall workspace)' },
  { id: 'newtonian', label: 'Newtonian',  hint: 'Pairwise G·m₁·m₂/r² without Earth background' },
  { id: 'hubble',    label: 'Hubble',     hint: 'Expansion mode H₀·r with Slice 9 drift' },
];

export interface WorldPhysicsHUDProps {
  liveState?: Partial<WorldPhysicsData> | null;
  alignment?: AlignmentSummary | null;
}

export const WorldPhysicsHUD: React.FC<WorldPhysicsHUDProps> = ({ liveState, alignment }) => {
  const [state, setState] = useState<WorldPhysicsData | null>(null);
  const [busy, setBusy] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [scenarioCatalog, setScenarioCatalog] = useState<Record<string, WorldScenarioSpec>>({});
  const [lastScenario, setLastScenario] = useState<string | null>(null);

  useEffect(() => {
    if (liveState && liveState.gravity_mode) {
      setState(prev => ({ ...(prev ?? {} as WorldPhysicsData), ...(liveState as WorldPhysicsData) }));
    }
  }, [liveState]);

  const refresh = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      const [worldRes, scenarioRes] = await Promise.all([
        fetch('/v54/world_physics'),
        fetch('/v54/world_scenarios'),
      ]);
      const worldJson = await worldRes.json();
      const scenarioJson = await scenarioRes.json();
      if (worldJson.error) setError(worldJson.error);
      else if (worldJson.data) setState(worldJson.data);
      if (!scenarioJson.error && scenarioJson.catalog) setScenarioCatalog(scenarioJson.catalog);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const update = async (updates: Partial<WorldPhysicsData>) => {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch('/v54/world_physics/set', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ updates }),
      });
      const j = await r.json();
      if (j.error) setError(j.error);
      if (j.data) setState(j.data);
      setLastScenario(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const applyScenario = async (scenarioId: string) => {
    setBusy(true);
    setError(null);
    try {
      const r = await fetch('/v54/world_scenarios/apply', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario_id: scenarioId }),
      });
      const j = await r.json();
      if (j.error) setError(j.error);
      if (j.data) setState(j.data);
      else if (j.world_physics) setState(j.world_physics);
      else if (j.applied && liveState) setState(prev => ({ ...(prev ?? {} as WorldPhysicsData), ...(liveState as WorldPhysicsData) }));
      setLastScenario(scenarioId);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  };

  const scoreColour = useMemo(() => {
    const score = alignment?.reality_score ?? 0;
    if (score >= 90) return 'text-emerald-300';
    if (score >= 60) return 'text-yellow-300';
    if (score >= 30) return 'text-orange-300';
    return 'text-red-300';
  }, [alignment?.reality_score]);

  const Chip = () => (
    <button
      onClick={() => setExpanded(!expanded)}
      className="flex items-center gap-2 px-3 py-1.5 bg-slate-900/90 border border-amber-500/40 rounded-lg text-xs font-mono hover:bg-slate-900 backdrop-blur transition-colors"
      title="World Physics controls"
    >
      <span className="text-amber-200">🌐</span>
      <span className="text-amber-100">
        {state ? `${state.gravity_mode} · g=${state.gravity_ms2.toFixed(2)} · T=${Math.round(state.ambient_temperature_K)}K` : busy ? 'Loading…' : '—'}
      </span>
      {alignment?.reality_score !== undefined && (
        <span className={`font-semibold ${scoreColour}`}>R={alignment.reality_score.toFixed(1)}</span>
      )}
      <span className="text-slate-500">{expanded ? '▾' : '▸'}</span>
    </button>
  );

  const Panel = () => {
    if (!state) return <div className="p-3 text-slate-400 text-xs">Loading world physics…</div>;
    return (
      <div className="space-y-3 p-3 text-xs font-mono">
        <div className="rounded border border-slate-700 bg-slate-800/40 p-2">
          <div className="text-amber-300 uppercase text-[10px] tracking-wide mb-1">Reality coupling</div>
          <div className="grid grid-cols-3 gap-2 text-[10px]">
            <div>
              <div className="text-slate-500">Reality</div>
              <div className={`text-lg font-bold ${scoreColour}`}>{alignment?.reality_score?.toFixed(1) ?? '—'}</div>
            </div>
            <div>
              <div className="text-slate-500">Mean err</div>
              <div className="text-slate-200">{alignment?.mean_abs_err_pct?.toFixed(3) ?? '—'}%</div>
            </div>
            <div>
              <div className="text-slate-500">Checks</div>
              <div className="text-slate-200">{alignment?.entity_alignment_count ?? 0}</div>
            </div>
          </div>
          <div className="text-slate-500 text-[10px] mt-1">
            Scenario switches re-score on the next live tick — no reload required.
          </div>
        </div>

        <div>
          <div className="text-amber-300 uppercase text-[10px] tracking-wide mb-1">World scenarios (Slice 11)</div>
          <div className="grid grid-cols-2 gap-1.5">
            {Object.entries(scenarioCatalog).map(([id, spec]) => (
              <button
                key={id}
                onClick={() => applyScenario(id)}
                disabled={busy}
                title={spec.description}
                className={`px-2 py-1.5 rounded border text-left transition-colors ${
                  lastScenario === id ? 'bg-cyan-500/15 border-cyan-500/50 text-cyan-100' : 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700'
                } disabled:opacity-50`}
              >
                <div className="font-semibold text-[11px]">{spec.label}</div>
                <div className="text-[9px] text-slate-500 truncate">{spec.use_cases?.join(' · ')}</div>
              </button>
            ))}
          </div>
          {lastScenario && scenarioCatalog[lastScenario] && (
            <div className="text-[10px] text-cyan-300 mt-1">
              Active scenario: {scenarioCatalog[lastScenario].label}
            </div>
          )}
        </div>

        <div>
          <div className="text-amber-300 uppercase text-[10px] tracking-wide mb-1">Gravity mode</div>
          <div className="grid grid-cols-3 gap-1">
            {GRAVITY_MODES.map(m => (
              <button
                key={m.id}
                title={m.hint}
                onClick={() => update({ gravity_mode: m.id })}
                disabled={busy}
                className={`px-2 py-1 rounded border transition-colors ${state.gravity_mode === m.id ? 'bg-amber-500/20 border-amber-500/60 text-amber-100' : 'bg-slate-800 border-slate-700 text-slate-300 hover:bg-slate-700'} disabled:opacity-50`}
              >
                {m.label}
              </button>
            ))}
          </div>
          <div className="text-slate-500 text-[10px] mt-1">
            g = {state.gravity_ms2.toExponential(4)} m/s² {state.gravity_pair_enabled && '· pairwise attraction ON'}
          </div>
        </div>

        <div>
          <div className="text-amber-300 uppercase text-[10px] tracking-wide mb-1">Ambient temperature</div>
          <div className="flex items-center gap-2">
            <input
              type="range"
              min={2.7}
              max={800}
              step={0.1}
              value={state.ambient_temperature_K}
              onChange={e => update({ ambient_temperature_K: parseFloat(e.target.value) })}
              disabled={busy}
              className="flex-1"
            />
            <span className="text-amber-100 w-16 text-right">{state.ambient_temperature_K.toFixed(1)} K</span>
          </div>
          <div className="text-slate-500 text-[10px] mt-1">
            = {(state.ambient_temperature_K - 273.15).toFixed(1)} °C · v_sound = {state.speed_of_sound_ms.toFixed(1)} m/s
          </div>
        </div>

        <div>
          <div className="text-amber-300 uppercase text-[10px] tracking-wide mb-1">Cosmology scale</div>
          <div className="flex items-center gap-2">
            <input
              type="range"
              min={-15}
              max={-5}
              step={0.5}
              value={Math.log10(state.cosmology_scale)}
              onChange={e => update({ cosmology_scale: Math.pow(10, parseFloat(e.target.value)) })}
              disabled={busy}
              className="flex-1"
            />
            <span className="text-amber-100 w-24 text-right">10^{Math.log10(state.cosmology_scale).toFixed(1)}</span>
          </div>
          <div className="text-slate-500 text-[10px] mt-1">1 workspace metre = {(1 / state.cosmology_scale).toExponential(2)} real metres</div>
        </div>

        <div>
          <div className="text-amber-300 uppercase text-[10px] tracking-wide mb-1">Force couplers</div>
          <div className="space-y-1">
            <label className="flex items-center gap-2 text-slate-300">
              <input type="checkbox" checked={state.gravity_pair_enabled} onChange={e => update({ gravity_pair_enabled: e.target.checked })} disabled={busy} />
              <span>Newtonian gravity (G·m₁·m₂/r²)</span>
            </label>
            <label className="flex items-center gap-2 text-slate-300">
              <input type="checkbox" checked={state.em_enabled} onChange={e => update({ em_enabled: e.target.checked })} disabled={busy} />
              <span>Coulomb interaction (k_e·q₁·q₂/r²)</span>
            </label>
          </div>
        </div>

        <div className="pt-2 border-t border-slate-700">
          <div className="text-slate-500 uppercase text-[10px] tracking-wide mb-1">Constants (read-only)</div>
          <div className="grid grid-cols-2 gap-x-2 text-[10px]">
            <div className="flex justify-between"><span className="text-slate-400">H₀</span><span className="text-slate-300">{state.hubble_h0_km_s_mpc.toFixed(3)}</span></div>
            <div className="flex justify-between"><span className="text-slate-400">G</span><span className="text-slate-300">{state.newton_G.toExponential(3)}</span></div>
          </div>
          <div className="text-slate-500 text-[9px] mt-1 italic">H₀ = (1/3)wY³U_e · G = (39/29)Y¹⁸/w</div>
        </div>

        {error && <div className="text-red-300 text-[10px] border border-red-500/40 rounded p-1.5 bg-red-500/10">{error}</div>}
      </div>
    );
  };

  return (
    <div className={`absolute bottom-3 left-3 z-30 ${expanded ? 'w-[360px]' : ''}`}>
      <Chip />
      {expanded && <div className="mt-2 bg-slate-900/95 border border-amber-500/40 rounded-lg overflow-hidden backdrop-blur shadow-2xl"><Panel /></div>}
    </div>
  );
};

export default WorldPhysicsHUD;
