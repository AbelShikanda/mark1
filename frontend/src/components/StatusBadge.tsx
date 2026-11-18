import type { ReactNode } from 'react';

export type StatusTone = 'ok' | 'info' | 'warning' | 'error' | 'neutral';

const TONE: Record<StatusTone, string> = {
  ok: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-200',
  info: 'bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-200',
  warning: 'bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-200',
  error: 'bg-red-100 text-red-700 dark:bg-red-950/60 dark:text-red-200',
  neutral: 'bg-slate-100 text-slate-600 dark:bg-[#161616] dark:text-[#a3a3a3]',
};

export function toneForStatus(status?: string | null): StatusTone {
  const s = (status ?? '').toLowerCase();
  if (['completed', 'sent', 'ok', 'isposted'].includes(s)) return 'ok';
  if (['running', 'starting', 'current', 'waiting_qr', 'waiting_login', 'isrunning'].includes(s)) return 'info';
  if (['reconnecting', 'interrupted', 'skipped', 'isbusy'].includes(s)) return 'warning';
  if (['failed', 'error'].includes(s)) return 'error';
  if (s === 'stopped') return 'warning';
  return 'neutral';
}

export default function StatusBadge({ tone = 'neutral', children }: { tone?: StatusTone; children: ReactNode }) {
  return <span className={`rounded px-2 py-0.5 text-xs font-medium ${TONE[tone]}`}>{children}</span>;
}

export function RunStatusBadge({ status }: { status?: string | null }) {
  return <StatusBadge tone={toneForStatus(status)}>{status ?? 'unknown'}</StatusBadge>;
}
