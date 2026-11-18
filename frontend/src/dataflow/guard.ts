/** Hand-written runtime validator for the /live/db payload.
 *
 * Goals: tolerate unknown keys, default missing optional keys, keep the last
 * good state upstream on any failure, and report a compat notice on v mismatch
 * instead of throwing. No zod — deliberately hand-rolled and tiny.
 */

import type { LiveDbPayload, LiveDbEvent, LiveDbFlow, LiveDbPool, LiveDbRun, LiveDbStepFailure } from './types';

const EMPTY_RUN: LiveDbRun = {
  active: false,
  run_id: null,
  campaign_name: null,
  status: null,
  phase: null,
  total: 0,
  processed: 0,
  sent: 0,
  failed: 0,
  skipped: 0,
  remaining: 0,
  preview: 0,
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === 'object' && value !== null && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function asString(value: unknown, fallback: string): string {
  return typeof value === 'string' && value.trim() ? value : fallback;
}

function asNumber(value: unknown, fallback = 0): number {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function asOptionalString(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value : value === null || value === undefined ? null : String(value);
}

function asOptionalInt(value: unknown): number | null {
  if (value === null || value === undefined) return null;
  const num = Number(value);
  return Number.isFinite(num) ? Math.trunc(num) : null;
}

function parsePool(raw: unknown): LiveDbPool | null {
  const rec = asRecord(raw);
  if (!rec) return null;
  if (typeof rec.id !== 'string' || !rec.id.trim()) return null;
  return {
    id: rec.id,
    label: asString(rec.label, rec.id),
    status: asString(rec.status, 'unknown'),
    percent: Math.max(0, Math.min(100, asNumber(rec.percent, 0))),
    detail: asString(rec.detail, ''),
  };
}

function parseFlow(raw: unknown): LiveDbFlow | null {
  const rec = asRecord(raw);
  if (!rec) return null;
  if (typeof rec.id !== 'string' || !rec.id.trim()) return null;
  return {
    id: rec.id,
    label: asString(rec.label, rec.id),
    sent_per_min: asNumber(rec.sent_per_min, 0),
    failed_1m: Math.max(0, Math.trunc(asNumber(rec.failed_1m, 0))),
    total: Math.max(0, Math.trunc(asNumber(rec.total, 0))),
    processed: Math.max(0, Math.trunc(asNumber(rec.processed, 0))),
    status: asString(rec.status, 'idle'),
  };
}

function parseEvent(raw: unknown): LiveDbEvent | null {
  const rec = asRecord(raw);
  if (!rec) return null;
  const message = asString(rec.message, '');
  if (!message) return null;
  return {
    id: asOptionalInt(rec.id),
    level: asString(rec.level, 'info'),
    event_type: asString(rec.event_type, 'progress'),
    message,
    created_at: asOptionalString(rec.created_at),
  };
}

function parseStep(raw: unknown): LiveDbStepFailure | null {
  const rec = asRecord(raw);
  if (!rec) return null;
  const step = asString(rec.step, '').trim();
  if (!step) return null;
  return { step, count: Math.max(0, Math.trunc(asNumber(rec.count, 0))) };
}

function parseRun(raw: unknown): LiveDbRun {
  const rec = asRecord(raw);
  if (!rec) return { ...EMPTY_RUN };
  return {
    active: Boolean(rec.active),
    run_id: asOptionalInt(rec.run_id),
    campaign_name: asOptionalString(rec.campaign_name),
    status: asOptionalString(rec.status),
    phase: asOptionalString(rec.phase),
    total: Math.max(0, Math.trunc(asNumber(rec.total, 0))),
    processed: Math.max(0, Math.trunc(asNumber(rec.processed, 0))),
    sent: Math.max(0, Math.trunc(asNumber(rec.sent, 0))),
    failed: Math.max(0, Math.trunc(asNumber(rec.failed, 0))),
    skipped: Math.max(0, Math.trunc(asNumber(rec.skipped, 0))),
    remaining: Math.max(0, Math.trunc(asNumber(rec.remaining, 0))),
    preview: Math.max(0, Math.trunc(asNumber(rec.preview, 0))),
  };
}

export type ParseResult = {
  ok: boolean;
  compat: boolean;
  errors: string[];
  value: LiveDbPayload | null;
};

export function parseLiveDb(raw: unknown): ParseResult {
  const errors: string[] = [];
  const compat = false;
  const root = asRecord(raw);
  if (!root) {
    return { ok: false, compat: false, errors: ['payload is not an object'], value: null };
  }
  const v = asNumber(root.v, NaN);
  if (!Number.isFinite(v)) {
    return { ok: false, compat, errors: ['missing required numeric field "v"'], value: null };
  }
  const vCompat = v === 1 ? false : true;

  const pools = Array.isArray(root.pools) ? root.pools.map(parsePool).filter((p): p is LiveDbPool => p !== null) : null;
  if (pools === null) errors.push('"pools" is missing or not an array');
  if (Array.isArray(root.pools) && pools && pools.length !== root.pools.length) {
    errors.push('some pool entries were unreadable and were dropped');
  }

  const flows = Array.isArray(root.flows) ? root.flows.map(parseFlow).filter((f): f is LiveDbFlow => f !== null) : null;
  if (flows === null) errors.push('"flows" is missing or not an array');
  if (Array.isArray(root.flows) && flows && flows.length !== root.flows.length) {
    errors.push('some flow entries were unreadable and were dropped');
  }

  const events = Array.isArray(root.events) ? root.events.map(parseEvent).filter((e): e is LiveDbEvent => e !== null) : null;
  if (events === null) errors.push('"events" is missing or not an array');
  if (Array.isArray(root.events) && events && events.length !== root.events.length) {
    errors.push('some event entries were unreadable and were dropped');
  }

  const steps = Array.isArray(root.steps) ? root.steps.map(parseStep).filter((s): s is LiveDbStepFailure => s !== null) : [];

  if (errors.length) {
    return { ok: false, compat: vCompat, errors, value: null };
  }

  const db = Object.fromEntries(
    Object.entries(asRecord(root.db) ?? {})
      .map(([key, value]) => [key, Number(value)])
      .filter(([, value]) => Number.isFinite(value)) as [string, number][],
  );

  return {
    ok: true,
    compat: vCompat,
    errors: [],
    value: {
      v,
      ts: asString(root.ts, new Date().toISOString()),
      pools: pools ?? [],
      flows: flows ?? [],
      events: events ?? [],
      runs: parseRun(root.runs),
      steps,
      db,
      scheduler_tick_seconds: Math.max(1, Math.trunc(asNumber(root.scheduler_tick_seconds, 5))),
    },
  };
}
