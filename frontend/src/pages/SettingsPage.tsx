import { useEffect, useMemo, useState } from 'react';
import { api, getErrorMessage } from '../api';
import ErrorBanner from '../components/ErrorBanner';
import CardSection from '../components/CardSection';
import PageHeader from '../components/PageHeader';
import { useTheme } from '../theme';
import {
  BTN_PRIMARY,
  BTN_SECONDARY,
  CARD_PAD,
  INPUT,
  MUTED,
  SUBTLE,
} from '../ui';

type SettingType = 'int' | 'float' | 'bool' | 'str';

type SettingDef = {
  key: string;
  label: string;
  description: string;
  type: SettingType;
  default: number | boolean | string;
  min?: number | null;
  max?: number | null;
  category: string;
  unit?: string;
};

type SettingValue = number | boolean | string;

type SettingsResponse = {
  values: Record<string, SettingValue>;
  schema: SettingDef[];
};

type SessionStatus = {
  used: number;
  limit: number;
  session_exists: boolean;
  connected: boolean;
  headless?: boolean;
  browser_open?: boolean;
  state?: string | null;
  qr_visible?: boolean;
};

type MaintenanceStats = {
  logs: number;
  campaign_runs: number;
  active_runs: number;
  finished_runs: number;
  run_targets: number;
  run_events: number;
  debug_files: number;
  debug_bytes: number;
  database_bytes: number;
  session_bytes: number;
  database_path: string;
  session_path: string;
  last_retention_run: string | null;
};

function formatBytes(bytes: number): string {
  if (!bytes) return '0 B';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

const STAT_CARD = 'rounded-md border border-slate-200 bg-slate-50 p-3 dark:border-[#222] dark:bg-[#111]';

export default function SettingsPage() {
  const [schema, setSchema] = useState<SettingDef[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [session, setSession] = useState<SessionStatus | null>(null);
  const [resetting, setResetting] = useState(false);
  const [sessionBusy, setSessionBusy] = useState(false);
  const [stats, setStats] = useState<MaintenanceStats | null>(null);
  const [statsLoading, setStatsLoading] = useState(false);
  const [clearing, setClearing] = useState<string | null>(null);
  const { theme, setTheme } = useTheme();

  const apply = (defs: SettingDef[], vals: Record<string, SettingValue>) => {
    setSchema(defs);
    setValues(Object.fromEntries(defs.map((def) => [def.key, String(vals[def.key] ?? def.default)])));
  };

  const load = async () => {
    setLoading(true);
    try {
      const res = await api.get<SettingsResponse>('/settings');
      const defs = Array.isArray(res.data?.schema) ? res.data.schema : [];
      apply(defs, res.data?.values ?? {});
      setError(null);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  const loadSession = async () => {
    try {
      const res = await api.get<SessionStatus>('/session/status');
      setSession(res.data);
    } catch {
      // The session card is supplementary; the settings form stays usable.
    }
  };

  const loadStats = async () => {
    setStatsLoading(true);
    try {
      const res = await api.get<MaintenanceStats>('/maintenance/stats');
      setStats(res.data);
    } catch {
      // Maintenance stats failing must not block the rest of the page.
    } finally {
      setStatsLoading(false);
    }
  };

  useEffect(() => {
    load();
    loadSession();
    loadStats();
  }, []);

  const categories = useMemo(() => {
    const order: string[] = [];
    const grouped = new Map<string, SettingDef[]>();
    for (const def of schema) {
      if (!grouped.has(def.category)) {
        grouped.set(def.category, []);
        order.push(def.category);
      }
      grouped.get(def.category)!.push(def);
    }
    return order.map((name) => ({ name, items: grouped.get(name)! }));
  }, [schema]);

  const update = (key: string, value: string) => setValues((prev) => ({ ...prev, [key]: value }));

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setNotice(null);

    const payload: Record<string, SettingValue> = {};
    for (const def of schema) {
      const raw = values[def.key] ?? '';
      if (def.type === 'bool') {
        payload[def.key] = raw === 'true';
        continue;
      }
      if (def.type === 'int' || def.type === 'float') {
        const num = Number(raw);
        if (!Number.isFinite(num)) {
          setError(`${def.label} must be a number.`);
          return;
        }
        payload[def.key] = def.type === 'int' ? Math.trunc(num) : num;
        continue;
      }
      payload[def.key] = raw;
    }

    setSaving(true);
    try {
      const res = await api.patch<SettingsResponse>('/settings', { values: payload });
      const defs = Array.isArray(res.data?.schema) ? res.data.schema : schema;
      apply(defs, res.data?.values ?? payload);
      setNotice('Settings saved. The bot uses them immediately.');
      loadSession();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  const resetToDefaults = () => {
    setValues(Object.fromEntries(schema.map((def) => [def.key, String(def.default)])));
    setNotice('Defaults loaded into the form. Choose “Save settings” to apply them.');
  };

  const resetSavedSession = async () => {
    if (!window.confirm('Forget the saved WhatsApp session? The next campaign run will show a QR code to scan.')) {
      return;
    }
    setResetting(true);
    setError(null);
    setNotice(null);
    try {
      const res = await api.post<SessionStatus>('/session/reset');
      setSession(res.data);
      setNotice('Saved session cleared. The next campaign run will show a QR code.');
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setResetting(false);
    }
  };

  const showBrowser = async () => {
    setSessionBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await api.post<{ message?: string }>('/session/show-browser');
      setNotice(res.data?.message ?? 'Opening the WhatsApp browser window…');
      await loadSession();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSessionBusy(false);
    }
  };

  const useHeadless = async () => {
    setSessionBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await api.post<{ message?: string }>('/session/use-headless');
      setNotice(res.data?.message ?? 'Switching WhatsApp to headless mode.');
      await loadSession();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSessionBusy(false);
    }
  };

  const useHeaded = async () => {
    setSessionBusy(true);
    setError(null);
    setNotice(null);
    try {
      const res = await api.post<{ message?: string }>('/session/use-headed');
      setNotice(res.data?.message ?? 'Switching WhatsApp to a visible browser window.');
      await loadSession();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setSessionBusy(false);
    }
  };

  const runMaintenance = async (kind: 'logs' | 'runs' | 'debug' | 'all' | 'cleanup') => {
    const prompts: Record<typeof kind, string> = {
      logs: 'Clear every log entry? Products, groups, campaigns and analytics are untouched.',
      runs: 'Clear finished run history (targets and events)? Active runs and analytics are untouched.',
      debug: 'Delete saved screenshots, DOM dumps and trace files from data/debug?',
      all: 'Clear logs, finished run history and debug files? Configuration, analytics and the saved WhatsApp session are kept.',
      cleanup: 'Run the retention cleanup now using the configured retention window?',
    };
    if (!window.confirm(prompts[kind])) return;

    setClearing(kind);
    setError(null);
    setNotice(null);
    try {
      const res = await api.post<Record<string, number | string>>(`/maintenance/${kind === 'cleanup' ? 'cleanup-now' : `clear-${kind}`}`);
      const data = res.data ?? {};
      const parts = Object.entries(data)
        .filter(([key]) => !key.endsWith('_bytes') && key !== 'cutoff' && key !== 'ran_at' && key !== 'days')
        .map(([key, value]) => `${value} ${key.replace(/_/g, ' ')}`);
      setNotice(`${kind === 'cleanup' ? 'Retention cleanup finished' : 'Cleared'}: ${parts.join(', ') || 'nothing to remove'}.`);
      await Promise.all([loadStats(), load()]);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setClearing(null);
    }
  };

  const browserMode = session?.headless ? 'Headless' : 'Visible browser';
  const browserState = session?.browser_open
    ? 'browser window open'
    : session?.headless
      ? 'browser window hidden'
      : 'browser window not open';

  return (
    <div className="space-y-4">
      <PageHeader title="Settings" description="Automation parameters, browser mode, retention and appearance.">
        <button type="button" onClick={load} disabled={loading} className={BTN_SECONDARY}>
          {loading ? 'Reloading…' : 'Reload'}
        </button>
        <button type="button" onClick={resetToDefaults} disabled={schema.length === 0} className={BTN_SECONDARY}>
          Load defaults
        </button>
      </PageHeader>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        <CardSection title="Session & browser" description="Saved WhatsApp profile and browser mode.">
          <p className={`text-sm ${MUTED}`}>
            Saved session: used <span className="font-semibold text-slate-700 dark:text-[#e5e5e5]">{session?.used ?? 0}</span> of{' '}
            <span className="font-semibold text-slate-700 dark:text-[#e5e5e5]">{session?.limit ?? '—'}</span> runs.
          </p>
          <p className={`mt-0.5 text-xs ${MUTED}`}>
            {session?.session_exists ? 'A saved WhatsApp profile is present.' : 'No saved WhatsApp profile.'}{' '}
            {session?.connected ? 'WhatsApp is connected.' : 'WhatsApp is not connected.'}
          </p>
          <div className="mt-3 rounded-md border border-slate-200 p-3 text-xs dark:border-[#222] dark:bg-[#111]">
            <div className="font-medium text-slate-700 dark:text-[#e5e5e5]">Browser mode: {browserMode}</div>
            <div className={`mt-0.5 ${MUTED}`}>
              {browserState}
              {session?.state ? ` · WhatsApp: ${session.state}` : ''}
              {session?.qr_visible ? ' · QR waiting to be scanned' : ''}
            </div>
            <p className={`mt-1 ${MUTED}`}>
              Headless runs keep the Chrome window hidden. If a run needs to pair WhatsApp, a visible browser opens automatically for the scan and closes itself once connected.
            </p>
          </div>
          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" onClick={showBrowser} disabled={sessionBusy || resetting} className={BTN_SECONDARY}>
              {sessionBusy ? 'Working…' : 'Show browser'}
            </button>
            <button
              type="button"
              onClick={useHeadless}
              disabled={sessionBusy || resetting || session?.headless}
              className={BTN_SECONDARY}
            >
              Switch to headless
            </button>
            <button
              type="button"
              onClick={useHeaded}
              disabled={sessionBusy || resetting || !session?.headless}
              className={BTN_SECONDARY}
            >
              Switch to headed
            </button>
            <button
              type="button"
              onClick={resetSavedSession}
              disabled={resetting || sessionBusy}
              className="rounded-md border border-red-300 px-3 py-1.5 text-xs text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/50"
            >
              {resetting ? 'Forgetting…' : 'Forget session & show QR'}
            </button>
          </div>
        </CardSection>

        <CardSection title="Appearance" description="Theme is stored in this browser and applies immediately.">
          <div className="inline-flex overflow-hidden rounded-md border border-slate-300 dark:border-[#2a2a2a]">
            <button
              type="button"
              onClick={() => setTheme('light')}
              aria-pressed={theme === 'light'}
              className={`px-4 py-2 text-sm ${theme === 'light' ? 'bg-indigo-600 text-white' : 'bg-white text-slate-700 hover:bg-slate-100 dark:bg-[#111] dark:text-neutral-200 dark:hover:bg-[#161616]'}`}
            >
              Light
            </button>
            <button
              type="button"
              onClick={() => setTheme('dark')}
              aria-pressed={theme === 'dark'}
              className={`border-l border-slate-300 px-4 py-2 text-sm dark:border-l-[#2a2a2a] ${theme === 'dark' ? 'bg-indigo-600 text-white dark:bg-indigo-500 dark:text-black' : 'bg-white text-slate-700 hover:bg-slate-100 dark:bg-[#111] dark:text-neutral-200 dark:hover:bg-[#161616]'}`}
            >
              Dark
            </button>
          </div>
          <p className={`mt-2 text-xs ${SUBTLE}`}>Use the toggle in the sidebar to switch without visiting this page.</p>
        </CardSection>
      </div>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      {notice && (
        <div className="flex items-start justify-between rounded-md border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-800 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-200">
          <span>{notice}</span>
          <button onClick={() => setNotice(null)} className="ml-4 text-emerald-700 hover:underline dark:text-emerald-200">
            Dismiss
          </button>
        </div>
      )}

      <section className={`${CARD_PAD} bg-white dark:bg-[#0a0a0a]`}>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-700 dark:text-[#f5f5f5]">Data &amp; maintenance</h2>
            <p className={`mt-1 text-xs ${MUTED}`}>
              Clear operational history to reclaim space. Products, groups, clients, campaigns, schedules, analytics, settings and the saved WhatsApp session are never deleted here.
            </p>
          </div>
          <button type="button" onClick={loadStats} disabled={statsLoading} className={`${BTN_SECONDARY} text-xs`}>
            {statsLoading ? 'Refreshing…' : 'Refresh stats'}
          </button>
        </div>

        <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
          {[
            ['Log entries', stats?.logs ?? '—'],
            ['Run history', stats?.campaign_runs ?? '—'],
            ['Active runs', stats?.active_runs ?? '—'],
            ['Finished runs', stats?.finished_runs ?? '—'],
            ['Run targets', stats?.run_targets ?? '—'],
            ['Run events', stats?.run_events ?? '—'],
            ['Debug files', stats?.debug_files ?? '—'],
            ['Debug size', stats ? formatBytes(stats.debug_bytes) : '—'],
          ].map(([label, value]) => (
            <div key={String(label)} className={STAT_CARD}>
              <div className={`text-xs uppercase tracking-wide ${SUBTLE}`}>{label}</div>
              <div className="mt-1 text-xl font-semibold text-slate-900 dark:text-[#f5f5f5]">{value}</div>
            </div>
          ))}
        </div>

        <div className={`mt-3 text-xs ${MUTED}`}>
          <div>Database: {stats ? formatBytes(stats.database_bytes) : '—'}{stats?.database_path ? ` · ${stats.database_path}` : ''}</div>
          <div>Session files: {stats ? formatBytes(stats.session_bytes) : '—'}{stats?.session_path ? ` · ${stats.session_path}` : ''}</div>
          <div>
            Retention window: <span className="font-medium text-slate-700 dark:text-[#e5e5e5]">{values['retention_days'] ?? '30'} day(s)</span>
            {' · '}Last automatic cleanup: {stats?.last_retention_run ?? 'not run yet'}
          </div>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <button type="button" onClick={() => runMaintenance('cleanup')} disabled={Boolean(clearing)} className={`${BTN_PRIMARY} text-xs`}>
            {clearing === 'cleanup' ? 'Cleaning…' : 'Run retention cleanup now'}
          </button>
          <button type="button" onClick={() => runMaintenance('logs')} disabled={Boolean(clearing)} className={`${BTN_SECONDARY} text-xs`}>
            {clearing === 'logs' ? 'Clearing…' : 'Clear logs'}
          </button>
          <button type="button" onClick={() => runMaintenance('runs')} disabled={Boolean(clearing)} className={`${BTN_SECONDARY} text-xs`}>
            {clearing === 'runs' ? 'Clearing…' : 'Clear finished runs'}
          </button>
          <button type="button" onClick={() => runMaintenance('debug')} disabled={Boolean(clearing)} className={`${BTN_SECONDARY} text-xs`}>
            {clearing === 'debug' ? 'Clearing…' : 'Clear debug files'}
          </button>
          <button
            type="button"
            onClick={() => runMaintenance('all')}
            disabled={Boolean(clearing)}
            className="rounded-md border border-red-300 px-3 py-1.5 text-xs text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-900 dark:text-red-300 dark:hover:bg-red-950/50"
          >
            {clearing === 'all' ? 'Clearing…' : 'Clear all safe data'}
          </button>
        </div>
      </section>

      {loading && schema.length === 0 && (
        <div className={`${CARD_PAD} text-center ${SUBTLE}`}>Loading settings…</div>
      )}

      <form onSubmit={save} className="space-y-4">
        {categories.map((category) => (
          <section key={category.name} className={CARD_PAD}>
            <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-700 dark:text-[#f5f5f5]">{category.name}</h2>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              {category.items.map((def) => (
                <label key={def.key} className="block text-sm">
                  <span className="font-medium text-slate-800 dark:text-neutral-100">{def.label}</span>
                  <div className="mt-1 flex items-center gap-2">
                    {def.type === 'bool' ? (
                      <input
                        type="checkbox"
                        checked={values[def.key] === 'true'}
                        onChange={(e) => update(def.key, e.target.checked ? 'true' : 'false')}
                      />
                    ) : (
                      <input
                        className={`${INPUT} w-36`}
                        type="number"
                        step={def.type === 'float' ? '0.1' : '1'}
                        min={def.min ?? undefined}
                        max={def.max ?? undefined}
                        value={values[def.key] ?? ''}
                        onChange={(e) => update(def.key, e.target.value)}
                      />
                    )}
                    {def.unit && <span className={`text-xs ${MUTED}`}>{def.unit}</span>}
                  </div>
                  <span className={`mt-1 block text-xs ${MUTED}`}>{def.description}</span>
                  <span className={`mt-0.5 block text-xs ${SUBTLE}`}>
                    Default: {String(def.default)}
                    {def.unit ? ` ${def.unit}` : ''}
                  </span>
                </label>
              ))}
            </div>
          </section>
        ))}

        {schema.length > 0 && (
          <div className="flex gap-2">
            <button type="submit" disabled={saving} className={BTN_PRIMARY}>
              {saving ? 'Saving…' : 'Save settings'}
            </button>
          </div>
        )}
      </form>
    </div>
  );
}
