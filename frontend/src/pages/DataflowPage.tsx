import { Suspense, lazy, useEffect, useMemo, useRef, useState } from 'react';
import { api, getErrorMessage } from '../api';
import ErrorBanner from '../components/ErrorBanner';
import ErrorBoundary from '../components/ErrorBoundary';
import PageHeader from '../components/PageHeader';
import DataTable, { TableToolbar, type DataTableColumn } from '../components/DataTable';
import { useTableFilters } from '../hooks/useTableFilters';
import { CARD, MUTED, NOTICE_INFO, PANEL, SUBTLE } from '../ui';
import { parseLiveDb } from '../dataflow/guard';
import { METRICS } from '../dataflow/registry';
import { ConclusionsPanel, ControlsPanel, LegendPanel } from '../dataflow/panels';
import { DENSITIES, DENSITY_STORAGE_KEY, readDensity, type DensityKey } from '../dataflow/density';
import type { LiveDbPayload } from '../dataflow/types';

const CanvasSection = lazy(() => import('../dataflow/CanvasSection'));

const DEFAULT_CADENCE_MS = 2000;
const MAX_THROUGHPUT_SAMPLES = 60;

/** Canvas fallback: the same metrics as a plain, always-readable table. */
function MetricsTable({ payload }: { payload: LiveDbPayload | null }) {
  const rows = useMemo(
    () =>
      METRICS.map((metric) => ({
        key: metric.key,
        metric: metric.label,
        value: payload ? String(metric.read(payload) ?? '—') : '—',
        why: metric.plainEnglish,
      })),
    [payload],
  );
  const table = useTableFilters(
    rows,
    (row) => `${row.key} ${row.metric} ${row.value} ${row.why}`,
    [
      { key: 'metric', label: 'Metric', getValue: (row) => `${row.key} ${row.metric}` },
      { key: 'value', label: 'Reading', getValue: (row) => row.value },
    ],
  );
  const columns: DataTableColumn<(typeof rows)[number]>[] = [
    { key: 'metric', header: 'Metric', filter: { type: 'text', placeholder: 'Filter metric' }, cell: (row) => <span className="font-medium">{row.metric}</span> },
    { key: 'value', header: 'Reading', filter: { type: 'text', placeholder: 'Filter reading' }, cell: (row) => <span className="font-mono text-xs text-[#d4d4d4]">{row.value}</span> },
    { key: 'why', header: 'Why it exists', cellClassName: `text-xs ${MUTED}`, cell: (row) => row.why },
  ];
  return (
    <div className="space-y-2">
      <TableToolbar
        search={table.search}
        onSearch={table.setSearch}
        placeholder="Search metrics…"
        count={table.count}
        total={table.total}
        onClear={table.clearFilters}
        isFiltered={table.isFiltered}
      />
      <DataTable
        columns={columns}
        rows={table.filtered}
        rowKey={(row) => row.key}
        filters={table.values}
        onFilterChange={table.setFilter}
        emptyMessage="No metrics match the current filter."
        maxHeight="max-h-[55vh]"
      />
    </div>
  );
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia('(prefers-reduced-motion: reduce)').matches : false,
  );
  useEffect(() => {
    const query = window.matchMedia('(prefers-reduced-motion: reduce)');
    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener('change', onChange);
    return () => query.removeEventListener('change', onChange);
  }, []);
  return reduced;
}

export default function DataflowPage() {
  const [view, setView] = useState<'canvas' | 'table'>('canvas');
  const [cadenceMs, setCadenceMs] = useState(DEFAULT_CADENCE_MS);
  const [paused, setPaused] = useState(false);
  const [density, setDensity] = useState<DensityKey>(() => readDensity());
  const [layoutResetKey, setLayoutResetKey] = useState(0);
  const [payload, setPayload] = useState<LiveDbPayload | null>(null);
  const [banner, setBanner] = useState<string | null>(null);
  const [compatNotice, setCompatNotice] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [throughputHistory, setThroughputHistory] = useState<number[]>([]);
  const lastGood = useRef<LiveDbPayload | null>(null);
  const inFlight = useRef(false);
  const history = useRef<number[]>([]);
  const reducedMotion = usePrefersReducedMotion();
  const pausedRef = useRef(paused);
  useEffect(() => {
    pausedRef.current = paused;
  }, [paused]);

  // Persist the canvas density choice so it survives reloads and restarts.
  useEffect(() => {
    try {
      window.localStorage.setItem(DENSITY_STORAGE_KEY, density);
    } catch {
      // localStorage unavailable; density still works for this session.
    }
  }, [density]);

  // Cadence comes from Settings with the same clamp as the other poll rates.
  useEffect(() => {
    let stopped = false;
    api
      .get<{ values: Record<string, number | string | boolean> }>('/settings')
      .then((res) => {
        const raw = res.data?.values?.dataflow_poll_ms;
        const value = typeof raw === 'number' ? raw : Number(raw);
        if (!stopped && Number.isFinite(value)) setCadenceMs(Math.max(500, Math.min(30000, value)));
      })
      .catch(() => {
        // Keep the default.
      });
    return () => {
      stopped = true;
    };
  }, []);

  const poll = async () => {
    if (pausedRef.current || inFlight.current) return;
    inFlight.current = true;
    try {
      const res = await api.get('/live/db', { transformResponse: [(data) => data] });
      const parsed = typeof res.data === 'string' ? JSON.parse(res.data) : res.data;
      const result = parseLiveDb(parsed);
      if (!result.ok || !result.value) {
        // Last-good state stays on screen; show a non-blocking banner.
        setBanner(result.errors.length ? `Dataflow payload unreadable: ${result.errors.join('; ')}` : 'Dataflow payload unreadable; showing the last known state.');
        return;
      }
      setPayload(result.value);
      lastGood.current = result.value;
      setCompatNotice(result.compat);
      setBanner(null);
      setError(null);

      const rate = result.value.flows[0]?.sent_per_min ?? 0;
      history.current = [...history.current, rate].slice(-MAX_THROUGHPUT_SAMPLES);
      setThroughputHistory(history.current);
    } catch (err) {
      // Never crash the page; keep last-good and say so.
      setError(getErrorMessage(err));
      if (!lastGood.current) {
        setBanner('The /live/db endpoint is not reachable yet. Start the backend with the new build.');
      }
    } finally {
      inFlight.current = false;
    }
  };

  useEffect(() => {
    poll();
    const timer = window.setInterval(poll, cadenceMs);
    return () => window.clearInterval(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cadenceMs]);

  return (
    <div className="space-y-4">
      <PageHeader
        title="Dataflow"
        description="Inner workings of the bot as data — health, throughput and where targets are failing."
      >
        <ControlsPanel
          paused={paused}
          onTogglePaused={() => setPaused((value) => !value)}
          view={view}
          onToggleView={() => setView((value) => (value === 'canvas' ? 'table' : 'canvas'))}
          cadenceMs={cadenceMs}
          density={density}
          onDensityChange={setDensity}
          onResetLayout={() => setLayoutResetKey((value) => value + 1)}
        />
      </PageHeader>

      {compatNotice && (
        <div className={`${NOTICE_INFO} text-xs`}>
          The /live/db payload version differs from this build; showing best-effort values.
        </div>
      )}
      {banner && (
        <div className={`${NOTICE_INFO} flex items-start justify-between gap-3 text-xs`}>
          <span>{banner}</span>
          <button onClick={() => setBanner(null)} className="text-blue-600 hover:underline dark:text-blue-300">Dismiss</button>
        </div>
      )}
      <ErrorBanner message={error} onDismiss={() => setError(null)} />

      {/* 3-column board; conclusions always visible, canvas demoted to a panel. */}
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
        <section
          aria-label="Live flow diagram"
          className="[perspective:1200px]"
        >
          <div
            className={`${PANEL} motion-safe:[transform:rotateX(2.5deg)_rotateY(-2deg)] motion-safe:transition-transform`}
            style={{ transformStyle: 'preserve-3d' }}
          >
            <div className="flex items-center justify-between gap-2 border-b border-slate-200 px-4 py-2 dark:border-[#222]">
              <span className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-[#a3a3a3]">Flow board</span>
              <span className={`text-[10px] ${SUBTLE}`}>drag nodes to rearrange · Reset layout restores</span>
            </div>
            <div className="p-2">
              <ErrorBoundary fallback={<MetricsTable payload={payload} />}>
                {view === 'canvas' && payload ? (
                  <Suspense fallback={<div className={`h-[420px] p-6 text-center ${SUBTLE}`}>Loading flow renderer…</div>}>
                    {/* Elevated frame, cosmetic only; disabled under reduced motion. */}
                    <div className={DENSITIES[density].heightClass}>
                      <CanvasSection payload={payload} reducedMotion={reducedMotion} paused={paused} density={density} resetSignal={layoutResetKey} />
                    </div>
                  </Suspense>
                ) : (
                  <MetricsTable payload={payload} />
                )}
              </ErrorBoundary>
            </div>
          </div>
        </section>

        <aside className="space-y-4 xl:sticky xl:top-4">
          <ConclusionsPanel payload={payload} throughputHistory={throughputHistory} />
          <LegendPanel />
        </aside>
      </div>

      {/* Trace heads-up strip (positions for the eye, data from the same payload). */}
      <section className={`${CARD} grid grid-cols-2 gap-3 p-4 text-center sm:grid-cols-4`}>
        {[
          ['Sent (run)', payload?.runs.sent ?? 0],
          ['Missed (run)', payload?.runs.failed ?? 0],
          ['Events/min', payload?.db?.events_rate_1m ?? 0],
          ['Tick interval', `${payload?.scheduler_tick_seconds ?? '—'}s`],
        ].map(([label, value]) => (
          <div key={String(label)} className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 dark:border-[#222] dark:bg-[#111]">
            <div className={`text-[10px] uppercase tracking-wide ${SUBTLE}`}>{label}</div>
            <div className="mt-0.5 text-xl font-semibold text-slate-900 dark:text-[#f5f5f5]">{value}</div>
          </div>
        ))}
      </section>
    </div>
  );
}
