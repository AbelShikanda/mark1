import { useEffect, useRef, useState } from 'react';
import { api, getErrorMessage } from '../api';
import ErrorBanner from '../components/ErrorBanner';
import DataTable, { TableToolbar, type DataTableColumn } from '../components/DataTable';
import { useTableFilters } from '../hooks/useTableFilters';
import { MUTED, NOTICE_INFO, PANEL, SUBTLE } from '../ui';

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

type SessionQr = {
  available: boolean;
  qr_data_url: string | null;
  message: string | null;
  headless: boolean;
  browser_open: boolean;
  state: string | null;
};

type RemainingRow = {
  key: string;
  index: number;
  name: string;
  batch: number | string | null;
  status: string;
  source: string;
  preview: boolean;
};

const CONNECTION_STYLES: Record<string, string> = {
  connected: 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/40 dark:text-emerald-200',
  launching: 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200',
  loading: 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200',
  reconnecting: 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200',
  waiting_login: 'border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-900/60 dark:bg-blue-950/40 dark:text-blue-200',
  waiting_qr: 'border-blue-200 bg-blue-50 text-blue-800 dark:border-blue-900/60 dark:bg-blue-950/40 dark:text-blue-200',
  disconnected: 'border-red-200 bg-red-50 text-red-800 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200',
  error: 'border-red-200 bg-red-50 text-red-800 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200',
  stopped: 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300',
  unknown: 'border-slate-200 bg-slate-50 text-slate-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300',
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
  running: 'bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-200',
  starting: 'bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-200',
  waiting_batch: 'bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-200',
  waiting_qr: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-950/60 dark:text-cyan-200',
  waiting_login: 'bg-cyan-100 text-cyan-700 dark:bg-cyan-950/60 dark:text-cyan-200',
  reconnecting: 'bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-200',
  completed: 'bg-green-100 text-green-700 dark:bg-green-950/60 dark:text-green-200',
  stopped: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
  failed: 'bg-red-100 text-red-700 dark:bg-red-950/60 dark:text-red-200',
  interrupted: 'bg-orange-100 text-orange-700 dark:bg-orange-950/60 dark:text-orange-200',
};

const TARGET_STATUS_STYLES: Record<string, string> = {
  pending: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
  current: 'bg-blue-100 text-blue-700 dark:bg-blue-950/60 dark:text-blue-200',
  sent: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-200',
  failed: 'bg-red-100 text-red-700 dark:bg-red-950/60 dark:text-red-200',
  skipped: 'bg-amber-100 text-amber-700 dark:bg-amber-950/60 dark:text-amber-200',
  deferred: 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400',
};

const LEVEL_STYLES: Record<string, string> = {
  error: 'text-red-700 dark:text-red-400',
  warning: 'text-amber-700 dark:text-amber-400',
  info: 'text-slate-700 dark:text-slate-300',
};

const TARGET_STATUS_LABELS: Record<string, string> = {
  pending: 'Remaining',
  current: 'Current',
  sent: 'Sent',
  failed: 'Missed',
  skipped: 'Skipped',
  deferred: 'Deferred',
  upcoming: 'Upcoming',
};

const TARGET_STATUS_OPTIONS = Object.entries(TARGET_STATUS_LABELS).map(([value, label]) => ({ value, label }));

const ACTION_BTN = 'rounded border px-3 py-1.5 text-sm disabled:opacity-40';

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
  const [qr, setQr] = useState<SessionQr | null>(null);
  const [qrBusy, setQrBusy] = useState(false);

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
  const needsQr = Boolean(
    connection?.qr_visible ||
      connection?.state === 'waiting_qr' ||
      connection?.state === 'waiting_login',
  );

  // Fetch the QR snapshot only while WhatsApp is waiting for a scan. This keeps
  // the polling loop cheap and lets the panel disappear on its own after login.
  useEffect(() => {
    if (!needsQr) {
      setQr(null);
      return;
    }
    let stopped = false;
    let inFlight = false;
    const tick = async () => {
      if (inFlight) return;
      inFlight = true;
      try {
        const res = await api.get<SessionQr>('/session/qr');
        if (!stopped) setQr(res.data);
      } catch {
        if (!stopped) setQr(null);
      } finally {
        inFlight = false;
      }
    };
    tick();
    const timer = window.setInterval(tick, 3000);
    return () => {
      stopped = true;
      window.clearInterval(timer);
    };
  }, [needsQr, refreshKey]);

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

  const showBrowser = async () => {
    setQrBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await api.post<{ message?: string }>('/session/show-browser');
      setNotice(res.data?.message ?? 'Opening the WhatsApp browser window…');
      setRefreshKey((value) => value + 1);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setQrBusy(false);
    }
  };

  const useHeadless = async () => {
    setQrBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await api.post<{ message?: string }>('/session/use-headless');
      setNotice(res.data?.message ?? 'Switching WhatsApp to headless mode. Use “Show browser” if you need to scan.');
      setRefreshKey((value) => value + 1);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setQrBusy(false);
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

  const remainingTableRows: RemainingRow[] = [
    ...remainingRows.map((target, index) => ({
      key: `current-${target.id}`,
      index: index + 1,
      name: target.target_name ?? `#${target.target_id}`,
      batch: target.batch_no ?? '—',
      status: target.status,
      source: target.source_name ?? '—',
      preview: false,
    })),
    ...previewRows.map((target, index) => ({
      key: `preview-${target.target_type}-${target.target_id}`,
      index: remainingRows.length + index + 1,
      name: target.target_name ?? `#${target.target_id}`,
      batch: target.batch_no ?? 'next',
      status: 'upcoming',
      source: '—',
      preview: true,
    })),
  ];

  // Filter state lives in these hooks, so the 2s polling refresh replaces rows
  // without resetting whatever the user typed.
  const remainingTable = useTableFilters<RemainingRow>(
    remainingTableRows,
    (row) => `${row.name} ${row.batch ?? ''} ${row.source}`,
    [
      { key: 'name', label: 'Target', getValue: (row) => row.name },
      { key: 'batch', label: 'Batch', getValue: (row) => String(row.batch ?? '') },
      {
        key: 'status',
        label: 'Status',
        type: 'select',
        options: TARGET_STATUS_OPTIONS,
        getValue: (row) => row.status,
      },
      { key: 'source', label: 'Source', getValue: (row) => row.source },
    ],
  );

  const missedTable = useTableFilters<RunTarget>(
    missed,
    (target) => `${target.target_name ?? ''} ${target.batch_no ?? ''} ${target.message ?? ''}`,
    [
      { key: 'name', label: 'Target', getValue: (target) => target.target_name ?? '' },
      { key: 'batch', label: 'Batch', getValue: (target) => String(target.batch_no ?? '') },
      { key: 'reason', label: 'Reason', getValue: (target) => target.message ?? '' },
    ],
  );

  const targetsTable = useTableFilters<RunTarget>(
    targets,
    (target) =>
      `${target.target_name ?? ''} ${target.target_type} ${target.batch_no ?? ''} ${target.status} ${target.message ?? ''}`,
    [
      { key: 'name', label: 'Target', getValue: (target) => target.target_name ?? '' },
      { key: 'type', label: 'Type', getValue: (target) => target.target_type },
      { key: 'batch', label: 'Batch', getValue: (target) => String(target.batch_no ?? '') },
      {
        key: 'status',
        label: 'Status',
        type: 'select',
        options: TARGET_STATUS_OPTIONS,
        getValue: (target) => target.status,
      },
      { key: 'message', label: 'Message', getValue: (target) => target.message ?? '' },
    ],
  );

  const remainingColumns: DataTableColumn<RemainingRow>[] = [
    {
      key: 'index',
      header: '#',
      cellClassName: 'text-xs text-slate-400 dark:text-slate-500',
      cell: (row) => row.index,
    },
    {
      key: 'name',
      header: 'Target',
      filter: { type: 'text', placeholder: 'Filter target' },
      cell: (row) => (
        <span className={row.preview ? 'text-slate-500 dark:text-slate-400' : undefined}>
          {row.name}
        </span>
      ),
    },
    {
      key: 'batch',
      header: 'Batch',
      filter: { type: 'text', placeholder: 'Filter batch' },
      cellClassName: 'text-slate-500 dark:text-slate-400',
      cell: (row) => row.batch ?? '—',
    },
    {
      key: 'status',
      header: 'Status',
      filter: { type: 'select', placeholder: 'All statuses', options: TARGET_STATUS_OPTIONS },
      cell: (row) => (
        <span className={`rounded px-2 py-0.5 text-xs ${row.preview ? 'bg-slate-50 text-slate-500 dark:bg-slate-800 dark:text-slate-400' : TARGET_STATUS_STYLES[row.status] ?? 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}`}>
          {TARGET_STATUS_LABELS[row.status] ?? row.status}
        </span>
      ),
    },
    {
      key: 'source',
      header: 'Source',
      filter: { type: 'text', placeholder: 'Filter source' },
      cellClassName: 'text-xs text-slate-500 dark:text-slate-400',
      cell: (row) => row.source,
    },
  ];

  const missedColumns: DataTableColumn<RunTarget>[] = [
    {
      key: 'name',
      header: 'Target',
      filter: { type: 'text', placeholder: 'Filter target' },
      cell: (target) => target.target_name ?? `#${target.target_id}`,
    },
    {
      key: 'batch',
      header: 'Batch',
      filter: { type: 'text', placeholder: 'Filter batch' },
      cellClassName: 'text-slate-500 dark:text-slate-400',
      cell: (target) => target.batch_no ?? '—',
    },
    {
      key: 'reason',
      header: 'Reason',
      filter: { type: 'text', placeholder: 'Filter reason' },
      cellClassName: 'text-xs text-red-600 dark:text-red-400',
      cell: (target) => target.message ?? 'Post failed or could not be confirmed',
    },
    {
      key: 'attempts',
      header: 'Attempts',
      cellClassName: 'text-slate-500 dark:text-slate-400',
      cell: (target) => target.attempts,
    },
    {
      key: 'finished',
      header: 'Finished',
      cellClassName: 'text-xs text-slate-500 dark:text-slate-400',
      cell: (target) => target.finished_at ?? '—',
    },
  ];

  const targetColumns: DataTableColumn<RunTarget>[] = [
    {
      key: 'name',
      header: 'Target',
      filter: { type: 'text', placeholder: 'Filter target' },
      cell: (target) => target.target_name ?? `#${target.target_id}`,
    },
    {
      key: 'type',
      header: 'Type',
      filter: { type: 'text', placeholder: 'Filter type' },
      cellClassName: 'text-xs text-slate-500 dark:text-slate-400',
      cell: (target) => target.target_type,
    },
    {
      key: 'batch',
      header: 'Batch',
      filter: { type: 'text', placeholder: 'Filter batch' },
      cellClassName: 'text-slate-500 dark:text-slate-400',
      cell: (target) => target.batch_no ?? '—',
    },
    {
      key: 'status',
      header: 'Status',
      filter: { type: 'select', placeholder: 'All statuses', options: TARGET_STATUS_OPTIONS },
      cell: (target) => (
        <span className={`rounded px-2 py-0.5 text-xs ${TARGET_STATUS_STYLES[target.status] ?? 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}`}>
          {TARGET_STATUS_LABELS[target.status] ?? target.status}
        </span>
      ),
    },
    {
      key: 'attempts',
      header: 'Attempts',
      cellClassName: 'text-slate-500 dark:text-slate-400',
      cell: (target) => target.attempts,
    },
    {
      key: 'message',
      header: 'Message',
      filter: { type: 'text', placeholder: 'Filter message' },
      cellClassName: 'text-xs text-slate-500 dark:text-slate-400',
      cell: (target) => target.message ?? '—',
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">Live</h1>
        <div className="flex items-center gap-2">
          <span className={`text-xs ${MUTED}`}>
            {isActive ? 'Polling every 2 seconds' : 'Showing the last run'}
          </span>
          <button onClick={refresh} className="rounded border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800">
            Refresh
          </button>
        </div>
      </div>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      {notice && (
        <div className={`flex items-start justify-between ${NOTICE_INFO}`}>
          <span>{notice}</span>
          <button onClick={() => setNotice(null)} className="ml-4 text-blue-600 hover:text-blue-900 dark:text-blue-300 dark:hover:text-blue-100">Dismiss</button>
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
            {connection?.qr_visible && <div className="font-semibold">QR visible</div>}
            {connection?.updated_at && <div>Updated {connection.updated_at}</div>}
          </div>
        </div>
        {(connection?.state === 'waiting_qr' || connection?.state === 'waiting_login') && (
          <div className="mt-2 rounded border border-blue-200 bg-white/60 p-2 text-xs text-blue-800 dark:border-blue-900/60 dark:bg-slate-900/70 dark:text-blue-200">
            Open WhatsApp on your phone → Linked devices → Link a device, then scan the QR code below.
          </div>
        )}
      </div>

      {needsQr && (
        <div className={`${PANEL} p-4`}>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h2 className="text-sm font-semibold">Pair this browser</h2>
              <p className={`mt-1 text-xs ${MUTED}`}>
                Scan the code with WhatsApp. If the browser window is hidden, the QR below still works — or open the window.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              {qr && !qr.browser_open && (
                <button
                  onClick={showBrowser}
                  disabled={qrBusy}
                  className={`${ACTION_BTN} border-sky-300 text-sky-700 hover:bg-sky-50 dark:border-sky-800 dark:text-sky-300 dark:hover:bg-sky-950/50`}
                >
                  {qrBusy ? 'Opening…' : 'Show browser'}
                </button>
              )}
              {qr?.headless === false && (
                <button
                  onClick={useHeadless}
                  disabled={qrBusy}
                  className={`${ACTION_BTN} border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800`}
                >
                  Switch to headless
                </button>
              )}
              <button
                onClick={refresh}
                className={`${ACTION_BTN} border-slate-300 text-slate-700 hover:bg-slate-100 dark:border-slate-600 dark:text-slate-200 dark:hover:bg-slate-800`}
              >
                Refresh QR
              </button>
            </div>
          </div>
          <div className="mt-3 flex flex-col items-start gap-2 sm:flex-row sm:items-center sm:gap-4">
            {qr?.qr_data_url ? (
              <img
                src={qr.qr_data_url}
                alt="WhatsApp login QR code"
                className="h-56 w-56 rounded border border-slate-200 bg-white p-2 dark:border-slate-700"
              />
            ) : (
              <div className="flex h-56 w-56 items-center justify-center rounded border border-dashed border-slate-300 p-3 text-center text-xs text-slate-500 dark:border-slate-600 dark:text-slate-400">
                {qr?.message ?? 'Waiting for the QR code…'}
              </div>
            )}
            <div className={`text-xs ${MUTED}`}>
              <p className="font-medium text-slate-700 dark:text-slate-200">Can’t scan?</p>
              <p className="mt-1">Show the browser window, or reload it from the Settings page. The QR refreshes every few seconds.</p>
              {qr && (
                <p className="mt-2">
                  Browser: {qr.browser_open ? 'open' : 'closed'} · Mode: {qr.headless ? 'headless' : 'visible'}
                </p>
              )}
            </div>
          </div>
        </div>
      )}

      {!run ? (
        <div className={`${PANEL} p-8 text-center ${SUBTLE}`}>
          No campaign run has started yet. Start a campaign from the Campaigns page.
        </div>
      ) : (
        <>
          {/* Run header */}
          <div className={`${PANEL} p-4`}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <h2 className="text-lg font-semibold">{run.campaign_name ?? `Campaign ${run.campaign_id}`}</h2>
                  <span className={`rounded px-2 py-0.5 text-xs ${STATUS_STYLES[run.status] ?? 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}`}>
                    {run.status}
                  </span>
                  <span className="rounded bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">{run.phase}</span>
                  {run.skip_requested && (
                    <span className="rounded bg-amber-100 px-2 py-0.5 text-xs text-amber-700 dark:bg-amber-950/60 dark:text-amber-200">Skip requested</span>
                  )}
                </div>
                <div className={`mt-1 text-xs ${MUTED}`}>
                  {run.campaign_type} · started {run.started_at ?? '—'} · elapsed {elapsedLabel(run.elapsed_seconds)}
                  {run.finished_at ? ` · finished ${run.finished_at}` : ''}
                </div>
                {run.error && <div className="mt-1 text-xs text-red-600 dark:text-red-400">{run.error}</div>}
              </div>
              <div className="flex flex-wrap gap-2">
                <button
                  onClick={skipCurrent}
                  disabled={busy || !isActive || !run.current_target}
                  className={`${ACTION_BTN} border-amber-300 text-amber-700 hover:bg-amber-50 dark:border-amber-800 dark:text-amber-300 dark:hover:bg-amber-950/50`}
                >
                  Skip current group
                </button>
                <button
                  onClick={stopRun}
                  disabled={busy || !isActive}
                  className={`${ACTION_BTN} border-orange-300 text-orange-700 hover:bg-orange-50 dark:border-orange-800 dark:text-orange-300 dark:hover:bg-orange-950/50`}
                >
                  Stop campaign
                </button>
              </div>
            </div>

            <div className="mt-4">
              <div className={`mb-1 flex justify-between text-xs ${MUTED}`}>
                <span>Progress</span>
                <span>{progressProcessed} / {progressTotal} ({progressPercent}%)</span>
              </div>
              <div className="h-2 w-full overflow-hidden rounded bg-slate-100 dark:bg-slate-800">
                <div className="h-full bg-indigo-500 transition-all dark:bg-indigo-400" style={{ width: `${progressPercent}%` }} />
              </div>
            </div>
          </div>

          {/* Current work */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className={`${PANEL} p-4`}>
              <div className={`text-xs uppercase tracking-wide ${SUBTLE}`}>Current group</div>
              {run.current_target ? (
                <>
                  <div className="mt-1 text-lg font-semibold">{run.current_target.name}</div>
                  <div className={`text-xs ${MUTED}`}>
                    {run.current_target.type} #{run.current_target.id} · attempt {run.current_target.attempts || 1}
                  </div>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs">
                    <span className={`rounded px-2 py-0.5 ${TARGET_STATUS_STYLES[run.current_target.status] ?? 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}`}>
                      {TARGET_STATUS_LABELS[run.current_target.status] ?? run.current_target.status}
                    </span>
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                      daily {run.current_target.daily_count ?? 0} / {run.current_target.daily_cap ?? '—'}
                    </span>
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                      misses {run.current_target.failures ?? 0} consecutive · {run.current_target.total_misses ?? 0} total
                    </span>
                    {run.current_target.is_silenced && (
                      <span className="rounded bg-red-100 px-2 py-0.5 text-red-700 dark:bg-red-950/60 dark:text-red-200">Silenced</span>
                    )}
                  </div>
                  {run.current_target.message && (
                    <div className={`mt-2 text-xs ${MUTED}`}>{run.current_target.message}</div>
                  )}
                </>
              ) : (
                <div className={`mt-2 text-sm ${SUBTLE}`}>Waiting for the next target…</div>
              )}
            </div>

            <div className={`${PANEL} p-4`}>
              <div className={`text-xs uppercase tracking-wide ${SUBTLE}`}>
                {run.campaign_type === 'myGroupLink' ? 'Current link source' : 'Current product'}
              </div>
              <div className="mt-1 text-lg font-semibold">{sourceLabel(run)}</div>
              <div className={`mt-2 text-xs ${MUTED}`}>
                {run.campaign_type === 'myGroupLink' ? 'Promoting this group’s invite link' : 'Product being posted'}
                {run.product?.has_media ? ' · image attached' : ' · text only'}
              </div>
              {run.product?.link && (
                <div className="mt-1 truncate text-xs text-indigo-600 dark:text-indigo-400">{run.product.link}</div>
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
              <div key={String(label)} className={`${PANEL} p-3`}>
                <div className={`text-xs uppercase tracking-wide ${SUBTLE}`}>{label}</div>
                <div className="mt-1 text-2xl font-semibold">{value}</div>
              </div>
            ))}
          </div>

          {/* Tabs */}
          <div className="flex flex-wrap gap-1 border-b border-slate-200 dark:border-slate-800">
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
                    ? 'border-indigo-600 text-indigo-700 dark:border-indigo-400 dark:text-indigo-300'
                    : 'border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100'
                }`}
              >
                {label}
              </button>
            ))}
          </div>

          {tab === 'remaining' && (
            <section className="space-y-3">
              <TableToolbar
                search={remainingTable.search}
                onSearch={remainingTable.setSearch}
                placeholder="Search remaining targets…"
                count={remainingTable.count}
                total={remainingTable.total}
                onClear={remainingTable.clearFilters}
                isFiltered={remainingTable.isFiltered}
              />
              <DataTable
                columns={remainingColumns}
                rows={remainingTable.filtered}
                rowKey={(row) => row.key}
                filters={remainingTable.values}
                onFilterChange={remainingTable.setFilter}
                emptyMessage="No remaining targets match the current filters."
              />
            </section>
          )}

          {tab === 'missed' && (
            <section className="space-y-3">
              <TableToolbar
                search={missedTable.search}
                onSearch={missedTable.setSearch}
                placeholder="Search missed targets…"
                count={missedTable.count}
                total={missedTable.total}
                onClear={missedTable.clearFilters}
                isFiltered={missedTable.isFiltered}
              />
              <DataTable
                columns={missedColumns}
                rows={missedTable.filtered}
                rowKey={(target) => target.id}
                filters={missedTable.values}
                onFilterChange={missedTable.setFilter}
                emptyMessage="No missed groups match the current filters."
              />
            </section>
          )}

          {tab === 'targets' && (
            <section className="space-y-3">
              <TableToolbar
                search={targetsTable.search}
                onSearch={targetsTable.setSearch}
                placeholder="Search all targets…"
                count={targetsTable.count}
                total={targetsTable.total}
                onClear={targetsTable.clearFilters}
                isFiltered={targetsTable.isFiltered}
              />
              <DataTable
                columns={targetColumns}
                rows={targetsTable.filtered}
                rowKey={(target) => target.id}
                filters={targetsTable.values}
                onFilterChange={targetsTable.setFilter}
                emptyMessage="No targets match the current filters."
                maxHeight="max-h-[55vh]"
              />
            </section>
          )}

          {tab === 'events' && (
            <div
              ref={feedRef}
              onScroll={() => {
                const element = feedRef.current;
                if (!element) return;
                stickToBottom.current = element.scrollHeight - element.scrollTop - element.clientHeight < 40;
              }}
              className="max-h-[55vh] overflow-auto rounded-lg border border-slate-200 bg-slate-900 p-3 font-mono text-xs dark:border-slate-700"
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
