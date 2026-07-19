/**
 * RealityAlignmentHUD (Slice 10) — LIVE reality-alignment scoreboard.
 *
 * Reads state.reality_alignment (streamed via WS on every tick) and renders:
 *   - the world Reality Score (0-100)
 *   - per-domain error % + status pie
 *   - per-entity list with GREEN/YELLOW/ORANGE/RED/RESEARCH badges
 *   - recent decay events fed by Slice 9 (state.recent_decay_events)
 */
import React, { useMemo } from 'react';

export interface AlignmentEntity {
  entity_id: number;
  label: string;
  domain_tag: string;
  domain_role?: string | null;
  entity_value?: number | null;
  canonical_value?: number | null;
  source: string;
  error_pct?: number | null;
  status: 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED' | 'RESEARCH' | 'NO_REFERENCE';
  research_candidate?: boolean;
  formula_source?: string | null;
}
export interface AlignmentPerDomain {
  count: number;
  green: number; yellow: number; orange: number; red: number; research: number;
  mean_abs_err_pct: number;
  worst_pct: number;
  worst_label?: string | null;
}
export interface AlignmentPayload {
  reality_score: number;
  mean_abs_err_pct: number;
  entity_alignment_count: number;
  research_candidate_count: number;
  per_entity: AlignmentEntity[];
  per_domain: Record<string, AlignmentPerDomain>;
  error?: string;
}
export interface DecayEvent {
  tick: number;
  kind: string;
  entity_id: number;
  label: string;
  detail?: Record<string, any>;
}

export interface RealityAlignmentHUDProps {
  alignment?: AlignmentPayload | null;
  decayEvents?: DecayEvent[];
  floating?: boolean;
}

const statusColour = (status: AlignmentEntity['status']) => {
  switch (status) {
    case 'GREEN': return '#22c55e';
    case 'YELLOW': return '#eab308';
    case 'ORANGE': return '#f97316';
    case 'RED': return '#ef4444';
    case 'RESEARCH': return '#c084fc';
    default: return '#94a3b8';
  }
};

const fmt = (n: number | null | undefined, digits = 4) => {
  if (n === null || n === undefined || !Number.isFinite(n)) return '—';
  const abs = Math.abs(n);
  if (abs !== 0 && (abs < 1e-3 || abs >= 1e5)) return n.toExponential(digits);
  return n.toFixed(digits);
};

const scoreColour = (score: number) => {
  if (score >= 90) return '#22c55e';
  if (score >= 60) return '#eab308';
  if (score >= 30) return '#f97316';
  return '#ef4444';
};

export const RealityAlignmentHUD: React.FC<RealityAlignmentHUDProps> = ({
  alignment,
  decayEvents,
  floating = true,
}) => {
  const perDomain = alignment?.per_domain ?? {};
  const perEntity = alignment?.per_entity ?? [];
  const recentDecays = (decayEvents ?? []).slice(-6).reverse();

  const domainRows = useMemo(
    () => Object.entries(perDomain).sort((a, b) => b[1].mean_abs_err_pct - a[1].mean_abs_err_pct),
    [perDomain],
  );

  return (
    <div className={`bg-slate-900/92 border border-slate-700 rounded-xl backdrop-blur shadow-2xl w-[360px] max-h-[75vh] overflow-hidden flex flex-col ${floating ? '' : 'w-full'}`}>
      <div className="px-3 py-2 border-b border-slate-700 flex items-center justify-between">
        <div className="text-[11px] uppercase tracking-wider text-slate-400 font-mono">Reality Alignment</div>
        <div className="text-[10px] text-slate-500">
          {alignment ? `${alignment.entity_alignment_count} checks` : 'waiting'}
        </div>
      </div>

      <div className="px-3 py-3 border-b border-slate-700 grid grid-cols-3 gap-2 text-[11px]">
        <div>
          <div className="text-slate-500 uppercase text-[9px] tracking-wide">Reality Score</div>
          <div className="text-2xl font-bold" style={{ color: scoreColour(alignment?.reality_score ?? 0) }}>
            {alignment ? (alignment.reality_score).toFixed(1) : '—'}
          </div>
        </div>
        <div>
          <div className="text-slate-500 uppercase text-[9px] tracking-wide">Mean Err %</div>
          <div className="text-lg text-slate-200">{alignment ? alignment.mean_abs_err_pct.toFixed(3) : '—'}</div>
        </div>
        <div>
          <div className="text-slate-500 uppercase text-[9px] tracking-wide">Research</div>
          <div className="text-lg text-fuchsia-300">{alignment?.research_candidate_count ?? 0}</div>
        </div>
      </div>

      {alignment?.error && (
        <div className="mx-3 my-2 text-[11px] text-red-300 bg-red-500/10 border border-red-500/20 rounded px-2 py-1">
          {alignment.error}
        </div>
      )}

      <div className="px-3 py-2 border-b border-slate-700">
        <div className="text-[10px] uppercase tracking-wider text-slate-500 font-mono mb-1">Per-domain</div>
        {domainRows.length === 0 && (
          <div className="text-[11px] text-slate-500 italic">Spawn a domain object to start scoring.</div>
        )}
        <div className="space-y-1">
          {domainRows.map(([domain, row]) => (
            <div key={domain} className="flex items-center justify-between text-[11px]">
              <div className="text-slate-300 truncate max-w-[130px]" title={domain}>{domain}</div>
              <div className="flex items-center gap-1">
                <span title="green" className="w-2 h-2 rounded-full" style={{ background: '#22c55e', opacity: row.green ? 1 : 0.2 }} />
                <span title="yellow" className="w-2 h-2 rounded-full" style={{ background: '#eab308', opacity: row.yellow ? 1 : 0.2 }} />
                <span title="orange" className="w-2 h-2 rounded-full" style={{ background: '#f97316', opacity: row.orange ? 1 : 0.2 }} />
                <span title="red" className="w-2 h-2 rounded-full" style={{ background: '#ef4444', opacity: row.red ? 1 : 0.2 }} />
                {row.research > 0 && <span title="research" className="w-2 h-2 rounded-full" style={{ background: '#c084fc' }} />}
              </div>
              <div className="text-slate-400 tabular-nums">{row.mean_abs_err_pct.toFixed(3)}%</div>
            </div>
          ))}
        </div>
      </div>

      <div className="flex-1 overflow-auto px-3 py-2 border-b border-slate-700">
        <div className="text-[10px] uppercase tracking-wider text-slate-500 font-mono mb-1">Per-entity</div>
        {perEntity.length === 0 && <div className="text-[11px] text-slate-500 italic">Nothing to score yet.</div>}
        <div className="space-y-1.5">
          {perEntity.slice(0, 40).map((r, i) => (
            <div key={`${r.entity_id}-${i}`} className="rounded border border-slate-800 bg-slate-800/40 px-2 py-1.5">
              <div className="flex items-center justify-between text-[11px]">
                <div className="text-slate-200 truncate max-w-[190px]" title={r.label}>{r.label}</div>
                <span
                  className="text-[9px] uppercase font-bold tracking-wide px-1.5 py-0.5 rounded"
                  style={{ color: statusColour(r.status), border: `1px solid ${statusColour(r.status)}44` }}
                >{r.status}</span>
              </div>
              <div className="grid grid-cols-2 gap-x-2 text-[10px] text-slate-400 mt-1">
                <div>err: <span style={{ color: statusColour(r.status) }}>{r.error_pct === null || r.error_pct === undefined ? 'n/a' : `${r.error_pct.toExponential(2)}%`}</span></div>
                <div>src: <span className="text-slate-300 truncate" title={r.source}>{r.source}</span></div>
                <div>entity: <span className="text-slate-300">{fmt(r.entity_value)}</span></div>
                <div>canon: <span className="text-slate-300">{fmt(r.canonical_value)}</span></div>
              </div>
              {r.research_candidate && (
                <div className="text-[10px] italic text-fuchsia-300 mt-1">
                  UBP research candidate — not null-model validated
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      <div className="px-3 py-2">
        <div className="text-[10px] uppercase tracking-wider text-slate-500 font-mono mb-1">
          Recent decays <span className="text-slate-600">(Slice 9)</span>
        </div>
        {recentDecays.length === 0 && <div className="text-[11px] text-slate-500 italic">None yet.</div>}
        <div className="space-y-1">
          {recentDecays.map(ev => (
            <div key={`${ev.tick}-${ev.entity_id}`} className="text-[10px] text-slate-300 flex justify-between">
              <span className="truncate max-w-[220px]" title={ev.label}>t={ev.tick} · {ev.label}</span>
              <span className="text-fuchsia-300 uppercase">{ev.kind}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
