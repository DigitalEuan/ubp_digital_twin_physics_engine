import React, { useEffect, useMemo, useState } from 'react';

/**
 * DomainSpawnPalette — Slice 4
 *
 * A compact top-centre viewport ribbon that exposes domain-native spawn presets.
 * The schema comes live from `/v54/domain_presets` — nothing about the domain
 * list or parameter controls is hardcoded in App.tsx.
 */

export interface DomainPresetParam {
  type: 'number' | 'string' | 'boolean';
  default: number | string | boolean;
  label: string;
}

export interface DomainPresetDef {
  label: string;
  description: string;
  params?: Record<string, DomainPresetParam>;
  research_candidate?: boolean;
}

export interface DomainCatalogEntry {
  label: string;
  colour: string;
  presets: Record<string, DomainPresetDef>;
}

export interface DomainCatalogResponse {
  type?: string;
  catalog?: {
    domain_count: number;
    domains: Record<string, DomainCatalogEntry>;
  };
  world_physics?: any;
  error?: string;
}

export interface DomainSpawnPaletteProps {
  onSpawn: (payload: {
    domain: string;
    preset: string;
    params: Record<string, any>;
  }) => void;
}

const badgeLabel = (domain: string, entry: DomainCatalogEntry) => {
  if (entry.label.length <= 6) return entry.label;
  return domain
    .split('_')
    .map(w => w[0]?.toUpperCase() ?? '')
    .join('')
    .slice(0, 4);
};

const DomainSpawnPalette: React.FC<DomainSpawnPaletteProps> = ({ onSpawn }) => {
  const [catalog, setCatalog] = useState<Record<string, DomainCatalogEntry>>({});
  const [openDomain, setOpenDomain] = useState<string | null>(null);
  const [selectedPreset, setSelectedPreset] = useState<string | null>(null);
  const [params, setParams] = useState<Record<string, any>>({});
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const r = await fetch('/v54/domain_presets');
        const j: DomainCatalogResponse = await r.json();
        if (cancelled) return;
        if (j.error) {
          setError(j.error);
          return;
        }
        setCatalog(j.catalog?.domains ?? {});
      } catch (e) {
        if (!cancelled) setError(String(e));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const domainEntry = openDomain ? catalog[openDomain] : null;
  const presetEntry = (openDomain && selectedPreset && domainEntry)
    ? domainEntry.presets[selectedPreset]
    : null;

  const initialisePreset = (domain: string, preset: string) => {
    const p = catalog[domain]?.presets?.[preset];
    const defaults: Record<string, any> = {};
    Object.entries(p?.params ?? {}).forEach(([k, def]) => {
      defaults[k] = def.default;
    });
    setParams(defaults);
    setSelectedPreset(preset);
  };

  const sortedDomains = useMemo(() => Object.entries(catalog), [catalog]);

  return (
    <div className="absolute top-3 left-1/2 -translate-x-1/2 z-30 flex flex-col items-center gap-2 pointer-events-auto">
      {/* Ribbon */}
      <div className="max-w-[90vw] flex flex-wrap justify-center gap-1.5 px-2 py-2 bg-slate-900/90 border border-slate-700 rounded-xl backdrop-blur shadow-xl">
        {loading && <div className="text-xs text-slate-400 px-2 py-1">Loading domains…</div>}
        {!loading && sortedDomains.map(([domain, entry]) => {
          const active = domain === openDomain;
          return (
            <button
              key={domain}
              onClick={() => {
                if (active) {
                  setOpenDomain(null);
                  setSelectedPreset(null);
                } else {
                  setOpenDomain(domain);
                  const firstPreset = Object.keys(entry.presets)[0] ?? null;
                  if (firstPreset) initialisePreset(domain, firstPreset);
                }
              }}
              className={`px-2.5 py-1 rounded-lg border text-[11px] font-semibold transition-colors ${
                active ? 'bg-white/10 border-white/30 text-white' : 'bg-slate-800/70 border-slate-700 text-slate-300 hover:bg-slate-800'
              }`}
              title={entry.label}
              style={active ? { boxShadow: `0 0 0 1px ${entry.colour}66 inset` } : undefined}
            >
              <span style={{ color: entry.colour }}>{badgeLabel(domain, entry)}</span>
            </button>
          );
        })}
      </div>

      {/* Popover */}
      {(domainEntry || error) && (
        <div className="w-[420px] max-w-[92vw] bg-slate-900/95 border border-slate-700 rounded-xl backdrop-blur shadow-2xl overflow-hidden">
          {error ? (
            <div className="p-3 text-xs text-red-300">{error}</div>
          ) : domainEntry && openDomain ? (
            <>
              <div className="px-3 py-2 border-b border-slate-700 flex items-center justify-between">
                <div>
                  <div className="text-sm font-semibold" style={{ color: domainEntry.colour }}>
                    {domainEntry.label}
                  </div>
                  <div className="text-[10px] text-slate-500">
                    Domain-native presets — values resolved live from the physics registry
                  </div>
                </div>
                <button
                  onClick={() => {
                    setOpenDomain(null);
                    setSelectedPreset(null);
                  }}
                  className="px-2 py-1 text-xs bg-slate-800 rounded hover:bg-slate-700"
                >
                  ✕
                </button>
              </div>

              <div className="p-3 space-y-3 text-xs font-mono">
                <div className="flex flex-wrap gap-1">
                  {Object.entries(domainEntry.presets).map(([presetId, preset]) => {
                    const active = presetId === selectedPreset;
                    return (
                      <button
                        key={presetId}
                        onClick={() => initialisePreset(openDomain, presetId)}
                        className={`px-2 py-1 rounded border transition-colors ${
                          active ? 'border-cyan-500/50 bg-cyan-500/10 text-cyan-200' : 'border-slate-700 bg-slate-800 text-slate-300 hover:bg-slate-700'
                        }`}
                      >
                        {preset.label}{preset.research_candidate ? ' 🧪' : ''}
                      </button>
                    );
                  })}
                </div>

                {presetEntry && (
                  <>
                    <div className="text-[11px] text-slate-300 leading-relaxed">
                      {presetEntry.description}
                      {presetEntry.research_candidate && (
                        <div className="mt-1 text-fuchsia-400 text-[10px] italic">
                          UBP research candidate — not null-model validated
                        </div>
                      )}
                    </div>

                    {Object.keys(presetEntry.params ?? {}).length > 0 && (
                      <div className="grid grid-cols-1 gap-2">
                        {Object.entries(presetEntry.params ?? {}).map(([key, def]) => (
                          <label key={key} className="block">
                            <div className="text-[10px] text-slate-500 mb-1">{def.label}</div>
                            {def.type === 'number' ? (
                              <input
                                type="number"
                                value={params[key] ?? def.default}
                                onChange={(e) => setParams(p => ({ ...p, [key]: parseFloat(e.target.value) }))}
                                className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200"
                              />
                            ) : (
                              <input
                                type="text"
                                value={String(params[key] ?? def.default)}
                                onChange={(e) => setParams(p => ({ ...p, [key]: e.target.value }))}
                                className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200"
                              />
                            )}
                          </label>
                        ))}
                      </div>
                    )}

                    <div className="flex items-center justify-between gap-2 pt-1">
                      <div className="text-[10px] text-slate-500">
                        Spawns into the live 3D world and tags the entity with domain metadata.
                      </div>
                      <button
                        onClick={() => {
                          if (!openDomain || !selectedPreset) return;
                          onSpawn({
                            domain: openDomain,
                            preset: selectedPreset,
                            params,
                          });
                        }}
                        className="px-3 py-1.5 rounded bg-cyan-600/20 hover:bg-cyan-600/30 border border-cyan-500/40 text-cyan-200 text-xs font-semibold"
                      >
                        Spawn in 3D space
                      </button>
                    </div>
                  </>
                )}
              </div>
            </>
          ) : null}
        </div>
      )}
    </div>
  );
};

export default DomainSpawnPalette;
