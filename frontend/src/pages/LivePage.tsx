import { useEffect, useRef, useState } from 'react';
import { api, getErrorMessage } from '../api';
import ErrorBanner from '../components/ErrorBanner';

type Connection = {
  state: string;
  message: string | null;
  attempt: number;
  max_attempts: number | null;
  qr_visible: boolean;
  next_retry_at: string | null;
  updated_at: string | null;
};

type CurrentTarget = {
  type: string;
  id: number;
  name: string;
  source_name: string | null;
  attempts: number;
  message: string | null;
  status: string;
  failures?: number;
  total_misses?: number;
  daily_count?: number;
  daily_cap?: number;
  is_silenced?: boolean;
};

type RunProduct = { id: number | null; name: string | null; link?: string | null; has_media?: boolean };

type Run = {
  id: number;
  campaign_id: number;
  campaign_name: string | null;
  campaign_type: string | null;
  status: string;
  phase: string;
  product: RunProduct | null;
  source: RunProduct | null;
  current_target: CurrentTarget | null;
  counts: {
    total: number;
    processed: number;
    sent: number;
    failed: number;
    skipped: number;
    remaining: number;
    preview: number;
  };
  skip_requested: boolean;
  cycle_complete: boolean;
  error: string | null;
  started_at: string | null;
  finished_at: string | null;
  last_update: string | null;
  elapsed_seconds: number | null;
};

type ActiveResponse = {
  active: boolean;
  run: Run | null;
  last_run: Run | null;
  connection: Connection;
};

type RunTarget = {
  id: number;
  target_type: string;
  target_id: number;
  target_name: string | null;
  source_name: string | null;
  status: string;
  attempts: number;
  message: string | null;
  batch_no: number | null;
  started_at: string | null;
  finished_at: string | null;
};

type RunEvent = {
  id: number;
  level: string;
  event_type: string;
  message: string;
  target_name: string | null;
  created_at: string;
};

type PreviewTarget = {
  target_id: number;
  target_name: string | null;
  target_type: string;
  batch_no: number | null;
};

type RemainingResponse = {
  campaign_id: number;
  run_id: number | null;
  current: RunTarget[];
  preview: PreviewTarget[];
  total: number;
};

const CONNECTION_STYLES: Record<string, string> = {
  connected: 'border-emerald-200 bg-emerald-50 text-emerald-800',
  launching: 'border-amber-200 bg-amber-50 text-amber-800',
  loading: 'border-amber-200 bg-amber-50 text-amber-800',
  reconnecting: 'border-amber-200 bg-amber-50 text-amber-800',
  waiting_login: 'border-blue-200 bg-blue-50 text-blue-800',
  waiting_qr: 'border-blue-200 bg-blue-50 text-blue-800',
  disconnected: 'border-red-200 bg-red-50 text-red-800',
  error: 'border-red-200 bg-red-50 text-red-800',
  stopped: 'border-slate-200 bg-slate-50 text-slate-700',
  unknown: 'border-slate-200 bg-slate-50 text-slate-700',
};

const CONNECTION_DOT: Record<string, string> = {
  connected: 'bg-emerald-500',
  launching: 'bg-amber-500',
  loading: 'bg-amber-500',
  reconnecting: 'bg-amber-500',
  waiting_login: 'bg-blue-500',
  waiting_qr: 'bg-blue-500',
  disconnected: 'bg-red-500',
  error: 'bg-red-500',
  stopped: 'bg-slate-400',
  unknown: 'bg-slate-400',
};

const STATUS_STYLES: Record<string, string> = {
  running: 'bg-blue-100 text-blue-700',
  starting: 'bg-blue-100 text-blue-700',
  waiting_batch: 'bg-amber-100 text-amber-700',
  waiting_qr: 'bg-cyan-100 text-cyan-700',
  waiting_login: 'bg-cyan-100 text-cyan-700',
  reconnecting: 'bg-amber-100 text-amber-700',
  completed: 'bg-green-100 text-green-700',
  stopped: 'bg-slate-100 text-slate-600',
  failed: 'bg-red-100 text-red-700',
  interrupted: 'bg-orange-100 text-orange-700',
};

const TARGET_STATUS_STYLES: Record<string, string> = {
  pending: 'bg-slate-100 text-slate-600',
  current: 'bg-blue-100 text-blue-700',
  sent: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-red-100 text-red-700',
  skipped: 'bg-amber-100 text-amber-700',
  deferred: 'bg-slate-100 text-slate-500',
};

const LEVEL_STYLES: Record<string, string> = {
  error: 'text-red-700',
  warning: 'text-amber-700',
  info: 'text-slate-700',
};

const TARGET_STATUS_LABELS: Record<string, string> = {
  pending: 'Remaining',
  current: 'Current',
  sent: 'Sent',
  failed: 'Missed',
  skipped: 'Skipped',
  deferred: 'Deferred',
};

function elapsedLabel(seconds: number | null): string {
  if (seconds === null || seconds === undefined) return '—';
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  if (mins >= 60) return `${Math.floor(mins / 60)}h ${mins % 60}m`;
  return `${mins}m ${secs}s`;
}

function sourceLabel(run: Run | null): string {
  if (!run) return '—';
  if (run.campaign_type === 'myGroupLink') {
    return run.source?.name ?? run.product?.name ?? 'Waiting for link source';
  }
  return run.product?.name ?? (run.campaign_type === 'product_client' ? 'Waiting for product' : 'No product');
}

export default function LivePage({ initialCampaignId }: { initialCampaignId?: number | null }) {
  const [active, setActive] = useState<ActiveResponse | null>(null);
  const [scopedRun, setScopedRun] = useState<Run | null>(null);
  const [targets, setTargets] = useState<RunTarget[]>([]);
  const [remaining, setRemaining] = useState<RemainingResponse | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [tab, setTab] = useState<'remaining' | 'missed' | 'targets' | 'events'>('remaining');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [refreshKey, setRefreshKey] = useState(0);

  const currentRunId = useRef<number | null>(null);
  const lastEventId = useRef(0);
  const feedRef = useRef<HTMLDivElement | null>(null);
  const stickToBottom = useRef(true);

  useEffect(() => {
    let stopped = false;
    // A slow request must not stack up behind the 2s interval; skip a tick
    // while the previous one is still in flight.
    let inFlight = false;

    const tick = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const res = await api.get<ActiveResponse>('/live/active');
        if (stopped) return;
        setActive(res.data);

        let run = res.data.run ?? res.data.last_run;
        // If the page was opened from a campaign's Live button, show that
        // campaign's newest run even when another campaign is active.
        if (initialCampaignId && (!res.data.active || res.data.run?.campaign_id !== initialCampaignId)) {
          try {
            const runs = await api.get<Run[]>('/live/runs', { params: { campaign_id: initialCampaignId, limit: 1 } });
            if (!stopped && Array.isArray(runs.data) && runs.data.length) run = runs.data[0];
          } catch {
            // Keep the global last run fallback.
          }
        }
        if (!stopped) setScopedRun(run);
        if (!run) {
          if (stopped) return;
          setTargets([]);
          setRemaining(null);
          return;
        }

        if (currentRunId.current !== run.id) {
          currentRunId.current = run.id;
          lastEventId.current = 0;
          setEvents([]);
        }

        const [targetRes, remainingRes, eventRes] = await Promise.all([
          api.get<RunTarget[]>(`/live/runs/${run.id}/targets`),
          api.get<RemainingResponse>(`/live/campaigns/${run.campaign_id}/remaining`),
          api.get<RunEvent[]>(`/live/runs/${run.id}/events`, {
            params: { after_id: lastEventId.current, limit: 200 },
          }),
        ]);
        if (stopped) return;
        setTargets(Array.isArray(targetRes.data) ? targetRes.data : []);
        setRemaining(remainingRes.data);
        const fresh = Array.isArray(eventRes.data) ? eventRes.data : [];
        if (fresh.length) {
          lastEventId.current = Math.max(
            lastEventId.current,
            fresh[fresh.length - 1].id,
          );
          setEvents((prev) => {
            const seen = new Set(prev.map((event) => event.id));
            const added = fresh.filter((event) => !seen.has(event.id));
            return [...prev, ...added].slice(-500);
          });
        }
        setError(null);
      } catch (err) {
        if (!stopped) setError(getErrorMessage(err));
      } finally {
        inFlight = false;
      }
    };

    tick();
    const timer = window.setInterval(tick, 2000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [initialCampaignId, refreshKey]);

  useEffect(() => {
    if (stickToBottom.current && feedRef.current) {
      feedRef.current.scrollTop = feedRef.current.scrollHeight;
    }
  }, [events]);

  const run = active?.run ?? scopedRun ?? active?.last_run ?? null;
  const isActive = Boolean(active?.active && active.run && run && active.run.id === run.id);
  const connection = active?.connection;

  const skipCurrent = async () => {
    if (!run) return;
    const label = run.current_target?.name ?? 'the current target';
    if (!window.confirm(`Skip “${label}”? It will not be counted as sent or missed.`)) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await api.post<{ message?: string }>(`/campaigns/${run.campaign_id}/skip-current`);
      setNotice(res.data?.message ?? 'Skip requested; the runner will move to the next target.');
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const stopRun = async () => {
    if (!run) return;
    if (!window.confirm(`Stop “${run.campaign_name ?? 'this campaign'}”? It will stop after the current step.`)) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await api.post(`/campaigns/${run.campaign_id}/stop`);
      setNotice('Stop requested; the runner will close out the current step.');
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const refresh = () => {
    setError(null);
    setRefreshKey((value) => value + 1);
  };

  const missed = targets.filter((target) => target.status === 'failed');
  const remainingRows = remaining?.current ?? [];
  const previewRows = remaining?.preview ?? [];
  const progressTotal = run?.counts.total ?? 0;
  const progressProcessed = run?.counts.processed ?? 0;
  const progressPercent = progressTotal > 0 ? Math.min(100, Math.round((progressProcessed / progressTotal) * 100)) : 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">Live</h1>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-500">
            {isActive ? 'Polling every 2 seconds' : 'Showing the last run'}
          </span>
          <button onClick={refresh} className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100">
            Refresh
          </button>
        </div>
      </div>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      {notice && (
        <div className="flex items-start justify-between rounded border border-blue-200 bg-blue-50 p-3 text-sm text-blue-800">
          <span>{notice}</span>
          <button onClick={() => setNotice(null)} className="ml-4 text-blue-600 hover:text-blue-900">Dismiss</button>
        </div>
      )}

      {/* Global connection banner */}
      <div className={`rounded-lg border p-4 ${CONNECTION_STYLES[connection?.state ?? 'unknown'] ?? CONNECTION_STYLES.unknown}`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-3">
            <span className={`inline-block h-3 w-3 animate-pulse rounded-full ${CONNECTION_DOT[connection?.state ?? 'unknown'] ?? CONNECTION_DOT.unknown}`} />
            <div>
              <div className="text-sm font-semibold">
                WhatsApp: {connection?.state ?? 'unknown'}
                {connection && connection.attempt > 0 && (
                  <span className="ml-2 text-xs font-normal">
                    attempt {connection.attempt}
                    {connection.max_attempts ? ` / ${connection.max_attempts}` : ''}
                  </span>
                )}
              </div>
              <div className="text-xs opacity-80">{connection?.message ?? 'No connection state recorded yet.'}</div>
            </div>
          </div>
          <div className="text-right text-xs opacity-70">
            {connection?.qr_visible && <div className="font-semibold">Scan the QR code in the WhatsApp window.</div>}
            {connection?.updated_at && <div>Updated {connection.updated_at}</div>}
          </div>
        </div>
        {(connection?.state === 'waiting_qr' || connection?.state === 'waiting_login') && (
          <div className="mt-2 rounded border border-blue-200 bg-white/60 p-2 text-xs text-blue-800">
            Open WhatsApp on your phone → Linked devices → Link a device, then scan the QR shown in the browser.
          </div>
        )}
      </div>

      {!run ? (
        <div className="rounded-lg border border-slate-200 bg-white p-8 text-center text-slate-400">
          No campaign run has started yet. Start a campaign from the Campaigns page.
        </div>
      ) : (
        <>
          {/* Run header */}
          <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-lg font-semibold">{run.campaign_name ?? `Campaign ${run.campaign_id}`}</h2>
                  <span className={`rounded px-2 py-0.5 text-xs ${STATUS_STYLES[run.status] ?? 'bg-slate-100 text-slate-600'}`}>
                    {run.status}
                  </span>
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{run.phase}</span>
                  {run.skip_requested && (
                    <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700">Skip requested</span>
                  )}
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {run.campaign_type} · started {run.started_at ?? '—'} · elapsed {elapsedLabel(run.elapsed_seconds)}
                  {run.finished_at ? ` · finished ${run.finished_at}` : ''}
                </div>
                {run.error && <div className="mt-1 text-xs text-red-600">{run.error}</div>}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={skipCurrent}
                  disabled={busy || !isActive || !run.current_target}
                  className="rounded border border-amber-300 px-3 py-1.5 text-sm text-amber-700 hover:bg-amber-50 disabled:opacity-40"
                >
                  Skip current group
                </button>
                <button
                  onClick={stopRun}
                  disabled={busy || !isActive}
                  className="rounded border border-orange-300 px-3 py-1.5 text-sm text-orange-700 hover:bg-orange-50 disabled:opacity-40"
                >
                  Stop campaign
                </button>
              </div>
            </div>

            <div className="mt-4">
              <div className="mb-1 flex justify-between text-xs text-slate-500">
                <span>Progress</span>
                <span>{progressProcessed} / {progressTotal} ({progressPercent}%)</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded bg-slate-100">
                <div className="h-full bg-indigo-500 transition-all" style={{ width: `${progressPercent}%` }} />
              </div>
            </div>
          </div>

          {/* Current work */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="text-xs uppercase tracking-wide text-slate-400">Current group</div>
              {run.current_target ? (
                <>
                  <div className="mt-1 text-lg font-semibold">{run.current_target.name}</div>
                  <div className="text-xs text-slate-500">
                    {run.current_target.type} #{run.current_target.id} · attempt {run.current_target.attempts || 1}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs">
                    <span className={`rounded px-2 py-0.5 ${TARGET_STATUS_STYLES[run.current_target.status] ?? 'bg-slate-100 text-slate-600'}`}>
                      {TARGET_STATUS_LABELS[run.current_target.status] ?? run.current_target.status}
                    </span>
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-600">
                      daily {run.current_target.daily_count ?? 0} / {run.current_target.daily_cap ?? '—'}
                    </span>
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-600">
                      misses {run.current_target.failures ?? 0} consecutive · {run.current_target.total_misses ?? 0} total
                    </span>
                    {run.current_target.is_silenced && (
                      <span className="rounded bg-red-100 px-2 py-0.5 text-red-700">Silenced</span>
                    )}
                  </div>
                  {run.current_target.message && (
                    <div className="mt-2 text-xs text-slate-500">{run.current_target.message}</div>
                  )}
                </>
              ) : (
                <div className="mt-2 text-sm text-slate-400">Waiting for the next target…</div>
              )}
            </div>

            <div className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
              <div className="text-xs uppercase tracking-wide text-slate-400">
                {run.campaign_type === 'myGroupLink' ? 'Current link source' : 'Current product'}
              </div>
              <div className="mt-1 text-lg font-semibold">{sourceLabel(run)}</div>
              <div className="mt-2 text-xs text-slate-500">
                {run.campaign_type === 'myGroupLink' ? 'Promoting this group’s invite link' : 'Product being posted'}
                {run.product?.has_media ? ' · image attached' : ' · text only'}
              </div>
              {run.product?.link && (
                <div className="mt-1 truncate text-xs text-indigo-600">{run.product.link}</div>
              )}
            </div>
          </div>

          {/* Counters */}
          <div className="grid grid-cols-2 gap-3 md:grid-cols-6">
            {[
              ['Total', run.counts.total],
              ['Sent', run.counts.sent],
              ['Missed', run.counts.failed],
              ['Skipped', run.counts.skipped],
              ['Remaining', run.counts.remaining],
              ['Upcoming preview', run.counts.preview],
            ].map(([label, value]) => (
              <div key={String(label)} className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm">
                <div className="text-xs uppercase tracking-wide text-slate-400">{label}</div>
                <div className="mt-1 text-2xl font-semibold">{value}</div>
              </div>
            ))}
          </div>

          {/* Tabs */}
          <div className="flex flex-wrap gap-1 border-b border-slate-200">
            {[
              ['remaining', `Remaining (${remainingRows.length + previewRows.length})`],
              ['missed', `Missed (${missed.length})`],
              ['targets', `All targets (${targets.length})`],
              ['events', `Live events (${events.length})`],
            ].map(([key, label]) => (
              <button
                key={String(key)}
                onClick={() => setTab(key as typeof tab)}
                className={`rounded-t border-b-2 px-4 py-2 text-sm font-medium ${
                  tab === key
                    ? 'border-indigo-600 text-indigo-700'
                    : 'border-transparent text-slate-500 hover:text-slate-800'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {tab === 'remaining' && (
            <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="bg-slate-100 text-left text-xs uppercase text-slate-500">
                    <th className="p-3">#</th>
                    <th className="p-3">Target</th>
                    <th className="p-3">Batch</th>
                    <th className="p-3">Status</th>
                    <th className="p-3">Source</th>
                  </tr>
                </thead>
                <tbody>
                  {remainingRows.map((target, index) => (
                    <tr key={`current-${target.id}`} className="border-b text-sm">
                      <td className="p-3 text-slate-400">{index + 1}</td>
                      <td className="p-3">{target.target_name ?? `#${target.target_id}`}</td>
                      <td className="p-3 text-slate-500">{target.batch_no ?? '—'}</td>
                      <td className="p-3">
                        <span className={`rounded px-2 py-0.5 text-xs ${TARGET_STATUS_STYLES[target.status] ?? 'bg-slate-100 text-slate-600'}`}>
                          {TARGET_STATUS_LABELS[target.status] ?? target.status}
                        </span>
                      </td>
                      <td className="p-3 text-xs text-slate-500">{target.source_name ?? '—'}</td>
                    </tr>
                  ))}
                  {previewRows.map((target, index) => (
                    <tr key={`preview-${target.target_type}-${target.target_id}`} className="border-b text-sm text-slate-500">
                      <td className="p-3 text-slate-400">{remainingRows.length + index + 1}</td>
                      <td className="p-3">{target.target_name ?? `#${target.target_id}`}</td>
                      <td className="p-3">{target.batch_no ?? 'next'}</td>
                      <td className="p-3">
                        <span className="rounded bg-slate-50 px-2 py-0.5 text-xs text-slate-500">Upcoming</span>
                      </td>
                      <td className="p-3 text-xs">—</td>
                    </tr>
                  ))}
                  {remainingRows.length === 0 && previewRows.length === 0 && (
                    <tr><td colSpan={5} className="p-4 text-center text-slate-400">No remaining targets.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === 'missed' && (
            <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
              <table className="w-full border-collapse">
                <thead>
                  <tr className="bg-slate-100 text-left text-xs uppercase text-slate-500">
                    <th className="p-3">Target</th>
                    <th className="p-3">Batch</th>
                    <th className="p-3">Reason</th>
                    <th className="p-3">Attempts</th>
                    <th className="p-3">Finished</th>
                  </tr>
                </thead>
                <tbody>
                  {missed.map((target) => (
                    <tr key={target.id} className="border-b text-sm">
                      <td className="p-3">{target.target_name ?? `#${target.target_id}`}</td>
                      <td className="p-3 text-slate-500">{target.batch_no ?? '—'}</td>
                      <td className="p-3 text-xs text-red-600">{target.message ?? 'Post failed or could not be confirmed'}</td>
                      <td className="p-3 text-slate-500">{target.attempts}</td>
                      <td className="p-3 text-xs text-slate-500">{target.finished_at ?? '—'}</td>
                    </tr>
                  ))}
                  {missed.length === 0 && (
                    <tr><td colSpan={5} className="p-4 text-center text-slate-400">No missed groups this run.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === 'targets' && (
            <div className="max-h-[55vh] overflow-auto rounded-lg border border-slate-200 bg-white">
              <table className="w-full border-collapse">
                <thead className="sticky top-0">
                  <tr className="bg-slate-100 text-left text-xs uppercase text-slate-500">
                    <th className="p-3">Target</th>
                    <th className="p-3">Type</th>
                    <th className="p-3">Batch</th>
                    <th className="p-3">Status</th>
                    <th className="p-3">Attempts</th>
                    <th className="p-3">Message</th>
                  </tr>
                </thead>
                <tbody>
                  {targets.map((target) => (
                    <tr key={target.id} className="border-b text-sm">
                      <td className="p-3">{target.target_name ?? `#${target.target_id}`}</td>
                      <td className="p-3 text-xs text-slate-500">{target.target_type}</td>
                      <td className="p-3 text-slate-500">{target.batch_no ?? '—'}</td>
                      <td className="p-3">
                        <span className={`rounded px-2 py-0.5 text-xs ${TARGET_STATUS_STYLES[target.status] ?? 'bg-slate-100 text-slate-600'}`}>
                          {TARGET_STATUS_LABELS[target.status] ?? target.status}
                        </span>
                      </td>
                      <td className="p-3 text-slate-500">{target.attempts}</td>
                      <td className="p-3 text-xs text-slate-500">{target.message ?? '—'}</td>
                    </tr>
                  ))}
                  {targets.length === 0 && (
                    <tr><td colSpan={6} className="p-4 text-center text-slate-400">No targets recorded for this run.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}

          {tab === 'events' && (
            <div
              ref={feedRef}
              onScroll={() => {
                const element = feedRef.current;
                if (!element) return;
                stickToBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 40;
              }}
              className="max-h-[55vh] overflow-auto rounded-lg border border-slate-200 bg-slate-900 p-3 font-mono text-xs"
            >
              {events.length === 0 && <div className="text-slate-500">No live events yet.</div>}
              {events.map((event) => (
                <div key={event.id} className="flex gap-2 border-b border-slate-800 py-1">
                  <span className="shrink-0 text-slate-500">{event.created_at?.slice(11) ?? ''}</span>
                  <span className={`shrink-0 uppercase ${LEVEL_STYLES[event.level] ?? 'text-slate-400'}`}>
                    {event.level}
                  </span>
                  <span className="shrink-0 text-indigo-300">{event.event_type}</span>
                  <span className="break-words text-slate-200">
                    {event.target_name ? `${event.target_name}: ` : ''}
                    {event.message}
                  </span>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  );
}
