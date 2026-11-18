/**
 * Panels for the Dataflow board: Conclusions, controls and legend.
 * Kept separate from the page shell so they can grow without touching it.
 */

import { MUTED, SUBTLE } from '../ui';
import { DENSITY_OPTIONS, type DensityKey } from './density';
import { buildConclusions } from './conclusions';
import { METRICS } from './registry';
import type { Conclusion, LiveDbPayload } from './types';

const TONE_TEXT: Record<Conclusion['tone'], string> = {
  ok: 'text-emerald-600 dark:text-emerald-400',
  info: 'text-blue-600 dark:text-blue-400',
  warning: 'text-amber-700 dark:text-amber-400',
  error: 'text-red-600 dark:text-red-400',
  neutral: 'text-slate-500 dark:text-[#a3a3a3]',
};

function ToneDot({ tone }: { tone: Conclusion['tone'] }) {
  const dot: Record<Conclusion['tone'], string> = {
    ok: 'bg-emerald-500',
    info: 'bg-blue-500',
    warning: 'bg-amber-500',
    error: 'bg-red-500',
    neutral: 'bg-slate-400 dark:bg-neutral-600',
  };
  return <span className={`mt-1 inline-block h-2 w-2 shrink-0 rounded-full ${dot[tone]}`} aria-hidden="true" />;
}

/** Conclusions — the primary deliverable; turns the payload into sentences. */
export function ConclusionsPanel({ payload, throughputHistory }: { payload: LiveDbPayload | null; throughputHistory: number[] }) {
  if (!payload) {
    return (
      <div className={`rounded-md border border-slate-200 bg-[#0a0a0a] p-4 text-sm text-[#d4d4d4] dark:border-[#222]`}>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[#f5f5f5]">Conclusions</h2>
        <p className={`mt-2 ${MUTED}`}>Waiting for the first /live/db response…</p>
      </div>
    );
  }
  const lines = buildConclusions(payload, throughputHistory);
  return (
    <div className="rounded-md border border-slate-200 bg-[#0a0a0a] p-4 text-sm text-[#d4d4d4] dark:border-[#222]">
      <h2 className="text-sm font-semibold uppercase tracking-wide text-[#f5f5f5]">Conclusions</h2>
      <ul className="mt-2 space-y-2">
        {lines.map((line, index) => (
          <li key={index} className="flex items-start gap-2">
            <ToneDot tone={line.tone} />
            <span className={TONE_TEXT[line.tone]}>{line.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Legend of every registered metric; keeps the renderer honest. */
export function LegendPanel() {
  return (
    <div className="rounded-md border border-slate-200 bg-[#0a0a0a] p-4 dark:border-[#222]">
      <h2 className="text-xs font-semibold uppercase tracking-wide text-[#f5f5f5]">Legend — registered metrics</h2>
      <ul className="mt-2 grid grid-cols-1 gap-1 text-xs sm:grid-cols-2">
        {METRICS.map((metric) => (
          <li key={metric.key} className="flex items-baseline gap-2">
            <span className="font-mono text-[10px] text-[#a3a3a3]">{metric.key}</span>
            <span className={`truncate ${MUTED}`} title={metric.plainEnglish}>{metric.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Pause/resume + canvas/table toggle + density controls. */
export function ControlsPanel({
  paused,
  onTogglePaused,
  view,
  onToggleView,
  cadenceMs,
  density,
  onDensityChange,
  onResetLayout,
}: {
  paused: boolean;
  onTogglePaused: () => void;
  view: 'canvas' | 'table';
  onToggleView: () => void;
  cadenceMs: number;
  density: DensityKey;
  onDensityChange: (density: DensityKey) => void;
  onResetLayout?: () => void;
}) {
  const button =
    'rounded-md border border-[#222] px-2.5 py-1 text-xs font-medium text-[#d4d4d4] transition-colors hover:border-[#2a2a2a] hover:bg-[#111] focus:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500';
  return (
    <div className="flex flex-wrap items-center gap-2">
      <button type="button" onClick={onTogglePaused} aria-pressed={paused} className={button}>
        {paused ? 'Resume live view' : 'Pause live view'}
      </button>
      <button type="button" onClick={onToggleView} className={button}>
        {view === 'canvas' ? 'Table view' : 'Canvas view'}
      </button>
      <span className="inline-flex items-center gap-1" role="group" aria-label="Canvas density">
        {DENSITY_OPTIONS.map((option) => {
          const active = option.key === density;
          return (
            <button
              key={option.key}
              type="button"
              onClick={() => onDensityChange(option.key)}
              aria-pressed={active}
              title={`${option.label} node spacing`}
              className={`${button} ${active ? 'border-indigo-500 bg-indigo-950/40 text-indigo-300 dark:text-indigo-300' : ''}`}
            >
              {option.label}
            </button>
          );
        })}
      </span>
      <span className={`text-xs ${SUBTLE}`}>poll every {cadenceMs}ms</span>
      {onResetLayout && (
        <button type="button" onClick={onResetLayout} className={button} title="Return nodes to their computed positions">
          Reset layout
        </button>
      )}
    </div>
  );
}
