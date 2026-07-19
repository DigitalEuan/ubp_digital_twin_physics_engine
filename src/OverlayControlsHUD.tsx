import React from 'react';

export interface OverlayControlsState {
  staticOverlays: boolean;
  gravityField: boolean;
  emField: boolean;
  thermalField: boolean;
}

export interface OverlayControlsHUDProps {
  value: OverlayControlsState;
  onChange: (next: OverlayControlsState) => void;
}

const Toggle = ({ active, onClick, label, colour }: { active: boolean; onClick: () => void; label: string; colour: string }) => (
  <button
    onClick={onClick}
    className={`px-2.5 py-1.5 rounded-lg border text-[11px] font-mono transition-colors ${
      active ? 'text-white border-white/30 bg-white/10' : 'text-slate-300 border-slate-700 bg-slate-800/80 hover:bg-slate-700'
    }`}
    style={active ? { boxShadow: `0 0 0 1px ${colour}55 inset` } : undefined}
  >
    <span style={{ color: active ? colour : undefined }}>{label}</span>
  </button>
);

const OverlayControlsHUD: React.FC<OverlayControlsHUDProps> = ({ value, onChange }) => {
  return (
    <div className="absolute right-4 bottom-4 z-30 pointer-events-auto bg-slate-900/90 border border-slate-700 rounded-xl backdrop-blur shadow-xl px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-slate-500 font-mono mb-2">Workspace overlays</div>
      <div className="flex flex-wrap gap-1.5">
        <Toggle active={value.staticOverlays} onClick={() => onChange({ ...value, staticOverlays: !value.staticOverlays })} label="Static" colour="#a78bfa" />
        <Toggle active={value.gravityField} onClick={() => onChange({ ...value, gravityField: !value.gravityField })} label="Gravity" colour="#f59e0b" />
        <Toggle active={value.emField} onClick={() => onChange({ ...value, emField: !value.emField })} label="EM" colour="#38bdf8" />
        <Toggle active={value.thermalField} onClick={() => onChange({ ...value, thermalField: !value.thermalField })} label="Thermal" colour="#ef4444" />
      </div>
      <div className="mt-2 text-[10px] text-slate-500 max-w-[250px] leading-relaxed">
        Static overlays show domain-native structures. Field overlays sample the live world and draw vector/scalar glyphs in the 3D viewport.
      </div>
    </div>
  );
};

export default OverlayControlsHUD;
