/**
 * Conclusions panel: turns the /live/db payload into plain-English sentences.
 * Every line is grounded in a measured number; nothing is speculated.
 */

import type { Conclusion, LiveDbPayload } from './types';

export function buildConclusions(payload: LiveDbPayload, throughputHistory: number[] = []): Conclusion[] {
  const lines: Conclusion[] = [];

  // ── WhatsApp session health ─────────────────────────────────────────
  const wa = payload.pools.find((pool) => pool.id === 'whatsapp');
  if (wa) {
    if (wa.status === 'critical') {
      lines.push({ tone: 'error', text: 'WhatsApp is unreachable — nothing will send until the browser is reconnected.' });
    } else if (wa.status === 'warning') {
      if (wa.detail.toLowerCase().includes('qr')) {
        lines.push({ tone: 'warning', text: 'WhatsApp is waiting for a QR scan — open the Live page or Settings → Session & browser to scan.' });
      } else {
        lines.push({ tone: 'warning', text: `WhatsApp session is not healthy right now (${wa.detail}).` });
      }
    } else if (wa.status === 'ok') {
      lines.push({ tone: 'ok', text: 'WhatsApp session is connected and able to send.' });
    } else {
      lines.push({ tone: 'neutral', text: 'No WhatsApp activity yet — start a campaign to see live health.' });
    }
  }

  // ── Queue saturation ─────────────────────────────────────────────────
  const queue = payload.pools.find((pool) => pool.id === 'run_queue');
  if (payload.runs.active && queue) {
    if (queue.status === 'critical') {
      lines.push({ tone: 'error', text: `Run queue is nearly empty of progress (${queue.detail}) — check for a stalled run.` });
    } else if (queue.status === 'warning') {
      lines.push({ tone: 'warning', text: `Run queue still has a lot of work ahead (${queue.detail}).` });
    } else {
      lines.push({ tone: 'ok', text: `Run progress is healthy (${queue.detail}).` });
    }
  }

  // ── Throughput trend (needs history) ─────────────────────────────────
  if (throughputHistory.length >= 5) {
    const first = throughputHistory[0];
    const last = throughputHistory[throughputHistory.length - 1];
    if (first > 0 || last > 0) {
      const delta = last - first;
      const pct = first > 0 ? Math.round((delta / first) * 100) : 100;
      if (Math.abs(pct) < 10) {
        lines.push({ tone: 'neutral', text: `Send throughput steady at about ${last.toFixed(0)} msg/min over the last window.` });
      } else if (delta > 0) {
        lines.push({ tone: 'ok', text: `Send throughput up ${Math.abs(pct)}% to ${last.toFixed(0)} msg/min in the last window.` });
      } else {
        lines.push({ tone: 'warning', text: `Send throughput down ${Math.abs(pct)}% to ${last.toFixed(0)} msg/min in the last window.` });
      }
    }
  }

  // ── Failure steps (from [result] TARGET FAILED | step=...) ───────────
  if (payload.steps.length) {
    for (const { step, count } of payload.steps.slice(0, 6)) {
      if (step === 'read_only') {
        lines.push({ tone: 'warning', text: `${count} target(s) opened but were blocked by WhatsApp (step=read_only; the chat is read-only).` });
      } else {
        lines.push({ tone: 'warning', text: `${count} target(s) failed at step=${step}.` });
      }
    }
  } else if (payload.runs.run_id) {
    lines.push({ tone: 'neutral', text: 'No TARGET FAILED entries recorded for the latest run.' });
  }

  // ── Event rate / heartbeats ──────────────────────────────────────────
  const eventsRate = Number(payload.db?.events_rate_1m ?? 0);
  if (eventsRate > 0) {
    lines.push({ tone: 'info', text: `Heartbeat: ${eventsRate} run event(s) logged in the last minute.` });
  }

  // ── Scheduler cadence ──────────────────────────────────────────────────
  lines.push({
    tone: 'info',
    text: `Scheduler ticks every ${payload.scheduler_tick_seconds}s (Settings → Campaigns). Drift is not observable from this process, so this line reports the configured interval, not a measured one.`,
  });

  // ── DB footprint ─────────────────────────────────────────────────────
  const dbBytes = Number(payload.db?.bytes ?? 0);
  const logRows = Number(payload.db?.log_rows ?? 0);
  if (dbBytes > 0) {
    const mb = (dbBytes / (1024 * 1024)).toFixed(1);
    lines.push({ tone: 'neutral', text: `Database is ${mb} MB with ${logRows.toLocaleString()} log rows — Settings → Data & maintenance can trim it.` });
  }

  if (!payload.runs.run_id) {
    lines.push({ tone: 'neutral', text: 'No campaign run recorded yet — start one from the Campaigns page and live numbers will appear here.' });
  }

  return lines;
}
