/**
 * Metric registry — the single source of truth for what the Dataflow page may
 * render. Adding a metric means: register it here, then write its draw code in
 * renderer (see ./CanvasSection.tsx) and its plain-English line in
 * ./conclusions.ts. Nothing else reads the raw payload.
 */

import type { LiveDbPayload, DashboardMetric } from './types';

const poolById = (payload: LiveDbPayload, id: string) => payload.pools.find((pool) => pool.id === id);

function formatBytes(bytes?: number): string {
  const n = Number(bytes ?? 0);
  if (!Number.isFinite(n) || n <= 0) return '0 B';
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export const METRICS: DashboardMetric[] = [
  {
    key: 'whatsapp',
    label: 'WhatsApp session',
    unit: 'pool',
    plainEnglish: 'Whether WhatsApp Web is reachable for sending (connected) or needs a QR re-login.',
    read: (p) => poolById(p, 'whatsapp')?.detail ?? null,
  },
  {
    key: 'run_queue',
    label: 'Active run queue',
    unit: 'targets remaining',
    plainEnglish: 'How many targets the current campaign still has to reach. 100% means the run just started.',
    read: (p) => {
      const pool = poolById(p, 'run_queue');
      if (!pool) return null;
      const run = p.runs;
      if (!run.active || run.total <= 0) return run.active ? 'n/a' : 'idle';
      return `${Math.round(pool.percent)}% remaining (${run.remaining}/${run.total})`;
    },
  },
  {
    key: 'log_rate',
    label: 'Log write rate',
    unit: 'lines/min',
    plainEnglish: 'How many log lines are written per minute; a busy run writes constantly.',
    read: (p) => Number(p.db?.logs_rate_1m ?? 0),
  },
  {
    key: 'whatsapp_pool',
    label: 'Headless browser pool',
    unit: 'browser',
    plainEnglish: 'The single browser session this app drives; it either serves sends or waits for a QR.',
    read: (p) => poolById(p, 'whatsapp')?.status ?? null,
  },
  {
    key: 'db_bytes',
    label: 'SQLite size',
    unit: 'bytes',
    plainEnglish: 'Size of the local SQLite database; cleanup with Settings → Data & maintenance.',
    read: (p) => formatBytes(p.db?.bytes),
  },
  {
    key: 'run_throughput',
    label: 'Send throughput',
    unit: 'msg/min',
    plainEnglish: 'Messages confirmed sent in the last 60 seconds by the latest run.',
    read: (p) => (p.flows[0]?.sent_per_min ?? 0).toFixed(0),
  },
  {
    key: 'run_failures',
    label: 'Failed targets (1m)',
    unit: 'targets/min',
    plainEnglish: 'Targets that failed in the last 60 seconds; trace lines look like [result] TARGET FAILED | step=read_only.',
    read: (p) => p.flows[0]?.failed_1m ?? 0,
  },
  {
    key: 'run_progress',
    label: 'Run progress',
    unit: 'processed / total',
    plainEnglish: 'How far the current run has gotten; skipped + sent + failed counts as processed.',
    read: (p) => (p.runs.active || p.runs.run_id ? `${p.runs.processed} / ${p.runs.total}` : 'no run yet'),
  },
  {
    key: 'run_sent',
    label: 'Messages sent (run)',
    unit: 'targets',
    plainEnglish: 'Targets confirmed sent during the current run.',
    read: (p) => p.runs.sent,
  },
  {
    key: 'run_failed',
    label: 'Missed targets (run)',
    unit: 'targets',
    plainEnglish: 'Targets that failed during the current run; see the failed-step breakdown below.',
    read: (p) => p.runs.failed,
  },
  {
    key: 'run_skipped',
    label: 'Skipped targets (run)',
    unit: 'targets',
    plainEnglish: 'Targets the runner skipped (e.g. you chose “Skip current”).',
    read: (p) => p.runs.skipped,
  },
  {
    key: 'event_rate',
    label: 'Event rate',
    unit: 'events/min',
    plainEnglish: 'How many run events are being recorded per minute — the runner’s own heartbeat.',
    read: (p) => Number(p.db?.events_rate_1m ?? 0),
  },
  {
    key: 'step_read_only',
    label: 'Failures at step=read_only',
    unit: 'targets',
    plainEnglish: 'Targets where the chat opened but WhatsApp blocked sending (read-only).',
    read: (p) => p.steps.find((step) => step.step === 'read_only')?.count ?? 0,
  },
  {
    key: 'step_other',
    label: 'Failures at other steps',
    unit: 'targets',
    plainEnglish: 'All failing targets whose step is not read_only (search, composer, send…).',
    read: (p) =>
      p.steps
        .filter((step) => step.step !== 'read_only')
        .reduce((sum, step) => sum + step.count, 0),
  },
  {
    key: 'scheduler_tick',
    label: 'Scheduler tick interval',
    unit: 'seconds',
    plainEnglish: 'How often the background scheduler checks for due campaigns; set in Settings → Campaigns.',
    read: (p) => p.scheduler_tick_seconds,
  },
  {
    key: 'events_rows',
    label: 'Run events stored',
    unit: 'rows',
    plainEnglish: 'Total run events persisted; retention cleanup trims this automatically.',
    read: (p) => Number(p.db?.event_rows ?? 0),
  },
];

export const METRIC_BY_KEY: ReadonlyMap<string, DashboardMetric> = new Map(METRICS.map((metric) => [metric.key, metric]));

/** Development-time contract check: every registry entry must round-trip through the payload. */
export function validateRegistry(): string[] {
  const errors: string[] = [];
  const keys = new Set(METRICS.map((metric) => metric.key));
  for (const metric of METRICS) {
    if (!metric.key.trim() || !metric.label.trim() || !metric.plainEnglish.trim()) {
      errors.push(`metric ${metric.key || '<no key>'} is missing key/label/plainEnglish`);
    }
  }
  if (keys.size !== METRICS.length) {
    errors.push('duplicate metric keys detected in the registry');
  }
  return errors;
}

/** Assertion used by the renderer for any node/edge it wants to draw. */
export function assertMetricRegistered(key: string): void {
  if (!METRIC_BY_KEY.has(key)) {
    throw new Error(`Dataflow: metric "${key}" is not registered (see ./registry.ts)`);
  }
}
