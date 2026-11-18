/**
 * Dataflow dashboard contracts.
 *
 * Everything rendered on the Dataflow page is driven by a small set of typed
 * metrics registered below. The renderer never invents numbers: each drawn
 * node/edge references one DashboardMetric, and that metric knows how to read
 * itself out of the /live/db payload and how to explain itself in plain
 * English for the Conclusions panel.
 */

export type LiveDbPoolStatus = 'idle' | 'ok' | 'warning' | 'critical';
export type LiveDbPool = {
  id: string;
  label: string;
  status: LiveDbPoolStatus | string;
  percent: number;
  detail: string;
};

export type LiveDbFlow = {
  id: string;
  label: string;
  sent_per_min: number;
  failed_1m: number;
  total: number;
  processed: number;
  status: string;
};

export type LiveDbStepFailure = { step: string; count: number };

export type LiveDbEvent = {
  id: number | null;
  level: string;
  event_type: string;
  message: string;
  created_at: string | null;
};

export type LiveDbRun = {
  active: boolean;
  run_id: number | null;
  campaign_name: string | null;
  status: string | null;
  phase: string | null;
  total: number;
  processed: number;
  sent: number;
  failed: number;
  skipped: number;
  remaining: number;
  preview: number;
};

export type LiveDbPayload = {
  v: number;
  ts: string;
  pools: LiveDbPool[];
  flows: LiveDbFlow[];
  events: LiveDbEvent[];
  runs: LiveDbRun;
  steps: LiveDbStepFailure[];
  db: Record<string, number>;
  scheduler_tick_seconds: number;
};

/** A registered, self-describing metric — the only things the renderer may draw. */
export type DashboardMetric = {
  /** Stable key, also used as the canvas node/edge id. */
  key: string;
  /** Human-readable name shown in legend / table / conclusions. */
  label: string;
  /** Rough unit for readouts, e.g. "per minute", "targets", "MB". */
  unit?: string;
  /** Plain-English explanation used by the Conclusions panel. */
  plainEnglish: string;
  /** Extract the rendered value from the payload (null => show "—"). */
  read: (payload: LiveDbPayload) => number | string | null;
};

export type MetricTone = 'ok' | 'info' | 'warning' | 'error' | 'neutral';

export type Conclusion = {
  tone: MetricTone;
  text: string;
};
