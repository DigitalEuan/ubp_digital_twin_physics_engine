import React, { useEffect, useMemo, useState } from 'react';
import { Line, Text } from '@react-three/drei';
import * as THREE from 'three';

interface Vec3 { x: number; y: number; z: number; }
interface DomainEntityLike {
  id: number;
  label: string;
  position: Vec3;
  size: Vec3;
  temperature_K: number;
  domain_tag?: string;
  domain_role?: string;
  domain_params?: Record<string, any>;
  formula_source?: string;
  research_candidate?: boolean;
  render_shape?: string;
  display_colour?: string;
  colour?: string;
}
interface SimulationStateLike {
  tick: number;
  entities: DomainEntityLike[];
}
interface SamplePoint {
  point: Vec3;
  vector?: Vec3;
  scalar?: number;
  delta_K?: number;
  magnitude?: number;
  ambient_temperature_K?: number;
}
export interface DomainOverlaysProps {
  state: SimulationStateLike | null;
  showStaticOverlays: boolean;
  showGravityField: boolean;
  showEMField: boolean;
  showThermalField: boolean;
}

const circlePoints = (radius: number, y = 0, segments = 48) => {
  const pts: [number, number, number][] = [];
  for (let i = 0; i <= segments; i += 1) {
    const t = (i / segments) * Math.PI * 2;
    pts.push([Math.cos(t) * radius, y, Math.sin(t) * radius]);
  }
  return pts;
};

const centerOf = (e: DomainEntityLike): Vec3 => ({
  x: e.position.x + e.size.x / 2,
  y: e.position.y + e.size.y / 2,
  z: e.position.z + e.size.z / 2,
});

const clamp = (x: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, x));

const fieldScale = (magnitude: number, mode: 'gravity' | 'em') => {
  if (!Number.isFinite(magnitude) || magnitude <= 0) return 0;
  const log = Math.log10(magnitude + 1);
  return mode === 'gravity' ? clamp(0.25 + 0.22 * log, 0.2, 2.0) : clamp(0.25 + 0.16 * log, 0.2, 2.0);
};

const thermalColour = (deltaK: number) => {
  if (deltaK > 40) return '#ef4444';
  if (deltaK > 10) return '#f97316';
  if (deltaK > 2) return '#f59e0b';
  if (deltaK < -40) return '#2563eb';
  if (deltaK < -10) return '#38bdf8';
  if (deltaK < -2) return '#67e8f9';
  return '#94a3b8';
};

const StaticOverlay: React.FC<{ entity: DomainEntityLike }> = ({ entity }) => {
  const c = centerOf(entity);
  const p = entity.domain_params ?? {};
  const colour = entity.display_colour || entity.colour || '#a78bfa';
  const maxSize = Math.max(entity.size.x, entity.size.y, entity.size.z);

  if (entity.domain_role === 'bohr_atom') {
    const scale = Number(p.interaction_scale_m_per_cell || 1);
    const orbitM = Number(p.orbital_radius_m || p.bohr_radius_m || 0);
    const radius = clamp(scale > 0 && orbitM > 0 ? orbitM / scale : maxSize * 1.25, 0.8, 3.0);
    return (
      <group position={[c.x, c.y, c.z]}>
        <Line points={circlePoints(radius)} color="#c084fc" lineWidth={1.2} transparent opacity={0.8} />
        <Line points={circlePoints(radius * 0.72).map(([x, y, z]) => [x, z * 0.2, y])} color="#8b5cf6" lineWidth={1} transparent opacity={0.5} />
      </group>
    );
  }

  if (entity.domain_tag === 'nuclear_physics' || entity.domain_tag === 'high_energy_physics') {
    const radius = clamp(maxSize * 0.8, 0.45, 1.5);
    return (
      <mesh position={[c.x, c.y, c.z]}>
        <sphereGeometry args={[radius, 20, 20]} />
        <meshBasicMaterial color={colour} wireframe transparent opacity={0.45} />
      </mesh>
    );
  }

  if (entity.domain_tag === 'astrophysics' || entity.domain_role === 'black_hole') {
    const scale = Number(p.interaction_scale_m_per_cell || 1);
    const rs = Number(p.schwarzschild_radius_m || 0);
    const radius = clamp(scale > 0 && rs > 0 ? rs / scale : maxSize * 1.5, 0.75, 4.0);
    return (
      <group position={[c.x, c.y, c.z]}>
        <mesh>
          <ringGeometry args={[radius * 1.15, radius * 1.45, 48]} />
          <meshBasicMaterial color="#f59e0b" transparent opacity={0.18} side={THREE.DoubleSide} />
        </mesh>
        <mesh rotation={[Math.PI / 2, 0, 0]}>
          <ringGeometry args={[radius * 1.25, radius * 1.6, 48]} />
          <meshBasicMaterial color="#fb7185" transparent opacity={0.18} side={THREE.DoubleSide} />
        </mesh>
      </group>
    );
  }

  if (entity.domain_tag === 'condensed_matter') {
    const r = clamp(maxSize * 0.8, 0.7, 2.0);
    return (
      <group position={[c.x, c.y, c.z]}>
        <Line points={[[-r, -r, -r], [r, -r, -r], [r, r, -r], [-r, r, -r], [-r, -r, -r]]} color="#22c55e" lineWidth={1} />
        <Line points={[[-r, -r, r], [r, -r, r], [r, r, r], [-r, r, r], [-r, -r, r]]} color="#22c55e" lineWidth={1} />
        <Line points={[[-r, -r, -r], [-r, -r, r]]} color="#22c55e" lineWidth={1} />
        <Line points={[[r, -r, -r], [r, -r, r]]} color="#22c55e" lineWidth={1} />
        <Line points={[[r, r, -r], [r, r, r]]} color="#22c55e" lineWidth={1} />
        <Line points={[[-r, r, -r], [-r, r, r]]} color="#22c55e" lineWidth={1} />
      </group>
    );
  }

  if (entity.domain_tag === 'information_theory') {
    return (
      <group position={[c.x, c.y + maxSize * 1.1, c.z]}>
        <Text fontSize={0.28} color="#22d3ee" anchorX="center" anchorY="middle">
          {entity.domain_role || 'info'}
        </Text>
      </group>
    );
  }

  if (entity.domain_tag === 'acoustics') {
    const radius = clamp(maxSize * 1.15, 0.9, 2.5);
    return (
      <group position={[c.x, c.y, c.z]}>
        <Line points={circlePoints(radius)} color="#fde047" lineWidth={1} transparent opacity={0.55} />
        <Line points={circlePoints(radius * 1.35)} color="#facc15" lineWidth={1} transparent opacity={0.35} />
      </group>
    );
  }

  if (entity.domain_tag === 'optics') {
    const radius = clamp(maxSize * 0.95, 0.4, 1.6);
    return (
      <mesh position={[c.x, c.y, c.z]}>
        <sphereGeometry args={[radius, 18, 18]} />
        <meshBasicMaterial color={colour} transparent opacity={0.12} />
      </mesh>
    );
  }

  if (entity.domain_tag === 'electromagnetism') {
    const radius = clamp(maxSize * 1.1, 0.55, 1.8);
    return (
      <group position={[c.x, c.y, c.z]}>
        <Line points={circlePoints(radius).map(([x, y, z]) => [x, z, y])} color="#38bdf8" lineWidth={1} transparent opacity={0.45} />
        <Line points={circlePoints(radius).map(([x, y, z]) => [y, x, z])} color="#7dd3fc" lineWidth={1} transparent opacity={0.25} />
      </group>
    );
  }

  if (entity.domain_tag === 'chemical_physics') {
    const radius = clamp(maxSize * 0.7, 0.55, 1.5);
    return (
      <mesh position={[c.x, c.y, c.z]}>
        <sphereGeometry args={[radius, 16, 16]} />
        <meshBasicMaterial color="#34d399" wireframe transparent opacity={0.35} />
      </mesh>
    );
  }

  return null;
};

const VectorFieldLayer: React.FC<{ samples: SamplePoint[]; mode: 'gravity' | 'em'; colour: string }> = ({ samples, mode, colour }) => {
  return (
    <group>
      {samples.map((s, idx) => {
        const v = s.vector;
        if (!v) return null;
        const mag = Math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
        if (!Number.isFinite(mag) || mag <= 0) return null;
        const scale = fieldScale(mag, mode);
        const end: [number, number, number] = [
          s.point.x + (v.x / mag) * scale,
          s.point.y + (v.y / mag) * scale,
          s.point.z + (v.z / mag) * scale,
        ];
        return (
          <group key={`${mode}-${idx}`}>
            <Line points={[[s.point.x, s.point.y, s.point.z], end]} color={colour} lineWidth={1.2} transparent opacity={0.8} />
            <mesh position={end}>
              <sphereGeometry args={[0.06, 10, 10]} />
              <meshBasicMaterial color={colour} />
            </mesh>
          </group>
        );
      })}
    </group>
  );
};

const ThermalFieldLayer: React.FC<{ samples: SamplePoint[] }> = ({ samples }) => {
  return (
    <group>
      {samples.map((s, idx) => {
        const delta = s.delta_K ?? 0;
        const height = clamp(0.18 + Math.abs(delta) * 0.012, 0.18, 1.2);
        const colour = thermalColour(delta);
        return (
          <mesh key={`thermal-${idx}`} position={[s.point.x, s.point.y + height / 2, s.point.z]}>
            <boxGeometry args={[0.22, height, 0.22]} />
            <meshBasicMaterial color={colour} transparent opacity={0.5} />
          </mesh>
        );
      })}
    </group>
  );
};

const DomainOverlays: React.FC<DomainOverlaysProps> = ({
  state,
  showStaticOverlays,
  showGravityField,
  showEMField,
  showThermalField,
}) => {
  const [gravitySamples, setGravitySamples] = useState<SamplePoint[]>([]);
  const [emSamples, setEMSamples] = useState<SamplePoint[]>([]);
  const [thermalSamples, setThermalSamples] = useState<SamplePoint[]>([]);

  const samplePoints = useMemo(() => {
    const pts: Array<{ x: number; y: number; z: number }> = [];
    for (let x = 2; x <= 18; x += 4) {
      for (let z = 2; z <= 18; z += 4) {
        pts.push({ x, y: 2.0, z });
      }
    }
    return pts;
  }, []);

  useEffect(() => {
    let cancelled = false;
    if (!state) return;
    const active = showGravityField || showEMField || showThermalField;
    if (!active) {
      setGravitySamples([]);
      setEMSamples([]);
      setThermalSamples([]);
      return;
    }

    const fetchField = async (field: 'gravity' | 'em' | 'thermal') => {
      const r = await fetch('/v54/field_sample', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ field, points: samplePoints }),
      });
      return await r.json();
    };

    const run = async () => {
      try {
        const jobs: Promise<any>[] = [];
        const tags: string[] = [];
        if (showGravityField) { jobs.push(fetchField('gravity')); tags.push('gravity'); }
        if (showEMField) { jobs.push(fetchField('em')); tags.push('em'); }
        if (showThermalField) { jobs.push(fetchField('thermal')); tags.push('thermal'); }
        const results = await Promise.all(jobs);
        if (cancelled) return;
        results.forEach((res, idx) => {
          const tag = tags[idx];
          const samples = res?.samples ?? [];
          if (tag === 'gravity') setGravitySamples(samples);
          if (tag === 'em') setEMSamples(samples);
          if (tag === 'thermal') setThermalSamples(samples);
        });
      } catch {
        if (cancelled) return;
      }
    };

    run();
    const timer = window.setInterval(run, 650);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [state?.tick, showGravityField, showEMField, showThermalField, samplePoints]);

  const staticEntities = useMemo(
    () => (state?.entities ?? []).filter(e => e.domain_tag),
    [state?.entities],
  );

  if (!state) return null;

  return (
    <group>
      {showStaticOverlays && staticEntities.map(entity => (
        <StaticOverlay key={`static-${entity.id}`} entity={entity} />
      ))}
      {showGravityField && <VectorFieldLayer samples={gravitySamples} mode="gravity" colour="#f59e0b" />}
      {showEMField && <VectorFieldLayer samples={emSamples} mode="em" colour="#38bdf8" />}
      {showThermalField && <ThermalFieldLayer samples={thermalSamples} />}
    </group>
  );
};

export default DomainOverlays;
