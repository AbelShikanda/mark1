/**
 * Density presets for the dataflow canvas: node/label/edge spacing.
 * Persisted in localStorage under `dataflow_density`.
 */
export type DensityKey = 'compact' | 'comfortable' | 'spacious';

export interface DensitySpec {
  /** Multiplier for isometric grid spacing and orbit radii. */
  scale: number;
  /** Multiplier for node width/height (diamonds). */
  nodeScale: number;
  /** Label font size in px. */
  fontLabel: number;
  /** Sub-label font size in px. */
  fontSub: number;
  /** Canvas section height classes (Tailwind). */
  heightClass: string;
}

export const DENSITIES: Record<DensityKey, DensitySpec> = {
  compact: { scale: 1, nodeScale: 1, fontLabel: 11, fontSub: 9, heightClass: 'h-[400px] md:h-[440px]' },
  comfortable: { scale: 1.3, nodeScale: 1.15, fontLabel: 13, fontSub: 10.5, heightClass: 'h-[470px] md:h-[520px]' },
  spacious: { scale: 1.6, nodeScale: 1.3, fontLabel: 15, fontSub: 12, heightClass: 'h-[540px] md:h-[600px]' },
};

export const DENSITY_OPTIONS: Array<{ key: DensityKey; label: string }> = [
  { key: 'compact', label: 'Compact' },
  { key: 'comfortable', label: 'Comfortable' },
  { key: 'spacious', label: 'Spacious' },
];

export const DENSITY_STORAGE_KEY = 'dataflow_density';
export const DEFAULT_DENSITY: DensityKey = 'comfortable';

export function readDensity(): DensityKey {
  try {
    const raw = window.localStorage.getItem(DENSITY_STORAGE_KEY);
    if (raw === 'compact' || raw === 'comfortable' || raw === 'spacious') return raw;
  } catch {
    // localStorage unavailable; keep the default.
  }
  return DEFAULT_DENSITY;
}
